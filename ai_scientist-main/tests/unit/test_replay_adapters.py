"""Focused contract and failure tests for the T005 Replay adapters."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import HashMismatchError, LedgerIntegrityError
from ai_scientist_mvp.domain.store_types import StageAttemptKey
from ai_scientist_mvp.domain.types import ArtifactRef, SourceAssetRef
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.providers.replay_validation import (
    DeterministicValidator,
    DevelopmentalReportRenderer,
    FixtureImportDecisionRequestFactory,
    ReplayFindingFactory,
)
from ai_scientist_mvp.providers.shrgt45_replay import (
    ManifestAssetCatalog,
    ReplayArtifactImporter,
    ReplayCandidateProvider,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "shrgt45"


@pytest.fixture(scope="module")
def catalog() -> ManifestAssetCatalog:
    result = ManifestAssetCatalog(FIXTURES)
    result.load()
    return result


def _fake_stage_refs() -> dict[str, ArtifactRef]:
    return {
        stage: {
            "artifact_id": f"artifact-{index}",
            "content_sha256": f"{index:064x}",
            "schema_version": "0.1.0",
        }
        for index, stage in enumerate(
            (
                "S01_CANDIDATE",
                "S02_MECHANISM",
                "S03_HYPOTHESIS",
                "S04_DATA_AND_VERIFICATION",
                "S05_COUNTEREXAMPLE",
                "S06_MAGNETOGRAM_QA",
            ),
            start=1,
        )
    }


def test_candidate_is_explicitly_expert_seed(catalog: ManifestAssetCatalog) -> None:
    snapshot = ReplayCandidateProvider(catalog).candidate_snapshot()
    assert snapshot["selection_method"] == "EXPERT_SEED"
    assert snapshot["ranking_status"] == "NOT_IMPLEMENTED"
    assert snapshot["parameter"] == "SHRGT45"
    assert canonical_json.content_hash_excluding(snapshot) == snapshot["content_hash"]


def test_derived_summary_has_imported_authority_parents(
    tmp_path: Path, catalog: ManifestAssetCatalog
) -> None:
    storage = LocalStorage(tmp_path, "derived-test")
    importer = ReplayArtifactImporter(
        storage.artifact_store, catalog, "derived-test", "task-5"
    )
    assets = catalog.stage_assets("S01_CANDIDATE")
    parents = [importer.import_source(asset["asset_id"]) for asset in assets]
    payload = cast(
        dict[str, Any], ReplayCandidateProvider(catalog).candidate_snapshot()
    )
    ref = importer.import_summary(
        "CandidateSnapshot",
        "candidate-snapshot",
        payload,
        [
            {
                "id": asset["asset_id"],
                "schema_version": asset["schema_version"],
                "content_hash": asset["content_hash"],
            }
            for asset in assets
        ],
        parents,
    )
    envelope = storage.artifact_store.get_envelope(ref["artifact_id"])
    assert envelope["origin_mode"] == "DERIVED"
    assert envelope["authority_mode"] == "CANONICAL_JSON"
    assert envelope["derivation_kind"] == "EXTRACTED_FROM_IMPORTED"
    assert envelope["derived_from_refs"] == parents
    assert envelope["parent_refs"] == parents
    storage.close()


def test_validator_rejects_stale_ref_and_classifies_warning(
    tmp_path: Path, catalog: ManifestAssetCatalog
) -> None:
    storage = LocalStorage(tmp_path, "validator-test")
    importer = ReplayArtifactImporter(
        storage.artifact_store, catalog, "validator-test", "task-5"
    )
    ref = importer.import_source(catalog.stage_assets("S01_CANDIDATE")[0]["asset_id"])
    validator = DeterministicValidator(storage.artifact_store, catalog.contracts)
    report = validator.validate(
        ref,
        [{"code": "KNOWN_LIMITATION", "severity": "WARNING", "message": "limited"}],
    )
    assert report["validation_status"] == "PASS_WITH_WARNINGS"
    stale = cast(ArtifactRef, {**ref, "content_sha256": "0" * 64})
    with pytest.raises(HashMismatchError):
        validator.validate(stale, [])
    storage.close()


def test_findings_come_from_frozen_case_and_audit(
    catalog: ManifestAssetCatalog,
) -> None:
    factory = ReplayFindingFactory(catalog)
    acceptable = factory.build_acceptable_findings(_fake_stage_refs())
    informational = factory.build_informational_gaps()
    assert len(acceptable) == 10
    assert len(informational) == 2
    assert {finding["code"] for finding in acceptable} == {
        spec["code"] for spec in catalog.case_manifest["declared_finding_specs"]
    }
    by_code = {finding["code"]: finding for finding in acceptable}
    for spec in catalog.case_manifest["declared_finding_specs"]:
        assert by_code[spec["code"]].get("evidence_refs", []) == spec.get(
            "rationale_source_refs", []
        )
    for finding in [*acceptable, *informational]:
        assert finding["initial_status"] == "OPEN"
        assert canonical_json.content_hash_excluding(finding) == finding["content_hash"]


def test_decision_request_rejects_empty_or_malformed_stage_context(
    tmp_path: Path, catalog: ManifestAssetCatalog
) -> None:
    storage = LocalStorage(tmp_path, "decision-test")
    importer = ReplayArtifactImporter(
        storage.artifact_store, catalog, "decision-test", "task-5"
    )
    artifact = importer.import_source(
        catalog.stage_assets("S01_CANDIDATE")[0]["asset_id"]
    )
    finding = ReplayFindingFactory(catalog).build_informational_gaps()[0]
    factory = FixtureImportDecisionRequestFactory(
        storage.artifact_store, catalog.contracts
    )
    with pytest.raises(LedgerIntegrityError, match="requires bound"):
        factory.build([artifact], [finding], [])
    malformed = cast(
        StageAttemptKey,
        {"run_id": "decision-test", "stage_id": "S01_CANDIDATE", "attempt": 1},
    )
    with pytest.raises(LedgerIntegrityError, match="malformed StageAttemptKey"):
        factory.build([artifact], [finding], [malformed])
    config_a = {"id": "config-a", "schema_version": "0.1.0", "content_hash": "1" * 64}
    config_b = {"id": "config-b", "schema_version": "0.1.0", "content_hash": "2" * 64}
    mixed: list[StageAttemptKey] = [
        {
            "run_id": "decision-test",
            "stage_id": "S01_CANDIDATE",
            "attempt": 1,
            "stage_configuration_ref": config_a,
        },
        {
            "run_id": "decision-test",
            "stage_id": "S02_MECHANISM",
            "attempt": 1,
            "stage_configuration_ref": config_b,
        },
    ]
    with pytest.raises(LedgerIntegrityError, match="different Run configurations"):
        factory.build([artifact], [finding], mixed)
    storage.close()


def test_report_renderer_preserves_four_frozen_states(
    catalog: ManifestAssetCatalog,
) -> None:
    summary = DevelopmentalReportRenderer(catalog.contracts).research_summary([])
    assert summary["scientific_verdict"] == "NOT_EVALUATED"
    assert summary["result_maturity"] == "DEVELOPMENTAL"
    assert summary["authorization_status"] == "NOT_AUTHORIZED"
    assert summary["release_scope"] == "NOT_READY"


def test_rehashed_0808_in_s04_fails_semantic_preflight(
    catalog: ManifestAssetCatalog,
) -> None:
    case = deepcopy(catalog.case_manifest)
    case["stage_asset_refs"]["S04_DATA_AND_VERIFICATION"][0] = deepcopy(
        catalog._packages["0808"]["member_asset_refs"][0]
    )
    case["content_hash"] = canonical_json.content_hash_excluding(case)
    objects: dict[str, dict[str, Any]] = {
        key: cast(dict[str, Any], value) for key, value in catalog._assets.items()
    }
    objects.update(
        {package["package_id"]: package for package in catalog._packages.values()}
    )
    with pytest.raises(LedgerIntegrityError, match="default S04"):
        catalog._verify_manifest_references(
            catalog.manifest,
            case,
            catalog.import_audit,
            objects,
            catalog._packages,
            catalog._assets,
        )


def test_rehashed_package_cannot_shrink_frozen_member_set(
    catalog: ManifestAssetCatalog,
) -> None:
    package = deepcopy(catalog._packages["0814"])
    package["member_asset_refs"] = package["member_asset_refs"][:-1]
    package["member_count"] = 42
    package["content_hash"] = canonical_json.content_hash_excluding(package)
    with pytest.raises(LedgerIntegrityError, match="frozen member count"):
        catalog._verify_package("0814", package, catalog._assets)


def test_path_escape_and_stale_versioned_ref_fail_closed(
    catalog: ManifestAssetCatalog,
) -> None:
    with pytest.raises(LedgerIntegrityError, match="repository-relative"):
        catalog._safe_path("../outside-fixture")
    asset = catalog.stage_assets("S01_CANDIDATE")[0]
    stale = {
        "id": asset["asset_id"],
        "schema_version": "9.9.9",
        "content_hash": asset["content_hash"],
    }
    with pytest.raises(LedgerIntegrityError, match="stale schema_version"):
        catalog.resolve_ref(stale)
    mutated = cast(SourceAssetRef, deepcopy(asset))
    mutated["repository_relative_path"] = "../outside-fixture"
    with pytest.raises(LedgerIntegrityError, match="unregistered SourceAssetRef"):
        catalog.read_bytes(mutated)
