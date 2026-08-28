"""Independent JW-SSD evaluator: the only process that reads Mount Wilson labels."""
from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path

from ai_scientist_mvp.skills.jwssd_evaluation import (
    JWSSD_LABELS,
    JWSSDValidationError,
    audit_jwssd_archive,
    compute_classification_metrics,
)


def evaluate(
    archive_path: Path,
    predictions_path: Path,
    *,
    sample_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    manifest = audit_jwssd_archive(archive_path, expected_sample_count=195)
    predictions = _read_predictions(predictions_path)
    manifest_ids = {row.sample_id for row in manifest.rows}
    if sample_ids is not None:
        expected_ids = set(sample_ids)
    elif len(predictions) == manifest.sample_count:
        expected_ids = manifest_ids
    else:
        expected_ids = set(predictions)
    if not expected_ids.issubset(manifest_ids):
        raise JWSSDValidationError("prediction sample IDs are not in the frozen archive")
    actual_ids = set(predictions)
    if actual_ids != expected_ids:
        raise JWSSDValidationError(
            f"prediction sample IDs differ: missing={sorted(expected_ids - actual_ids)[:3]}, "
            f"extra={sorted(actual_ids - expected_ids)[:3]}"
        )
    labels_by_id = {row.sample_id: row.label for row in manifest.rows}
    ordered_ids = [row.sample_id for row in manifest.rows if row.sample_id in expected_ids]
    metrics = compute_classification_metrics(
        [labels_by_id[sample_id] for sample_id in ordered_ids],
        [predictions[sample_id] for sample_id in ordered_ids],
        labels=JWSSD_LABELS,
    )
    return {
        "archive_sha256": manifest.archive_sha256,
        "manifest_sha256": manifest.manifest_sha256,
        "sample_count": len(ordered_ids),
        "labels": list(metrics.labels),
        "confusion_matrix": [list(row) for row in metrics.confusion_matrix],
        "accuracy": metrics.accuracy,
        "macro_f1": metrics.macro_f1,
        "micro_f1": metrics.micro_f1,
        "balanced_accuracy": metrics.balanced_accuracy,
        "class_metrics": {
            label: {
                "support": class_metric.support,
                "predicted": class_metric.predicted,
                "true_positive": class_metric.true_positive,
                "precision": class_metric.precision,
                "recall": class_metric.recall,
                "f1": class_metric.f1,
                "recall_ci95": {
                    "estimate": class_metric.recall_ci95.estimate,
                    "lower": class_metric.recall_ci95.lower,
                    "upper": class_metric.recall_ci95.upper,
                },
            }
            for label, class_metric in metrics.class_metrics
        },
    }


def _read_predictions(path: Path) -> dict[str, str]:
    required = {"sample_id", "pred_label", *(f"prob_{label}" for label in JWSSD_LABELS)}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise JWSSDValidationError("prediction CSV is missing required columns")
        predictions: dict[str, str] = {}
        for record in reader:
            sample_id = (record.get("sample_id") or "").strip()
            pred_label = (record.get("pred_label") or "").strip()
            if not sample_id or sample_id in predictions or pred_label not in JWSSD_LABELS:
                raise JWSSDValidationError("invalid or duplicate prediction row")
            try:
                probabilities = [float(record[f"prob_{label}"] or "") for label in JWSSD_LABELS]
            except (KeyError, TypeError, ValueError) as exc:
                raise JWSSDValidationError("invalid prediction probability") from exc
            if any(value < 0 or value > 1 for value in probabilities) or abs(
                sum(probabilities) - 1
            ) > 1e-6:
                raise JWSSDValidationError(
                    "prediction probabilities must be in [0,1] and sum to one"
                )
            predictions[sample_id] = pred_label
    if not predictions:
        raise JWSSDValidationError("prediction CSV must contain rows")
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate JW-SSD Mount Wilson predictions")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-id", action="append", default=[], help="evaluate a pilot subset")
    args = parser.parse_args()
    report = evaluate(args.archive, args.predictions, sample_ids=args.sample_id or None)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote JW-SSD metrics to {args.out}")


if __name__ == "__main__":
    main()
