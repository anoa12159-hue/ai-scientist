"""End-to-end persistence tests for the T005 SHRGT45 Replay preparation."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_scientist_mvp.application.replay_service import ReplayPreparation, ReplayService
from ai_scientist_mvp.domain.errors import LedgerIntegrityError
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.providers.shrgt45_replay import ManifestAssetCatalog

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "shrgt45"
STAGES = {
    "S01_CANDIDATE",
    "S02_MECHANISM",
    "S03_HYPOTHESIS",
    "S04_DATA_AND_VERIFICATION",
    "S05_COUNTEREXAMPLE",
    "S06_MAGNETOGRAM_QA",
}


@pytest.fixture(scope="module")
def prepared(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[LocalStorage, ReplayService, ReplayPreparation]]:
    storage = LocalStorage(tmp_path_factory.mktemp("replay"), "run-review")
    service = ReplayService(
        storage.artifact_store,
        storage.run_store,
        FIXTURES,
        "run-review",
        "task-5",
    )
    preparation = service.prepare_fixture_review()
    yield storage, service, preparation
    storage.close()


def test_catalog_closes_171_90_43_identity_sets() -> None:
    catalog = ManifestAssetCatalog(FIXTURES)
    catalog.load()
    assert len(catalog.manifest["source_assets"]) == 171
    assert len(catalog.provenance_assets()) == 90
    assert len(catalog.default_s04_assets()) == 43
    assert catalog.default_s04_assets() == catalog.stage_assets(
        "S04_DATA_AND_VERIFICATION"
    )
    assert not {
        asset["asset_id"] for asset in catalog.default_s04_assets()
    } & {asset["asset_id"] for asset in catalog.provenance_assets()}


def test_preparation_persists_all_public_objects(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    storage, _, result = prepared
    assert len(result.source_refs) == 81
    assert not any(key.startswith("s04.source0808::") for key in result.source_refs)
    assert set(result.snapshot_refs) == STAGES
    assert set(result.validation_reports) == STAGES
    assert len(result.findings) == 12
    assert len(result.finding_refs) == 12
    assert set(result.stage_runs) == STAGES
    assert len(result.stage_attempt_keys) == 6
    assert result.run_record["execution_status"] == "WAITING_HUMAN"

    persisted_refs = [
        result.configuration_artifact_ref,
        *result.source_refs.values(),
        *result.snapshot_refs.values(),
        *result.validation_artifact_refs.values(),
        *result.finding_artifact_refs.values(),
        result.decision_request_artifact_ref,
    ]
    for ref in persisted_refs:
        storage.artifact_store.verify_ref(ref)
    assert len({ref["artifact_id"] for ref in persisted_refs}) == 107


def test_snapshots_are_derived_from_registered_source_artifacts(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    storage, _, result = prepared
    for ref in result.snapshot_refs.values():
        envelope = storage.artifact_store.get_envelope(ref["artifact_id"])
        assert envelope["artifact_type"].endswith("Snapshot")
        assert envelope["origin_mode"] == "DERIVED"
        assert envelope["authority_mode"] == "CANONICAL_JSON"
        assert envelope["derivation_kind"] == "EXTRACTED_FROM_IMPORTED"
        assert envelope["derived_from_refs"]
        assert all(
            parent in result.source_refs.values()
            for parent in envelope["derived_from_refs"]
        )


def test_stage_runs_are_recoverable_and_bound_to_configuration(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    storage, _, result = prepared
    for key in result.stage_attempt_keys:
        assert key["stage_configuration_ref"] == result.configuration_ref
        stage = storage.run_store.get_stage(key)
        assert stage == result.stage_runs[key["stage_id"]]
        assert stage["execution_status"] == "SUCCEEDED"
        assert stage["output_artifact_refs"] == [result.snapshot_refs[key["stage_id"]]]
        assert len(stage["validation_report_refs"]) == 1
    assert storage.run_store.get_run("run-review") == result.run_record
    assert result.run_record["configuration_ref"] == result.configuration_ref
    assert result.run_record["configuration_ref"]["content_hash"] != "0" * 64


def test_decision_request_binds_exact_persisted_context(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    storage, _, result = prepared
    request = result.decision_request
    assert request["gate_id"] == "FIXTURE_IMPORT_REVIEW"
    assert request["context_stage_attempt_keys"] == result.stage_attempt_keys
    assert request["context_finding_refs"] == result.finding_refs
    assert len(request["context_artifact_refs"]) == 106
    assert {ref["artifact_id"] for ref in request["context_artifact_refs"]} == {
        result.configuration_artifact_ref["artifact_id"],
        *(ref["artifact_id"] for ref in result.source_refs.values()),
        *(ref["artifact_id"] for ref in result.snapshot_refs.values()),
        *(ref["artifact_id"] for ref in result.validation_artifact_refs.values()),
        *(ref["artifact_id"] for ref in result.finding_artifact_refs.values()),
    }
    assert storage.artifact_store.get_envelope(
        result.decision_request_artifact_ref["artifact_id"]
    )["artifact_type"] == "DecisionRequest"


def test_same_run_retry_is_idempotent(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    _, service, first = prepared
    second = service.prepare_fixture_review()
    assert second.configuration_ref == first.configuration_ref
    assert second.source_refs == first.source_refs
    assert second.snapshot_refs == first.snapshot_refs
    assert second.finding_refs == first.finding_refs
    assert second.stage_runs == first.stage_runs
    assert second.decision_request == first.decision_request
    assert second.run_record == first.run_record


def test_report_join_persists_real_summary_and_manifest(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    storage, service, result = prepared
    report = service.build_report(
        result.snapshot_refs["S05_COUNTEREXAMPLE"],
        result.snapshot_refs["S06_MAGNETOGRAM_QA"],
        result.finding_refs,
        list(result.finding_artifact_refs.values()),
    )
    assert report.research_summary["scientific_verdict"] == "NOT_EVALUATED"
    assert report.research_summary["result_maturity"] == "DEVELOPMENTAL"
    assert report.research_summary["authorization_status"] == "NOT_AUTHORIZED"
    assert report.research_summary["release_scope"] == "NOT_READY"
    assert report.report_manifest["research_summary_ref"] == report.research_summary_ref
    assert report.report_manifest["s05_branch_ref"] == result.snapshot_refs[
        "S05_COUNTEREXAMPLE"
    ]
    assert report.report_manifest["s06_branch_ref"] == result.snapshot_refs[
        "S06_MAGNETOGRAM_QA"
    ]
    storage.artifact_store.verify_ref(report.research_summary_ref)
    storage.artifact_store.verify_ref(report.report_manifest_ref)
    assert storage.artifact_store.get_envelope(
        report.research_summary_ref["artifact_id"]
    )["artifact_type"] == "ResearchSummary"
    assert storage.artifact_store.get_envelope(
        report.report_manifest_ref["artifact_id"]
    )["artifact_type"] == "ReportManifest"


@pytest.mark.parametrize(
    ("s05_stage", "s06_stage", "expected"),
    [
        ("S01_CANDIDATE", "S06_MAGNETOGRAM_QA", "CounterexampleSnapshot"),
        ("S05_COUNTEREXAMPLE", "S01_CANDIDATE", "MagnetogramQASnapshot"),
    ],
)
def test_report_join_rejects_wrong_branch_types(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
    s05_stage: str,
    s06_stage: str,
    expected: str,
) -> None:
    _, service, result = prepared
    with pytest.raises(LedgerIntegrityError, match=expected):
        service.build_report(
            result.snapshot_refs[s05_stage],
            result.snapshot_refs[s06_stage],
            result.finding_refs,
            list(result.finding_artifact_refs.values()),
        )


def test_report_join_rejects_mismatched_finding_artifacts(
    prepared: tuple[LocalStorage, ReplayService, ReplayPreparation],
) -> None:
    _, service, result = prepared
    with pytest.raises(LedgerIntegrityError, match="not a Finding Artifact"):
        service.build_report(
            result.snapshot_refs["S05_COUNTEREXAMPLE"],
            result.snapshot_refs["S06_MAGNETOGRAM_QA"],
            result.finding_refs,
            [
                *list(result.finding_artifact_refs.values())[:-1],
                result.snapshot_refs["S01_CANDIDATE"],
            ],
        )
