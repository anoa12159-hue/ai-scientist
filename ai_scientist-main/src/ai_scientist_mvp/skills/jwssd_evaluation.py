"""Read-only JW-SSD archive auditing and deterministic five-class metrics."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np
from astropy.io import fits

from ai_scientist_mvp.application.ports import ArtifactStore
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.types import ArtifactEnvelope, ArtifactRef, MagnetogramQASnapshot

JWSSD_LABELS: tuple[str, ...] = (
    "alpha",
    "beta",
    "beta-delta",
    "beta-gamma",
    "beta-gamma-delta",
)
JWSSD_MODALITIES: tuple[str, ...] = (
    "continuum_fits",
    "continuum_png",
    "magnetogram_fits",
    "magnetogram_png",
)
_REQUIRED_COLUMNS = (
    "sample_id",
    "mount_wilson_class",
    "harpnum",
    "t_rec_tai",
    "selection_rank",
    *JWSSD_MODALITIES,
)
_TIME_RE = re.compile(r"^\d{8}_\d{6}_TAI$")
_MODALITY_SUFFIXES = {
    "continuum_fits": ".continuum.fits",
    "continuum_png": ".continuum.png",
    "magnetogram_fits": ".magnetogram.fits",
    "magnetogram_png": ".magnetogram.png",
}


class JWSSDValidationError(ValueError):
    """The archive, manifest, prediction labels, or split assignment is invalid."""


@dataclass(frozen=True)
class UnlabeledJWSSDSample:
    sample_id: str
    harpnum: int
    t_rec_tai: str
    paths: tuple[tuple[str, str], ...]

    def path_for(self, modality: str) -> str:
        for name, path in self.paths:
            if name == modality:
                return path
        raise JWSSDValidationError(f"unknown modality: {modality}")


@dataclass(frozen=True)
class JWSSDManifestRow:
    sample_id: str
    label: str
    harpnum: int
    t_rec_tai: str
    selection_rank: int
    paths: tuple[tuple[str, str], ...]

    def path_for(self, modality: str) -> str:
        for name, path in self.paths:
            if name == modality:
                return path
        raise JWSSDValidationError(f"unknown modality: {modality}")


@dataclass(frozen=True)
class JWSSDArchiveManifest:
    archive_sha256: str
    manifest_sha256: str
    internal_root: str
    sample_count: int
    modality_file_count: int
    logical_member_count: int
    class_counts: tuple[tuple[str, int], ...]
    rows: tuple[JWSSDManifestRow, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "archive_sha256": self.archive_sha256,
            "manifest_sha256": self.manifest_sha256,
            "internal_root": self.internal_root,
            "sample_count": self.sample_count,
            "modality_file_count": self.modality_file_count,
            "logical_member_count": self.logical_member_count,
            "class_counts": dict(self.class_counts),
            "rows": [
                {
                    "sample_id": row.sample_id,
                    "label": row.label,
                    "harpnum": row.harpnum,
                    "t_rec_tai": row.t_rec_tai,
                    "selection_rank": row.selection_rank,
                    "paths": dict(row.paths),
                }
                for row in self.rows
            ],
        }


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float
    successes: int
    trials: int


@dataclass(frozen=True)
class ClassMetrics:
    support: int
    predicted: int
    true_positive: int
    precision: float
    recall: float
    f1: float
    recall_ci95: ConfidenceInterval


@dataclass(frozen=True)
class ClassificationMetrics:
    labels: tuple[str, ...]
    confusion_matrix: tuple[tuple[int, ...], ...]
    class_metrics: tuple[tuple[str, ClassMetrics], ...]
    accuracy: float
    macro_f1: float
    micro_f1: float
    balanced_accuracy: float

    def class_metric(self, label: str) -> ClassMetrics:
        for name, metrics in self.class_metrics:
            if name == label:
                return metrics
        raise JWSSDValidationError(f"unknown label: {label}")


@dataclass(frozen=True)
class ConfusionCase:
    sample_id: str
    true_label: str
    predicted_label: str
    error_type: str
    recommended_next_step: str


@dataclass(frozen=True)
class ModalityQACheck:
    modality: str
    status: str
    detail: str


@dataclass(frozen=True)
class PilotAuditRecord:
    """Recomputable pilot chain metadata; never a formal five-class result."""

    record_id: str
    archive_sha256: str
    prediction_sha256: str
    sample_ids: tuple[str, ...]
    metrics: Mapping[str, Any]
    confusion_cases: tuple[ConfusionCase, ...]
    qa_artifact_ref: ArtifactRef
    prediction_artifact_ref: ArtifactRef
    content_hash: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "record_id": self.record_id,
            "schema_version": "0.1.0",
            "archive_sha256": self.archive_sha256,
            "prediction_sha256": self.prediction_sha256,
            "sample_ids": list(self.sample_ids),
            "metrics": dict(self.metrics),
            "confusion_cases": [
                {
                    "sample_id": case.sample_id,
                    "true_label": case.true_label,
                    "predicted_label": case.predicted_label,
                    "error_type": case.error_type,
                    "recommended_next_step": case.recommended_next_step,
                }
                for case in self.confusion_cases
            ],
            "qa_artifact_ref": dict(self.qa_artifact_ref),
            "prediction_artifact_ref": dict(self.prediction_artifact_ref),
            "status_note": "Pilot only; not a formal full-dataset result.",
        }
        payload["content_hash"] = canonical_json.content_hash_excluding(payload)
        return payload


def audit_inference_source_isolation(source_path: Path) -> tuple[str, ...]:
    """Audit the inference entry point without importing or executing it."""
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise JWSSDValidationError("inference source must be readable UTF-8") from exc
    checks: list[str] = []
    forbidden_tokens = ("mount_wilson_class", "audit_jwssd_archive", "evaluate_jwssd")
    for token in forbidden_tokens:
        if token in source:
            raise JWSSDValidationError(
                f"inference source references forbidden evaluator token: {token}"
            )
    checks.append("label_schema_not_referenced")
    if re.search(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp)/)", source):
        raise JWSSDValidationError("inference source contains a machine-specific absolute path")
    checks.append("machine_paths_not_referenced")
    if "expected_sha256" not in source or "EXPECTED_ARCHIVE_SHA256" not in source:
        raise JWSSDValidationError("inference source does not pin the archive SHA256")
    checks.append("archive_sha256_pinned")
    if "load_unlabeled_jwssd_samples" not in source:
        raise JWSSDValidationError("inference source does not use the label-blind loader")
    checks.append("label_blind_loader_used")
    return tuple(checks)


def audit_four_modality_sample(
    archive_path: Path,
    sample_id: str,
    *,
    expected_sha256: str | None = None,
) -> tuple[ModalityQACheck, ...]:
    """Validate one sample's four files and basic FITS/PNG image integrity."""
    samples = load_unlabeled_jwssd_samples(archive_path, expected_sha256=expected_sha256)
    if len(samples) != 195:
        raise JWSSDValidationError(f"sample count mismatch: expected 195, got {len(samples)}")
    row = next((item for item in samples if item.sample_id == sample_id), None)
    if row is None:
        raise JWSSDValidationError("unknown sample_id")
    checks: list[ModalityQACheck] = []
    with _open_archive(archive_path.read_bytes()) as archive:
        png_shapes: list[tuple[int, int]] = []
        fits_shapes: list[tuple[int, int]] = []
        for modality in JWSSD_MODALITIES:
            source = archive.read(row.path_for(modality))
            if modality.endswith("_png"):
                width, height = _png_shape(source)
                png_shapes.append((height, width))
                checks.append(ModalityQACheck(modality, "PASS", f"shape={width}x{height}"))
            else:
                shape, finite_fraction = _fits_quality(source)
                fits_shapes.append(shape)
                status = "PASS" if finite_fraction == 1.0 else "FAIL"
                checks.append(
                    ModalityQACheck(
                        modality,
                        status,
                        f"shape={shape[1]}x{shape[0]}, finite_fraction={finite_fraction:.6f}",
                    )
                )
        if len(set(png_shapes)) != 1:
            checks.append(ModalityQACheck("paired_png", "FAIL", "PNG dimensions differ"))
        if len(set(fits_shapes)) != 1:
            checks.append(ModalityQACheck("paired_fits", "FAIL", "FITS dimensions differ"))
    return tuple(checks)


def build_magnetogram_qa_snapshot(
    archive_path: Path,
    sample_id: str,
    *,
    expected_sha256: str | None = None,
    source_refs: Sequence[ArtifactRef] = (),
) -> MagnetogramQASnapshot:
    """Build a contract-valid, label-blind QA snapshot for one four-file sample.

    ``source_refs`` are references to the four immutable source-byte Artifacts in
    modality order. They are recorded as provenance text because the frozen
    domain snapshot intentionally has no new fields; the ArtifactEnvelope keeps
    the same refs as parents for machine-readable lineage.
    """
    samples = load_unlabeled_jwssd_samples(archive_path, expected_sha256=expected_sha256)
    if len(samples) != 195:
        raise JWSSDValidationError(f"sample count mismatch: expected 195, got {len(samples)}")
    row = next((item for item in samples if item.sample_id == sample_id), None)
    if row is None:
        raise JWSSDValidationError("unknown sample_id")
    if source_refs and len(source_refs) != len(JWSSD_MODALITIES):
        raise JWSSDValidationError("source_refs must contain exactly four modality refs")
    checks = audit_four_modality_sample(
        archive_path, sample_id, expected_sha256=expected_sha256
    )
    archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    file_checks = [
        f"sample_id={sample_id}",
        f"archive_sha256={archive_sha256}",
        *[
            f"{check.modality}:{check.status}:{check.detail}"
            for check in checks
            if check.modality in JWSSD_MODALITIES
        ],
    ]
    frame_checks = [
        f"{check.modality}:{check.status}:{check.detail}"
        for check in checks
        if check.modality not in JWSSD_MODALITIES
    ]
    with _open_archive(archive_path.read_bytes()) as archive:
        provenance_checks = [
            f"{modality}:member={row.path_for(modality)}:sha256="
            f"{hashlib.sha256(archive.read(row.path_for(modality))).hexdigest()}"
            for modality in JWSSD_MODALITIES
        ]
    provenance_checks.extend(
        f"source_artifact_ref={ref['artifact_id']}:{ref['content_sha256']}"
        for ref in source_refs
    )
    statuses = [check.status for check in checks]
    verdict = "PASS" if statuses and all(status == "PASS" for status in statuses) else "FAIL"
    payload: dict[str, Any] = {
        "snapshot_id": f"magnetogram-qa-{sample_id}",
        "schema_version": "0.1.0",
        "file_checks": file_checks,
        "frame_checks": frame_checks,
        "provenance_checks": provenance_checks,
        "qa_verdict": verdict,
        "qa_scope_note": (
            "QA PASS 仅表示四模态文件、帧和来源检查通过；不等于机制证据、"
            "因果证据或预测能力。标签未被推理侧读取。"
        ),
    }
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return cast(MagnetogramQASnapshot, payload)


def persist_magnetogram_qa_snapshot(
    store: ArtifactStore,
    snapshot: MagnetogramQASnapshot,
    *,
    task_id: str,
    run_id: str,
    parent_refs: Sequence[ArtifactRef],
    created_at: str,
) -> ArtifactRef:
    """Persist a QA snapshot as an immutable native Artifact with four parents."""
    if len(parent_refs) != len(JWSSD_MODALITIES):
        raise JWSSDValidationError("exactly four modality parent ArtifactRefs are required")
    if snapshot["qa_verdict"] not in {"PASS", "FAIL"}:
        raise JWSSDValidationError("qa_verdict must be PASS or FAIL")
    from ai_scientist_mvp.application.services import compute_authority_hash

    artifact_id = (
        f"{run_id}-native-magnetogram-qa-"
        f"{hashlib.sha256(snapshot['snapshot_id'].encode('utf-8')).hexdigest()[:20]}"
    )
    envelope = {
        "artifact_id": artifact_id,
        "logical_artifact_id": snapshot["snapshot_id"],
        "artifact_type": "MagnetogramQASnapshot",
        "schema_version": snapshot["schema_version"],
        "artifact_revision": 1,
        "task_id": task_id,
        "run_id": run_id,
        "run_mode": "REPLAY",
        "origin_mode": "NATIVE",
        "authority_mode": "CANONICAL_JSON",
        "payload": dict(snapshot),
        "content_sha256": compute_authority_hash("CANONICAL_JSON", dict(snapshot)),
        "parent_refs": list(parent_refs),
        "producer": {"id": "jwssd-qa", "version": "0.1.0"},
        "created_at": created_at,
    }
    return store.put(cast(ArtifactEnvelope, envelope), dict(snapshot), "CANONICAL_JSON")


def create_visual_evidence_artifact(
    store: ArtifactStore,
    archive_path: Path,
    sample_id: str,
    *,
    task_id: str,
    run_id: str,
    created_at: str,
    expected_sha256: str | None = None,
) -> ArtifactRef:
    """Import four modality bytes and persist their immutable QA evidence.

    The manifest is consumed through the label-blind loader. Each source byte
    receives its own ``SourceDocument`` parent, so the resulting QA Artifact is
    independently verifiable and can be replayed without extracting the ZIP.
    """
    samples = load_unlabeled_jwssd_samples(archive_path, expected_sha256=expected_sha256)
    if len(samples) != 195:
        raise JWSSDValidationError(f"sample count mismatch: expected 195, got {len(samples)}")
    row = next((item for item in samples if item.sample_id == sample_id), None)
    if row is None:
        raise JWSSDValidationError("unknown sample_id")
    source_refs: list[ArtifactRef] = []
    with _open_archive(archive_path.read_bytes()) as archive:
        for modality in JWSSD_MODALITIES:
            content = archive.read(row.path_for(modality))
            digest = hashlib.sha256(content).hexdigest()
            member_key = hashlib.sha256(f"{sample_id}:{modality}".encode()).hexdigest()[:20]
            artifact_id = f"{run_id}-source-jwssd-{member_key}"
            source_refs.append(
                store.put(
                    cast(ArtifactEnvelope, {
                        "artifact_id": artifact_id,
                        "logical_artifact_id": f"{sample_id}:{modality}",
                        "artifact_type": "SourceDocument",
                        "schema_version": "0.1.0",
                        "artifact_revision": 1,
                        "task_id": task_id,
                        "run_id": run_id,
                        "run_mode": "REPLAY",
                        "origin_mode": "IMPORTED",
                        "authority_mode": "SOURCE_BYTES",
                        "content_ref": f"artifact-content://{digest}",
                        "content_sha256": digest,
                        "producer": {"id": "jwssd-qa", "version": "0.1.0"},
                        "created_at": created_at,
                    }),
                    content,
                    "SOURCE_BYTES",
                )
            )
    snapshot = build_magnetogram_qa_snapshot(
        archive_path,
        sample_id,
        expected_sha256=expected_sha256,
        source_refs=source_refs,
    )
    return persist_magnetogram_qa_snapshot(
        store,
        snapshot,
        task_id=task_id,
        run_id=run_id,
        parent_refs=source_refs,
        created_at=created_at,
    )


def build_pilot_audit_record(
    manifest: JWSSDArchiveManifest,
    predictions: Mapping[str, str],
    evaluation_report: Mapping[str, Any],
    *,
    qa_artifact_ref: ArtifactRef,
    prediction_artifact_ref: ArtifactRef,
    prediction_sha256: str,
) -> PilotAuditRecord:
    """Join independent evaluator output with QA and prediction provenance."""
    expected_archive = evaluation_report.get("archive_sha256")
    if not isinstance(expected_archive, str) or (
        expected_archive.casefold() != manifest.archive_sha256.casefold()
    ):
        raise JWSSDValidationError("evaluation report archive hash does not match frozen archive")
    sample_ids = tuple(sorted(predictions))
    manifest_ids = {row.sample_id for row in manifest.rows}
    if not sample_ids or not set(sample_ids).issubset(manifest_ids):
        raise JWSSDValidationError("pilot predictions contain unknown or no sample IDs")
    reported_count = evaluation_report.get("sample_count")
    if reported_count != len(sample_ids):
        raise JWSSDValidationError("evaluation report sample_count does not match predictions")
    subset_rows = tuple(row for row in manifest.rows if row.sample_id in predictions)
    subset_counts = Counter(row.label for row in subset_rows)
    subset_manifest = JWSSDArchiveManifest(
        archive_sha256=manifest.archive_sha256,
        manifest_sha256=manifest.manifest_sha256,
        internal_root=manifest.internal_root,
        sample_count=len(subset_rows),
        modality_file_count=len(subset_rows) * len(JWSSD_MODALITIES),
        logical_member_count=manifest.logical_member_count,
        class_counts=tuple(
            (label, subset_counts.get(label, 0)) for label in JWSSD_LABELS
        ),
        rows=subset_rows,
    )
    cases = mine_confusion_cases(subset_manifest, predictions)
    record_id = f"jwssd-pilot-audit-{prediction_sha256[:20]}"
    seed: dict[str, Any] = {
        "record_id": record_id,
        "schema_version": "0.1.0",
        "archive_sha256": manifest.archive_sha256,
        "prediction_sha256": prediction_sha256,
        "sample_ids": list(sample_ids),
        "metrics": dict(evaluation_report),
        "confusion_cases": [case.__dict__ for case in cases],
        "qa_artifact_ref": dict(qa_artifact_ref),
        "prediction_artifact_ref": dict(prediction_artifact_ref),
        "status_note": "Pilot only; not a formal full-dataset result.",
    }
    return PilotAuditRecord(
        record_id=record_id,
        archive_sha256=manifest.archive_sha256,
        prediction_sha256=prediction_sha256,
        sample_ids=sample_ids,
        metrics=dict(evaluation_report),
        confusion_cases=cases,
        qa_artifact_ref=qa_artifact_ref,
        prediction_artifact_ref=prediction_artifact_ref,
        content_hash=canonical_json.content_hash_excluding(seed),
    )


def persist_pilot_audit_artifact(
    store: ArtifactStore,
    archive_path: Path,
    predictions_path: Path,
    evaluation_report: Mapping[str, Any],
    *,
    qa_artifact_ref: ArtifactRef,
    task_id: str,
    run_id: str,
    created_at: str,
    expected_sha256: str | None = None,
) -> ArtifactRef:
    """Persist a pilot-only audit Artifact after independent evaluation."""
    manifest = audit_jwssd_archive(
        archive_path,
        expected_sha256=expected_sha256,
        expected_sample_count=195,
    )
    prediction_bytes = predictions_path.read_bytes()
    predictions = _read_prediction_labels(prediction_bytes)
    prediction_sha256 = hashlib.sha256(prediction_bytes).hexdigest()
    prediction_id = f"{run_id}-source-predictions-{prediction_sha256[:20]}"
    prediction_ref = store.put(
        cast(ArtifactEnvelope, {
            "artifact_id": prediction_id,
            "logical_artifact_id": f"jwssd-predictions-{prediction_sha256[:20]}",
            "artifact_type": "SourceDocument",
            "schema_version": "0.1.0",
            "artifact_revision": 1,
            "task_id": task_id,
            "run_id": run_id,
            "run_mode": "REPLAY",
            "origin_mode": "IMPORTED",
            "authority_mode": "SOURCE_BYTES",
            "content_ref": f"artifact-content://{prediction_sha256}",
            "content_sha256": prediction_sha256,
            "producer": {"id": "jwssd-qa", "version": "0.1.0"},
            "created_at": created_at,
        }),
        prediction_bytes,
        "SOURCE_BYTES",
    )
    record = build_pilot_audit_record(
        manifest,
        predictions,
        evaluation_report,
        qa_artifact_ref=qa_artifact_ref,
        prediction_artifact_ref=prediction_ref,
        prediction_sha256=prediction_sha256,
    )
    payload = record.to_payload()
    envelope = {
        "artifact_id": f"{run_id}-native-pilot-audit-{record.content_hash[:20]}",
        "logical_artifact_id": record.record_id,
        "artifact_type": "JWSSDPilotAudit",
        "schema_version": "0.1.0",
        "artifact_revision": 1,
        "task_id": task_id,
        "run_id": run_id,
        "run_mode": "REPLAY",
        "origin_mode": "NATIVE",
        "authority_mode": "CANONICAL_JSON",
        "payload": payload,
        "content_sha256": hashlib.sha256(canonical_json.canonicalize(payload)).hexdigest(),
        "parent_refs": [qa_artifact_ref, prediction_ref],
        "producer": {"id": "jwssd-qa", "version": "0.1.0"},
        "created_at": created_at,
    }
    return store.put(cast(ArtifactEnvelope, envelope), payload, "CANONICAL_JSON")


def _read_prediction_labels(source: bytes) -> dict[str, str]:
    try:
        rows = list(csv.DictReader(io.StringIO(source.decode("utf-8"), newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise JWSSDValidationError("prediction CSV must be valid UTF-8") from exc
    required = {"sample_id", "pred_label"}
    if not rows or not rows[0] or not required.issubset(rows[0]):
        raise JWSSDValidationError("prediction CSV is missing sample_id/pred_label")
    result: dict[str, str] = {}
    for row in rows:
        sample_id = (row.get("sample_id") or "").strip()
        label = (row.get("pred_label") or "").strip()
        if not sample_id or sample_id in result or label not in JWSSD_LABELS:
            raise JWSSDValidationError("prediction CSV contains invalid or duplicate labels")
        result[sample_id] = label
    return result


def mine_confusion_cases(
    manifest: JWSSDArchiveManifest,
    predictions: Mapping[str, str],
) -> tuple[ConfusionCase, ...]:
    """Create deterministic per-sample error and minority-class review cases."""
    labels_by_id = {row.sample_id: row.label for row in manifest.rows}
    if set(predictions) != set(labels_by_id):
        raise JWSSDValidationError("predictions must cover exactly the manifest sample IDs")
    minority_threshold = max(1, manifest.sample_count // (len(JWSSD_LABELS) * 2))
    cases: list[ConfusionCase] = []
    for sample_id in sorted(labels_by_id):
        true_label = labels_by_id[sample_id]
        predicted_label = predictions[sample_id]
        if predicted_label not in JWSSD_LABELS:
            raise JWSSDValidationError("unknown predicted class")
        if true_label == predicted_label:
            continue
        support = dict(manifest.class_counts).get(true_label, 0)
        error_type = (
            "MINORITY_FALSE_NEGATIVE" if support <= minority_threshold else "MISCLASSIFICATION"
        )
        cases.append(
            ConfusionCase(
                sample_id,
                true_label,
                predicted_label,
                error_type,
                "Review all four modalities and inspect class-boundary ambiguity",
            )
        )
    return tuple(cases)


def audit_jwssd_archive(
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
    expected_sample_count: int | None = None,
) -> JWSSDArchiveManifest:
    """Audit the frozen archive without extracting or executing any member."""
    archive_bytes = archive_path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if expected_sha256 is not None and archive_sha256.casefold() != expected_sha256.casefold():
        raise JWSSDValidationError(
            f"archive SHA256 mismatch: expected {expected_sha256}, got {archive_sha256}"
        )
    try:
        archive = _open_archive(archive_bytes)
    except (OSError, zipfile.BadZipFile) as exc:
        raise JWSSDValidationError("invalid ZIP archive") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise JWSSDValidationError("duplicate ZIP member names are not allowed")
        logical_names = [name for name in names if _is_logical_member(name)]
        manifest_name, manifest_bytes = _find_manifest_member(archive)
        internal_root = manifest_name[: -len("样本清单.csv")]
        rows = _parse_manifest(manifest_bytes, internal_root, set(names), archive)
        modality_names = {path for row in rows for _, path in row.paths}
        actual_modality_names = {
            name
            for name in names
            if name.startswith(internal_root + "01_五分类四模态/")
            and name.lower().endswith((".fits", ".png"))
        }
        if modality_names != actual_modality_names:
            missing = sorted(modality_names - actual_modality_names)
            extra = sorted(actual_modality_names - modality_names)
            raise JWSSDValidationError(
                "manifest modality members differ from archive: "
                f"missing={missing[:3]}, extra={extra[:3]}"
            )
        class_counts = Counter(row.label for row in rows)
        if expected_sample_count is not None and len(rows) != expected_sample_count:
            raise JWSSDValidationError(
                f"sample count mismatch: expected {expected_sample_count}, got {len(rows)}"
            )
        return JWSSDArchiveManifest(
            archive_sha256=archive_sha256,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            internal_root=internal_root,
            sample_count=len(rows),
            modality_file_count=len(modality_names),
            logical_member_count=len(logical_names),
            class_counts=tuple((label, class_counts.get(label, 0)) for label in JWSSD_LABELS),
            rows=tuple(rows),
        )


def audit_split_leakage(
    manifest: JWSSDArchiveManifest,
    split_by_sample: Mapping[str, str],
    *,
    evaluation_split: str = "evaluation",
) -> tuple[str, ...]:
    """Return deterministic leakage findings for sample and HARP group overlap."""
    known_ids = {row.sample_id for row in manifest.rows}
    findings = [
        f"UNKNOWN_SAMPLE:{sample_id}" for sample_id in sorted(set(split_by_sample) - known_ids)
    ]
    findings.extend(
        f"MISSING_SPLIT:{sample_id}" for sample_id in sorted(known_ids - set(split_by_sample))
    )
    harp_splits: dict[int, set[str]] = {}
    for row in manifest.rows:
        split = split_by_sample.get(row.sample_id)
        if split is not None:
            harp_splits.setdefault(row.harpnum, set()).add(split)
    for harpnum, splits in sorted(harp_splits.items()):
        if evaluation_split in splits and len(splits) > 1:
            findings.append(f"HARP_CROSS_SPLIT:{harpnum}:{','.join(sorted(splits))}")
    return tuple(findings)


def load_unlabeled_jwssd_samples(
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
) -> tuple[UnlabeledJWSSDSample, ...]:
    """Read only sample identities and modality paths for an inference process."""
    archive_bytes = archive_path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if expected_sha256 is not None and archive_sha256.casefold() != expected_sha256.casefold():
        raise JWSSDValidationError("archive SHA256 mismatch")
    with _open_archive(archive_bytes) as archive:
        names = set(archive.namelist())
        manifest_name, source = _find_manifest_member(archive)
        internal_root = (
            manifest_name[: -len("样本清单.csv")]
            if manifest_name.endswith("样本清单.csv")
            else ""
        )
        try:
            records = list(csv.DictReader(io.StringIO(source.decode("utf-8-sig"), newline="")))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise JWSSDValidationError("sample manifest must be valid UTF-8 CSV") from exc
        if not records:
            raise JWSSDValidationError("sample manifest must contain rows")
        required = {"sample_id", "harpnum", "t_rec_tai", *JWSSD_MODALITIES}
        if not required.issubset(records[0]):
            raise JWSSDValidationError("sample manifest is missing inference columns")
        samples: list[UnlabeledJWSSDSample] = []
        seen_ids: set[str] = set()
        for record in records:
            values = {
                key: (value or "").strip()
                for key, value in record.items()
                if key is not None
            }
            sample_id = values.get("sample_id", "")
            if not sample_id or sample_id in seen_ids:
                raise JWSSDValidationError("invalid or duplicate sample_id")
            try:
                harpnum = int(values["harpnum"])
            except (KeyError, ValueError) as exc:
                raise JWSSDValidationError("invalid HARP number") from exc
            if harpnum <= 0 or not _TIME_RE.fullmatch(values.get("t_rec_tai", "")):
                raise JWSSDValidationError("invalid sample identity")
            paths = []
            for modality in JWSSD_MODALITIES:
                path = _safe_member_path(values.get(modality, ""), internal_root, modality)
                info = archive.getinfo(path) if path in names else None
                if info is None or info.is_dir() or info.file_size == 0:
                    raise JWSSDValidationError("missing or empty modality member")
                paths.append((modality, path))
            seen_ids.add(sample_id)
            samples.append(
                UnlabeledJWSSDSample(sample_id, harpnum, values["t_rec_tai"], tuple(paths))
            )
        return tuple(samples)


def compute_classification_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    labels: Sequence[str] = JWSSD_LABELS,
) -> ClassificationMetrics:
    """Compute explicit-label metrics and Wilson 95% recall intervals."""
    metric_labels = tuple(labels)
    if not metric_labels or len(metric_labels) != len(set(metric_labels)):
        raise JWSSDValidationError("labels must be non-empty and unique")
    if len(y_true) != len(y_pred) or not y_true:
        raise JWSSDValidationError("true and predicted labels must have equal non-zero length")
    label_set = set(metric_labels)
    if any(label not in label_set for label in (*y_true, *y_pred)):
        raise JWSSDValidationError("unknown class label in predictions or ground truth")
    index = {label: position for position, label in enumerate(metric_labels)}
    matrix = [[0 for _ in metric_labels] for _ in metric_labels]
    for truth, prediction in zip(y_true, y_pred, strict=True):
        matrix[index[truth]][index[prediction]] += 1
    class_metrics: list[tuple[str, ClassMetrics]] = []
    f1_values: list[float] = []
    recalls: list[float] = []
    for position, label in enumerate(metric_labels):
        support = sum(matrix[position])
        predicted = sum(matrix[row][position] for row in range(len(metric_labels)))
        true_positive = matrix[position][position]
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        interval = _wilson_interval(true_positive, support)
        class_metrics.append(
            (
                label,
                ClassMetrics(
                    support, predicted, true_positive, precision, recall, f1, interval
                ),
            )
        )
        f1_values.append(f1)
        recalls.append(recall)
    correct = sum(matrix[position][position] for position in range(len(metric_labels)))
    accuracy = correct / len(y_true)
    macro_f1 = sum(f1_values) / len(f1_values)
    return ClassificationMetrics(
        labels=metric_labels,
        confusion_matrix=tuple(tuple(row) for row in matrix),
        class_metrics=tuple(class_metrics),
        accuracy=accuracy,
        macro_f1=macro_f1,
        micro_f1=accuracy,
        balanced_accuracy=sum(recalls) / len(recalls),
    )


def _parse_manifest(
    source: bytes,
    internal_root: str,
    names: set[str],
    archive: zipfile.ZipFile,
) -> list[JWSSDManifestRow]:
    try:
        text = source.decode("utf-8-sig")
        records = list(csv.DictReader(io.StringIO(text, newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise JWSSDValidationError("sample manifest must be valid UTF-8 CSV") from exc
    if not records:
        raise JWSSDValidationError("sample manifest must contain rows")
    fieldnames = tuple(records[0].keys())
    if any(name is None for name in fieldnames) or not set(_REQUIRED_COLUMNS).issubset(fieldnames):
        raise JWSSDValidationError("sample manifest is missing required columns")
    rows: list[JWSSDManifestRow] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for line_number, record in enumerate(records, start=2):
        values = {key: (value or "").strip() for key, value in record.items() if key is not None}
        sample_id = values.get("sample_id", "")
        label = values.get("mount_wilson_class", "")
        if not sample_id or sample_id in seen_ids:
            raise JWSSDValidationError(f"invalid or duplicate sample_id at row {line_number}")
        if label not in JWSSD_LABELS:
            raise JWSSDValidationError(f"unknown Mount Wilson class at row {line_number}")
        try:
            harpnum = int(values["harpnum"])
            selection_rank = int(values["selection_rank"])
        except (KeyError, ValueError) as exc:
            raise JWSSDValidationError(f"invalid integer field at row {line_number}") from exc
        if harpnum <= 0 or selection_rank <= 0 or not _TIME_RE.fullmatch(values["t_rec_tai"]):
            raise JWSSDValidationError(f"invalid identity field at row {line_number}")
        paths: list[tuple[str, str]] = []
        for modality in JWSSD_MODALITIES:
            raw_path = values.get(modality, "")
            path = _safe_member_path(raw_path, internal_root, modality)
            info = archive.getinfo(path) if path in names else None
            if info is None or path in seen_paths or info.is_dir():
                raise JWSSDValidationError(
                    f"missing or duplicate modality member at row {line_number}"
                )
            if info.file_size == 0:
                raise JWSSDValidationError(f"empty modality member at row {line_number}")
            seen_paths.add(path)
            paths.append((modality, path))
        seen_ids.add(sample_id)
        rows.append(
            JWSSDManifestRow(
                sample_id, label, harpnum, values["t_rec_tai"], selection_rank, tuple(paths)
            )
        )
    return rows


def _open_archive(source: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(source), metadata_encoding="utf-8")
    except TypeError:
        return zipfile.ZipFile(io.BytesIO(source))


def _find_manifest_member(archive: zipfile.ZipFile) -> tuple[str, bytes]:
    candidates: list[tuple[str, bytes]] = []
    for name in archive.namelist():
        if not _is_logical_member(name) or not name.lower().endswith(".csv"):
            continue
        source = archive.read(name)
        try:
            header = next(csv.reader(io.StringIO(source.decode("utf-8-sig"), newline="")))
        except (UnicodeDecodeError, csv.Error, StopIteration):
            continue
        if set(_REQUIRED_COLUMNS).issubset(header):
            candidates.append((name, source))
    if len(candidates) != 1:
        raise JWSSDValidationError("archive must contain exactly one sample manifest")
    return candidates[0]


def _png_shape(source: bytes) -> tuple[int, int]:
    if len(source) < 24 or source[:8] != b"\x89PNG\r\n\x1a\n" or source[12:16] != b"IHDR":
        raise JWSSDValidationError("invalid PNG signature or IHDR")
    width = int.from_bytes(source[16:20], "big")
    height = int.from_bytes(source[20:24], "big")
    if width <= 0 or height <= 0:
        raise JWSSDValidationError("PNG dimensions must be positive")
    return width, height


def _fits_quality(source: bytes) -> tuple[tuple[int, int], float]:
    try:
        with fits.open(io.BytesIO(source), memmap=False) as hdul:
            image = next(
                (hdu.data for hdu in hdul if getattr(hdu, "data", None) is not None),
                None,
            )
            if image is None or image.ndim != 2:
                raise JWSSDValidationError("FITS contains no two-dimensional image")
            values = np.asarray(image, dtype="float64")
            finite_fraction = float(np.isfinite(values).sum() / values.size)
            return (int(values.shape[0]), int(values.shape[1])), finite_fraction
    except (OSError, ValueError) as error:
        raise JWSSDValidationError("invalid FITS image") from error


def _safe_member_path(raw_path: str, internal_root: str, modality: str) -> str:
    if not raw_path or "\\" in raw_path:
        raise JWSSDValidationError(f"invalid path for {modality}")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise JWSSDValidationError(f"unsafe path for {modality}")
    full = internal_root + raw_path
    if not full.startswith(internal_root + "01_五分类四模态/"):
        raise JWSSDValidationError(f"modality path outside data directory for {modality}")
    if not raw_path.endswith(_MODALITY_SUFFIXES[modality]):
        raise JWSSDValidationError(f"wrong file suffix for {modality}")
    return full


def _is_logical_member(name: str) -> bool:
    return bool(
        name
        and not name.endswith("/")
        and "__MACOSX/" not in name
        and ".DS_Store" not in name
    )


def _wilson_interval(
    successes: int, trials: int, z: float = 1.959963984540054
) -> ConfidenceInterval:
    if trials < 0 or successes < 0 or successes > trials:
        raise JWSSDValidationError("invalid binomial counts")
    if trials == 0:
        return ConfidenceInterval(0.0, 0.0, 0.0, successes, trials)
    estimate = successes / trials
    denominator = 1 + z * z / trials
    centre = (estimate + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(
        estimate * (1 - estimate) / trials + z * z / (4 * trials * trials)
    ) / denominator
    return ConfidenceInterval(
        estimate,
        max(0.0, centre - margin),
        min(1.0, centre + margin),
        successes,
        trials,
    )
