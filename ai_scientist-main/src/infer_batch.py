"""Label-blind JW-SSD batch inference entry point."""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import zipfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from astropy.io import fits

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    QwenChatModel,
    QwenRuntimeConfig,
    ResilientChatModel,
)
from ai_scientist_mvp.skills.jwssd_evaluation import (
    JWSSD_LABELS,
    UnlabeledJWSSDSample,
    load_unlabeled_jwssd_samples,
)

EXPECTED_ARCHIVE_SHA256 = "db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4"


def uniform_predictor(
    samples: Sequence[UnlabeledJWSSDSample],
) -> list[tuple[str, tuple[float, ...]]]:
    """Return an explicit smoke baseline until a trained predictor is registered."""
    probabilities = tuple(1.0 / len(JWSSD_LABELS) for _ in JWSSD_LABELS)
    return [(sample.sample_id, probabilities) for sample in samples]


_QWEN_PROMPT = """Classify the solar active-region observation into exactly one Mount Wilson class.
Use only the supplied continuum and magnetogram visuals plus the FITS numeric summaries.
Return JSON only with this shape:
{"label":"alpha|beta|beta-delta|beta-gamma|beta-gamma-delta",
 "probabilities":{"alpha":0.0,"beta":0.0,"beta-delta":0.0,
 "beta-gamma":0.0,"beta-gamma-delta":0.0}}
Probabilities must be finite, non-negative, and sum to 1. Do not infer flare labels or M1+ events.
"""


def qwen_predictor(
    archive_path: Path,
    samples: Sequence[UnlabeledJWSSDSample],
    *,
    config_path: Path,
    env_file: Path | None = None,
) -> list[tuple[str, tuple[float, ...]]]:
    runtime = QwenRuntimeConfig.from_toml(config_path)
    environment = dict(os.environ)
    if env_file is not None:
        environment.update(_read_env_file(env_file))
    model = ResilientChatModel(
        QwenChatModel(runtime.model, environ=environment),
        policy=runtime.retry,
    )
    archive_bytes = archive_path.read_bytes()
    predictions: list[tuple[str, tuple[float, ...]]] = []
    with zipfile.ZipFile(io.BytesIO(archive_bytes), metadata_encoding="utf-8") as archive:
        for sample in samples:
            parts: list[dict[str, object]] = [{"type": "text", "text": _QWEN_PROMPT}]
            fits_summaries: list[str] = []
            for modality in ("continuum_png", "magnetogram_png"):
                encoded = base64.b64encode(archive.read(sample.path_for(modality))).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    }
                )
            for modality in ("continuum_fits", "magnetogram_fits"):
                fits_summaries.append(
                    f"{modality}: {_summarize_fits(archive.read(sample.path_for(modality)))}"
                )
            parts.append({"type": "text", "text": "\n".join(fits_summaries)})
            response = model.invoke(
                [ChatMessage("user", parts)],
                response_format={"type": "json_object"},
            )
            predictions.append((sample.sample_id, _parse_qwen_prediction(response.message.content)))
    return predictions


def write_predictions(
    output_path: Path,
    predictions: Sequence[tuple[str, Sequence[float]]],
) -> None:
    header = ["sample_id", "pred_label", *(f"prob_{label}" for label in JWSSD_LABELS)]
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for sample_id, raw_probabilities in predictions:
            probabilities = tuple(float(value) for value in raw_probabilities)
            if len(probabilities) != len(JWSSD_LABELS) or any(
                value < 0 or value > 1 for value in probabilities
            ):
                raise ValueError(f"invalid probability vector for {sample_id}")
            total = sum(probabilities)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"probabilities must sum to one for {sample_id}")
            winner = JWSSD_LABELS[max(range(len(probabilities)), key=probabilities.__getitem__)]
            writer.writerow([sample_id, winner, *[f"{value:.10f}" for value in probabilities]])


def run(archive_path: Path, output_path: Path) -> int:
    samples = load_unlabeled_jwssd_samples(
        archive_path,
        expected_sha256=EXPECTED_ARCHIVE_SHA256,
    )
    write_predictions(output_path, uniform_predictor(samples))
    return len(samples)


def select_pilot_samples(
    samples: Sequence[UnlabeledJWSSDSample],
    *,
    limit: int | None = None,
    sample_ids: Sequence[str] = (),
) -> tuple[UnlabeledJWSSDSample, ...]:
    """Select at most four label-blind samples for an agent pilot run."""
    if limit is not None and not 1 <= limit <= 4:
        raise ValueError("pilot limit must be between 1 and 4")
    if sample_ids and limit is not None:
        raise ValueError("use either pilot limit or explicit sample IDs")
    if sample_ids:
        requested = set(sample_ids)
        selected = tuple(sample for sample in samples if sample.sample_id in requested)
        if len(selected) != len(requested) or len(selected) > 4:
            raise ValueError("pilot sample IDs must identify between 1 and 4 known samples")
        return selected
    return tuple(samples[: limit or 4])


def _parse_qwen_prediction(content: object) -> tuple[float, ...]:
    if not isinstance(content, str):
        raise ValueError("Qwen response content must be JSON text")
    try:
        document = json.loads(content)
        probabilities_payload = document["probabilities"]
        label = document["label"]
        probabilities = tuple(float(probabilities_payload[name]) for name in JWSSD_LABELS)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Qwen response does not match the classification contract") from error
    if label not in JWSSD_LABELS or any(value < 0 or value > 1 for value in probabilities):
        raise ValueError("Qwen response contains an invalid class or probability")
    total = sum(probabilities)
    if total <= 0 or abs(total - 1.0) > 0.05:
        raise ValueError("Qwen probabilities must sum to one")
    return tuple(value / total for value in probabilities)


def _summarize_fits(source: bytes) -> str:
    with fits.open(io.BytesIO(source), memmap=False) as hdul:
        image = next((hdu.data for hdu in hdul if getattr(hdu, "data", None) is not None), None)
        if image is None:
            raise ValueError("FITS contains no image data")
        values = image.astype("float64", copy=False)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            raise ValueError("FITS image contains no finite values")
        return json.dumps(
            {
                "shape": list(values.shape),
                "finite_fraction": float(finite.size / values.size),
                "min": float(finite.min()),
                "max": float(finite.max()),
                "mean": float(finite.mean()),
            },
            separators=(",", ":"),
        )


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if separator != "=" or not name.isidentifier():
            raise ValueError(f"invalid env assignment at line {line_number}")
        values[name] = value.strip().strip("\"'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Run label-blind JW-SSD batch inference")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("qwen", "uniform"), default="qwen")
    parser.add_argument("--limit", type=int, help="pilot mode: process 1 to 4 samples")
    parser.add_argument(
        "--sample-id", action="append", default=[], help="pilot sample ID (repeatable)"
    )
    parser.add_argument(
        "--confirm-batch",
        action="store_true",
        help="explicitly authorize processing all 195 samples",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.qwen_jwssd.toml",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
    )
    args = parser.parse_args()
    if args.mode == "qwen" and args.limit is None and not args.sample_id and not args.confirm_batch:
        parser.error("full Qwen evaluation requires explicit --confirm-batch")
    samples = load_unlabeled_jwssd_samples(args.archive, expected_sha256=EXPECTED_ARCHIVE_SHA256)
    samples = select_pilot_samples(samples, limit=args.limit, sample_ids=args.sample_id)
    if args.mode == "uniform":
        predictions = uniform_predictor(samples)
    else:
        predictions = qwen_predictor(
            args.archive,
            samples,
            config_path=args.config,
            env_file=args.env_file if args.env_file.exists() else None,
        )
    write_predictions(args.out, predictions)
    count = len(predictions)
    print(f"wrote {count} label-blind predictions to {args.out}")


if __name__ == "__main__":
    main()
