"""LangGraph orchestration for the SHRGT45 Replay workflow (T006).

Graph shape (see ``governance/workflow.json``):

    START
      -> S01_CANDIDATE -> S02_MECHANISM -> S03_HYPOTHESIS
      -> S04_DATA_AND_VERIFICATION
      -> [S05_COUNTEREXAMPLE || S06_MAGNETOGRAM_QA]   (real parallel branches)
      -> JOIN_REQUIRE_S05_AND_S06
      -> FIXTURE_IMPORT_REVIEW   (LangGraph interrupt, WAITING_HUMAN)
      -> S07_REPORT
      -> FINAL_REPLAY_REVIEW     (non-blocking acknowledgement)
      -> END

S05 and S06 run in the same super-step and are only joined by a node that
requires both snapshots. The ``FIXTURE_IMPORT_REVIEW`` node calls the real
LangGraph ``interrupt()`` primitive; it does not simulate the gate with an empty
node. Node functions only drive idempotent application services from
:mod:`ai_scientist_mvp.application.replay_workflow_service`.
"""
from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.domain.types import VersionedRef
from ai_scientist_mvp.workflow.state import (
    FINAL_REVIEW_AVAILABLE,
    GATE_APPROVED,
    GATE_PENDING,
    GATE_REJECTED,
    RUN_MODE_REPLAY,
    ReplayGraphState,
)

_STAGES = (
    "S01_CANDIDATE",
    "S02_MECHANISM",
    "S03_HYPOTHESIS",
    "S04_DATA_AND_VERIFICATION",
    "S05_COUNTEREXAMPLE",
    "S06_MAGNETOGRAM_QA",
)
_JOIN_NODE = "join_require_s05_and_s06"
_GATE_NODE = "fixture_import_review"
_S07_NODE = "s07_report"
_FINAL_NODE = "final_replay_review"
_FAILURE_NODE = "failure"


def stage_dependencies(service: ReplayWorkflowService, stage_id: str) -> list[str]:
    """Return the upstream stage ids for a stage, from the frozen Case Manifest."""
    return list(service.catalog.case_manifest["stage_dependencies"].get(stage_id, []))


def _record_failure(
    service: ReplayWorkflowService,
    stage_id: str,
    category: str,
    code: str,
    message: str,
    retryable: bool = True,
    attempt: int = 1,
) -> VersionedRef:
    return service.record_failure(stage_id, category, code, message, retryable, attempt, [])


def _stage_node_factory(
    service: ReplayWorkflowService, stage_id: str
) -> Any:
    def node(state: ReplayGraphState) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if stage_id == "S01_CANDIDATE":
            if state.get("run_mode", RUN_MODE_REPLAY) != RUN_MODE_REPLAY:
                return {
                    "stage_status": {stage_id: "FAILED"},
                    "failure_refs": [
                        _record_failure(
                            service,
                            stage_id,
                            "AUTHORIZATION",
                            "UNAUTHORIZED_FORMAL_EXECUTION",
                            "run_mode must be REPLAY",
                            retryable=False,
                        )
                    ],
                }
            _, _, prepared_config_ref = service.prepare_configuration()
            updates["configuration_ref"] = prepared_config_ref

        current_config_ref = cast(
            VersionedRef,
            updates.get("configuration_ref") or state.get("configuration_ref"),
        )
        deps = stage_dependencies(service, stage_id)
        status = state.get("stage_status", {})
        if any(status.get(upstream) != "SUCCEEDED" for upstream in deps):
            return {
                **updates,
                "stage_status": {stage_id: "FAILED"},
                "failure_refs": [
                    _record_failure(
                        service,
                        stage_id,
                        "QUALITY",
                        "REQUIRED_UPSTREAM_STAGE_FAILURE",
                        "required upstream stage did not succeed",
                        retryable=False,
                    )
                ],
            }

        upstream_refs = {
            upstream: state["stage_snapshot_refs"][upstream] for upstream in deps
        }
        result = service.run_stage_bounded(stage_id, current_config_ref, upstream_refs)
        if result.succeeded:
            assert result.output is not None
            return {
                **updates,
                "stage_snapshot_refs": {stage_id: result.output.snapshot_ref},
                "stage_status": {stage_id: "SUCCEEDED"},
            }
        return {
            **updates,
            "stage_status": {stage_id: "FAILED"},
            "failure_refs": [
                _record_failure(
                    service,
                    stage_id,
                    result.failure_category or "PROGRAM",
                    result.failure_code or "REPLAY_STAGE_FAILURE",
                    result.failure_message or "stage failed",
                    retryable=result.retryable,
                    attempt=result.attempts,
                )
            ],
        }

    return node


def _join_node_factory(
    service: ReplayWorkflowService,
) -> Any:
    def node(state: ReplayGraphState) -> dict[str, Any]:
        status = state.get("stage_status", {})
        snapshot_refs = state.get("stage_snapshot_refs", {})
        incomplete = [
            stage_id
            for stage_id in _STAGES
            if status.get(stage_id) != "SUCCEEDED" or stage_id not in snapshot_refs
        ]
        if incomplete:
            return {
                "gate_decision": "FAILED",
                "gate_error": "required branch not complete: " + ",".join(incomplete),
                "failure_refs": [
                    _record_failure(
                        service,
                        "S07_REPORT",
                        "QUALITY",
                        "REQUIRED_S05_OR_S06_BRANCH_FAILURE",
                        "required branch not complete: " + ",".join(incomplete),
                        retryable=False,
                    )
                ],
            }

        s05_ref = snapshot_refs["S05_COUNTEREXAMPLE"]
        s06_ref = snapshot_refs["S06_MAGNETOGRAM_QA"]
        if not service.verify_branch_types(s05_ref, s06_ref):
            return {
                "gate_decision": "FAILED",
                "gate_error": "S05/S06 snapshot types do not satisfy the report join",
                "failure_refs": [
                    _record_failure(
                        service,
                        "S07_REPORT",
                        "VALIDATION",
                        "REPORT_JOIN_FAILURE",
                        "S05/S06 snapshot types do not satisfy the report join",
                        retryable=False,
                    )
                ],
            }

        gate = service.replay.prepare_fixture_review()
        service.write_gate_checkpoint(gate)
        return {
            "finding_refs": gate.finding_refs,
            "decision_request_ref": gate.decision_request_artifact_ref,
            "gate_decision": GATE_PENDING,
        }

    return node


def _join_router(state: ReplayGraphState) -> str:
    return _GATE_NODE if state.get("gate_decision") == GATE_PENDING else _FAILURE_NODE


def _gate_node_factory(
    service: ReplayWorkflowService,
) -> Any:
    def node(state: ReplayGraphState) -> dict[str, Any]:
        # Real LangGraph interrupt: the first execution pauses here and projects
        # the Run into WAITING_HUMAN. On resume this call returns the DecisionRecord.
        decision = interrupt(
            {
                "gate_id": "FIXTURE_IMPORT_REVIEW",
                "run_id": state.get("run_id"),
                "decision_request_ref": state.get("decision_request_ref"),
            }
        )
        result, decision_ref = service.accept_gate_decision(
            decision, state["decision_request_ref"]
        )
        if result.outcome == GATE_APPROVED:
            assert decision_ref is not None
            return {
                "gate_decision": GATE_APPROVED,
                "gate_decision_ref": decision_ref,
            }
        return {"gate_decision": GATE_REJECTED, "gate_error": result.error or "rejected"}

    return node


def _gate_router(state: ReplayGraphState) -> str:
    return _S07_NODE if state.get("gate_decision") == GATE_APPROVED else _FAILURE_NODE


def _s07_node_factory(
    service: ReplayWorkflowService,
) -> Any:
    def node(state: ReplayGraphState) -> dict[str, Any]:
        gate = service.replay.prepare_fixture_review()
        snapshot_refs = state["stage_snapshot_refs"]
        report = service.build_report(
            snapshot_refs["S05_COUNTEREXAMPLE"],
            snapshot_refs["S06_MAGNETOGRAM_QA"],
            gate.finding_refs,
            list(gate.finding_artifact_refs.values()),
        )
        service.project_run_succeeded()
        return {
            "report_summary_ref": report.research_summary_ref,
            "report_manifest_ref": report.report_manifest_ref,
        }

    return node


def _final_node_factory(
    service: ReplayWorkflowService,
) -> Any:
    def node(state: ReplayGraphState) -> dict[str, Any]:
        # Report visibility is non-blocking, but no acknowledgement is claimed
        # until record_project_ack() receives an explicit human DecisionRecord.
        return {
            "final_review_status": FINAL_REVIEW_AVAILABLE,
            "completed": True,
        }

    return node


def _failure_node(state: ReplayGraphState) -> dict[str, Any]:
    return {"completed": False}


def build_replay_graph(
    service: ReplayWorkflowService, checkpointer: Any
) -> Any:
    """Compile the S01-S07 replay graph with a persistent checkpointer."""
    graph = StateGraph(ReplayGraphState)
    for stage_id in _STAGES:
        graph.add_node(stage_id, _stage_node_factory(service, stage_id))
    graph.add_node(_JOIN_NODE, _join_node_factory(service))
    graph.add_node(_GATE_NODE, _gate_node_factory(service))
    graph.add_node(_S07_NODE, _s07_node_factory(service))
    graph.add_node(_FINAL_NODE, _final_node_factory(service))
    graph.add_node(_FAILURE_NODE, _failure_node)

    graph.add_edge(START, "S01_CANDIDATE")
    graph.add_edge("S01_CANDIDATE", "S02_MECHANISM")
    graph.add_edge("S02_MECHANISM", "S03_HYPOTHESIS")
    graph.add_edge("S03_HYPOTHESIS", "S04_DATA_AND_VERIFICATION")
    graph.add_edge("S04_DATA_AND_VERIFICATION", "S05_COUNTEREXAMPLE")
    graph.add_edge("S04_DATA_AND_VERIFICATION", "S06_MAGNETOGRAM_QA")
    graph.add_edge("S05_COUNTEREXAMPLE", _JOIN_NODE)
    graph.add_edge("S06_MAGNETOGRAM_QA", _JOIN_NODE)
    graph.add_conditional_edges(
        _JOIN_NODE,
        _join_router,
        {_GATE_NODE: _GATE_NODE, _FAILURE_NODE: _FAILURE_NODE},
    )
    graph.add_conditional_edges(
        _GATE_NODE,
        _gate_router,
        {_S07_NODE: _S07_NODE, _FAILURE_NODE: _FAILURE_NODE},
    )
    graph.add_edge(_S07_NODE, _FINAL_NODE)
    graph.add_edge(_FINAL_NODE, END)
    graph.add_edge(_FAILURE_NODE, END)

    return graph.compile(checkpointer=checkpointer)
