from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from ai_scientist_mvp.application.services import compute_authority_hash
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.skills.jwssd_evaluation import (
    JWSSD_LABELS,
    JWSSDValidationError,
    audit_four_modality_sample,
    audit_inference_source_isolation,
    audit_jwssd_archive,
    audit_split_leakage,
    build_magnetogram_qa_snapshot,
    compute_classification_metrics,
    create_visual_evidence_artifact,
    mine_confusion_cases,
    persist_magnetogram_qa_snapshot,
    persist_pilot_audit_artifact,
)
from infer_batch import select_pilot_samples


def _archive(tmp_path: Path, *, missing: str | None = None) -> Path:
    path = tmp_path / "jwssd.zip"
    root = "dataset/"
    rows: list[dict[str, str]] = []
    for index, label in enumerate(JWSSD_LABELS):
        fields = {
            "sample_id": f"sample-{index}",
            "mount_wilson_class": label,
            "harpnum": str(7200 + index),
            "t_rec_tai": f"2018010{index + 1}_000000_TAI",
            "selection_rank": str(index + 1),
        }
        for modality, suffix in (
            ("continuum_fits", ".continuum.fits"),
            ("continuum_png", ".continuum.png"),
            ("magnetogram_fits", ".magnetogram.fits"),
            ("magnetogram_png", ".magnetogram.png"),
        ):
            fields[modality] = f"01_五分类四模态/{label}/hmi.{index}{suffix}"
        rows.append(fields)
    manifest = io.StringIO(newline="")
    writer = csv.DictWriter(manifest, fieldnames=tuple(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(root + "样本清单.csv", manifest.getvalue())
        for row in rows:
            for modality in (
                "continuum_fits",
                "continuum_png",
                "magnetogram_fits",
                "magnetogram_png",
            ):
                member = root + row[modality]
                if member != missing:
                    archive.writestr(member, b"x")
    return path


def test_archive_manifest_is_label_and_modality_strict(tmp_path: Path) -> None:
    manifest = audit_jwssd_archive(_archive(tmp_path), expected_sample_count=5)

    assert manifest.sample_count == 5
    assert manifest.modality_file_count == 20
    assert dict(manifest.class_counts) == {label: 1 for label in JWSSD_LABELS}
    assert manifest.rows[0].path_for("magnetogram_png").endswith(".magnetogram.png")


def test_archive_missing_member_fails_closed(tmp_path: Path) -> None:
    missing = "dataset/01_五分类四模态/alpha/hmi.0.continuum.fits"
    with pytest.raises(JWSSDValidationError, match="missing"):
        audit_jwssd_archive(_archive(tmp_path, missing=missing))


def test_split_leakage_detects_harp_crossing_evaluation_boundary(tmp_path: Path) -> None:
    manifest = audit_jwssd_archive(_archive(tmp_path), expected_sample_count=5)
    rows = list(manifest.rows)
    rows[1] = replace(rows[1], harpnum=rows[0].harpnum)
    leaked_manifest = replace(manifest, rows=tuple(rows))
    assignments = {row.sample_id: "evaluation" for row in rows}
    assignments[rows[1].sample_id] = "train"

    leaked = audit_split_leakage(leaked_manifest, assignments)

    assert any(item.startswith("HARP_CROSS_SPLIT") for item in leaked)


def test_metrics_include_macro_micro_balanced_and_wilson_recall_ci() -> None:
    metrics = compute_classification_metrics(
        ["alpha", "alpha", "beta", "beta-delta"],
        ["alpha", "beta", "beta", "beta-delta"],
        labels=("alpha", "beta", "beta-delta"),
    )

    assert metrics.confusion_matrix == ((1, 1, 0), (0, 1, 0), (0, 0, 1))
    assert metrics.micro_f1 == metrics.accuracy == 0.75
    assert metrics.balanced_accuracy == pytest.approx((0.5 + 1 + 1) / 3)
    assert 0 <= metrics.class_metric("alpha").recall_ci95.lower <= 0.5
    assert metrics.class_metric("alpha").recall_ci95.upper <= 1


def test_metrics_reject_unknown_or_empty_labels() -> None:
    with pytest.raises(JWSSDValidationError):
        compute_classification_metrics([], [], labels=JWSSD_LABELS)
    with pytest.raises(JWSSDValidationError):
        compute_classification_metrics(["alpha"], ["unknown"], labels=JWSSD_LABELS)


def test_confusion_cases_mark_misclassification_and_require_complete_predictions(
    tmp_path: Path,
) -> None:
    manifest = audit_jwssd_archive(_archive(tmp_path), expected_sample_count=5)
    predictions = {row.sample_id: row.label for row in manifest.rows}
    predictions[manifest.rows[0].sample_id] = "beta"

    cases = mine_confusion_cases(manifest, predictions)

    assert len(cases) == 1
    assert cases[0].error_type == "MINORITY_FALSE_NEGATIVE"
    with pytest.raises(JWSSDValidationError, match="exactly"):
        mine_confusion_cases(manifest, {})


def test_four_modality_qa_checks_real_sample(tmp_path: Path) -> None:
    del tmp_path
    archive = Path("../SHRGT45_官方五分类四模态扩展样本_20260826.zip")
    checks = audit_four_modality_sample(
        archive,
        "JWSSD_alpha_HARP7211_20171228_000000_TAI",
        expected_sha256="db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    )
    assert len(checks) == 4
    assert all(check.status == "PASS" for check in checks)


def test_visual_evidence_snapshot_is_label_blind_and_persisted_with_four_parents(
    tmp_path: Path,
) -> None:
    archive = Path(__file__).resolve().parents[3] / "SHRGT45_官方五分类四模态扩展样本_20260826.zip"
    sample_id = "JWSSD_alpha_HARP7211_20171228_000000_TAI"
    snapshot = build_magnetogram_qa_snapshot(
        archive,
        sample_id,
        expected_sha256="db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    )
    assert snapshot["qa_verdict"] == "PASS"
    assert any(item.startswith("archive_sha256=") for item in snapshot["file_checks"])
    assert all("label" not in item.casefold() for item in snapshot["provenance_checks"])

    storage = LocalStorage(tmp_path, "qa-artifact-run")
    parents = []
    for index in range(4):
        content = f"source-{index}".encode()
        artifact_id = f"source-modality-{index}"
        content_hash = compute_authority_hash("SOURCE_BYTES", content)
        parents.append(
            storage.artifact_store.put(
                {
                    "artifact_id": artifact_id,
                    "logical_artifact_id": artifact_id,
                    "artifact_type": "SourceDocument",
                    "schema_version": "0.1.0",
                    "artifact_revision": 1,
                    "task_id": "qa-task",
                    "run_id": "qa-artifact-run",
                    "run_mode": "REPLAY",
                    "origin_mode": "IMPORTED",
                    "authority_mode": "SOURCE_BYTES",
                    "content_ref": f"artifact-content://{content_hash}",
                    "content_sha256": content_hash,
                    "producer": {"id": "test", "version": "0.1.0"},
                    "created_at": "2026-08-26T00:00:00Z",
                },
                content,
                "SOURCE_BYTES",
            )
        )
    ref = persist_magnetogram_qa_snapshot(
        storage.artifact_store,
        snapshot,
        task_id="qa-task",
        run_id="qa-artifact-run",
        parent_refs=parents,
        created_at="2026-08-26T00:00:00Z",
    )
    envelope = storage.artifact_store.get_envelope(ref["artifact_id"])
    assert envelope["artifact_type"] == "MagnetogramQASnapshot"
    assert envelope["parent_refs"] == parents
    storage.artifact_store.verify_ref(ref)
    storage.close()


def test_visual_evidence_entrypoint_imports_source_bytes_and_is_idempotent(tmp_path: Path) -> None:
    archive = Path(__file__).resolve().parents[3] / "SHRGT45_官方五分类四模态扩展样本_20260826.zip"
    storage = LocalStorage(tmp_path, "qa-entrypoint-run")
    kwargs = {
        "task_id": "qa-task",
        "run_id": "qa-entrypoint-run",
        "created_at": "2026-08-26T00:00:00Z",
        "expected_sha256": "db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    }
    ref = create_visual_evidence_artifact(
        storage.artifact_store,
        archive,
        "JWSSD_alpha_HARP7211_20171228_000000_TAI",
        **kwargs,
    )
    retry = create_visual_evidence_artifact(
        storage.artifact_store,
        archive,
        "JWSSD_alpha_HARP7211_20171228_000000_TAI",
        **kwargs,
    )
    assert retry == ref
    assert len(storage.ledger.read("artifact_envelope")) == 5
    storage.artifact_store.verify_ref(ref)
    storage.close()


def test_pilot_audit_artifact_binds_prediction_and_qa_chain(tmp_path: Path) -> None:
    archive = Path(__file__).resolve().parents[3] / "SHRGT45_官方五分类四模态扩展样本_20260826.zip"
    storage = LocalStorage(tmp_path, "pilot-audit-run")
    qa_ref = create_visual_evidence_artifact(
        storage.artifact_store,
        archive,
        "JWSSD_alpha_HARP7211_20171228_000000_TAI",
        task_id="pilot-task",
        run_id="pilot-audit-run",
        created_at="2026-08-26T00:00:00Z",
        expected_sha256="db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    )
    prediction_path = tmp_path / "pilot.csv"
    prediction_path.write_text(
        "sample_id,pred_label\n"
        "JWSSD_alpha_HARP7211_20171228_000000_TAI,alpha\n"
        "JWSSD_alpha_HARP7227_20180110_000000_TAI,alpha\n",
        encoding="utf-8",
    )
    report = {
        "archive_sha256": "db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
        "sample_count": 2,
        "accuracy": 1.0,
    }
    ref = persist_pilot_audit_artifact(
        storage.artifact_store,
        archive,
        prediction_path,
        report,
        qa_artifact_ref=qa_ref,
        task_id="pilot-task",
        run_id="pilot-audit-run",
        created_at="2026-08-26T00:00:00Z",
        expected_sha256="db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    )
    envelope = storage.artifact_store.get_envelope(ref["artifact_id"])
    assert envelope["artifact_type"] == "JWSSDPilotAudit"
    assert envelope["parent_refs"][0] == qa_ref
    assert len(envelope["parent_refs"]) == 2
    storage.artifact_store.verify_ref(ref)
    storage.close()


def test_pilot_selection_is_bounded_and_label_blind(tmp_path: Path) -> None:
    manifest = audit_jwssd_archive(_archive(tmp_path), expected_sample_count=5)
    samples = tuple(
        type("Sample", (), {"sample_id": row.sample_id})() for row in manifest.rows
    )

    assert [sample.sample_id for sample in select_pilot_samples(samples, limit=2)] == [
        "sample-0",
        "sample-1",
    ]
    with pytest.raises(ValueError, match="between 1 and 4"):
        select_pilot_samples(samples, limit=5)


def test_inference_entrypoint_is_label_blind_and_path_independent() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "infer_batch.py"
    assert audit_inference_source_isolation(source) == (
        "label_schema_not_referenced",
        "machine_paths_not_referenced",
        "archive_sha256_pinned",
        "label_blind_loader_used",
    )
