"""Dependency-free HTTP API for RunReadModel and the replay demo workflow."""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ai_scientist_mvp.api.read_model import (
    ReadModelNotFound,
    build_run_read_model,
    get_artifact,
    list_artifacts,
    list_findings,
    list_reviews,
    list_stages,
)
from ai_scientist_mvp.api.workbench import (
    JWSSDWorkbench,
    WorkbenchBinary,
    WorkbenchConflict,
    WorkbenchNotFound,
)
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.workflow.replay_web import ReplayWebController


def make_handler(
    storage: LocalStorage,
    fixtures_root: Path | None = None,
    task_id: str = "task-6",
    workbench: JWSSDWorkbench | None = None,
) -> type[BaseHTTPRequestHandler]:
    default_fixtures = Path(__file__).resolve().parents[3] / "fixtures" / "shrgt45"
    replay = ReplayWebController(storage, fixtures_root or default_fixtures, task_id)

    class Handler(BaseHTTPRequestHandler):
        server_version = "ai-scientist-mvp/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parts = [unquote(part) for part in urlsplit(self.path).path.split("/") if part]
            try:
                payload = self._route(parts)
            except (ReadModelNotFound, WorkbenchNotFound):
                self._send({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            except (KeyError, ValueError):
                self._send({"error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            except Exception:
                self._send({"error": "internal_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                if isinstance(payload, WorkbenchBinary):
                    self._send_bytes(payload, HTTPStatus.OK)
                else:
                    self._send(payload, HTTPStatus.OK)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            parts = [unquote(part) for part in urlsplit(self.path).path.split("/") if part]
            try:
                payload = self._post_route(parts, self._read_json())
            except (ReadModelNotFound, WorkbenchNotFound):
                self._send({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            except WorkbenchConflict as exc:
                self._send({"error": "analysis_conflict", "message": str(exc)}, HTTPStatus.CONFLICT)
            except (KeyError, ValueError, TypeError):
                self._send({"error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send({"error": "workflow_failed", "message": str(exc)}, HTTPStatus.CONFLICT)
            else:
                self._send(payload, HTTPStatus.OK)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _route(self, parts: list[str]) -> object:
            if parts == ["health"]:
                return {
                    "status": "ok",
                    "read_only": True,
                    "read_only_queries": True,
                    "workflow_operations": ["start", "approve"],
                    "workbench": workbench is not None,
                }
            if workbench is not None:
                if parts == ["workbench", "catalog"]:
                    return workbench.catalog()
                if len(parts) == 3 and parts[:2] == ["workbench", "observations"]:
                    return workbench.observation(parts[2])
                if (
                    len(parts) == 5
                    and parts[:2] == ["workbench", "observations"]
                    and parts[3] == "images"
                ):
                    return workbench.image(parts[2], parts[4])
                if len(parts) == 3 and parts[:2] == ["workbench", "jobs"]:
                    return workbench.analysis_job(parts[2])
            if len(parts) < 2 or parts[0] != "runs" or parts[1] != storage.run_id:
                raise ReadModelNotFound("run")
            if parts == ["runs", storage.run_id, "read-model"]:
                return build_run_read_model(storage)
            if parts == ["runs", storage.run_id, "stages"]:
                return list_stages(storage)
            if parts == ["runs", storage.run_id, "artifacts"]:
                return list_artifacts(storage)
            if parts == ["runs", storage.run_id, "findings"]:
                return list_findings(storage)
            if parts == ["runs", storage.run_id, "reviews"]:
                return list_reviews(storage)
            if parts == ["runs", storage.run_id, "status"]:
                return replay.status()
            if len(parts) == 4 and parts[2] == "artifacts":
                return get_artifact(storage, parts[3])
            raise ReadModelNotFound("resource")

        def _post_route(self, parts: list[str], body: dict[str, object]) -> object:
            if workbench is not None and parts == ["workbench", "analyses"]:
                observation_id = body.get("observation_id")
                if not isinstance(observation_id, str):
                    raise ValueError("observation_id is required")
                return workbench.start_analysis(observation_id)
            if parts[:2] != ["runs", storage.run_id] or len(parts) != 3:
                raise ReadModelNotFound("run")
            if parts[2] == "start":
                return replay.start()
            if parts[2] == "approve":
                return replay.approve(body)
            raise ReadModelNotFound("operation")

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            return payload

        def _send(self, payload: object, status: HTTPStatus) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, payload: WorkbenchBinary, status: HTTPStatus) -> None:
            self.send_response(status)
            self.send_header("Content-Type", payload.content_type)
            self.send_header("Content-Length", str(len(payload.body)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.body)

    return Handler


def serve(
    runs_root: Path,
    run_id: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    fixtures_root: Path | None = None,
    task_id: str = "task-6",
    archive_path: Path | None = None,
    qwen_config: Path | None = None,
    env_file: Path | None = None,
) -> None:
    storage = LocalStorage(runs_root, run_id)
    workbench = (
        JWSSDWorkbench(
            archive_path,
            config_path=qwen_config,
            env_file=env_file,
        )
        if archive_path is not None
        else None
    )
    server = ThreadingHTTPServer(
        (host, port), make_handler(storage, fixtures_root, task_id, workbench)
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the read-only AI Scientist Run API")
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fixtures-root", type=Path, default=None)
    parser.add_argument("--task-id", default="task-6")
    parser.add_argument("--archive", type=Path, default=None)
    parser.add_argument("--qwen-config", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()
    serve(
        args.runs_root,
        args.run_id,
        args.host,
        args.port,
        args.fixtures_root,
        args.task_id,
        args.archive,
        args.qwen_config,
        args.env_file,
    )


if __name__ == "__main__":
    main()
