"""Graph-facing application service for the SHRGT45 Replay workflow (T006).

This service composes the T004 persistence kernel with the T005 offline replay
adapters and exposes the per-stage, gate, report, and review boundaries that the
LangGraph nodes call. It adds the concerns that belong to the workflow layer and
not to the offline adapter:

- bounded, idempotent per-stage retry with typed failure routing;
- structured ``FailureRecord`` persistence (never a scientific verdict change);
- exact-binding ``DecisionRecord`` validation for the ``FIXTURE_IMPORT_REVIEW``
  gate (Fail Closed on missing/extra/stale/cross-Run references);
- reference-only ``CheckpointRef`` recovery points via the T004 CheckpointStore;
- the non-blocking ``FINAL_REPLAY_REVIEW`` acknowledgement (never a
  ``ReleaseDisposition``).
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ai_scientist_mvp.application.replay_service import (
    ReplayPreparation,
    ReplayReport,
    ReplayService,
    StageOutput,
)
from ai_scientist_mvp.application.services import verify_checkpoint
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import (
    LedgerIntegrityError,
    StoreError,
)
from ai_scientist_mvp.domain.types import (
    ArtifactRef,
    CheckpointRef,
    FailureRecord,
    RunConfigurationSnapshot,
    RunRecord,
    VersionedRef,
)
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.providers.shrgt45_replay import ManifestAssetCatalog
from ai_scientist_mvp.workflow.state import (
    GATE_APPROVED,
    GATE_REJECTED,
)

_SCHEMA_VERSION = "0.1.0"
_FIXED_TS = "2026-08-20T00:00:00Z"
_GATE_ID = "FIXTURE_IMPORT_REVIEW"


@dataclass(frozen=True)
class StageRunResult:
    """Outcome of one bounded, idempotent stage execution."""

    stage_id: str
    output: StageOutput | None
    failure_category: str | None
    failure_code: str | None
    failure_message: str | None
    retryable: bool
    attempts: int

    @property
    def succeeded(self) -> bool:
        return self.output is not None


@dataclass(frozen=True)
class GateDecision:
    """Validated outcome of the FIXTURE_IMPORT_REVIEW decision."""

    outcome: str  # GATE_APPROVED or GATE_REJECTED
    error: str | None = None


def _failure_category(exc: StoreError) -> str:
    name = type(exc).__name__
    if name in {"SchemaValidationError", "HashMismatchError", "LedgerIntegrityError"}:
        return "VALIDATION"
    return "PROGRAM"


def _failure_code(exc: StoreError) -> str:
    name = type(exc).__name__
    if name == "HashMismatchError":
        return "SHA256_MISMATCH"
    if name == "SchemaValidationError":
        return "UNKNOWN_SCHEMA_OR_VERSION"
    return "REPLAY_STAGE_FAILURE"


def _is_retryable(exc: StoreError) -> bool:
    """Only the unclassified base StoreError is treated as transient in T006.

    Every named StoreError subclass represents a deterministic contract,
    identity, isolation, or persistence-integrity violation and must fail closed
    without replaying the same write.
    """
    return type(exc) is StoreError


class ReplayWorkflowService:
    """Offline orchestration facade used by the LangGraph replay graph."""

    def __init__(
        self,
        storage: LocalStorage,
        fixtures_root: Path,
        run_id: str,
        task_id: str,
        max_attempts: int = 3,
    ) -> None:
        self.storage = storage
        self.run_id = run_id
        self.task_id = task_id
        self.max_attempts = max_attempts
        # Serializes access to the shared Run storage from the parallel S05/S06
        # worker threads; the connection itself is never used concurrently.
        self._db_lock = threading.RLock()
        self.replay = ReplayService(
            storage.artifact_store, storage.run_store, fixtures_root, run_id, task_id
        )
        self.catalog: ManifestAssetCatalog = self.replay.catalog
        self.contracts = self.catalog.contracts

    @property
    def workflow_version(self) -> str:
        return cast(str, self.catalog.case_manifest["workflow_version"])

    @property
    def run_mode(self) -> str:
        return cast(str, self.catalog.case_manifest["mode"])

    def prepare_configuration(
        self,
    ) -> tuple[RunConfigurationSnapshot, ArtifactRef, VersionedRef]:
        return self.replay.prepare_configuration()

    def run_stage_bounded(
        self,
        stage_id: str,
        configuration_ref: VersionedRef,
        upstream_refs: dict[str, ArtifactRef],
    ) -> StageRunResult:
        """Run one stage idempotently with finite, typed retry."""
        attempts = 0
        while True:
            attempts += 1
            try:
                with self._db_lock:
                    output = self.replay.run_stage(stage_id, configuration_ref, upstream_refs)
                return StageRunResult(stage_id, output, None, None, None, False, attempts)
            except StoreError as exc:
                retryable = _is_retryable(exc)
                if not retryable or attempts >= self.max_attempts:
                    return StageRunResult(
                        stage_id,
                        None,
                        _failure_category(exc),
                        _failure_code(exc),
                        str(exc),
                        retryable,
                        attempts,
                    )

    def record_failure(
        self,
        stage_id: str,
        category: str,
        code: str,
        message: str,
        retryable: bool,
        attempt: int,
        input_refs: list[ArtifactRef],
    ) -> VersionedRef:
        """Persist a structured FailureRecord; never changes scientific_verdict."""
        with self._db_lock:
            return self._record_failure_locked(
                stage_id, category, code, message, retryable, attempt, input_refs
            )

    def _record_failure_locked(
        self,
        stage_id: str,
        category: str,
        code: str,
        message: str,
        retryable: bool,
        attempt: int,
        input_refs: list[ArtifactRef],
    ) -> VersionedRef:
        failure: dict[str, Any] = {
            "failure_id": "failure-" + hashlib.sha256(
                canonical_json.canonicalize(
                    {"run_id": self.run_id, "stage_id": stage_id, "code": code, "attempt": attempt}
                )
            ).hexdigest()[:20],
            "schema_version": _SCHEMA_VERSION,
            "run_id": self.run_id,
            "stage_id": stage_id,
            "category": category,
            "code": code,
            "message": message,
            "retryable": retryable,
            "attempt": attempt,
            "input_artifact_refs": input_refs,
            "occurred_at": _FIXED_TS,
        }
        failure["content_hash"] = canonical_json.content_hash_excluding(failure)
        self.contracts.validate("failure-record", failure)
        typed = cast(FailureRecord, failure)
        self.replay.importer.persist_native(
            "FailureRecord",
            "failure-record",
            typed["failure_id"],
            cast(dict[str, Any], typed),
            input_refs,
        )
        self.storage.ledger.append("failure_record", typed)
        return _object_ref(failure, "failure_id")

    def write_gate_checkpoint(self, gate: ReplayPreparation) -> CheckpointRef:
        """Persist a reference-only recovery point before the import gate."""
        checkpoint: dict[str, Any] = {
            "checkpoint_id": "checkpoint-gate-" + self.run_id,
            "schema_version": _SCHEMA_VERSION,
            "run_id": self.run_id,
            "stage_ids": [
                "S01_CANDIDATE",
                "S02_MECHANISM",
                "S03_HYPOTHESIS",
                "S04_DATA_AND_VERIFICATION",
                "S05_COUNTEREXAMPLE",
                "S06_MAGNETOGRAM_QA",
            ],
            "artifact_refs": _unique_artifact_refs(
                [
                    gate.configuration_artifact_ref,
                    *gate.source_refs.values(),
                    *gate.snapshot_refs.values(),
                    *gate.validation_artifact_refs.values(),
                    *gate.finding_artifact_refs.values(),
                    gate.decision_request_artifact_ref,
                ]
            ),
            "created_at": _FIXED_TS,
        }
        checkpoint["content_hash"] = canonical_json.content_hash_excluding(checkpoint)
        self.contracts.validate("checkpoint-ref", checkpoint)
        self.storage.checkpoint_store.put(cast(CheckpointRef, checkpoint))
        return cast(CheckpointRef, checkpoint)

    def verify_gate_checkpoint(self) -> None:
        """Verify the last recovery point's ArtifactRefs still resolve (Fail Closed)."""
        checkpoint = self.storage.checkpoint_store.latest(self.run_id)
        if checkpoint is None:
            raise LedgerIntegrityError("missing recovery checkpoint for run")
        errors = verify_checkpoint(checkpoint, self.storage.artifact_store)
        if errors:
            raise LedgerIntegrityError("recovery checkpoint integrity failed: " + "; ".join(errors))

    def validate_decision(
        self,
        decision: dict[str, Any],
        decision_request_ref: ArtifactRef,
    ) -> GateDecision:
        """Validate a HUMAN_SELECTED RUN_GATE decision against the persisted request.

        Missing, extra, stale, or cross-Run references all Fail Closed. This
        method never constructs a DecisionRecord and never defaults to approval.
        """
        if not isinstance(decision, dict):
            return GateDecision(GATE_REJECTED, "decision is not an object")
        try:
            self.contracts.validate("decision-record", decision)
        except StoreError as exc:
            return GateDecision(GATE_REJECTED, f"invalid decision-record: {exc}")
        if canonical_json.content_hash_excluding(dict(decision)) != decision.get("content_hash"):
            return GateDecision(GATE_REJECTED, "decision content_hash mismatch")

        if decision.get("decision_mode") != "HUMAN_SELECTED":
            return GateDecision(GATE_REJECTED, "decision_mode must be HUMAN_SELECTED")
        if decision.get("decision_context") != "RUN_GATE":
            return GateDecision(GATE_REJECTED, "decision_context must be RUN_GATE")
        if decision.get("gate_id") != _GATE_ID:
            return GateDecision(GATE_REJECTED, f"gate_id must be {_GATE_ID}")
        if decision.get("workflow_version") != self.workflow_version:
            return GateDecision(GATE_REJECTED, "workflow_version mismatch")

        try:
            request = self._load_decision_request(decision_request_ref)
            configuration_ref = self._configuration_ref()
        except StoreError as exc:
            return GateDecision(GATE_REJECTED, f"gate context unavailable: {exc}")
        request_ref = _object_ref(request, "request_id")
        if decision.get("decision_request_ref") != request_ref:
            return GateDecision(GATE_REJECTED, "decision_request_ref mismatch")

        # Exact bound sets: no missing, extra, or cross-Run references.
        if not _same_set(
            decision.get("bound_artifact_refs", []), request.get("context_artifact_refs", [])
        ):
            return GateDecision(GATE_REJECTED, "bound_artifact_refs do not match request context")
        if not _same_set(
            decision.get("bound_finding_refs", []), request.get("context_finding_refs", [])
        ):
            return GateDecision(GATE_REJECTED, "bound_finding_refs do not match request context")
        if not _same_set(
            decision.get("bound_stage_attempt_keys", []),
            request.get("context_stage_attempt_keys", []),
        ):
            return GateDecision(
                GATE_REJECTED, "bound_stage_attempt_keys do not match request context"
            )

        # Every bound ArtifactRef must resolve inside the local Run.
        for ref in decision.get("bound_artifact_refs", []):
            try:
                self.storage.artifact_store.verify_ref(cast(ArtifactRef, ref))
            except StoreError as exc:
                return GateDecision(GATE_REJECTED, f"unresolved bound artifact: {exc}")

        # Every bound StageAttemptKey must target this Run and this configuration.
        for key in decision.get("bound_stage_attempt_keys", []):
            if key.get("run_id") != self.run_id:
                return GateDecision(GATE_REJECTED, "cross-Run StageAttemptKey")
            if key.get("stage_configuration_ref") != configuration_ref:
                return GateDecision(
                    GATE_REJECTED, "StageAttemptKey binds a different configuration"
                )

        selected = decision.get("selected_option_id")
        valid_options = {option["option_id"] for option in request.get("options", [])}
        if selected not in valid_options:
            return GateDecision(GATE_REJECTED, "selected_option_id is not a request option")

        if decision.get("action") == "APPROVE" and selected == "ACCEPT":
            return GateDecision(GATE_APPROVED)
        return GateDecision(GATE_REJECTED, "decision does not approve replay")

    def accept_gate_decision(
        self,
        decision: dict[str, Any],
        decision_request_ref: ArtifactRef,
    ) -> tuple[GateDecision, VersionedRef | None]:
        """Validate and persist the exact accepted DecisionRecord atomically in order.

        Rejected or malformed input is never stored as an accepted decision.
        """
        with self._db_lock:
            outcome = self.validate_decision(decision, decision_request_ref)
            if outcome.outcome != GATE_APPROVED:
                return outcome, None
            artifact_ref = self.replay.importer.persist_native(
                "DecisionRecord",
                "decision-record",
                cast(str, decision["decision_id"]),
                decision,
                [decision_request_ref, *cast(list[ArtifactRef], decision["bound_artifact_refs"])],
            )
            self.storage.artifact_store.verify_ref(artifact_ref)
            return outcome, _object_ref(decision, "decision_id")

    def resolve_versioned_artifact(
        self, ref: VersionedRef, expected_artifact_type: str
    ) -> ArtifactRef:
        """Resolve a VersionedRef to its immutable native Artifact authority."""
        for envelope in self.storage.ledger.read("artifact_envelope"):
            if envelope.get("artifact_type") != expected_artifact_type:
                continue
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                continue
            candidate_id = next(
                (
                    payload[key]
                    for key in ("decision_id", "failure_id", "ack_id")
                    if key in payload
                ),
                None,
            )
            if (
                candidate_id == ref["id"]
                and payload.get("schema_version") == ref["schema_version"]
                and payload.get("content_hash") == ref["content_hash"]
            ):
                artifact_ref: ArtifactRef = {
                    "artifact_id": envelope["artifact_id"],
                    "content_sha256": envelope["content_sha256"],
                    "schema_version": envelope["schema_version"],
                }
                self.storage.artifact_store.verify_ref(artifact_ref)
                return artifact_ref
        raise LedgerIntegrityError(
            f"unresolved {expected_artifact_type} VersionedRef: {ref['id']}"
        )

    def verify_branch_types(self, s05_ref: ArtifactRef, s06_ref: ArtifactRef) -> bool:
        """Return True only when S05 and S06 refs resolve to the required snapshot types."""
        return (
            self._artifact_type(s05_ref) == "CounterexampleSnapshot"
            and self._artifact_type(s06_ref) == "MagnetogramQASnapshot"
        )

    def _artifact_type(self, ref: ArtifactRef) -> str:
        try:
            self.storage.artifact_store.verify_ref(ref)
            envelope = self.storage.artifact_store.get_envelope(ref["artifact_id"])
            return envelope["artifact_type"]
        except StoreError:
            return ""

    def build_report(
        self,
        s05_ref: ArtifactRef,
        s06_ref: ArtifactRef,
        finding_refs: list[VersionedRef],
        finding_artifact_refs: list[ArtifactRef],
    ) -> ReplayReport:
        return self.replay.build_report(s05_ref, s06_ref, finding_refs, finding_artifact_refs)

    def project_run_succeeded(self) -> None:
        """Append the post-report RunRecord projection; never rewrite the gate record."""
        with self._db_lock:
            current = dict(self.storage.run_store.get_run(self.run_id))
            if current["execution_status"] == "SUCCEEDED":
                return
            if current["execution_status"] != "WAITING_HUMAN":
                raise LedgerIntegrityError("run is not waiting at the fixture review gate")
            current["execution_status"] = "SUCCEEDED"
            current["active_stage_ids"] = []
            current["completed_at"] = _FIXED_TS
            self.contracts.validate("run-record", current)
            self.storage.run_store.put_run(cast(RunRecord, current))

    def record_project_ack(
        self,
        report_manifest_ref: ArtifactRef,
        decision_ref: VersionedRef,
        actor_id: str,
        actor_role: str,
    ) -> ArtifactRef:
        """Append a non-blocking ProjectReviewAck bound to the exact report version.

        This is the only allowed FINAL_REPLAY_REVIEW side effect; it never creates
        a ReleaseDisposition and never changes NOT_AUTHORIZED / NOT_READY.
        """
        decision_artifact_ref = self.resolve_versioned_artifact(
            decision_ref, "DecisionRecord"
        )
        decision_envelope = self.storage.artifact_store.get_envelope(
            decision_artifact_ref["artifact_id"]
        )
        decision = decision_envelope["payload"]
        if (
            decision.get("decision_context") != "RUN_GATE"
            or decision.get("gate_id") != "FINAL_REPLAY_REVIEW"
            or decision.get("decision_mode") != "HUMAN_SELECTED"
            or decision.get("action") != "APPROVE"
            or decision.get("workflow_version") != self.workflow_version
            or not _same_set(decision.get("bound_artifact_refs", []), [report_manifest_ref])
        ):
            raise LedgerIntegrityError(
                "ProjectReviewAck requires an exact FINAL_REPLAY_REVIEW DecisionRecord"
            )
        ack: dict[str, Any] = {
            "ack_id": "project-review-ack-" + self.run_id,
            "schema_version": _SCHEMA_VERSION,
            "report_artifact_ref": report_manifest_ref,
            "decision_ref": decision_ref,
            "status": "ACKNOWLEDGED_FOR_PROJECT_REVIEW",
            "actor_id": actor_id,
            "actor_role": actor_role,
            "created_at": _FIXED_TS,
        }
        ack["content_hash"] = canonical_json.content_hash_excluding(ack)
        self.contracts.validate("project-review-ack", ack)
        return self.replay.importer.persist_native(
            "ProjectReviewAck",
            "project-review-ack",
            ack["ack_id"],
            ack,
            [report_manifest_ref, decision_artifact_ref],
        )

    def make_approval_decision(
        self,
        decision_request_ref: ArtifactRef,
        actor_id: str = "project_owner_01",
        actor_role: str = "project_owner",
        reason: str = "接受精确绑定的历史兼容性与来源限制，允许本次历史回放进入报告阶段。",
    ) -> dict[str, Any]:
        """Construct a HUMAN_SELECTED approval DecisionRecord for the CLI/demo.

        This is an explicit human action helper; the graph never calls it and
        never defaults to approval. It binds exactly the persisted DecisionRequest
        context, Run, workflow_version, and configuration.
        """
        request = self._load_decision_request(decision_request_ref)
        decision: dict[str, Any] = {
            "decision_id": "decision-approve-" + self.run_id,
            "schema_version": _SCHEMA_VERSION,
            "decision_context": "RUN_GATE",
            "decision_request_ref": _object_ref(request, "request_id"),
            "gate_id": _GATE_ID,
            "action": "APPROVE",
            "decision_mode": "HUMAN_SELECTED",
            "selected_option_id": "ACCEPT",
            "actor_id": actor_id,
            "actor_role": actor_role,
            "reason": reason,
            "scope": "FIXTURE_IMPORT_REVIEW",
            "bound_artifact_refs": request["context_artifact_refs"],
            "bound_finding_refs": request["context_finding_refs"],
            "bound_stage_attempt_keys": request["context_stage_attempt_keys"],
            "workflow_version": self.workflow_version,
            "created_at": _FIXED_TS,
        }
        decision["content_hash"] = canonical_json.content_hash_excluding(decision)
        self.contracts.validate("decision-record", decision)
        return decision

    def _load_decision_request(self, ref: ArtifactRef) -> dict[str, Any]:
        self.storage.artifact_store.verify_ref(ref)
        envelope = self.storage.artifact_store.get_envelope(ref["artifact_id"])
        if envelope["artifact_type"] != "DecisionRequest":
            raise LedgerIntegrityError("gate reference is not a DecisionRequest Artifact")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise LedgerIntegrityError("DecisionRequest Artifact is missing canonical payload")
        return payload

    def _configuration_ref(self) -> VersionedRef:
        run = self.storage.run_store.get_run(self.run_id)
        return run["configuration_ref"]


def _object_ref(obj: dict[str, Any], id_field: str) -> VersionedRef:
    return {
        "id": obj[id_field],
        "schema_version": obj["schema_version"],
        "content_hash": obj["content_hash"],
    }


def _same_set(left: list[Any], right: list[Any]) -> bool:
    """Order-independent exact-set equality over JSON-canonicalized members."""
    if len(left) != len(right):
        return False
    return {canonical_json.canonicalize(item) for item in left} == {
        canonical_json.canonicalize(item) for item in right
    }


def _unique_artifact_refs(refs: list[ArtifactRef]) -> list[ArtifactRef]:
    unique: dict[str, ArtifactRef] = {}
    for ref in refs:
        existing = unique.setdefault(ref["artifact_id"], ref)
        if existing != ref:
            raise LedgerIntegrityError(f"conflicting ArtifactRefs for {ref['artifact_id']}")
    return list(unique.values())
