"""Offline command-line demonstration of the SHRGT45 Replay workflow (T006).

This is an inspectable CLI, not a web API. It drives the real LangGraph graph
and shows stage progression, the S05/S06 parallel branches, the human
``FIXTURE_IMPORT_REVIEW`` interrupt, a bounded-approval resume, and the final
report references. It never prints machine-specific absolute paths and never
presents a structural PASS as scientific support.

Example::

    python -m ai_scientist_mvp.workflow.replay_cli start --run-id demo
    python -m ai_scientist_mvp.workflow.replay_cli approve --run-id demo
    python -m ai_scientist_mvp.workflow.replay_cli status --run-id demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from langgraph.types import Command

from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.domain.errors import StoreError
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.workflow.checkpoint import SqliteGraphSaver, graph_saver_path
from ai_scientist_mvp.workflow.replay_graph import build_replay_graph
from ai_scientist_mvp.workflow.state import RUN_MODE_REPLAY

_DEFAULT_TASK_ID = "task-6"
_DEFAULT_FIXTURES = "fixtures/shrgt45"
_DEFAULT_RUNS_ROOT = "runs"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve(repository_relative: str) -> Path:
    return _project_root() / repository_relative


def _runtime(
    runs_root: str, fixtures_root: str, run_id: str, task_id: str
) -> tuple[Any, Any, ReplayWorkflowService]:
    root = _resolve(runs_root)
    fixtures = _resolve(fixtures_root)
    storage = LocalStorage(root, run_id)
    service = ReplayWorkflowService(storage, fixtures, run_id, task_id)
    saver = SqliteGraphSaver(graph_saver_path(root, run_id))
    graph = build_replay_graph(service, saver)
    return storage, graph, service


def _config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def _print(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


def _close_runtime(storage: LocalStorage, graph: Any) -> None:
    graph.checkpointer.close()
    storage.close()


def cmd_start(args: argparse.Namespace) -> int:
    storage, graph, service = _runtime(
        args.runs_root, args.fixtures_root, args.run_id, args.task_id
    )
    try:
        result = graph.invoke(
            {
                "run_id": args.run_id,
                "task_id": args.task_id,
                "workflow_version": service.workflow_version,
                "run_mode": RUN_MODE_REPLAY,
            },
            _config(args.run_id),
        )
    finally:
        _close_runtime(storage, graph)
    snapshot = _describe(result)
    snapshot["gate"] = "FIXTURE_IMPORT_REVIEW"
    snapshot["run_execution_status"] = "WAITING_HUMAN"
    _print(snapshot)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    storage, graph, service = _runtime(
        args.runs_root, args.fixtures_root, args.run_id, args.task_id
    )
    try:
        service.verify_gate_checkpoint()
        state = graph.get_state(_config(args.run_id))
        values = state.values or {}
        decision_request_ref = values.get("decision_request_ref")
        if not decision_request_ref:
            print("no pending FIXTURE_IMPORT_REVIEW decision request; run start first")
            return 2
        decision = service.make_approval_decision(decision_request_ref, args.actor, args.role)
        result = graph.invoke(Command(resume=decision), _config(args.run_id))
    except StoreError as exc:
        print(f"approve failed closed: {exc}")
        return 2
    finally:
        _close_runtime(storage, graph)
    _print(_describe(result))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    storage, graph, service = _runtime(
        args.runs_root, args.fixtures_root, args.run_id, args.task_id
    )
    try:
        state = graph.get_state(_config(args.run_id))
        values = dict(state.values or {})
        checkpoint = storage.checkpoint_store.latest(args.run_id)
    finally:
        _close_runtime(storage, graph)
    payload: dict[str, Any] = {
        "run_id": args.run_id,
        "pending_nodes": list(state.next) if state.next else [],
        "checkpoint_ref": (
            {"checkpoint_id": checkpoint["checkpoint_id"], "run_id": checkpoint["run_id"]}
            if checkpoint
            else None
        ),
        "stage_status": values.get("stage_status", {}),
        "gate_decision": values.get("gate_decision"),
        "final_review_status": values.get("final_review_status"),
    }
    _print(payload)
    return 0


def _describe(state: dict[str, Any]) -> dict[str, Any]:
    report_ref = state.get("report_manifest_ref")
    return {
        "stage_status": state.get("stage_status", {}),
        "stage_snapshot_count": len(state.get("stage_snapshot_refs", {})),
        "finding_ref_count": len(state.get("finding_refs", [])),
        "gate_decision": state.get("gate_decision"),
        "gate_error": state.get("gate_error"),
        "final_review_status": state.get("final_review_status"),
        "report_manifest_ref": report_ref,
        "scientific_verdict": "NOT_EVALUATED",
        "result_maturity": "DEVELOPMENTAL",
        "authorization_status": "NOT_AUTHORIZED",
        "release_scope": "NOT_READY",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay-cli", description="SHRGT45 Replay workflow demo")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--run-id", required=True, help="isolated run id")
    common.add_argument("--task-id", default=_DEFAULT_TASK_ID, help="research task id")
    common.add_argument(
        "--fixtures-root", default=_DEFAULT_FIXTURES, help="repository-relative fixtures dir"
    )
    common.add_argument(
        "--runs-root", default=_DEFAULT_RUNS_ROOT, help="repository-relative runs dir"
    )

    start = sub.add_parser("start", parents=[common], help="run S01-S06 and interrupt at the gate")
    start.set_defaults(func=cmd_start)

    approve = sub.add_parser(
        "approve", parents=[common], help="resume with a bound approval decision"
    )
    approve.add_argument("--actor", default="project_owner_01", help="human actor id")
    approve.add_argument("--role", default="project_owner", help="human actor role")
    approve.set_defaults(func=cmd_approve)

    status = sub.add_parser("status", parents=[common], help="show the current workflow state")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return cast(int, args.func(args))


if __name__ == "__main__":
    sys.exit(main())
