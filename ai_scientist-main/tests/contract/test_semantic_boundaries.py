"""Cross-schema semantic boundaries frozen by the contract.

These assert the science/governance ceilings that the schemas cannot fully
encode on their own: version identity, release-disposition authority, the
S05/S06 join, hash-bound decision validity, and orthogonal state separation.
"""
from __future__ import annotations

from conftest import make_validator
from fixtures_data import VALID

from ai_scientist_mvp.domain import canonical_json


def test_v22_not_silently_v23() -> None:
    assert canonical_json.content_hash({"source_version": "V2.2"}) != (
        canonical_json.content_hash({"source_version": "V2.3"})
    ), "V2.2 and V2.3 are distinct identities; relabeling changes content identity"


def test_project_review_ack_is_not_release_disposition(schemas: dict, registry) -> None:
    ack_schema = schemas["project-review-ack"]
    assert "release_scope" not in ack_schema["properties"], (
        "FINAL_REPLAY_REVIEW must not carry release scope"
    )
    disposition_validator = make_validator(schemas["release-disposition"], registry)
    assert list(disposition_validator.iter_errors(VALID["project-review-ack"])), (
        "a project-review ack must not validate as a ReleaseDisposition"
    )
    assert "release_scope" in schemas["release-disposition"]["properties"]


def test_report_manifest_requires_both_s05_and_s06(schemas: dict, registry) -> None:
    manifest_schema = schemas["report-manifest"]
    assert "s05_branch_ref" in manifest_schema["required"]
    assert "s06_branch_ref" in manifest_schema["required"]
    validator = make_validator(manifest_schema, registry)
    for dropped in ("s05_branch_ref", "s06_branch_ref"):
        instance = {k: v for k, v in VALID["report-manifest"].items() if k != dropped}
        assert list(validator.iter_errors(instance)), f"missing {dropped} must fail"


def test_old_disposition_does_not_apply_after_finding_hash_change() -> None:
    finding = dict(VALID["compatibility-finding"])
    old_hash = canonical_json.content_hash_excluding(finding)
    finding["summary"] = "a materially different summary"
    new_hash = canonical_json.content_hash_excluding(finding)
    assert old_hash != new_hash
    disposition = dict(VALID["finding-disposition"])
    disposition["finding_ref"] = {
        "finding_id": "find-1",
        "content_hash": old_hash,
        "schema_version": "0.1.0",
    }
    assert disposition["finding_ref"]["content_hash"] != new_hash, (
        "a disposition bound to the old hash must not silently apply to the new finding"
    )


def test_mvp_orthogonal_states_kept_separate(schemas: dict, registry) -> None:
    summary_schema = schemas["research-summary"]
    for field in ("scientific_verdict", "result_maturity", "authorization_status", "release_scope"):
        assert field in summary_schema["properties"], f"orthogonal state {field} missing"
    summary = VALID["research-summary"]
    assert summary["scientific_verdict"] == "NOT_EVALUATED"
    assert summary["result_maturity"] == "DEVELOPMENTAL"
    assert summary["authorization_status"] == "NOT_AUTHORIZED"
    assert summary["release_scope"] == "NOT_READY"
    assert not list(make_validator(summary_schema, registry).iter_errors(summary))


def test_structural_success_does_not_carry_scientific_conclusion(schemas: dict) -> None:
    assert "scientific_verdict" not in schemas["validation-report"]["properties"]
    assert "scientific_verdict" not in schemas["failure-record"]["properties"]
    assert "scientific_verdict" not in schemas["artifact-lifecycle-event"]["properties"]
