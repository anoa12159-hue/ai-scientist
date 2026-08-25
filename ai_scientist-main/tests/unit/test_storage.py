"""Contract-valid unit tests for the T004 persistence kernel."""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from ai_scientist_mvp.application.services import compute_authority_hash, verify_checkpoint
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import (
    ArtifactIdentityConflictError,
    CheckpointIntegrityError,
    HashMismatchError,
    IdempotencyConflictError,
    IllegalTransitionError,
    LedgerIntegrityError,
    MissingParentError,
    PathEscapeError,
    RunIsolationError,
    SchemaValidationError,
    StoreError,
)
from ai_scientist_mvp.domain.store_types import StageAttemptKey
from ai_scientist_mvp.infrastructure import paths
from ai_scientist_mvp.infrastructure.paths import derive_artifact_path
from ai_scientist_mvp.infrastructure.storage import LocalStorage

H = "0" * 64
TS = "2026-08-20T00:00:00Z"
VREF = {"id": "ref-1", "schema_version": "0.1.0", "content_hash": H}


def _rehash(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("content_hash", None)
    result["content_hash"] = canonical_json.content_hash_excluding(result)
    return result


def _source_envelope(
    artifact_id: str,
    content: bytes,
    run_id: str = "run-1",
    **overrides: object,
) -> dict:
    envelope: dict = {
        "artifact_id": artifact_id,
        "logical_artifact_id": "logical-" + artifact_id,
        "artifact_type": "SourceDocument",
        "schema_version": "0.1.0",
        "artifact_revision": 1,
        "task_id": "task-1",
        "run_id": run_id,
        "run_mode": "REPLAY",
        "origin_mode": "IMPORTED",
        "authority_mode": "SOURCE_BYTES",
        "content_ref": "artifact-content://" + artifact_id,
        "content_sha256": compute_authority_hash("SOURCE_BYTES", content),
        "producer": {"id": "fixture-adapter", "version": "0.1.0"},
        "created_at": TS,
    }
    envelope.update(overrides)
    return envelope


def _native_envelope(
    artifact_id: str,
    payload: dict,
    run_id: str = "run-1",
    **overrides: object,
) -> dict:
    envelope: dict = {
        "artifact_id": artifact_id,
        "logical_artifact_id": "logical-" + artifact_id,
        "artifact_type": "CandidateSnapshot",
        "schema_version": "0.1.0",
        "artifact_revision": 1,
        "task_id": "task-1",
        "run_id": run_id,
        "run_mode": "REPLAY",
        "origin_mode": "NATIVE",
        "authority_mode": "CANONICAL_JSON",
        "payload": copy.deepcopy(payload),
        "content_sha256": compute_authority_hash("CANONICAL_JSON", payload),
        "producer": {"id": "system", "version": "0.1.0"},
        "created_at": TS,
    }
    envelope.update(overrides)
    return envelope


def _run_record(run_id: str = "run-1", **overrides: object) -> dict:
    run: dict = {
        "run_id": run_id,
        "task_id": "task-1",
        "question_ref": copy.deepcopy(VREF),
        "case_ref": copy.deepcopy(VREF),
        "workflow_version": "0.1.0",
        "run_mode": "REPLAY",
        "run_purpose": "HISTORICAL_REPLAY",
        "configuration_ref": copy.deepcopy(VREF),
        "execution_status": "PENDING",
        "stage_runs": [],
        "created_at": TS,
    }
    run.update(overrides)
    return run


def _stage(
    run_id: str = "run-1",
    configuration_ref: dict | None = None,
    **overrides: object,
) -> dict:
    stage: dict = {
        "run_id": run_id,
        "stage_id": "S01_CANDIDATE",
        "attempt": 1,
        "schema_version": "0.1.0",
        "stage_configuration_ref": copy.deepcopy(configuration_ref or VREF),
        "execution_status": "SUCCEEDED",
    }
    stage.update(overrides)
    return _rehash(stage)


def _checkpoint(run_id: str, artifact_refs: list[dict], checkpoint_id: str = "cp-1") -> dict:
    return _rehash(
        {
            "checkpoint_id": checkpoint_id,
            "schema_version": "0.1.0",
            "run_id": run_id,
            "stage_ids": ["S01_CANDIDATE"],
            "artifact_refs": copy.deepcopy(artifact_refs),
            "created_at": TS,
        }
    )


def _put_source(store: LocalStorage, artifact_id: str = "art-1", content: bytes = b"data") -> dict:
    envelope = _source_envelope(artifact_id, content, store.run_id)
    return store.artifact_store.put(envelope, content, "SOURCE_BYTES")


def test_schema_valid_source_bytes_roundtrip(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"historical bytes\r\n"
    envelope = _source_envelope("art-1", content)
    ref = store.artifact_store.put(envelope, content, "SOURCE_BYTES")
    assert ref == {
        "artifact_id": "art-1",
        "content_sha256": compute_authority_hash("SOURCE_BYTES", content),
        "schema_version": "0.1.0",
    }
    assert store.artifact_store.get_envelope("art-1") == envelope
    assert store.artifact_store.get_content("art-1") == content
    store.artifact_store.verify_ref(ref)


def test_schema_valid_canonical_json_roundtrip(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    payload = {"parameter": "SHRGT45", "n": 1}
    envelope = _native_envelope("art-2", payload)
    store.artifact_store.put(envelope, payload, "CANONICAL_JSON")
    assert store.artifact_store.get_content("art-2") == canonical_json.canonicalize(payload)


def test_invalid_authority_combination_fails_schema(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"x"
    envelope = _source_envelope("art-1", content, origin_mode="NATIVE")
    with pytest.raises(SchemaValidationError):
        store.artifact_store.put(envelope, content, "SOURCE_BYTES")


def test_canonical_content_must_equal_declared_payload(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    envelope = _native_envelope("art-1", {"declared": 1})
    with pytest.raises(HashMismatchError):
        store.artifact_store.put(envelope, {"actual": 2}, "CANONICAL_JSON")


def test_artifact_rejects_foreign_run(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-local")
    content = b"x"
    envelope = _source_envelope("art-1", content, "run-foreign")
    with pytest.raises(RunIsolationError):
        store.artifact_store.put(envelope, content, "SOURCE_BYTES")


def test_idempotent_retry_requires_complete_same_envelope(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"same"
    envelope = _source_envelope("art-1", content)
    first = store.artifact_store.put(envelope, content, "SOURCE_BYTES")
    assert store.artifact_store.put(copy.deepcopy(envelope), content, "SOURCE_BYTES") == first
    changed = copy.deepcopy(envelope)
    changed["producer"] = {"id": "other", "version": "0.1.0"}
    with pytest.raises(ArtifactIdentityConflictError):
        store.artifact_store.put(changed, content, "SOURCE_BYTES")
    assert store.artifact_store.get_envelope("art-1") == envelope


def test_same_artifact_id_different_content_fails_closed(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    store.artifact_store.put(_source_envelope("art-1", b"one"), b"one", "SOURCE_BYTES")
    with pytest.raises(ArtifactIdentityConflictError):
        store.artifact_store.put(_source_envelope("art-1", b"two"), b"two", "SOURCE_BYTES")


def test_tampered_content_path_is_not_silently_repaired(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"authority"
    envelope = _source_envelope("art-1", content)
    store.artifact_store.put(envelope, content, "SOURCE_BYTES")
    path = derive_artifact_path(tmp_path, "run-1", envelope["content_sha256"])
    path.write_bytes(b"tampered")
    with pytest.raises(HashMismatchError):
        store.artifact_store.get_content("art-1")
    with pytest.raises(HashMismatchError):
        store.artifact_store.put(envelope, content, "SOURCE_BYTES")
    assert path.read_bytes() == b"tampered"


def test_complete_artifact_ref_schema_version_is_checked(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    ref = _put_source(store)
    stale = {**ref, "schema_version": "9.9.9"}
    with pytest.raises(StoreError):
        store.artifact_store.verify_ref(stale)


def test_missing_parent_fails_closed(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"child"
    missing = {"artifact_id": "missing", "content_sha256": H, "schema_version": "0.1.0"}
    envelope = _source_envelope("child", content, parent_refs=[missing])
    with pytest.raises(MissingParentError):
        store.artifact_store.put(envelope, content, "SOURCE_BYTES")


def test_schema_valid_run_record_uses_internal_ledger_identity(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    run = _run_record()
    assert "content_hash" not in run
    store.run_store.put_run(run)
    store.run_store.put_run(copy.deepcopy(run))
    assert store.run_store.get_run("run-1") == run
    assert len(store.ledger.read("run_record")) == 1


def test_run_record_rejects_foreign_run(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-local")
    with pytest.raises(RunIsolationError):
        store.run_store.put_run(_run_record("run-foreign"))
    with pytest.raises(RunIsolationError):
        store.run_store.get_run("run-foreign")


def test_unknown_ledger_kind_fails_closed(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    with pytest.raises(LedgerIntegrityError):
        store.ledger.append("invented_kind", {"content_hash": H})


def test_rehashed_unknown_schema_version_fails_closed(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    stage = _stage()
    stage["schema_version"] = "9.9.9"
    stage = _rehash(stage)
    with pytest.raises(SchemaValidationError):
        store.run_store.put_stage(stage)


def test_lifecycle_append_enforces_contiguous_sequence(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    ref = _put_source(store)
    first = _rehash(
        {
            "event_id": "event-1",
            "schema_version": "0.1.0",
            "artifact_ref": ref,
            "from_lifecycle": "DRAFT",
            "to_lifecycle": "REVIEW_REQUIRED",
            "reason": "review",
            "actor_id": "project_owner_01",
            "created_at": TS,
        }
    )
    store.ledger.append("artifact_lifecycle_event", first)
    store.ledger.append("artifact_lifecycle_event", copy.deepcopy(first))
    assert store.ledger.read("artifact_lifecycle_event") == [first]
    non_contiguous = _rehash(
        {
            "event_id": "event-2",
            "schema_version": "0.1.0",
            "artifact_ref": ref,
            "from_lifecycle": "DRAFT",
            "to_lifecycle": "REJECTED",
            "reason": "invalid sequence",
            "actor_id": "project_owner_01",
            "created_at": TS,
        }
    )
    with pytest.raises(IllegalTransitionError):
        store.ledger.append("artifact_lifecycle_event", non_contiguous)


def test_stage_attempt_key_uses_complete_configuration_ref(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    config_a = {"id": "config-a", "schema_version": "0.1.0", "content_hash": H}
    config_b = {"id": "config-b", "schema_version": "0.1.0", "content_hash": H}
    stage_a = _stage(configuration_ref=config_a)
    stage_b = _stage(configuration_ref=config_b)
    store.run_store.put_stage(stage_a)
    store.run_store.put_stage(stage_b)
    key_a: StageAttemptKey = {
        "run_id": "run-1",
        "stage_id": "S01_CANDIDATE",
        "attempt": 1,
        "stage_configuration_ref": config_a,
    }
    key_b: StageAttemptKey = {**key_a, "stage_configuration_ref": config_b}
    assert store.run_store.get_stage(key_a) == stage_a
    assert store.run_store.get_stage(key_b) == stage_b


def test_stage_retry_conflict_uses_full_payload(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    original = _stage(provider={"id": "provider-a", "version": "1.0.0"})
    store.run_store.put_stage(original)
    store.run_store.put_stage(copy.deepcopy(original))
    changed = _stage(provider={"id": "provider-b", "version": "1.0.0"})
    with pytest.raises(IdempotencyConflictError):
        store.run_store.put_stage(changed)


def test_stage_rejects_foreign_run(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-local")
    with pytest.raises(RunIsolationError):
        store.run_store.put_stage(_stage("run-foreign"))


def test_checkpoint_write_and_latest_verify_every_ref(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    ref = _put_source(store)
    checkpoint = _checkpoint("run-1", [ref])
    store.checkpoint_store.put(checkpoint)
    assert store.checkpoint_store.latest("run-1") == checkpoint
    assert verify_checkpoint(checkpoint, store.artifact_store) == []


def test_checkpoint_rejects_missing_artifact_and_foreign_run(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    missing = {"artifact_id": "missing", "content_sha256": H, "schema_version": "0.1.0"}
    with pytest.raises(CheckpointIntegrityError):
        store.checkpoint_store.put(_checkpoint("run-1", [missing]))
    with pytest.raises(CheckpointIntegrityError):
        store.checkpoint_store.put(_checkpoint("run-other", []))


def test_invalid_committed_checkpoint_tail_is_not_returned(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    missing = {"artifact_id": "missing", "content_sha256": H, "schema_version": "0.1.0"}
    invalid = _checkpoint("run-1", [missing], "cp-invalid")
    payload = canonical_json.canonicalize(invalid).decode("utf-8")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("checkpoint_ref", "run-1", invalid["content_hash"], payload, TS),
        )
    with pytest.raises(CheckpointIntegrityError):
        store.checkpoint_store.latest("run-1")


def test_direct_ledger_update_and_delete_are_rejected(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    store.run_store.put_run(_run_record())
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("UPDATE facts SET payload='x'")
    with pytest.raises(sqlite3.DatabaseError):
        store.conn.execute("DELETE FROM facts")


def test_path_escape_and_link_like_artifact_directory_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(StoreError):
        LocalStorage(tmp_path, "../escape")
    store = LocalStorage(tmp_path, "run-1")
    original = paths._is_link_like
    monkeypatch.setattr(
        paths,
        "_is_link_like",
        lambda path: path.name == "artifacts" or original(path),
    )
    with pytest.raises(PathEscapeError):
        derive_artifact_path(store.runs_root, "run-1", H)


def test_leftover_temp_file_is_not_an_artifact(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    temp = tmp_path / "run-1" / "artifacts" / (".tmp-" + H + "-1")
    temp.write_bytes(b"partial")
    assert not store.artifact_store.exists("artifact-not-committed")
    with pytest.raises(KeyError):
        store.artifact_store.get_envelope("artifact-not-committed")


def test_artifact_envelope_cannot_bypass_artifact_store(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    envelope = _source_envelope("art-1", b"data")
    with pytest.raises(LedgerIntegrityError):
        store.ledger.append("artifact_envelope", envelope)


def test_artifact_retry_does_not_repair_an_orphan_envelope_fact(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    envelope = _source_envelope("art-1", b"data")
    payload = canonical_json.canonicalize(envelope).decode("utf-8")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("artifact_envelope", "run-1", "art-1", payload, TS),
        )
    with pytest.raises(ArtifactIdentityConflictError, match="incomplete identity commit"):
        store.artifact_store.put(envelope, b"data", "SOURCE_BYTES")
    assert store.conn.execute("SELECT COUNT(*) FROM artifact_identity").fetchone()[0] == 0


def test_checkpoint_id_cannot_be_rebound_to_new_content(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    original = _checkpoint("run-1", [], "cp-stable")
    store.checkpoint_store.put(original)
    changed = copy.deepcopy(original)
    changed["created_at"] = "2026-08-20T00:00:01Z"
    changed = _rehash(changed)
    with pytest.raises(IdempotencyConflictError):
        store.checkpoint_store.put(changed)
    assert store.checkpoint_store.latest("run-1") == original


def test_direct_stage_ledger_append_cannot_bypass_atomic_stage_store(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    original = _stage(provider={"id": "provider-a", "version": "1.0.0"})
    with pytest.raises(LedgerIntegrityError, match="RunStore.put_stage"):
        store.ledger.append("stage_run", original)


def test_lifecycle_event_id_cannot_be_rebound(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    ref = _put_source(store)
    event = _rehash(
        {
            "event_id": "event-stable",
            "schema_version": "0.1.0",
            "artifact_ref": ref,
            "from_lifecycle": "DRAFT",
            "to_lifecycle": "REVIEW_REQUIRED",
            "reason": "original",
            "actor_id": "project_owner_01",
            "created_at": TS,
        }
    )
    store.ledger.append("artifact_lifecycle_event", event)
    changed = copy.deepcopy(event)
    changed["reason"] = "changed"
    changed = _rehash(changed)
    with pytest.raises(IdempotencyConflictError, match="event_id"):
        store.ledger.append("artifact_lifecycle_event", changed)


def test_ledger_read_fails_closed_on_stored_identity_drift(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    run = _run_record()
    payload = canonical_json.canonicalize(run).decode("utf-8")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("run_record", "run-1", "canonical-sha256:" + H, payload, TS),
        )
    with pytest.raises(LedgerIntegrityError, match="identity is inconsistent"):
        store.ledger.read("run_record")


def test_stage_retry_does_not_repair_an_orphan_ledger_fact(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    stage = _stage()
    key: StageAttemptKey = {
        "run_id": stage["run_id"],
        "stage_id": stage["stage_id"],
        "attempt": stage["attempt"],
        "stage_configuration_ref": stage["stage_configuration_ref"],
    }
    payload = canonical_json.canonicalize(stage).decode("utf-8")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("stage_run", "run-1", canonical_json.canonicalize(key).decode("utf-8"), payload, TS),
        )
    with pytest.raises(IdempotencyConflictError, match="incomplete commit"):
        store.run_store.put_stage(stage)
    assert store.conn.execute("SELECT COUNT(*) FROM stages").fetchone()[0] == 0


def test_latest_run_snapshot_is_ordered_and_identity_checked(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    pending = _run_record(execution_status="PENDING")
    running = _run_record(execution_status="RUNNING", started_at=TS)
    store.run_store.put_run(pending)
    store.run_store.put_run(running)
    assert store.run_store.get_run("run-1") == running

    succeeded = _run_record(execution_status="SUCCEEDED", started_at=TS, completed_at=TS)
    payload = canonical_json.canonicalize(succeeded).decode("utf-8")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("run_record", "run-1", "canonical-sha256:" + H, payload, TS),
        )
    with pytest.raises(LedgerIntegrityError, match="identity key"):
        store.run_store.get_run("run-1")


def test_malformed_checkpoint_json_is_wrapped_as_integrity_failure(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("checkpoint_ref", "run-1", "cp-broken", "{", TS),
        )
    with pytest.raises(CheckpointIntegrityError, match="not valid JSON"):
        store.checkpoint_store.latest("run-1")


def test_direct_invalid_json_payload_in_ledger_is_detected_on_recovery(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    with store.conn:
        store.conn.execute(
            "INSERT INTO facts(kind, run_id, identity_key, payload, appended_at) "
            "VALUES(?,?,?,?,?)",
            ("checkpoint_ref", "run-1", H, json.dumps({"run_id": "run-1"}), TS),
        )
    with pytest.raises(CheckpointIntegrityError):
        store.checkpoint_store.latest("run-1")
