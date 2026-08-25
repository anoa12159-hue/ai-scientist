"""Focused unit tests for the T006 Replay graph state and gate validation."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver

from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.workflow import state as graph_state
from ai_scientist_mvp.workflow.checkpoint import SqliteGraphSaver
from ai_scientist_mvp.workflow.replay_graph import (
    _JOIN_NODE,
    build_replay_graph,
    stage_dependencies,
)
from ai_scientist_mvp.workflow.state import (
    GATE_APPROVED,
    GATE_REJECTED,
    ReplayGraphState,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "shrgt45"

_STAGE_IDS = (
    "S01_CANDIDATE",
    "S02_MECHANISM",
    "S03_HYPOTHESIS",
    "S04_DATA_AND_VERIFICATION",
    "S05_COUNTEREXAMPLE",
    "S06_MAGNETOGRAM_QA",
)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> tuple[ReplayWorkflowService, Any]:
    """One prepared gate context (no graph) shared by the decision-validation tests."""
    runs_root = tmp_path_factory.mktemp("unit-graph")
    storage = LocalStorage(runs_root, "unit-run")
    service = ReplayWorkflowService(storage, FIXTURES, "unit-run", "task-6")
    gate = service.replay.prepare_fixture_review()
    yield service, gate
    storage.close()


def test_state_only_holds_reference_fields() -> None:
    annotations = ReplayGraphState.__annotations__
    expected = {
        "run_id",
        "task_id",
        "workflow_version",
        "run_mode",
        "configuration_ref",
        "stage_snapshot_refs",
        "stage_status",
        "finding_refs",
        "decision_request_ref",
        "gate_decision_ref",
        "gate_decision",
        "gate_error",
        "report_summary_ref",
        "report_manifest_ref",
        "final_review_status",
        "failure_refs",
        "retry_counts",
        "completed",
    }
    assert set(annotations) == expected
    # No field may carry raw bytes / large payloads.
    assert "bytes" not in repr(annotations.values())


def test_state_serializes_small() -> None:
    representative: ReplayGraphState = {
        "run_id": "run-x",
        "task_id": "task-6",
        "workflow_version": "0.1.0",
        "run_mode": "REPLAY",
        "configuration_ref": {
            "id": "cfg",
            "schema_version": "0.1.0",
            "content_hash": "A" * 64,
        },
        "stage_snapshot_refs": {
            stage: {
                "artifact_id": f"artifact-{stage}",
                "content_sha256": "0" * 64,
                "schema_version": "0.1.0",
            }
            for stage in _STAGE_IDS
        },
        "stage_status": {stage: "SUCCEEDED" for stage in _STAGE_IDS},
        "finding_refs": [
            {"id": f"finding-{index}", "schema_version": "0.1.0", "content_hash": "B" * 64}
            for index in range(12)
        ],
        "decision_request_ref": {
            "artifact_id": "artifact-decision",
            "content_sha256": "1" * 64,
            "schema_version": "0.1.0",
        },
        "gate_decision": "PENDING",
        "gate_error": "",
        "report_summary_ref": {
            "artifact_id": "artifact-summary",
            "content_sha256": "2" * 64,
            "schema_version": "0.1.0",
        },
        "report_manifest_ref": {
            "artifact_id": "artifact-manifest",
            "content_sha256": "3" * 64,
            "schema_version": "0.1.0",
        },
        "gate_decision_ref": {
            "id": "decision-approve-run-x",
            "schema_version": "0.1.0",
            "content_hash": "C" * 64,
        },
        "final_review_status": "AVAILABLE_FOR_PROJECT_REVIEW",
        "failure_refs": [],
        "retry_counts": {},
        "completed": True,
    }
    payload = canonical_json.canonicalize(representative)
    assert len(payload) < 16_384, f"graph state is unexpectedly large: {len(payload)} bytes"


def test_graph_declares_parallel_s05_s06_and_join(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, _ = prepared
    graph = build_replay_graph(service, MemorySaver())
    edges = {tuple(edge) for edge in graph.builder.edges}
    # S04 fans out to both branches; both fan into the single join node.
    assert ("S04_DATA_AND_VERIFICATION", "S05_COUNTEREXAMPLE") in edges
    assert ("S04_DATA_AND_VERIFICATION", "S06_MAGNETOGRAM_QA") in edges
    assert ("S05_COUNTEREXAMPLE", _JOIN_NODE) in edges
    assert ("S06_MAGNETOGRAM_QA", _JOIN_NODE) in edges
    # No S05<->S06 ordering exists (they are siblings, not sequential).
    assert ("S05_COUNTEREXAMPLE", "S06_MAGNETOGRAM_QA") not in edges
    assert ("S06_MAGNETOGRAM_QA", "S05_COUNTEREXAMPLE") not in edges


def test_stage_dependencies_match_workflow_contract(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, _ = prepared
    assert stage_dependencies(service, "S05_COUNTEREXAMPLE") == ["S04_DATA_AND_VERIFICATION"]
    assert stage_dependencies(service, "S06_MAGNETOGRAM_QA") == ["S04_DATA_AND_VERIFICATION"]
    assert stage_dependencies(service, "S01_CANDIDATE") == []


def _rehash(decision: dict[str, Any]) -> dict[str, Any]:
    decision["content_hash"] = canonical_json.content_hash_excluding(decision)
    return decision


def test_approval_decision_is_accepted(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    outcome = service.validate_decision(decision, gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_APPROVED


def test_decision_rejects_stale_request_ref(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    decision["decision_request_ref"] = {
        "id": "other",
        "schema_version": "0.1.0",
        "content_hash": "F" * 64,
    }
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED


def test_decision_rejects_extra_artifact(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    extra = {
        "artifact_id": "artifact-extra",
        "content_sha256": "e" * 64,
        "schema_version": "0.1.0",
    }
    decision["bound_artifact_refs"] = [*decision["bound_artifact_refs"], extra]
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED
    assert "bound_artifact_refs" in (outcome.error or "")


def test_decision_rejects_missing_finding(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    decision["bound_finding_refs"] = decision["bound_finding_refs"][:-1]
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED
    assert "bound_finding_refs" in (outcome.error or "")


def test_decision_rejects_cross_run_stage_key(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    mutated = deepcopy(decision["bound_stage_attempt_keys"])
    mutated[0]["run_id"] = "other-run"
    decision["bound_stage_attempt_keys"] = mutated
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED


def test_decision_rejects_wrong_workflow_version(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    decision["workflow_version"] = "9.9.9"
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED


def test_decision_rejects_system_delegated(
    prepared: tuple[ReplayWorkflowService, Any],
) -> None:
    service, gate = prepared
    decision = service.make_approval_decision(gate.decision_request_artifact_ref)
    decision["decision_mode"] = "SYSTEM_DELEGATED"
    decision["delegated_scope"] = "FIXTURE_IMPORT_REVIEW"
    outcome = service.validate_decision(_rehash(decision), gate.decision_request_artifact_ref)
    assert outcome.outcome == GATE_REJECTED


def test_gate_literals_are_distinct() -> None:
    assert {graph_state.GATE_PENDING, GATE_APPROVED, GATE_REJECTED} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }


def test_sqlite_saver_preserves_checkpoint_identity_and_pending_writes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "graph.sqlite"
    saver = SqliteGraphSaver(path)
    checkpoint = empty_checkpoint()
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    saved = saver.put(config, checkpoint, {"source": "input", "step": 0}, {})
    assert saved["configurable"]["checkpoint_id"] == checkpoint["id"]
    saver.put_writes(saved, [("branch-result", {"ok": True})], "task-1")
    saver.close()

    reopened = SqliteGraphSaver(path)
    loaded = reopened.get_tuple(saved)
    assert loaded is not None
    assert loaded.checkpoint["id"] == checkpoint["id"]
    assert loaded.pending_writes == [("task-1", "branch-result", {"ok": True})]
    assert list(reopened.list(config, filter={"source": "input"}, limit=1))[0].config == saved
    assert list(reopened.list(config, filter={"source": "other"})) == []
    reopened.close()
