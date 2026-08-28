"""D-006 RunReadModel projection and safe detail queries."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, cast

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import StoreError
from ai_scientist_mvp.domain.types import ArtifactRef, RunReadModel, VersionedRef
from ai_scientist_mvp.infrastructure.storage import LocalStorage

_DOMAIN_TYPES = {
    "CandidateSnapshot",
    "MechanismSnapshot",
    "HypothesisSnapshot",
    "DataPlan",
    "DatasetManifest",
    "DataDemoSnapshot",
    "CounterexampleReviewSnapshot",
    "CounterexampleSnapshot",
    "MagnetogramQASnapshot",
    "ResearchSummary",
}
_FINDING_TYPES = {"CompatibilityFinding", "GapFinding"}
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")


class ReadModelNotFound(KeyError):
    """The requested Run or versioned detail does not exist."""


def _versioned_ref(identifier: str, schema_version: str, content_hash: str) -> VersionedRef:
    return {"id": identifier, "schema_version": schema_version, "content_hash": content_hash}


def _artifact_ref(envelope: Mapping[str, Any]) -> ArtifactRef:
    return {
        "artifact_id": cast(str, envelope["artifact_id"]),
        "content_sha256": cast(str, envelope["content_sha256"]),
        "schema_version": cast(str, envelope["schema_version"]),
    }


def _run_ref(run: Mapping[str, Any]) -> VersionedRef:
    digest = hashlib.sha256(canonical_json.canonicalize(dict(run))).hexdigest().upper()
    return _versioned_ref(cast(str, run["run_id"]), "0.1.0", digest)


def build_run_read_model(storage: LocalStorage) -> RunReadModel:
    """Build and validate the read-only aggregate for the storage Run."""
    try:
        run = storage.run_store.get_run(storage.run_id)
    except KeyError as exc:
        raise ReadModelNotFound(storage.run_id) from exc
    envelopes = [
        envelope
        for envelope in storage.ledger.read("artifact_envelope")
        if envelope.get("run_id") == storage.run_id
    ]
    artifacts = [_artifact_ref(envelope) for envelope in envelopes]
    stage_facts = [
        stage
        for stage in storage.ledger.read("stage_run")
        if stage.get("run_id") == storage.run_id
    ]
    stages = [
        _versioned_ref(
            f"stage-run-{stage['run_id']}-{stage['stage_id']}-{stage['attempt']}",
            cast(str, stage["schema_version"]),
            cast(str, stage["content_hash"]),
        )
        for stage in stage_facts
    ]
    domain_snapshots: list[VersionedRef] = []
    findings: list[VersionedRef] = []
    report: VersionedRef | None = None
    gate_entries = [
        {"gate_id": "FIXTURE_IMPORT_REVIEW", "status": "NOT_RECORDED"},
        {"gate_id": "FINAL_REPLAY_REVIEW", "status": "NOT_RECORDED"},
    ]
    for envelope in envelopes:
        artifact_type = envelope.get("artifact_type")
        ref = _versioned_ref(
            cast(str, envelope["logical_artifact_id"]),
            cast(str, envelope["schema_version"]),
            cast(str, envelope["content_sha256"]),
        )
        if artifact_type in _DOMAIN_TYPES:
            domain_snapshots.append(ref)
        if artifact_type in _FINDING_TYPES:
            payload = envelope.get("payload")
            if isinstance(payload, Mapping) and isinstance(payload.get("finding_id"), str):
                findings.append(
                    _versioned_ref(
                        payload["finding_id"],
                        cast(str, payload.get("schema_version", envelope["schema_version"])),
                        cast(str, payload.get("content_hash", envelope["content_sha256"])),
                    )
                )
        if artifact_type == "ReportManifest":
            report = ref
        if artifact_type == "DecisionRecord":
            payload = envelope.get("payload")
            if isinstance(payload, Mapping) and payload.get("gate_id") in {
                "FIXTURE_IMPORT_REVIEW",
                "FINAL_REPLAY_REVIEW",
            }:
                for entry in gate_entries:
                    if entry["gate_id"] == payload["gate_id"]:
                        entry["status"] = cast(str, payload.get("action", "RECORDED"))
        if artifact_type == "ProjectReviewAck":
            gate_entries[1]["status"] = "ACKNOWLEDGED_FOR_PROJECT_REVIEW"
    lineage_status = "VERIFIED"
    for artifact in artifacts:
        try:
            storage.artifact_store.verify_ref(artifact)
        except (KeyError, StoreError):
            lineage_status = "PARTIAL"
            break
    model: dict[str, Any] = {
        "read_model_schema_version": "0.1.0",
        "run": _run_ref(run),
        "stages": stages,
        "domain_snapshots": domain_snapshots,
        "artifacts": artifacts,
        "findings": findings,
        "gates": gate_entries,
        "lineage_summary": {"lineage_status": lineage_status},
    }
    if report is not None:
        model["report"] = report
    storage.contracts.validate("run-read-model", model)
    return cast(RunReadModel, model)


def list_artifacts(storage: LocalStorage) -> list[dict[str, Any]]:
    return [
        _public_detail(envelope)
        for envelope in storage.ledger.read("artifact_envelope")
        if envelope.get("run_id") == storage.run_id
    ]


def get_artifact(storage: LocalStorage, artifact_id: str) -> dict[str, Any]:
    try:
        envelope = storage.artifact_store.get_envelope(artifact_id)
    except KeyError as exc:
        raise ReadModelNotFound(artifact_id) from exc
    return _public_detail(cast(dict[str, Any], envelope))


def list_stages(storage: LocalStorage) -> list[dict[str, Any]]:
    return [
        _public_detail(stage)
        for stage in storage.ledger.read("stage_run")
        if stage.get("run_id") == storage.run_id
    ]


def list_findings(storage: LocalStorage) -> list[dict[str, Any]]:
    return [
        _public_detail(envelope)
        for envelope in storage.ledger.read("artifact_envelope")
        if envelope.get("run_id") == storage.run_id
        and envelope.get("artifact_type") in _FINDING_TYPES
    ]


def list_reviews(storage: LocalStorage) -> list[dict[str, Any]]:
    review_types = {"DecisionRecord", "ProjectReviewAck", "DecisionRequest"}
    return [
        _public_detail(envelope)
        for envelope in storage.ledger.read("artifact_envelope")
        if envelope.get("run_id") == storage.run_id
        and envelope.get("artifact_type") in review_types
    ]


def _public_detail(value: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], _redact_paths(value))


def _redact_paths(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _redact_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_paths(item) for item in value]
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        return f"<redacted-absolute-path:{PurePosixPath(value).name}>"
    return value
