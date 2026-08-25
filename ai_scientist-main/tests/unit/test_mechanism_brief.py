from __future__ import annotations

from pathlib import Path

import pytest

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.skills.mechanism_brief import (
    MechanismBriefValidationError,
    parse_mechanism_brief,
    parse_phase1_output,
    project_mechanism_snapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V22_PATH = PROJECT_ROOT / "fixtures" / "shrgt45" / "assets" / "s02" / (
    "MechanismBrief-V2.2-SHRGT45.md"
)
V23_PATH = PROJECT_ROOT / "fixtures" / "shrgt45" / "assets" / "s02" / (
    "MechanismBrief-V2.3-SHRGT45.md"
)


def test_parses_frozen_v22_mechanism_brief_fixture() -> None:
    brief = parse_mechanism_brief(V22_PATH.read_text(encoding="utf-8"))

    assert brief.parameter.startswith("SHRGT45")
    assert [table.section_id for table in brief.evidence_tables] == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
    ]
    assert brief.evidence_count == 15
    assert len(brief.bibliography) == 11
    assert brief.section_fields["3"]["科学声称上限"]


def test_phase1_maps_candidates_and_p1_to_p5_plan() -> None:
    phase1 = """# Phase 1 中间交付表：SHRGT45

## 论文拉取候选（程序化累积自 s2_search）
**[1] First paper**
- DOI: 10.1000/one | ArXiv: 2401.00001
**[2] Second paper**
- DOI: N/A | ArXiv: 2401.00002

## P1：参数定义
## P2：前兆窗口与趋势
## P3：预测窗口
## P4：统计关联方向
## P5：物理机制关联
## 进入Phase 2自审核
"""

    plan = parse_phase1_output(phase1)

    assert plan.parameter == "SHRGT45"
    assert plan.section_ids == ("P1", "P2", "P3", "P4", "P5")
    assert plan.ready_for_phase2 is True
    assert plan.candidates[0].doi == "10.1000/one"
    assert plan.candidates[1].doi is None
    assert plan.candidates[1].arxiv == "2401.00002"


def test_projects_v22_dto_to_existing_mechanism_snapshot_contract() -> None:
    brief = parse_mechanism_brief(V22_PATH.read_text(encoding="utf-8"))
    source_ref = {
        "id": "s02.mechanism-brief-v2_2-historical",
        "schema_version": "0.1.0",
        "content_hash": "A07A7D71A1F33329447119528E1F204E6B328516AB00F1EB696C9A1D3B87F493",
    }

    snapshot = project_mechanism_snapshot(
        brief,
        snapshot_id="mechanism-v22-extract",
        source_version="V2.2",
        source_refs=[source_ref],
    )

    assert snapshot["parameter"] == "SHRGT45"
    assert snapshot["source_refs"] == [source_ref]
    assert snapshot["extraction_completeness"] == "COMPLETE_V13_V2_2_STRUCTURE"
    assert canonical_json.content_hash_excluding(snapshot) == snapshot["content_hash"]


def test_rejects_v23_as_v22_and_duplicate_evidence_ids() -> None:
    with pytest.raises(MechanismBriefValidationError, match="expected MechanismBrief V2.2"):
        parse_mechanism_brief(V23_PATH.read_text(encoding="utf-8"))

    duplicate = V22_PATH.read_text(encoding="utf-8").replace("| E02 |", "| E01 |", 1)
    with pytest.raises(MechanismBriefValidationError, match="evidence IDs must be unique"):
        parse_mechanism_brief(duplicate)


def test_rejects_missing_required_field_and_source_refs() -> None:
    source = V22_PATH.read_text(encoding="utf-8")
    missing_field = source.replace("- **参数名称**：", "- **未定义字段**：", 1)
    with pytest.raises(MechanismBriefValidationError, match="参数名称"):
        parse_mechanism_brief(missing_field)

    brief = parse_mechanism_brief(source)
    with pytest.raises(MechanismBriefValidationError, match="source_refs"):
        project_mechanism_snapshot(
            brief,
            snapshot_id="mechanism-v22-extract",
            source_version="V2.2",
            source_refs=[],
        )
