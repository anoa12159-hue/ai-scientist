from __future__ import annotations

import time
from pathlib import Path

from ai_scientist_mvp.api.workbench import AnalysisResult, JWSSDWorkbench

ARCHIVE = Path(__file__).resolve().parents[3] / "SHRGT45_官方五分类四模态扩展样本_20260826.zip"


def _analysis(_sample: object) -> AnalysisResult:
    return AnalysisResult(
        "beta",
        {
            "alpha": 0.05,
            "beta": 0.7,
            "beta-delta": 0.05,
            "beta-gamma": 0.15,
            "beta-gamma-delta": 0.05,
        },
        ("可见双极结构",),
        ("磁图具有有限像素",),
        "仅供开发性判读。",
        "test-model",
    )


def test_workbench_catalog_is_label_blind_and_images_are_real_png() -> None:
    workbench = JWSSDWorkbench(ARCHIVE, analyzer=_analysis)
    catalog = workbench.catalog()
    assert catalog["observation_count"] == 195
    assert catalog["label_policy"] == "HIDDEN_FROM_INFERENCE"
    first = catalog["observations"][0]
    assert first["observation_id"] == "OBS-0001"
    assert "label" not in first
    assert "alpha" not in str(first).lower()
    detail = workbench.observation("OBS-0001")
    assert set(detail["fits"]) == {"continuum", "magnetogram"}
    assert detail["fits"]["continuum"]["finite_fraction"] > 0
    image = workbench.image("OBS-0001", "magnetogram")
    assert image.content_type == "image/png"
    assert image.body.startswith(b"\x89PNG\r\n\x1a\n")


def test_workbench_runs_one_analysis_as_an_async_job() -> None:
    workbench = JWSSDWorkbench(ARCHIVE, analyzer=_analysis)
    started = workbench.start_analysis("OBS-0001")
    assert started["status"] in {"QUEUED", "RUNNING", "SUCCEEDED"}
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = workbench.analysis_job(str(started["job_id"]))
        if job["status"] == "SUCCEEDED":
            break
        time.sleep(0.01)
    assert job["status"] == "SUCCEEDED"
    assert job["result"]["label"] == "beta"
    assert job["result"]["scientific_status"] == "DEVELOPMENTAL_AI_INTERPRETATION"
