from pathlib import Path

import pytest

from ai_scientist_mvp.quality import audit_reproducibility_manifest, build_quality_gate_report


def test_quality_report_distinguishes_pass_fail_and_not_evaluable() -> None:
    report = build_quality_gate_report(
        schema_valid=2,
        schema_total=2,
        citations_verified=1,
        citations_total=2,
        hypotheses_operational=0,
        hypotheses_total=0,
        recomputations_matching=3,
        recomputations_total=3,
    )
    assert report.schema_validity.status == "PASS"
    assert report.citation_accuracy.status == "FAIL"
    assert report.hypothesis_operationalization.status == "NOT_EVALUABLE"
    assert len(report.content_hash) == 64


def test_quality_report_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError):
        build_quality_gate_report(
            schema_valid=2,
            schema_total=1,
            citations_verified=0,
            citations_total=0,
            hypotheses_operational=0,
            hypotheses_total=0,
            recomputations_matching=0,
            recomputations_total=0,
        )


def test_reproducibility_manifest_is_path_relative_and_hashed(tmp_path: Path) -> None:
    item = tmp_path / "config.toml"
    item.write_text("fixed=true\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    result = audit_reproducibility_manifest(tmp_path, {"config.toml": digest})
    assert result[0].status == "PASS"
    escaped = audit_reproducibility_manifest(tmp_path, {"../secret": digest})
    assert escaped[0].status == "FAIL"
