"""Label-blind JW-SSD observation and single-sample analysis service."""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from astropy.io import fits

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    QwenChatModel,
    QwenRuntimeConfig,
    ResilientChatModel,
)
from ai_scientist_mvp.skills.jwssd_evaluation import (
    UnlabeledJWSSDSample,
    load_unlabeled_jwssd_samples,
)

JWSSD_ARCHIVE_SHA256 = "db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4"
JWSSD_CLASSES = ("alpha", "beta", "beta-delta", "beta-gamma", "beta-gamma-delta")
_IMAGE_MODALITIES = {
    "continuum": "continuum_png",
    "magnetogram": "magnetogram_png",
}
_FITS_MODALITIES = {
    "continuum": "continuum_fits",
    "magnetogram": "magnetogram_fits",
}
_PROMPT = """你是太阳物理观测分析助手。请依据给定的 HMI 连续谱、磁图图像和 FITS 数值摘要，
对该活动区进行 Mount Wilson 五分类。只允许输出 JSON，不要使用训练标签或文件路径。
输出格式：
{"label":"alpha|beta|beta-delta|beta-gamma|beta-gamma-delta",
 "probabilities":{"alpha":0.0,"beta":0.0,"beta-delta":0.0,"beta-gamma":0.0,"beta-gamma-delta":0.0},
 "visual_evidence":["最多三条可见形态依据"],
 "fits_evidence":["最多三条数值依据"],
 "caveat":"一句局限说明"}
概率必须有限、非负且总和为 1。该判读不代表耀斑预测或因果结论。
"""


@dataclass(frozen=True)
class WorkbenchBinary:
    body: bytes
    content_type: str


@dataclass(frozen=True)
class AnalysisResult:
    label: str
    probabilities: dict[str, float]
    visual_evidence: tuple[str, ...]
    fits_evidence: tuple[str, ...]
    caveat: str
    model: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "probabilities": self.probabilities,
            "visual_evidence": list(self.visual_evidence),
            "fits_evidence": list(self.fits_evidence),
            "caveat": self.caveat,
            "model": self.model,
            "scientific_status": "DEVELOPMENTAL_AI_INTERPRETATION",
        }


Analyzer = Callable[[UnlabeledJWSSDSample], AnalysisResult]


class WorkbenchNotFound(KeyError):
    """An observation or analysis job does not exist."""


class WorkbenchConflict(RuntimeError):
    """An analysis cannot start in the current service state."""


class JWSSDWorkbench:
    """Expose label-blind observations and bounded asynchronous analysis jobs."""

    def __init__(
        self,
        archive_path: Path,
        *,
        config_path: Path | None = None,
        env_file: Path | None = None,
        analyzer: Analyzer | None = None,
    ) -> None:
        self.archive_path = archive_path.resolve()
        self.config_path = config_path.resolve() if config_path is not None else None
        self.env_file = env_file.resolve() if env_file is not None else None
        samples = load_unlabeled_jwssd_samples(
            self.archive_path,
            expected_sha256=JWSSD_ARCHIVE_SHA256,
        )
        self._samples = {
            f"OBS-{index:04d}": sample for index, sample in enumerate(samples, start=1)
        }
        self._analyzer = analyzer or self._analyze_with_qwen
        self._jobs: dict[str, dict[str, object]] = {}
        self._active_job_id: str | None = None
        self._lock = threading.RLock()

    def catalog(self) -> dict[str, object]:
        observations = [self._observation_summary(public_id) for public_id in self._samples]
        return {
            "dataset": "JW-SSD 五分类四模态观测集",
            "archive_status": "SHA256_VERIFIED",
            "observation_count": len(observations),
            "modalities": [
                "continuum_png",
                "magnetogram_png",
                "continuum_fits",
                "magnetogram_fits",
            ],
            "label_policy": "HIDDEN_FROM_INFERENCE",
            "analysis_mode": "SINGLE_OBSERVATION_ONLY",
            "observations": observations,
        }

    def observation(self, public_id: str) -> dict[str, object]:
        sample = self._sample(public_id)
        summaries = {
            name: self._fits_summary(self._member_bytes(sample.path_for(modality)))
            for name, modality in _FITS_MODALITIES.items()
        }
        return {
            **self._observation_summary(public_id),
            "images": {
                name: f"/workbench/observations/{public_id}/images/{name}"
                for name in _IMAGE_MODALITIES
            },
            "fits": summaries,
            "instrument": "SDO/HMI SHARP 720s",
            "coordinate_context": "HARP patch",
        }

    def image(self, public_id: str, image_name: str) -> WorkbenchBinary:
        sample = self._sample(public_id)
        try:
            modality = _IMAGE_MODALITIES[image_name]
        except KeyError as exc:
            raise WorkbenchNotFound(image_name) from exc
        body = self._member_bytes(sample.path_for(modality))
        if not body.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("observation image is not a PNG")
        return WorkbenchBinary(body, "image/png")

    def start_analysis(self, public_id: str) -> dict[str, object]:
        sample = self._sample(public_id)
        with self._lock:
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                if active["status"] in {"QUEUED", "RUNNING"}:
                    if active["observation_id"] == public_id:
                        return dict(active)
                    raise WorkbenchConflict("another observation analysis is still running")
            job_id = "analysis-" + uuid4().hex[:16]
            job: dict[str, object] = {
                "job_id": job_id,
                "observation_id": public_id,
                "status": "QUEUED",
                "stage": "PREPARING_MODALITIES",
                "progress": 5,
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
        worker = threading.Thread(
            target=self._run_analysis,
            args=(job_id, sample),
            name=f"jwssd-{job_id}",
            daemon=True,
        )
        worker.start()
        return dict(job)

    def analysis_job(self, job_id: str) -> dict[str, object]:
        with self._lock:
            try:
                return dict(self._jobs[job_id])
            except KeyError as exc:
                raise WorkbenchNotFound(job_id) from exc

    def _run_analysis(self, job_id: str, sample: UnlabeledJWSSDSample) -> None:
        self._update_job(job_id, status="RUNNING", stage="QWEN_MULTIMODAL_REASONING", progress=35)
        try:
            result = self._analyzer(sample)
        except Exception as exc:
            self._update_job(
                job_id,
                status="FAILED",
                stage="FAILED",
                progress=100,
                error=_safe_error(exc),
            )
        else:
            self._update_job(
                job_id,
                status="SUCCEEDED",
                stage="EVIDENCE_READY",
                progress=100,
                result=result.to_dict(),
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def _update_job(self, job_id: str, **updates: object) -> None:
        with self._lock:
            self._jobs[job_id].update(updates)

    def _analyze_with_qwen(self, sample: UnlabeledJWSSDSample) -> AnalysisResult:
        if self.config_path is None:
            raise WorkbenchConflict("Qwen configuration is not available")
        runtime = QwenRuntimeConfig.from_toml(self.config_path)
        environment = dict(os.environ)
        if self.env_file is not None and self.env_file.exists():
            environment.update(_read_env_file(self.env_file))
        model = ResilientChatModel(
            QwenChatModel(runtime.model, environ=environment),
            policy=runtime.retry,
        )
        parts: list[dict[str, object]] = [{"type": "text", "text": _PROMPT}]
        for modality in ("continuum_png", "magnetogram_png"):
            encoded = base64.b64encode(
                self._member_bytes(sample.path_for(modality))
            ).decode("ascii")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            )
        fits_payload = {
            name: self._fits_summary(self._member_bytes(sample.path_for(modality)))
            for name, modality in _FITS_MODALITIES.items()
        }
        parts.append(
            {
                "type": "text",
                "text": "FITS summaries: " + json.dumps(fits_payload, ensure_ascii=False),
            }
        )
        response = model.invoke(
            [ChatMessage("user", parts)],
            response_format={"type": "json_object"},
        )
        return _parse_analysis(response.message.content, response.model)

    def _observation_summary(self, public_id: str) -> dict[str, object]:
        sample = self._sample(public_id)
        return {
            "observation_id": public_id,
            "harpnum": sample.harpnum,
            "observed_at_tai": sample.t_rec_tai,
            "modality_count": 4,
        }

    def _sample(self, public_id: str) -> UnlabeledJWSSDSample:
        try:
            return self._samples[public_id]
        except KeyError as exc:
            raise WorkbenchNotFound(public_id) from exc

    def _member_bytes(self, member: str) -> bytes:
        with zipfile.ZipFile(self.archive_path, metadata_encoding="utf-8") as archive:
            return archive.read(member)

    @staticmethod
    def _fits_summary(source: bytes) -> dict[str, object]:
        with fits.open(io.BytesIO(source), memmap=False) as hdul:
            image = next((hdu.data for hdu in hdul if getattr(hdu, "data", None) is not None), None)
            if image is None:
                raise ValueError("FITS contains no image data")
            values = image.astype("float64", copy=False)
            finite = values[np.isfinite(values)]
            if finite.size == 0:
                raise ValueError("FITS image contains no finite values")
            return {
                "shape": list(values.shape),
                "finite_fraction": round(float(finite.size / values.size), 6),
                "min": round(float(finite.min()), 4),
                "max": round(float(finite.max()), 4),
                "mean": round(float(finite.mean()), 4),
                "std": round(float(finite.std()), 4),
            }


def _parse_analysis(content: object, model: str) -> AnalysisResult:
    if not isinstance(content, str):
        raise ValueError("Qwen response content must be JSON text")
    try:
        payload = json.loads(content)
        label = payload["label"]
        raw_probabilities = payload["probabilities"]
        probabilities = {name: float(raw_probabilities[name]) for name in JWSSD_CLASSES}
        visual_evidence = _short_strings(payload.get("visual_evidence", []))
        fits_evidence = _short_strings(payload.get("fits_evidence", []))
        caveat = str(payload.get("caveat", "模型判读需由太阳物理专家复核。"))[:300]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Qwen response does not match the workbench contract") from exc
    if label not in JWSSD_CLASSES or any(
        not np.isfinite(value) or value < 0 or value > 1 for value in probabilities.values()
    ):
        raise ValueError("Qwen response contains an invalid class or probability")
    total = sum(probabilities.values())
    if total <= 0 or abs(total - 1.0) > 0.05:
        raise ValueError("Qwen probabilities must sum to one")
    normalized = {name: round(value / total, 6) for name, value in probabilities.items()}
    return AnalysisResult(
        label,
        normalized,
        visual_evidence,
        fits_evidence,
        caveat,
        model,
    )


def _short_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item)[:300] for item in value[:3] if str(item).strip())


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


def _safe_error(error: Exception) -> dict[str, str]:
    message = " ".join(str(error).split())[:300] or "analysis failed"
    message = re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s]+", "<redacted-path>", message)
    return {
        "code": type(error).__name__,
        "message": message,
    }
