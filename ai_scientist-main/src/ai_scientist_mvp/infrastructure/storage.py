"""Fail-Closed local SQLite + filesystem persistence kernel for T004."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any, cast

from ai_scientist_mvp.application.ports import ArtifactStore, CheckpointStore, Ledger, RunStore
from ai_scientist_mvp.application.services import project_lifecycle
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import (
    ArtifactIdentityConflictError,
    CheckpointIntegrityError,
    HashMismatchError,
    IdempotencyConflictError,
    LedgerIntegrityError,
    MissingParentError,
    RunIsolationError,
    StoreError,
)
from ai_scientist_mvp.domain.store_types import Authority, StageAttemptKey, attempt_key_string
from ai_scientist_mvp.domain.types import (
    ArtifactEnvelope,
    ArtifactLifecycleEvent,
    ArtifactRef,
    CheckpointRef,
    RunRecord,
    StageRun,
)
from ai_scientist_mvp.infrastructure.contract_validation import (
    ContractValidator,
    default_contracts_root,
)
from ai_scientist_mvp.infrastructure.paths import derive_artifact_path, derive_run_dir, validate_id

_FACT_SCHEMAS = {
    "artifact_envelope": "artifact-envelope",
    "artifact_lifecycle_event": "artifact-lifecycle-event",
    "lineage_edge": "lineage-edge",
    "run_record": "run-record",
    "stage_run": "stage-run",
    "checkpoint_ref": "checkpoint-ref",
    "failure_record": "failure-record",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    run_id TEXT,
    identity_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    appended_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS facts_idempotency ON facts(kind, identity_key);

CREATE TABLE IF NOT EXISTS artifact_identity (
    artifact_id TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_key TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    config_ref_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    appended_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS facts_no_update BEFORE UPDATE ON facts
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON facts
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS artifact_identity_no_update BEFORE UPDATE ON artifact_identity
BEGIN SELECT RAISE(ABORT, 'artifact identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS artifact_identity_no_delete BEFORE DELETE ON artifact_identity
BEGIN SELECT RAISE(ABORT, 'artifact identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS stages_no_update BEFORE UPDATE ON stages
BEGIN SELECT RAISE(ABORT, 'stage facts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS stages_no_delete BEFORE DELETE ON stages
BEGIN SELECT RAISE(ABORT, 'stage facts are immutable'); END;
"""


def _now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _canonical_bytes(payload: Any) -> bytes:
    return canonical_json.canonicalize(payload)


def _internal_digest(payload: bytes) -> str:
    return "canonical-sha256:" + hashlib.sha256(payload).hexdigest().lower()


def _insert_fact_row(
    conn: sqlite3.Connection,
    kind: str,
    run_id: str | None,
    identity_key: str,
    payload: str,
) -> None:
    try:
        conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            (kind, run_id, identity_key, payload, _now()),
        )
    except sqlite3.IntegrityError:
        existing = conn.execute(
            "SELECT payload FROM facts WHERE kind=? AND identity_key=?",
            (kind, identity_key),
        ).fetchone()
        if existing is not None and existing[0] == payload:
            return
        raise IdempotencyConflictError(f"conflict on {kind}/{identity_key}") from None


def _stage_attempt_key(stage: StageRun) -> StageAttemptKey:
    return {
        "run_id": stage["run_id"],
        "stage_id": stage["stage_id"],
        "attempt": stage["attempt"],
        "stage_configuration_ref": stage.get("stage_configuration_ref"),
    }


class _Base:
    def __init__(self, kernel: LocalStorage) -> None:
        self._kernel = kernel

    @property
    def conn(self) -> sqlite3.Connection:
        return self._kernel.conn

    def _require_local_run(self, run_id: object, object_kind: str) -> None:
        if run_id != self._kernel.run_id:
            raise RunIsolationError(
                f"{object_kind} run_id {run_id!r} does not match local Run "
                f"{self._kernel.run_id!r}"
            )


class FilesystemArtifactStore(_Base):
    def put(
        self, envelope: ArtifactEnvelope, content: bytes | dict[str, Any], authority: Authority
    ) -> ArtifactRef:
        self._kernel.contracts.validate("artifact-envelope", envelope)
        self._require_local_run(envelope["run_id"], "ArtifactEnvelope")
        artifact_id = validate_id(envelope["artifact_id"])
        if envelope["authority_mode"] != authority:
            raise HashMismatchError(
                f"authority_mode {envelope['authority_mode']} != supplied {authority}"
            )

        if authority == "SOURCE_BYTES":
            if not isinstance(content, bytes):
                raise TypeError("SOURCE_BYTES authority requires bytes content")
            authority_bytes = content
        else:
            if not isinstance(content, dict):
                raise TypeError("CANONICAL_JSON authority requires a dict payload")
            authority_bytes = _canonical_bytes(content)
            declared_bytes = _canonical_bytes(envelope["payload"])
            if authority_bytes != declared_bytes:
                raise HashMismatchError("canonical content does not equal ArtifactEnvelope.payload")

        computed = hashlib.sha256(authority_bytes).hexdigest().lower()
        if envelope["content_sha256"].lower() != computed:
            raise HashMismatchError(
                f"envelope content_sha256 {envelope['content_sha256']} != computed {computed}"
            )
        self._verify_envelope_refs(envelope)

        row = self.conn.execute(
            "SELECT content_sha256, schema_version FROM artifact_identity WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        fact_row = self.conn.execute(
            "SELECT payload FROM facts WHERE kind='artifact_envelope' AND identity_key=?",
            (artifact_id,),
        ).fetchone()
        if (row is None) != (fact_row is None):
            raise ArtifactIdentityConflictError(
                f"artifact_id {artifact_id} has an incomplete identity commit"
            )
        if row is not None:
            stored = self.get_envelope(artifact_id)
            if _canonical_bytes(stored) != _canonical_bytes(envelope):
                raise ArtifactIdentityConflictError(
                    f"artifact_id {artifact_id} retry changed immutable Envelope fields"
                )
            if row != (computed, stored["schema_version"]):
                raise ArtifactIdentityConflictError(
                    f"artifact_id {artifact_id} identity row conflicts with stored Envelope"
                )
            self._atomic_write(computed, authority_bytes)
            self.verify(artifact_id)
            return self._ref(stored)

        self._atomic_write(computed, authority_bytes)
        envelope_payload = _canonical_bytes(envelope).decode("utf-8")
        with self.conn:
            self.conn.execute(
                "INSERT INTO artifact_identity(artifact_id, content_sha256, schema_version) "
                "VALUES(?,?,?)",
                (artifact_id, computed, envelope["schema_version"]),
            )
            _insert_fact_row(
                self.conn,
                "artifact_envelope",
                self._kernel.run_id,
                artifact_id,
                envelope_payload,
            )
        return self._ref(envelope)

    def _verify_envelope_refs(self, envelope: ArtifactEnvelope) -> None:
        refs: list[ArtifactRef] = []
        refs.extend(envelope.get("parent_refs", []))
        refs.extend(envelope.get("derived_from_refs", []))
        supersedes = envelope.get("supersedes_ref")
        if supersedes is not None:
            refs.append(supersedes)
        for ref in refs:
            try:
                self.verify_ref(ref)
            except KeyError as exc:
                raise MissingParentError(
                    f"missing referenced Artifact: {ref['artifact_id']}"
                ) from exc

    @staticmethod
    def _ref(envelope: ArtifactEnvelope) -> ArtifactRef:
        return {
            "artifact_id": envelope["artifact_id"],
            "content_sha256": envelope["content_sha256"].lower(),
            "schema_version": envelope["schema_version"],
        }

    def _atomic_write(self, content_sha256: str, payload: bytes) -> None:
        target = derive_artifact_path(self._kernel.runs_root, self._kernel.run_id, content_sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = derive_artifact_path(self._kernel.runs_root, self._kernel.run_id, content_sha256)
        if target.exists():
            if not target.is_file() or target.read_bytes() != payload:
                raise HashMismatchError(
                    f"content-addressed path already contains different bytes: {content_sha256}"
                )
            return
        tmp = target.with_name(f".tmp-{content_sha256}-{os.getpid()}-{uuid.uuid4().hex}")
        try:
            with open(tmp, "xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                tmp.unlink()
        try:
            dir_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    def get_envelope(self, artifact_id: str) -> ArtifactEnvelope:
        validate_id(artifact_id)
        row = self.conn.execute(
            "SELECT payload FROM facts WHERE kind='artifact_envelope' AND identity_key=?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown artifact: {artifact_id}")
        try:
            envelope = cast(ArtifactEnvelope, json.loads(row[0]))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ArtifactIdentityConflictError(
                f"stored ArtifactEnvelope is not valid JSON: {artifact_id}"
            ) from exc
        self._kernel.contracts.validate("artifact-envelope", envelope)
        self._require_local_run(envelope["run_id"], "stored ArtifactEnvelope")
        identity = self.conn.execute(
            "SELECT content_sha256, schema_version FROM artifact_identity WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        expected = (envelope["content_sha256"].lower(), envelope["schema_version"])
        if identity != expected:
            raise ArtifactIdentityConflictError(f"identity mismatch for Artifact {artifact_id}")
        return envelope

    def get_content(self, artifact_id: str) -> bytes:
        envelope = self.get_envelope(artifact_id)
        path = derive_artifact_path(
            self._kernel.runs_root, self._kernel.run_id, envelope["content_sha256"]
        )
        if not path.is_file():
            raise HashMismatchError(f"missing content for artifact: {artifact_id}")
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest().lower()
        if actual != envelope["content_sha256"].lower():
            raise HashMismatchError(
                f"{artifact_id}: stored {actual} != recorded {envelope['content_sha256']}"
            )
        if envelope["authority_mode"] == "CANONICAL_JSON":
            expected = _canonical_bytes(envelope["payload"])
            if content != expected:
                raise HashMismatchError(
                    f"{artifact_id}: stored canonical payload differs from Envelope"
                )
        return content

    def verify(self, artifact_id: str) -> None:
        self.get_content(artifact_id)

    def verify_ref(self, ref: ArtifactRef) -> None:
        self._kernel.contracts.validate("artifact-ref", ref)
        envelope = self.get_envelope(ref["artifact_id"])
        if envelope["content_sha256"].lower() != ref["content_sha256"].lower():
            raise HashMismatchError(f"stale content hash in ArtifactRef {ref['artifact_id']}")
        if envelope["schema_version"] != ref["schema_version"]:
            raise HashMismatchError(f"stale schema version in ArtifactRef {ref['artifact_id']}")
        self.verify(ref["artifact_id"])

    def exists(self, artifact_id: str) -> bool:
        validate_id(artifact_id)
        row = self.conn.execute(
            "SELECT 1 FROM artifact_identity AS i JOIN facts AS f "
            "ON f.kind='artifact_envelope' AND f.identity_key=i.artifact_id "
            "WHERE i.artifact_id=?",
            (artifact_id,),
        ).fetchone()
        return row is not None


class SqliteLedger(_Base):
    def _prepare_core(self, kind: str, fact: Any) -> tuple[str, str, str | None]:
        schema_name = _FACT_SCHEMAS.get(kind)
        if schema_name is None:
            raise LedgerIntegrityError(f"unknown ledger fact kind: {kind}")
        self._kernel.contracts.validate(schema_name, fact)
        if not isinstance(fact, dict):
            raise LedgerIntegrityError(f"{kind} must be a JSON object")
        if "run_id" in fact:
            self._require_local_run(fact["run_id"], kind)

        payload_bytes = _canonical_bytes(fact)
        if kind == "artifact_envelope":
            identity_key = fact["artifact_id"]
        elif kind == "artifact_lifecycle_event":
            identity_key = fact["event_id"]
        elif kind == "lineage_edge":
            identity_key = fact["edge_id"]
        elif kind == "stage_run":
            identity_key = attempt_key_string(_stage_attempt_key(cast(StageRun, fact)))
        elif kind == "checkpoint_ref":
            identity_key = fact["checkpoint_id"]
        elif kind == "failure_record":
            identity_key = fact["failure_id"]
        elif kind == "run_record":
            identity_key = _internal_digest(payload_bytes)
        else:
            raise LedgerIntegrityError(f"fact of kind {kind} has no supported identity")

        if "content_hash" in fact:
            if canonical_json.content_hash_excluding(fact) != fact["content_hash"]:
                raise LedgerIntegrityError(f"content_hash mismatch for {kind}")
        elif kind not in {"artifact_envelope", "run_record"}:
            raise LedgerIntegrityError(f"fact of kind {kind} has no supported identity")

        return identity_key, payload_bytes.decode("utf-8"), fact.get("run_id")

    def _prepare(self, kind: str, fact: Any) -> tuple[str, str, str | None]:
        prepared = self._prepare_core(kind, fact)
        self._verify_references(kind, fact)
        return prepared

    def _verify_references(self, kind: str, fact: dict[str, Any]) -> None:
        refs: list[dict[str, Any]] = []
        if kind == "artifact_envelope":
            if not self._kernel.artifact_store.exists(fact["artifact_id"]):
                raise LedgerIntegrityError(
                    "ArtifactEnvelope must be committed via ArtifactStore.put"
                )
            stored = self._kernel.artifact_store.get_envelope(fact["artifact_id"])
            if _canonical_bytes(stored) != _canonical_bytes(fact):
                raise LedgerIntegrityError(
                    "ArtifactEnvelope differs from immutable stored Envelope"
                )
            self._kernel.artifact_store.verify(fact["artifact_id"])
            return
        if kind == "artifact_lifecycle_event":
            refs.append(fact["artifact_ref"])
        elif kind == "lineage_edge":
            refs.extend((fact["upstream_artifact_ref"], fact["downstream_artifact_ref"]))
        elif kind in {"stage_run", "failure_record", "checkpoint_ref"}:
            refs.extend(fact.get("input_artifact_refs", []))
            refs.extend(fact.get("output_artifact_refs", []))
            refs.extend(fact.get("artifact_refs", []))
        for ref in refs:
            try:
                self._kernel.artifact_store.verify_ref(cast(ArtifactRef, ref))
            except KeyError as exc:
                raise LedgerIntegrityError(
                    f"unresolved ArtifactRef: {ref.get('artifact_id')}"
                ) from exc

        if kind == "artifact_lifecycle_event":
            artifact_id = fact["artifact_ref"]["artifact_id"]
            same_event = self.conn.execute(
                "SELECT payload FROM facts "
                "WHERE kind='artifact_lifecycle_event' AND identity_key=?",
                (fact["event_id"],),
            ).fetchone()
            if same_event is not None:
                if same_event[0] == _canonical_bytes(fact).decode("utf-8"):
                    return
                raise IdempotencyConflictError(
                    f"event_id {fact['event_id']} is already bound to different content"
                )
            existing = [
                cast(ArtifactLifecycleEvent, event)
                for event in self.read("artifact_lifecycle_event")
                if event["artifact_ref"]["artifact_id"] == artifact_id
            ]
            project_lifecycle(existing + [cast(ArtifactLifecycleEvent, fact)])

    def append(self, kind: str, fact: Any) -> None:
        if kind in {"artifact_envelope", "stage_run"}:
            owner = "ArtifactStore.put" if kind == "artifact_envelope" else "RunStore.put_stage"
            raise LedgerIntegrityError(f"{kind} must be committed via {owner}")
        identity_key, payload, run_id = self._prepare(kind, fact)
        with self.conn:
            _insert_fact_row(self.conn, kind, run_id, identity_key, payload)

    def read(self, kind: str) -> list[dict[str, Any]]:
        if kind not in _FACT_SCHEMAS:
            raise LedgerIntegrityError(f"unknown ledger fact kind: {kind}")
        rows = self.conn.execute(
            "SELECT identity_key, payload FROM facts WHERE kind=? ORDER BY seq", (kind,)
        ).fetchall()
        facts: list[dict[str, Any]] = []
        for stored_identity, stored_payload in rows:
            try:
                fact = json.loads(stored_payload)
            except (json.JSONDecodeError, TypeError) as exc:
                raise LedgerIntegrityError(f"stored {kind} fact is not valid JSON") from exc
            identity_key, payload, _ = self._prepare_core(kind, fact)
            if stored_identity != identity_key or stored_payload != payload:
                raise LedgerIntegrityError(f"stored {kind} fact identity is inconsistent")
            facts.append(fact)
        return facts

    def has(self, kind: str, identity_key: str) -> bool:
        if kind not in _FACT_SCHEMAS:
            raise LedgerIntegrityError(f"unknown ledger fact kind: {kind}")
        row = self.conn.execute(
            "SELECT 1 FROM facts WHERE kind=? AND identity_key=?", (kind, identity_key)
        ).fetchone()
        return row is not None


class SqliteRunStore(_Base):
    def put_run(self, run: RunRecord) -> None:
        self._kernel.ledger.append("run_record", run)

    def get_run(self, run_id: str) -> RunRecord:
        self._require_local_run(run_id, "RunRecord query")
        row = self.conn.execute(
            "SELECT identity_key, payload FROM facts WHERE kind='run_record' AND run_id=? "
            "ORDER BY seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        try:
            run = cast(RunRecord, json.loads(row[1]))
        except (json.JSONDecodeError, TypeError) as exc:
            raise LedgerIntegrityError("stored RunRecord is not valid JSON") from exc
        self._kernel.contracts.validate("run-record", run)
        self._require_local_run(run["run_id"], "stored RunRecord")
        expected_identity = _internal_digest(_canonical_bytes(run))
        if row[0] != expected_identity:
            raise LedgerIntegrityError("stored RunRecord identity key is inconsistent")
        return run

    def put_stage(self, stage: StageRun) -> None:
        identity_key, payload, run_id = self._kernel._ledger._prepare("stage_run", stage)
        config_ref = stage.get("stage_configuration_ref")
        key = _stage_attempt_key(stage)
        attempt_key = attempt_key_string(key)
        config_ref_json = _canonical_bytes(config_ref).decode("utf-8")
        stage_row = self.conn.execute(
            "SELECT payload FROM stages WHERE attempt_key=?", (attempt_key,)
        ).fetchone()
        ledger_row = self.conn.execute(
            "SELECT payload FROM facts WHERE kind='stage_run' AND identity_key=?",
            (identity_key,),
        ).fetchone()
        if (stage_row is None) != (ledger_row is None):
            raise IdempotencyConflictError(
                f"stage attempt {attempt_key} has an incomplete commit"
            )
        if stage_row is not None:
            if stage_row[0] == payload and ledger_row is not None and ledger_row[0] == payload:
                return
            raise IdempotencyConflictError(f"conflict on stage attempt {attempt_key}")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO stages(attempt_key, run_id, stage_id, attempt, "
                    "config_ref_hash, content_hash, payload, appended_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        attempt_key,
                        stage["run_id"],
                        stage["stage_id"],
                        stage["attempt"],
                        config_ref_json,
                        stage["content_hash"],
                        payload,
                        _now(),
                    ),
                )
                _insert_fact_row(self.conn, "stage_run", run_id, identity_key, payload)
        except sqlite3.IntegrityError:
            existing = self.conn.execute(
                "SELECT payload FROM stages WHERE attempt_key=?", (attempt_key,)
            ).fetchone()
            if existing is not None and existing[0] == payload:
                ledger_row = self.conn.execute(
                    "SELECT payload FROM facts WHERE kind='stage_run' AND identity_key=?",
                    (identity_key,),
                ).fetchone()
                if ledger_row is not None and ledger_row[0] == payload:
                    return
            raise IdempotencyConflictError(f"conflict on stage attempt {attempt_key}") from None

    def get_stage(self, key: StageAttemptKey) -> StageRun:
        self._require_local_run(key["run_id"], "StageAttemptKey")
        attempt_key = attempt_key_string(key)
        row = self.conn.execute(
            "SELECT content_hash, payload FROM stages WHERE attempt_key=?", (attempt_key,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown stage attempt: {attempt_key}")
        try:
            stage = cast(StageRun, json.loads(row[1]))
        except (json.JSONDecodeError, TypeError) as exc:
            raise LedgerIntegrityError("stored StageRun is not valid JSON") from exc
        identity_key, payload, _ = self._kernel._ledger._prepare("stage_run", stage)
        if identity_key != attempt_key or row[0] != stage["content_hash"]:
            raise LedgerIntegrityError("stored StageRun identity is inconsistent")
        ledger_row = self.conn.execute(
            "SELECT payload FROM facts WHERE kind='stage_run' AND identity_key=?",
            (identity_key,),
        ).fetchone()
        if ledger_row is None or ledger_row[0] != payload:
            raise LedgerIntegrityError("stored StageRun is missing its Ledger fact")
        return stage


class SqliteCheckpointStore(_Base):
    def _prepare(self, checkpoint: CheckpointRef) -> tuple[str, str, str | None]:
        try:
            return self._kernel._ledger._prepare("checkpoint_ref", checkpoint)
        except StoreError as exc:
            raise CheckpointIntegrityError(str(exc)) from exc

    def put(self, checkpoint: CheckpointRef) -> None:
        identity_key, payload, run_id = self._prepare(checkpoint)
        with self.conn:
            _insert_fact_row(self.conn, "checkpoint_ref", run_id, identity_key, payload)

    def latest(self, run_id: str) -> CheckpointRef | None:
        self._require_local_run(run_id, "Checkpoint query")
        row = self.conn.execute(
            "SELECT identity_key, payload FROM facts WHERE kind='checkpoint_ref' AND run_id=? "
            "ORDER BY seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            checkpoint = cast(CheckpointRef, json.loads(row[1]))
        except (json.JSONDecodeError, TypeError) as exc:
            raise CheckpointIntegrityError("stored checkpoint is not valid JSON") from exc
        identity_key, _, _ = self._prepare(checkpoint)
        if identity_key != row[0]:
            raise CheckpointIntegrityError("stored checkpoint identity key is inconsistent")
        return checkpoint


class LocalStorage:
    """Compose all persistence ports over one isolated per-Run namespace."""

    def __init__(
        self,
        runs_root: Path,
        run_id: str,
        contracts_root: Path | None = None,
    ) -> None:
        self.runs_root = runs_root.resolve()
        self.run_id = validate_id(run_id)
        self.contracts = ContractValidator(contracts_root or default_contracts_root())
        run_dir = derive_run_dir(runs_root, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = run_dir / "artifacts"
        artifact_dir.mkdir(exist_ok=True)
        derive_artifact_path(self.runs_root, self.run_id, "0" * 64)
        self.db_path = run_dir / "ledger.sqlite"
        # ``check_same_thread=False`` lets the LangGraph graph touch the same Run
        # namespace from parallel S05/S06 worker threads. Access is serialized by
        # the workflow service, so the connection is never used concurrently;
        # storage semantics (append-only, immutable, idempotent, fail-closed) are
        # unchanged.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

        artifact_store = FilesystemArtifactStore(self)
        ledger = SqliteLedger(self)
        run_store = SqliteRunStore(self)
        checkpoint_store = SqliteCheckpointStore(self)
        self.artifact_store: ArtifactStore = artifact_store
        self.ledger: Ledger = ledger
        self.run_store: RunStore = run_store
        self.checkpoint_store: CheckpointStore = checkpoint_store
        self._ledger = ledger

    def close(self) -> None:
        self.conn.close()
