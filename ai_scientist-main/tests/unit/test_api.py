from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ai_scientist_mvp.api.read_model import build_run_read_model
from ai_scientist_mvp.api.server import make_handler
from ai_scientist_mvp.application.replay_workflow_service import ReplayWorkflowService
from ai_scientist_mvp.infrastructure.storage import LocalStorage

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "shrgt45"


def test_run_read_model_is_contract_valid_and_contains_domain_sections(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path, "api-run")
    service = ReplayWorkflowService(storage, FIXTURES, "api-run", "api-task")
    preparation = service.replay.prepare_fixture_review()
    model = build_run_read_model(storage)
    assert model["run"]["id"] == "api-run"
    assert len(model["stages"]) == 6
    assert len(model["artifacts"]) >= 6
    assert len(model["findings"]) == len(preparation.finding_refs)
    assert model["gates"][0]["status"] == "NOT_RECORDED"
    assert model["lineage_summary"]["lineage_status"] == "VERIFIED"
    storage.close()


def test_read_only_http_api_routes_model_without_socket_or_mutation(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path, "http-run")
    ReplayWorkflowService(
        storage, FIXTURES, "http-run", "http-task"
    ).replay.prepare_fixture_review()
    handler_class = make_handler(storage)
    handler = cast(Any, handler_class.__new__(handler_class))
    try:
        payload = handler._route(["runs", "http-run", "read-model"])
        assert payload["run"]["id"] == "http-run"
        assert handler._route(["health"])["read_only"] is True
    finally:
        storage.close()
