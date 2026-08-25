"""End-to-end integration tests for the T006 LangGraph replay workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langgraph.types import Command

from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import LedgerIntegrityError, StoreError
from ai_scientist_mvp.infrastructure.paths import derive_artifact_path
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.workflow.checkpoint import SqliteGraphSaver, graph_saver_path
from ai_scientist_mvp.workflow.replay_graph import build_replay_graph
from ai_scientist_mvp.workflow.state import (
    FINAL_REVIEW_AVAILABLE,
    GATE_APPROVED,
    GATE_PENDING,
    RUN_MODE_REPLAY,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "shrgt45"


def _runtime(
    runs_root: Path, run_id: str
) -> tuple[LocalStorage, ReplayWorkflowService, Any, dict[str, Any]]:
    storage = LocalStorage(runs_root, run_id)
    service = ReplayWorkflowService(storage, FIXTURES, run_id, "task-6")
    saver = SqliteGraphSaver(graph_saver_path(runs_root, run_id))
    graph = build_replay_graph(service, saver)
    config = {"configurable": {"thread_id": run_id}}
    return storage, service, graph, config


def _initial(service: ReplayWorkflowService, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "task_id": "task-6",
        "workflow_version": service.workflow_version,
        "run_mode": RUN_MODE_REPLAY,
    }


def _report_artifact_types(storage: LocalStorage) -> set[str]:
    return {
        envelope["artifact_type"]
        for envelope in storage.ledger.read("artifact_envelope")
    }


def _close(storage: LocalStorage, graph: Any) -> None:
    graph.checkpointer.close()
    storage.close()


def test_interrupt_projects_waiting_human(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-happy")
    result = graph.invoke(_initial(service, "run-happy"), config)
    assert result.get("gate_decision") == GATE_PENDING
    assert result.get("stage_status", {}).get("S05_COUNTEREXAMPLE") == "SUCCEEDED"
    assert result.get("stage_status", {}).get("S06_MAGNETOGRAM_QA") == "SUCCEEDED"
    assert result.get("__interrupt__")
    assert storage.run_store.get_run("run-happy")["execution_status"] == "WAITING_HUMAN"
    snapshot = graph.get_state(config)
    assert snapshot.next == ("fixture_import_review",)
    _close(storage, graph)


def test_approve_resume_produces_report_binding_s05_s06(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-approve")
    graph.invoke(_initial(service, "run-approve"), config)
    state = graph.get_state(config)
    decision_request_ref = state.values["decision_request_ref"]
    decision = service.make_approval_decision(decision_request_ref)
    result = graph.invoke(Command(resume=decision), config)

    assert result.get("gate_decision") == GATE_APPROVED
    assert result.get("final_review_status") == FINAL_REVIEW_AVAILABLE
    assert result.get("gate_decision_ref") == {
        "id": decision["decision_id"],
        "schema_version": decision["schema_version"],
        "content_hash": decision["content_hash"],
    }
    decision_artifact_ref = service.resolve_versioned_artifact(
        result["gate_decision_ref"], "DecisionRecord"
    )
    decision_envelope = storage.artifact_store.get_envelope(
        decision_artifact_ref["artifact_id"]
    )
    assert decision_envelope["payload"] == decision
    manifest_ref = result["report_manifest_ref"]
    manifest = storage.artifact_store.get_envelope(manifest_ref["artifact_id"])
    assert manifest["artifact_type"] == "ReportManifest"
    assert manifest["payload"]["s05_branch_ref"] == result["stage_snapshot_refs"][
        "S05_COUNTEREXAMPLE"
    ]
    assert manifest["payload"]["s06_branch_ref"] == result["stage_snapshot_refs"][
        "S06_MAGNETOGRAM_QA"
    ]

    summary_ref = result["report_summary_ref"]
    summary = storage.artifact_store.get_envelope(summary_ref["artifact_id"])
    payload = summary["payload"]
    assert payload["scientific_verdict"] == "NOT_EVALUATED"
    assert payload["result_maturity"] == "DEVELOPMENTAL"
    assert payload["authorization_status"] == "NOT_AUTHORIZED"
    assert payload["release_scope"] == "NOT_READY"
    assert storage.run_store.get_run("run-approve")["execution_status"] == "SUCCEEDED"
    assert "ProjectReviewAck" not in _report_artifact_types(storage)
    _close(storage, graph)


def test_invalid_decision_blocks_report(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-invalid")
    graph.invoke(_initial(service, "run-invalid"), config)
    state = graph.get_state(config)
    decision_request_ref = state.values["decision_request_ref"]
    decision = service.make_approval_decision(decision_request_ref)
    decision["selected_option_id"] = "REVISE"
    decision["action"] = "REJECT"
    decision["content_hash"] = canonical_json.content_hash_excluding(decision)
    result = graph.invoke(Command(resume=decision), config)

    assert result.get("gate_decision") != GATE_APPROVED
    assert result.get("completed") is False
    assert "ReportManifest" not in _report_artifact_types(storage)
    assert "DecisionRecord" not in _report_artifact_types(storage)
    _close(storage, graph)


def test_branch_failure_prevents_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-branchfail")
    real_run_stage = service.replay.run_stage

    def fail_s06(stage_id: str, *args: Any, **kwargs: Any) -> Any:
        if stage_id == "S06_MAGNETOGRAM_QA":
            raise LedgerIntegrityError("injected S06 failure")
        return real_run_stage(stage_id, *args, **kwargs)

    monkeypatch.setattr(service.replay, "run_stage", fail_s06)
    result = graph.invoke(_initial(service, "run-branchfail"), config)

    assert result.get("gate_decision") != GATE_PENDING
    assert result.get("completed") is False
    assert "ReportManifest" not in _report_artifact_types(storage)
    failures = storage.ledger.read("failure_record")
    assert failures
    failure_ref = result["failure_refs"][0]
    failure_artifact_ref = service.resolve_versioned_artifact(
        failure_ref, "FailureRecord"
    )
    failure_envelope = storage.artifact_store.get_envelope(
        failure_artifact_ref["artifact_id"]
    )
    assert failure_envelope["payload"] == failures[0]
    _close(storage, graph)


def test_wrong_branch_type_prevents_report(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-wrongtype")
    # Prepare a real gate, then verify the join type guard rejects a wrong pairing.
    gate = service.replay.prepare_fixture_review()
    wrong_s05 = gate.snapshot_refs["S01_CANDIDATE"]  # CandidateSnapshot, not Counterexample
    assert service.verify_branch_types(wrong_s05, gate.snapshot_refs["S06_MAGNETOGRAM_QA"]) is False
    with pytest.raises(LedgerIntegrityError):
        service.build_report(
            wrong_s05,
            gate.snapshot_refs["S06_MAGNETOGRAM_QA"],
            gate.finding_refs,
            list(gate.finding_artifact_refs.values()),
        )
    _close(storage, graph)


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-idempotent")
    graph.invoke(_initial(service, "run-idempotent"), config)
    # The stage nodes and the join node both touch the same idempotent writes.
    assert len(storage.ledger.read("artifact_envelope")) == 107
    assert len(storage.ledger.read("stage_run")) == 6
    _close(storage, graph)

    # Fresh process view of the same Run namespace: nothing is duplicated.
    storage2, service2, graph2, _config2 = _runtime(tmp_path, "run-idempotent")
    service2.replay.prepare_fixture_review()
    assert len(storage2.ledger.read("artifact_envelope")) == 107
    assert len(storage2.ledger.read("stage_run")) == 6
    _close(storage2, graph2)


def test_cross_process_recovery_and_resume(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-crossproc")
    graph.invoke(_initial(service, "run-crossproc"), config)
    decision_request_ref = graph.get_state(config).values["decision_request_ref"]
    decision = service.make_approval_decision(decision_request_ref)
    _close(storage, graph)

    # Rebuild graph + checkpointer from disk; the checkpoint must survive.
    storage2, service2, graph2, config2 = _runtime(tmp_path, "run-crossproc")
    service2.verify_gate_checkpoint()
    result = graph2.invoke(Command(resume=decision), config2)
    assert result.get("gate_decision") == GATE_APPROVED
    assert result.get("final_review_status") == FINAL_REVIEW_AVAILABLE
    persisted_ref = result["gate_decision_ref"]
    assert persisted_ref["content_hash"] == decision["content_hash"]
    service2.resolve_versioned_artifact(persisted_ref, "DecisionRecord")
    _close(storage2, graph2)


def test_tampered_artifact_fails_closed(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-tamper")
    graph.invoke(_initial(service, "run-tamper"), config)
    checkpoint = storage.checkpoint_store.latest("run-tamper")
    assert checkpoint is not None
    victim = checkpoint["artifact_refs"][0]
    path = derive_artifact_path(tmp_path, "run-tamper", victim["content_sha256"])
    path.unlink()
    with pytest.raises(StoreError):
        service.verify_gate_checkpoint()
    _close(storage, graph)


def test_retry_finite_and_no_scientific_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-retry")

    def always_fail(stage_id: str, *args: Any, **kwargs: Any) -> Any:
        raise StoreError("injected system failure")

    monkeypatch.setattr(service.replay, "run_stage", always_fail)
    result = graph.invoke(_initial(service, "run-retry"), config)

    assert result.get("completed") is False
    assert "ReportManifest" not in _report_artifact_types(storage)
    assert "ResearchSummary" not in _report_artifact_types(storage)
    failures = storage.ledger.read("failure_record")
    assert failures, "expected at least one structured FailureRecord"
    assert failures[0]["attempt"] == service.max_attempts
    assert failures[0]["retryable"] is True
    _close(storage, graph)


def test_integrity_failure_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-integrity")
    calls: dict[str, int] = {}

    def fail_integrity(stage_id: str, *args: Any, **kwargs: Any) -> Any:
        calls[stage_id] = calls.get(stage_id, 0) + 1
        raise LedgerIntegrityError("injected immutable identity failure")

    monkeypatch.setattr(service.replay, "run_stage", fail_integrity)
    result = graph.invoke(_initial(service, "run-integrity"), config)

    assert result.get("completed") is False
    # S01-S03 are independent evidence stages in the frozen manifest. Each may
    # fail independently, but no individual integrity failure is retried.
    assert calls == {
        "S01_CANDIDATE": 1,
        "S02_MECHANISM": 1,
        "S03_HYPOTHESIS": 1,
    }
    failures = storage.ledger.read("failure_record")
    assert failures[0]["attempt"] == 1
    assert failures[0]["retryable"] is False
    _close(storage, graph)


def test_final_review_does_not_create_release_disposition(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-norelease")
    graph.invoke(_initial(service, "run-norelease"), config)
    state = graph.get_state(config)
    decision = service.make_approval_decision(state.values["decision_request_ref"])
    result = graph.invoke(Command(resume=decision), config)
    assert result.get("final_review_status") == FINAL_REVIEW_AVAILABLE

    types = _report_artifact_types(storage)
    assert "ReportManifest" in types
    assert "ReleaseDisposition" not in types
    assert "ProjectReviewAck" not in types
    with pytest.raises(LedgerIntegrityError, match="FINAL_REPLAY_REVIEW"):
        service.record_project_ack(
            result["report_manifest_ref"],
            result["gate_decision_ref"],
            "project_owner_01",
            "project_owner",
        )
    _close(storage, graph)


def test_non_replay_run_mode_is_rejected(tmp_path: Path) -> None:
    storage, service, graph, config = _runtime(tmp_path, "run-mode")
    initial = _initial(service, "run-mode")
    initial["run_mode"] = "LIVE"
    result = graph.invoke(initial, config)
    assert result.get("completed") is False
    assert result.get("stage_status", {}).get("S01_CANDIDATE") == "FAILED"
    assert "ReportManifest" not in _report_artifact_types(storage)
    _close(storage, graph)
