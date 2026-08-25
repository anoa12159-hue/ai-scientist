"""V13 V2.2 Phase 1/2 DTOs, Markdown validation, and snapshot projection."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.types import MechanismSnapshot, VersionedRef

_SECTION_LABELS = {
    "P1": "P1：参数定义",
    "P2": "P2：前兆窗口+趋势",
    "P3": "P3：预测窗口",
    "P4": "P4：统计关联方向",
    "P5": "P5：物理机制关联",
}
_TABLE_COLUMNS = (
    "类别",
    "证据编号",
    "内容摘要",
    "方向",
    "直/间接",
    "原始文献",
    "原文位置",
    "可信度",
)
_SECTION_FIELDS = {
    "1": (
        "参数名称",
        "参数定义",
        "单位",
        "观测层级",
        "数据来源",
        "直接测量什么",
        "不能直接测量什么",
        "数据来源是否已核实",
    ),
    "3": (
        "参数变化（主候选）",
        "反映的物理状态",
        "可能关联的现象",
        "证据支持到哪里——参数层（P1–P2：参数定义 + 物理机制）",
        "证据支持到哪里——时间变换层（P3–P5：前兆窗口 + 预测窗口 + 与耀斑统计关联）",
        "科学声称上限",
        "禁止表述",
    ),
    "4": (
        "适用对象",
        "项目主分析范围",
        "适用条件",
        "统计局限",
        "物理局限",
        "观测系统替代解释",
        "潜在混杂／替代解释",
        "负面证据",
        "尚未解决的问题",
    ),
    "5": (
        "研究总体",
        "主候选参数",
        "主候选参数形式",
        "预期方向",
        "预期变化发生的时段",
        "目标事件",
        "事件时间窗",
        "特征历史窗",
        "机制依据",
        "对应证据编号",
        "适用范围",
        "当前不确定性",
    ),
    "6": ("建议结论", "主要依据", "交接边界", "执行门"),
}
_SECTION_HEADINGS = {
    "1": "## 1. 参数基本信息",
    "2": "## 2. 证据表（按假设五部分 × 四类组织）",
    "3": "## 3. 机制链与解释边界",
    "4": "## 4. 适用范围与局限",
    "5": "## 5. 候选假设种子",
    "6": "## 6. 候选准入建议",
}
_FIELD_PATTERN = re.compile(r"^- \*\*(?P<label>.+?)\*\*[：:]\s*(?P<value>.*)$")
_PHASE1_CANDIDATE_PATTERN = re.compile(
    r"^\*\*\[(?P<index>\d+)\]\s+(?P<title>.+?)\*\*$", re.MULTILINE
)


class MechanismBriefValidationError(ValueError):
    """The V13 output does not match its V2.2 DTO/Markdown contract."""


@dataclass(frozen=True)
class Phase1PaperCandidate:
    index: int
    title: str
    doi: str | None
    arxiv: str | None


@dataclass(frozen=True)
class Phase1EvidencePlan:
    parameter: str
    candidates: tuple[Phase1PaperCandidate, ...]
    section_ids: tuple[str, ...]
    ready_for_phase2: bool


@dataclass(frozen=True)
class EvidenceRow:
    category: str
    evidence_id: str
    summary: str
    direction: str
    directness: str
    source: str
    location: str
    confidence: str


@dataclass(frozen=True)
class EvidenceTable:
    section_id: str
    label_cn: str
    columns: tuple[str, ...]
    rows: tuple[EvidenceRow, ...]


@dataclass(frozen=True)
class MechanismBriefV22:
    parameter: str
    section_fields: Mapping[str, Mapping[str, str]]
    evidence_tables: tuple[EvidenceTable, ...]
    hypothesis_statement: str
    bibliography: tuple[str, ...]

    @property
    def evidence_count(self) -> int:
        return sum(len(table.rows) for table in self.evidence_tables)


def parse_phase1_output(markdown_text: str) -> Phase1EvidencePlan:
    title_match = re.search(r"^# Phase 1 中间交付表：(.+)$", markdown_text, re.MULTILINE)
    if title_match is None:
        raise MechanismBriefValidationError("missing Phase 1 title")
    parameter = title_match.group(1).strip()
    section_ids = tuple(
        section_id
        for section_id in _SECTION_LABELS
        if re.search(rf"^## {section_id}[：:]", markdown_text, re.MULTILINE)
    )
    if section_ids != tuple(_SECTION_LABELS):
        raise MechanismBriefValidationError("Phase 1 must contain P1 through P5")
    candidates: list[Phase1PaperCandidate] = []
    matches = list(_PHASE1_CANDIDATE_PATTERN.finditer(markdown_text))
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown_text)
        block = markdown_text[match.end() : end]
        candidates.append(
            Phase1PaperCandidate(
                index=int(match.group("index")),
                title=match.group("title").strip(),
                doi=_metadata_value(block, "DOI"),
                arxiv=_metadata_value(block, "ArXiv"),
            )
        )
    if not candidates:
        raise MechanismBriefValidationError("Phase 1 must contain paper candidates")
    indices = [candidate.index for candidate in candidates]
    if len(indices) != len(set(indices)):
        raise MechanismBriefValidationError("Phase 1 candidate indices must be unique")
    return Phase1EvidencePlan(
        parameter=parameter,
        candidates=tuple(candidates),
        section_ids=section_ids,
        ready_for_phase2="## 进入Phase 2自审核" in markdown_text,
    )


def parse_mechanism_brief(markdown_text: str) -> MechanismBriefV22:
    title_match = re.search(
        r"^# MechanismBrief V(?P<version>\d+\.\d+)：结构化交接包", markdown_text, re.MULTILINE
    )
    if title_match is None:
        raise MechanismBriefValidationError("missing MechanismBrief versioned title")
    if title_match.group("version") != "2.2":
        raise MechanismBriefValidationError("expected MechanismBrief V2.2 input")
    for heading in (*_SECTION_HEADINGS.values(), "## 引用文献"):
        if heading not in markdown_text:
            raise MechanismBriefValidationError(f"missing heading: {heading}")
    section_fields = _parse_section_fields(markdown_text)
    tables = tuple(
        _parse_evidence_table(markdown_text, section_id, label)
        for section_id, label in _SECTION_LABELS.items()
    )
    evidence_ids = [row.evidence_id for table in tables for row in table.rows]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise MechanismBriefValidationError("evidence IDs must be unique")
    hypothesis = _between(markdown_text, "候选假设表述：", _SECTION_HEADINGS["6"]).strip()
    if not hypothesis:
        raise MechanismBriefValidationError("candidate hypothesis statement must not be empty")
    bibliography_text = markdown_text.split("## 引用文献", maxsplit=1)[1]
    bibliography = tuple(
        line.strip() for line in bibliography_text.splitlines() if line.strip().startswith("[")
    )
    if not bibliography:
        raise MechanismBriefValidationError("bibliography must not be empty")
    parameter = section_fields["1"]["参数名称"]
    return MechanismBriefV22(
        parameter=parameter,
        section_fields=section_fields,
        evidence_tables=tables,
        hypothesis_statement=hypothesis,
        bibliography=bibliography,
    )


def project_mechanism_snapshot(
    brief: MechanismBriefV22,
    *,
    snapshot_id: str,
    source_version: str,
    source_refs: Sequence[VersionedRef],
) -> MechanismSnapshot:
    if not source_refs:
        raise MechanismBriefValidationError("MechanismSnapshot requires source_refs")
    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "schema_version": "0.1.0",
        "parameter": brief.parameter.split("（", maxsplit=1)[0].strip(),
        "source_version": source_version,
        "allowed_interpretation": brief.section_fields["3"]["科学声称上限"],
        "forbidden_claims": [brief.section_fields["3"]["禁止表述"]],
        "source_refs": list(source_refs),
        "extraction_completeness": "COMPLETE_V13_V2_2_STRUCTURE",
    }
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return cast(MechanismSnapshot, payload)


def _parse_section_fields(markdown_text: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    heading_items = list(_SECTION_HEADINGS.items())
    for index, (section_id, heading) in enumerate(heading_items):
        if section_id == "2":
            continue
        next_heading = (
            heading_items[index + 1][1] if index + 1 < len(heading_items) else "## 引用文献"
        )
        section_text = _between(markdown_text, heading, next_heading)
        parsed: dict[str, str] = {}
        for line in section_text.splitlines():
            match = _FIELD_PATTERN.match(line.strip())
            if match is not None:
                parsed[match.group("label")] = match.group("value").strip()
        for label in _SECTION_FIELDS[section_id]:
            if not parsed.get(label):
                raise MechanismBriefValidationError(f"missing or empty field: {label}")
        result[section_id] = parsed
    return result


def _parse_evidence_table(markdown_text: str, section_id: str, label: str) -> EvidenceTable:
    start_heading = f"### {label}"
    start = markdown_text.find(start_heading)
    if start < 0:
        raise MechanismBriefValidationError(f"missing evidence table: {label}")
    later_starts = [
        markdown_text.find(f"### {other_label}", start + len(start_heading))
        for other_label in _SECTION_LABELS.values()
    ]
    section_three = markdown_text.find(_SECTION_HEADINGS["3"], start)
    stops = [position for position in (*later_starts, section_three) if position >= 0]
    block = markdown_text[start : min(stops)]
    rows: list[EvidenceRow] = []
    header_seen = False
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if cells == _TABLE_COLUMNS:
            header_seen = True
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if len(cells) != len(_TABLE_COLUMNS):
            raise MechanismBriefValidationError(f"invalid evidence row in {section_id}")
        rows.append(EvidenceRow(*cells))
    if not header_seen or not rows:
        raise MechanismBriefValidationError(f"evidence table {section_id} is incomplete")
    return EvidenceTable(section_id, label, _TABLE_COLUMNS, tuple(rows))


def _split_markdown_row(line: str) -> tuple[str, ...]:
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return tuple(cell.strip().replace(r"\|", "|") for cell in cells)


def _between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise MechanismBriefValidationError(f"missing marker: {start_marker}")
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end < 0:
        raise MechanismBriefValidationError(f"missing marker: {end_marker}")
    return text[start:end]


def _metadata_value(block: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}:\s*([^|\r\n]+)", block)
    if match is None:
        return None
    value = match.group(1).strip()
    return None if value.casefold() == "n/a" else value
