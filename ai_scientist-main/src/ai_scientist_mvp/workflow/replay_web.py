"""Web-facing controller that keeps LangGraph internals inside workflow/."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, cast

from langgraph.types import Command

from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.domain.types import ArtifactRef
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.workflow.checkpoint import SqliteGraphSaver, graph_saver_path
from ai_scientist_mvp.workflow.replay_graph import build_replay_graph
from ai_scientist_mvp.workflow.state import RUN_MODE_REPLAY


class ReplayWebController:
    """Start, inspect, and approve one Replay Run for the HTTP adapter."""

    def __init__(self, storage: LocalStorage, fixtures_root: Path, task_id: str) -> None:
        self.storage = storage
        self.fixtures_root = fixtures_root
        self.task_id = task_id
        self._lock = threading.RLock()

    def start(self) -> dict[str, object]:
        with self._lock:
            service, graph = self._runtime()
            try:
                result = graph.invoke(
                    {
                        "run_id": self.storage.run_id,
                        "task_id": self.task_id,
                        "workflow_version": service.workflow_version,
                        "run_mode": RUN_MODE_REPLAY,
                    },
                    self._config(),
                )
                return {"operation": "start", "workflow": _describe_workflow(result)}
            finally:
                graph.checkpointer.close()

    def approve(self, body: dict[str, object]) -> dict[str, object]:
        with self._lock:
            service, graph = self._runtime()
            try:
                service.verify_gate_checkpoint()
                state = graph.get_state(self._config())
                request_ref = state.values.get("decision_request_ref") if state.values else None
                if not isinstance(request_ref, dict):
                    raise ValueError("no pending FIXTURE_IMPORT_REVIEW decision request")
                actor = str(body.get("actor_id") or "project_owner_01")
                role = str(body.get("actor_role") or "project_owner")
                decision = service.make_approval_decision(
                    cast(ArtifactRef, request_ref), actor, role
                )
                result = graph.invoke(Command(resume=decision), self._config())
                return {"operation": "approve", "workflow": _describe_workflow(result)}
            finally:
                graph.checkpointer.close()

    def status(self) -> dict[str, object]:
        service, graph = self._runtime()
        try:
            state = graph.get_state(self._config())
            values = dict(state.values or {})
            return {
                "run_id": self.storage.run_id,
                "pending_nodes": list(state.next) if state.next else [],
                "stage_status": values.get("stage_status", {}),
                "gate_decision": values.get("gate_decision"),
                "final_review_status": values.get("final_review_status"),
            }
        finally:
            graph.checkpointer.close()

    def _runtime(self) -> tuple[ReplayWorkflowService, Any]:
        service = ReplayWorkflowService(
            self.storage,
            self.fixtures_root,
            self.storage.run_id,
            self.task_id,
        )
        saver = SqliteGraphSaver(graph_saver_path(self.storage.runs_root, self.storage.run_id))
        return service, build_replay_graph(service, saver)

    def _config(self) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": self.storage.run_id}}


def _describe_workflow(state: dict[str, object]) -> dict[str, object]:
    return {
        "stage_status": state.get("stage_status", {}),
        "gate_decision": state.get("gate_decision"),
        "gate_error": state.get("gate_error"),
        "final_review_status": state.get("final_review_status"),
        "completed": state.get("completed", False),
    }
