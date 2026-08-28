from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_web_is_an_astronomy_workbench_with_label_blind_single_sample_analysis() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "太阳活动区智能研究工作台" in html
    assert "连续谱强度图" in html
    assert "视向磁图" in html
    assert "Mount Wilson 五分类" in html
    assert "启动单样本 AI 分析" in html
    assert "fetch(" in script
    assert "/workbench/catalog" in script
    assert "/workbench/analyses" in script
    assert "/workbench/jobs/" in script
    assert "confirm-batch" not in script
    assert "scientific_verdict" not in script
    assert "mount_wilson_class" not in script
