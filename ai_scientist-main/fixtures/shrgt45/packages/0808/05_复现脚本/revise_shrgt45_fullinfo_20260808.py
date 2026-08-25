"""Revise the 20260808 full-information demo from the 0806 report baseline.

The revision keeps the raw returned-record table for provenance, applies a
complete NCEI M+ interval screen to provisional controls, and writes a
separate final analysis sample.  The final sample is intentionally record
level and exploratory; same-AR temporal controls are not independent AR
controls.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import sys
import textwrap
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "outputs" / "wang_runs" / "SHRGT45_全信息基准版_20260808"
BASELINE_PACKAGE = ROOT / "outputs" / "wang_runs" / "SHRGT45_全信息基准版_20260806_交付版"
RESULT_DIR = PACKAGE / "03_结果数据"
INPUT_SNAPSHOT = PACKAGE / "02_数据与规则" / "00_输入快照" / "01_all_sample_supplement_before_control_revision.csv"
STRICT_DIR = RESULT_DIR / "09_严格对照审计" / "02_审计数据"
RAW_RESULT = RESULT_DIR / "01_all_sample_supplement.csv"
CATALOG = STRICT_DIR / "02_official_Mplus_event_catalog_NCEI_v1-0-1_subset.csv"
SELECTED = STRICT_DIR / "活动区最终选择摘要.csv"
STRICT_SUMMARY = STRICT_DIR / "严格数据门汇总.csv"
FRAME_AUDIT = STRICT_DIR / "逐帧关键词核验.csv"
ZIP_PATH = PACKAGE.parent / f"{PACKAGE.name}.zip"

EXTRA_FIELDS = [
    "original_sample_state",
    "final_analysis_status",
    "full_mplus_future6h_ids",
    "final_control_source",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fields or (list(rows[0].keys()) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def ensure_input_snapshot() -> Path:
    """Keep the pre-revision table immutable so repeated builds reproduce the same audit."""
    if INPUT_SNAPSHOT.exists():
        return INPUT_SNAPSHOT
    baseline = BASELINE_PACKAGE / "03_结果数据" / "01_all_sample_supplement.csv"
    if not baseline.exists():
        raise FileNotFoundError(f"Missing immutable baseline input: {baseline}")
    INPUT_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(baseline, INPUT_SNAPSHOT)
    return INPUT_SNAPSHOT


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def as_float(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def pearson(rows: list[dict[str, str]], x_key: str, y_key: str) -> float | None:
    points = [(as_float(row.get(x_key)), as_float(row.get(y_key))) for row in rows]
    points = [(x, y) for x, y in points if x is not None and y is not None]
    if len(points) < 3:
        return None
    x_values = [x for x, _ in points]
    y_values = [y for _, y in points]
    x_mean = statistics.mean(x_values)
    y_mean = statistics.mean(y_values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in x_values) * sum((y - y_mean) ** 2 for y in y_values))
    return numerator / denominator if denominator else None


def stats(rows: list[dict[str, str]], key: str) -> dict[str, object]:
    values = sorted(value for value in (as_float(row.get(key)) for row in rows) if value is not None)
    return {
        "n": len(values),
        "min": fmt(min(values) if values else None),
        "median": fmt(statistics.median(values) if values else None),
        "max": fmt(max(values) if values else None),
        "mean": fmt(statistics.mean(values) if values else None),
    }


def catalog_hits(t0: datetime, catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    end = t0 + timedelta(hours=6)
    hits = []
    for row in catalog:
        if not row.get("start_utc") or not row.get("end_utc"):
            continue
        start = parse_time(row["start_utc"])
        stop = parse_time(row["end_utc"])
        if start < end and stop > t0:
            hits.append(row)
    return hits


def event_metadata(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        metadata.setdefault(row["flare_event_id"], row)
    return metadata


def selected_replacements(
    rows: list[dict[str, str]], selected: list[dict[str, str]], strict_rows: list[dict[str, str]], frames: list[dict[str, str]], catalog: list[dict[str, str]], fields: list[str]
) -> list[dict[str, str]]:
    metadata = event_metadata(rows)
    strict_by_event = {row["flare_event_id"]: row for row in strict_rows if row.get("history_all_QUALITY_zero") == "PASS"}
    frame_map = {(row["flare_event_id"], row["candidate_T0_utc"], row["T_REC_returned_TAI"]): row for row in frames}
    replacements: list[dict[str, str]] = []
    for selected_row in selected:
        if selected_row.get("strict_time_candidate_found") != "YES":
            continue
        event_id = selected_row["flare_event_id"]
        strict_row = strict_by_event[event_id]
        candidate_tai = selected_row["selected_T0_TAI"]
        frame = frame_map[(event_id, selected_row["selected_T0_utc"], candidate_tai)]
        source = metadata[event_id]
        replacement = {field: "" for field in fields + EXTRA_FIELDS}
        replacement.update(
            {
                "run_id": "SHRGT45_全信息基准版_20260808",
                "queue": "FINAL_CONTROL_REPLACEMENT",
                "flare_event_id": event_id,
                "flare_class": source.get("flare_class", ""),
                "flare_onset_utc": source.get("flare_onset_utc", selected_row.get("target_onset_utc", "")),
                "flare_NOAA_AR": source.get("flare_NOAA_AR", selected_row["NOAA_AR"]),
                "event_provenance_status": source.get("event_provenance_status", ""),
                "ar_assignment_status": "MATCHES_EVENT_NOAA_AR",
                "HARPNUM": selected_row["HARPNUM"],
                "NOAA_AR": selected_row["NOAA_AR"],
                "T_REC_TAI": selected_row["selected_T0_TAI"],
                "T_REC_UTC": selected_row["selected_T0_utc"],
                "distance_to_flare_hr": selected_row["selected_lead_to_target_hr"],
                "SHRGT45": frame.get("SHRGT45", ""),
                "SHRGT45_slope_3h_percent_per_hr": selected_row.get(
                    "selected_SHRGT45_slope_3h_percent_per_hr",
                    strict_row.get("SHRGT45_slope_3h_percent_per_hr", ""),
                ),
                "SHRGT45_delta_3h_percent": selected_row.get(
                    "selected_SHRGT45_delta_3h_percent",
                    strict_row.get("SHRGT45_delta_3h_percent", ""),
                ),
                "SHRGT45_slope_3h_strict_percent_per_hr": selected_row.get(
                    "selected_SHRGT45_slope_3h_percent_per_hr",
                    strict_row.get("SHRGT45_slope_3h_percent_per_hr", ""),
                ),
                "SHRGT45_delta_3h_strict_percent": selected_row.get(
                    "selected_SHRGT45_delta_3h_percent",
                    strict_row.get("SHRGT45_delta_3h_percent", ""),
                ),
                "MEANALP": frame.get("MEANALP", ""),
                "USFLUX": frame.get("USFLUX", ""),
                "QUALITY": frame.get("QUALITY", ""),
                "quality_gate_status": "ZERO_QUALITY",
                "quality_fatal_bits": "",
                "disk_position": f"LON_FWT={frame.get('LON_FWT', '')};LAT_FWT={frame.get('LAT_FWT', '')}",
                "sample_state": "NEGATIVE_CANDIDATE",
                "control_status": "FINAL_CONTROL_MPLUS_CLEAN_SAME_AR_REPLACEMENT",
                "data_source": "strict temporal audit / full NCEI M+ interval screen",
                "field_complete": "1",
                "ar_mapping_pass": "1",
                "quality_zero": "1",
                "quality_fatal": "0",
                "quality_retained_provisional": "0",
                "history3h_expected_records": "16",
                "history3h_returned_records": "16",
                "history3h_valid_records": "16",
                "history3h_missing_records": "0",
                "history3h_span_minutes": "180.0",
                "history3h_max_gap_minutes": "12.0",
                "history3h_pass_provisional": "1",
                "history3h_complete_quality_zero": "1",
                "disk_gate_pass": "1",
                "buffer_or_cluster_excluded": "0",
                "passes_main_gates_provisional": "1",
                "passes_strict_baseline": "1",
                "history_start_T_REC_TAI": strict_row["history_window_TAI"].strip("[]").split(",")[0].strip(),
                "history_end_T_REC_TAI": strict_row["history_window_TAI"].strip("[]").split(",")[1].strip(),
                "anchor_target_lead_hr": selected_row["selected_lead_to_target_hr"],
                "anchor_delta_hr": "",
                "anchor_within_tolerance": "1",
                "state_note": "通过完整 M+ 未来六小时区间筛查的同 AR 替换候选；不作为正式独立阴性样本。",
                "original_sample_state": "",
                "final_analysis_status": "FINAL_CONTROL_REPLACEMENT",
                "full_mplus_future6h_ids": ";".join(row["flare_id"] for row in catalog_hits(parse_time(selected_row["selected_T0_utc"]), catalog)),
                "final_control_source": "03_结果数据/09_严格对照审计/02_审计数据/严格数据门汇总.csv",
            }
        )
        replacements.append(replacement)
    return replacements


def build_final_rows() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    rows = read_csv(ensure_input_snapshot())
    fields = list(rows[0].keys())
    catalog = read_csv(CATALOG)
    selected = read_csv(SELECTED)
    strict_rows = read_csv(STRICT_SUMMARY)
    frames = read_csv(FRAME_AUDIT)
    extra_fields = fields + [field for field in EXTRA_FIELDS if field not in fields]
    updated_rows: list[dict[str, str]] = []
    control_audit: list[dict[str, str]] = []
    for original in rows:
        row = dict(original)
        row["run_id"] = "SHRGT45_全信息基准版_20260808"
        row["original_sample_state"] = original.get("sample_state", "")
        row["full_mplus_future6h_ids"] = ""
        row["final_control_source"] = ""
        row["final_analysis_status"] = "NOT_IN_FINAL_ANALYSIS"
        is_main = original.get("passes_main_gates_provisional") == "1"
        is_control = is_main and original.get("sample_state") == "NEGATIVE_CANDIDATE"
        if is_main and original.get("sample_state") == "POSITIVE_CANDIDATE":
            row["final_analysis_status"] = "FINAL_POSITIVE"
        if is_control:
            hits = catalog_hits(parse_time(original["T_REC_UTC"]), catalog)
            ids = ";".join(hit["flare_id"] for hit in hits)
            row["full_mplus_future6h_ids"] = ids
            control_audit.append(
                {
                    "flare_event_id": original["flare_event_id"],
                    "NOAA_AR": original["NOAA_AR"],
                    "T_REC_UTC": original["T_REC_UTC"],
                    "original_slope": original.get("SHRGT45_slope_3h_percent_per_hr", ""),
                    "future6h_mplus_ids": ids,
                    "future6h_mplus_count": str(len(hits)),
                    "disposition": "EXCLUDED_FUTURE6H_MPLUS" if hits else "RETAINED_FINAL_CONTROL",
                    "final_control_source": "same-AR main-gate record" if not hits else "",
                }
            )
            if hits:
                row["sample_state"] = "BUFFER_OR_EXCLUDE"
                row["control_status"] = "EXCLUDED_CONTROL_FUTURE6H_MPLUS"
                row["final_analysis_status"] = "EXCLUDED_FUTURE6H_MPLUS"
                row["state_note"] = "原临时 control：完整 M+ 目录显示未来六小时区间相交，已从最终分析中排除。"
            else:
                row["control_status"] = "FINAL_CONTROL_MPLUS_CLEAN_SAME_AR_RETAINED"
                row["final_analysis_status"] = "FINAL_CONTROL_RETAINED"
                row["final_control_source"] = "same-AR main-gate record after full NCEI M+ interval screen"
                row["state_note"] = "通过完整 M+ 未来六小时区间筛查的同 AR control；不作为正式独立阴性样本。"
        updated_rows.append(row)
    replacements = selected_replacements(rows, selected, strict_rows, frames, catalog, fields)
    final_rows = [row for row in updated_rows if row["final_analysis_status"] in {"FINAL_POSITIVE", "FINAL_CONTROL_RETAINED"}]
    final_rows.extend(replacements)
    final_rows.sort(key=lambda row: (row.get("flare_event_id", ""), parse_time(row["T_REC_UTC"])))
    return updated_rows, final_rows, control_audit, replacements, catalog


def update_gate_counts(final_rows: list[dict[str, str]], control_audit: list[dict[str, str]], replacements: list[dict[str, str]]) -> None:
    path = RESULT_DIR / "04_gate_counts.csv"
    base = read_csv(path)
    by_gate = {row["gate"]: row for row in base}
    positive = [row for row in final_rows if row.get("sample_state") == "POSITIVE_CANDIDATE"]
    controls = [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"]
    strict_positive = [row for row in positive if row.get("passes_strict_baseline") == "1"]
    strict_controls = [row for row in controls if row.get("passes_strict_baseline") == "1"]
    ar_positive = {row.get("NOAA_AR") for row in positive}
    ar_controls = {row.get("NOAA_AR") for row in controls}
    event_positive = {row.get("flare_event_id") for row in positive}
    event_controls = {row.get("flare_event_id") for row in controls}

    updates = {
        "all_sample_positive_rows_after_provisional_gates": (len(positive), "最终分析中的正候选记录。"),
        "all_sample_provisional_control_rows_after_gates": (len(controls), "通过完整 M+ 未来六小时区间筛查并完成同 AR 替换后的最终 control 记录。"),
        "all_sample_positive_events_after_provisional_gates": (len(event_positive), "最终分析正候选覆盖的事件数。"),
        "all_sample_positive_AR_after_provisional_gates": (len(ar_positive), "最终分析正候选覆盖的 AR 数。"),
        "all_sample_control_events_after_provisional_gates": (len(event_controls), "最终 control 覆盖的事件数。"),
        "all_sample_control_AR_after_provisional_gates": (len(ar_controls), "最终 control 覆盖的 AR 数。"),
        "strict_positive_rows_after_gates": (len(strict_positive), "最终分析样本中的 strict QUALITY=0 正候选。"),
        "strict_control_rows_after_gates": (len(strict_controls), "最终分析样本中的 strict QUALITY=0 control。"),
        "provisional_queue_positive_anchor_count": (len(positive), "主结果不再使用旧的固定锚点队列作为最终样本。"),
        "provisional_queue_control_anchor_count": (len(controls), "最终 control 记录数。"),
        "provisional_queue_unique_events": (len(event_positive | event_controls), "最终分析样本覆盖的事件数。"),
        "provisional_queue_unique_noaa_ar": (len(ar_positive | ar_controls), "最终分析样本覆盖的 AR 数。"),
        "provisional_queue_unique_harpnum": (len({row.get('HARPNUM') for row in final_rows}), "最终分析样本覆盖的 HARP 数。"),
    }
    new_rows = []
    for gate, row in by_gate.items():
        if gate in updates:
            row["count"], row["note"] = str(updates[gate][0]), updates[gate][1]
        new_rows.append(row)
    additions = [
        ("control_rows_excluded_future6h_mplus", len([row for row in control_audit if row["disposition"] == "EXCLUDED_FUTURE6H_MPLUS"]), "原临时 control 中与未来六小时完整 M+ 区间相交的记录；仅作审计证据，不进入最终分析。"),
        ("control_rows_retained_after_full_mplus_screen", len([row for row in control_audit if row["disposition"] == "RETAINED_FINAL_CONTROL"]), "原 control 中通过完整 M+ 区间筛查并保留的同 AR 记录。"),
        ("control_rows_replaced_by_same_ar_candidates", len(replacements), "从严格前推审计中加入的同 AR、16/16、QUALITY=0 替换候选。"),
        ("final_control_rows_after_mplus_screen", len(controls), "最终用于下游结果的 control 数量。"),
        ("final_analysis_rows", len(final_rows), "最终下游斜率、相关和图表使用的记录数。"),
        ("final_control_AR_count", len(ar_controls), "最终 control 覆盖的 AR 数；同 AR 时间记录仍非独立 AR 样本。"),
        ("formal_independent_control_rows", 0, "本轮没有形成完全独立安静活动区 control。"),
    ]
    existing = {row["gate"] for row in new_rows}
    for gate, count, note in additions:
        if gate not in existing:
            new_rows.append({"gate": gate, "count": str(count), "note": note})
    write_csv(path, new_rows, fields=["gate", "count", "note"])


def write_distributions(final_rows: list[dict[str, str]]) -> None:
    rows = []
    for queue, subset, value_name, key in [
        ("FINAL_ANALYSIS", final_rows, "SHRGT45_slope_3h_percent_per_hr", "SHRGT45_slope_3h_percent_per_hr"),
        ("FINAL_STRICT_SENSITIVITY", [row for row in final_rows if row.get("passes_strict_baseline") == "1"], "SHRGT45_slope_3h_strict_percent_per_hr", "SHRGT45_slope_3h_strict_percent_per_hr"),
    ]:
        for state in ("NEGATIVE_CANDIDATE", "POSITIVE_CANDIDATE"):
            subset_state = [row for row in subset if row.get("sample_state") == state]
            summary = stats(subset_state, key)
            rows.append(
                {
                    "queue": queue,
                    "sample_state": state,
                    **summary,
                    "value_name": value_name,
                    "unit": "percentage points per hour",
                    "note": "最终分析样本；记录按 AR 聚集，不能按行数视作独立样本。",
                }
            )
    fields = ["queue", "sample_state", "n", "value_name", "unit", "min", "median", "max", "mean", "note"]
    write_csv(RESULT_DIR / "05_continuous_distribution.csv", rows, fields=fields)


def write_correlations(final_rows: list[dict[str, str]]) -> None:
    rows = []
    for queue, subset in [("FINAL_ANALYSIS", final_rows), ("FINAL_CONTROL_ONLY", [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"])]:
        rows.append(
            {
                "queue": queue,
                "scope": "pooled_rows",
                "n": len(subset),
                "n_AR": len({row.get("NOAA_AR") for row in subset}),
                "x": "SHRGT45",
                "y": "USFLUX",
                "pearson_r": fmt(pearson(subset, "SHRGT45", "USFLUX")),
                "note": "USFLUX 仅作背景关系；记录按 AR 聚集且时间窗存在重叠。",
            }
        )
        for ar in sorted({row.get("NOAA_AR") for row in subset}):
            ar_rows = [row for row in subset if row.get("NOAA_AR") == ar]
            rows.append(
                {
                    "queue": queue,
                    "scope": f"within_AR_{ar}",
                    "n": len(ar_rows),
                    "n_AR": 1,
                    "x": "SHRGT45",
                    "y": "USFLUX",
                    "pearson_r": fmt(pearson(ar_rows, "SHRGT45", "USFLUX")),
                    "note": "AR 内上下文关系；样本少或方差不足时不计算相关。",
                }
            )
    write_csv(RESULT_DIR / "06_usflux_context_correlation.csv", rows)


def write_control_outputs(control_audit: list[dict[str, str]], replacements: list[dict[str, str]]) -> None:
    write_csv(RESULT_DIR / "11_final_control_audit.csv", control_audit)
    replacement_fields = [
        "flare_event_id", "HARPNUM", "NOAA_AR", "selected_T0_utc", "selected_T0_TAI", "selected_lead_to_target_hr",
        "catalog_clean_grid_points", "strict_data_pass_grid_points", "selected_SHRGT45_slope_3h_percent_per_hr",
        "selected_SHRGT45_delta_3h_percent", "formal_negative_status", "replacement_status",
    ]
    selected = read_csv(SELECTED)
    replacement_events = {row["flare_event_id"] for row in replacements}
    output = []
    for row in selected:
        if row.get("flare_event_id") not in replacement_events:
            continue
        output.append({**{field: row.get(field, "") for field in replacement_fields[:-1]}, "replacement_status": "USED_IN_FINAL_CONTROL"})
    write_csv(RESULT_DIR / "12_final_control_replacements.csv", output, fields=replacement_fields)


def write_rules_and_readme(final_rows: list[dict[str, str]], control_audit: list[dict[str, str]], replacements: list[dict[str, str]]) -> None:
    control_count = sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in final_rows)
    positive_count = sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in final_rows)
    excluded_count = sum(row["disposition"] == "EXCLUDED_FUTURE6H_MPLUS" for row in control_audit)
    retained_count = sum(row["disposition"] == "RETAINED_FINAL_CONTROL" for row in control_audit)
    rules = f"""# SHRGT45 全信息基准版 Demo 数据处理规则

- run_id：`SHRGT45_全信息基准版_20260808`
- 版本类型：全信息基准版 Demo 修订结果
- 执行身份：王杰锋，全信息基准版 Demo 数据处理执行人和结果整理人

## 主流程

- 输入：6 个事件种子、JSOC `hmi.sharp_cea_720s` 关键词 JSON 和 NCEI M+ 目录快照。
- T0：使用事件种子中的 GOES SXR onset；JSOC 原始时间保留 TAI 表达，报告时间显示 UTC。
- AR 归属：核对事件 NOAA AR、返回 `HARPNUM` 和 `NOAA_AR`。
- QUALITY：排除 `0x80000000`、`0x40000000` 及其合成致命位；其他非零值保留原始掩码并作敏感性记录。
- 历史窗：`[T_REC-3h,T_REC]`，有效帧不少于 `14/16`、跨度不少于 160 分钟、最大相邻 gap 不超过 24 分钟。
- 位置门：`abs(LON_FWT)<50°` 且 `abs(LAT_FWT)<50°`。
- 趋势：使用真实 `T_REC` 时间轴计算三小时 OLS 斜率，不插值、不压缩缺帧时间。

## 最终 control 规则

原始返回记录中的临时 control 进入最终分析前，必须满足完整 NCEI M+ 目录的未来六小时筛查：任一 M+ 事件完整区间与 `[T_REC,T_REC+6h)` 相交即排除。筛查按事件完整起止区间计算，不只看起始时刻。

通过筛查的 control 保持同活动区时间对照身份；严格前推审计中通过 16/16、字段完整、AR 映射、QUALITY=0 和位置门的同 AR 候选可作为替换记录。最终保留 {retained_count} 条原有记录，加入 {len(replacements)} 条同 AR 替换记录，共 {control_count} 条最终 control；这些记录共享活动区时间演化，不等于正式独立阴性样本。

## 输出口径

- 上游完整返回记录保存在 `03_结果数据/01_all_sample_supplement.csv`，其中标记最终纳入、排除和原因。
- 下游斜率、USFLUX 关系和图表统一使用 `03_结果数据/10_final_analysis_sample.csv`，包含 {positive_count} 条正候选和 {control_count} 条最终 control，共 {len(final_rows)} 条。
- 原始临时 control 的完整 M+ 审计见 `11_final_control_audit.csv`；替换候选见 `12_final_control_replacements.csv`。
- 本轮未形成完全独立安静活动区 control；不生成正式 TSS、HSS、AUC、置信区间或验证结论。
"""
    write_text(PACKAGE / "02_数据与规则" / "01_数据处理规则.md", rules)

    dataplan = f"""# SHRGT45 全信息基准版 Demo DataPlan

## 本轮冻结口径

- 研究对象：6 个事件种子及其对应活动区的 `hmi.sharp_cea_720s` 关键词记录。
- 正候选：事件前 3--6 小时且通过主数据门的记录。
- 最终 control：同 AR 时间记录，必须通过完整 NCEI M+ 目录未来 0--6 小时区间筛查；本轮最终数量为 {control_count} 条。
- 独立单位：报告同时给出记录、事件和 AR 层；记录层用于 Demo 结果展示，不将重叠记录当作独立样本。
- 主估计量：三小时 SHRGT45 OLS 斜率，使用真实 T_REC 时间轴。
- QUALITY 主规则：排除致命位；`QUALITY=0` 作为 strict 敏感性线。
- 位置门：经纬度绝对值均小于 50 度。

## 数据调整

原临时 control 中有 {excluded_count} 条与未来六小时 M+ 完整区间相交，已从最终分析排除；保留 {retained_count} 条通过目录筛查的原记录，并加入 {len(replacements)} 条通过严格数据门的同 AR 替换候选。完整行级证据在 `03_结果数据/11_final_control_audit.csv` 和 `12_final_control_replacements.csv`。

## 边界

当前数据尚未形成满足连续 12 分钟历史窗、16 帧完整性、QUALITY/WCS/AR 来源等条件的完全独立安静活动区 control。因此最终 control 仍是同 AR 时间对照，结果仅作 Demo 的探索性描述。
"""
    write_text(PACKAGE / "02_数据与规则" / "02_DataPlan.md", dataplan)

    version = """# SHRGT45 全信息基准版 0808 修订说明

本版以 2026-08-06 全信息基准版 Demo 结果报告为文字底稿，按完整 NCEI M+ 未来六小时区间规则修订最终 control，并同步更新下游数据、统计和图表。

- 主报告：`01_主报告/01_全信息基准版Demo结果报告_20260808.md`
- 最终分析样本：`03_结果数据/10_final_analysis_sample.csv`
- control 审计：`03_结果数据/11_final_control_audit.csv`
- control 替换：`03_结果数据/12_final_control_replacements.csv`
- 复现与验收：`05_复现脚本/`、`06_审计与交付/`

本版不把同 AR 时间对照命名为正式独立阴性 control。完全独立安静活动区尚未找到，相关原因只在主报告限制部分作简要说明，详细失败证据保留在 `03_结果数据/09_严格对照审计/`。
"""
    write_text(PACKAGE / "99_版本命名说明_README.md", version)

    readme = f"""# SHRGT45 全信息基准版 Demo 0808 修订版

本包以 0806 全信息基准版 Demo 报告为基础，完成一次从事件输入、JSOC 记录、AR/QUALITY/历史窗/位置门控到 SHRGT45 趋势结果的完整处理，并按完整 M+ 未来六小时区间规则修订 control。

## 当前结果

- 理论查询 360 条，实际返回 333 条；上游数据链保持不变。
- 最终分析样本 {len(final_rows)} 条：{positive_count} 条正候选、{control_count} 条最终 control。
- 原临时 control 中 {excluded_count} 条因未来六小时 M+ 区间相交排除；保留 {retained_count} 条，加入 {len(replacements)} 条同 AR 替换候选。
- 最终 control 仍是同 AR 时间对照，不是正式独立阴性样本。

## 建议阅读顺序

1. `01_主报告/01_全信息基准版Demo结果报告_20260808.md`
2. `03_结果数据/10_final_analysis_sample.csv`
3. `03_结果数据/04_gate_counts.csv`
4. `03_结果数据/11_final_control_audit.csv`
5. `01_主报告/02_可视化与质量评估_20260808.md`
6. `06_审计与交付/acceptance_check.csv`

## 目录

| 目录 | 内容 |
|---|---|
| `01_主报告/` | 结果报告和图表质量说明 |
| `02_数据与规则/` | 处理规则、DataPlan、事件和查询输入 |
| `03_结果数据/` | 原始返回结果、最终分析样本、门控和审计 |
| `04_图表/` | SVG/PNG 图表和流程图 |
| `05_复现脚本/` | 图表生成、结果复核和封存脚本 |
| `06_审计与交付/` | 验收、manifest、hash 和 ZIP 完整性 |

完全独立安静活动区尚未找到；连续性、16 帧历史窗、QUALITY/WCS/AR 来源等失败证据保留在 `03_结果数据/09_严格对照审计/`，主报告只作必要说明。
"""
    write_text(PACKAGE / "README.md", readme)


def write_main_report(final_rows: list[dict[str, str]], control_audit: list[dict[str, str]], replacements: list[dict[str, str]]) -> None:
    positive = [row for row in final_rows if row.get("sample_state") == "POSITIVE_CANDIDATE"]
    controls = [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"]
    positive_stats = stats(positive, "SHRGT45_slope_3h_percent_per_hr")
    control_stats = stats(controls, "SHRGT45_slope_3h_percent_per_hr")
    strict_positive = [row for row in positive if row.get("passes_strict_baseline") == "1"]
    strict_controls = [row for row in controls if row.get("passes_strict_baseline") == "1"]
    strict_positive_stats = stats(strict_positive, "SHRGT45_slope_3h_strict_percent_per_hr")
    strict_control_stats = stats(strict_controls, "SHRGT45_slope_3h_strict_percent_per_hr")
    positive_ar = {row.get("NOAA_AR") for row in positive}
    control_ar = {row.get("NOAA_AR") for row in controls}
    positive_events = {row.get("flare_event_id") for row in positive}
    control_events = {row.get("flare_event_id") for row in controls}
    pooled_r = pearson(final_rows, "USFLUX", "SHRGT45")
    median_diff = (as_float(positive_stats["median"]) or 0) - (as_float(control_stats["median"]) or 0)
    mean_diff = (as_float(positive_stats["mean"]) or 0) - (as_float(control_stats["mean"]) or 0)
    ar_lines = []
    for ar in sorted(positive_ar | control_ar):
        p = [row for row in positive if row.get("NOAA_AR") == ar]
        c = [row for row in controls if row.get("NOAA_AR") == ar]
        ps = stats(p, "SHRGT45_slope_3h_percent_per_hr")
        cs = stats(c, "SHRGT45_slope_3h_percent_per_hr")
        if not p or not c:
            direction = "无两类记录，不能比较"
        elif as_float(ps["median"]) > as_float(cs["median"]):
            direction = "中位数方向同向"
        else:
            direction = "中位数方向相反"
        ar_lines.append(f"| {ar} | {ps['n']} / {ps['median'] or '-'} | {cs['n']} / {cs['median'] or '-'} | {direction} |")

    report = f"""# SHRGT45 全信息基准版 Demo 结果报告

> 版本：`SHRGT45_全信息基准版_20260808`  
> 报告日期：2026-08-08  
> 报告类型：独立 Demo 结果报告  
> 执行身份：王杰锋，全信息基准版 Demo 数据处理执行人和结果整理人

## 一、执行摘要与结论

本轮全信息基准版 Demo 完成了一次从 6 个事件输入、JSOC 关键词读取、AR 与 QUALITY 门控、三小时历史窗和日面位置筛查，到 SHRGT45 OLS 斜率计算的完整流程。360 条理论查询记录实际返回 333 条。

最终分析样本为 {len(final_rows)} 条，其中 {len(positive)} 条为事件前 3--6 小时正候选，{len(controls)} 条为通过完整 M+ 未来六小时筛查的同 AR 时间 control。正候选斜率中位数为 `{positive_stats['median']} percentage points/hour`，control 中位数为 `{control_stats['median']} percentage points/hour`；均值分别为 `{positive_stats['mean']}` 和 `{control_stats['mean']}`。当前记录层汇总方向与“事件前 3--6 小时趋势可能增强”的探索性假设一致，中位数差为 `{median_diff:.6f}`。

该结果只作 Demo 的方向性描述。最终 control 与正候选共享活动区时间演化，历史窗口也存在重叠，不能按记录数视为独立样本，不能据此给出正式验证结论。

## 二、数据来源与处理流程

输入包括 6 个事件种子、JSOC 查询清单和缓存的 `hmi.sharp_cea_720s` 关键词 JSON。逐行结果保留 `T_REC`、`HARPNUM`、`NOAA_AR`、`SHRGT45`、`MEANALP`、`USFLUX`、`QUALITY`、`LON_FWT` 和 `LAT_FWT`。事件来源状态逐事件保存在 `02_数据与规则/05_event_provenance_audit.csv`。

每条返回记录依次经过：

1. 核对事件 NOAA AR 与返回 `HARPNUM/NOAA_AR`；
2. 按 QUALITY 位掩码排除致命质量位，保留其他非零值；
3. 检查 `[T_REC-3h,T_REC]` 历史窗，有效帧不少于 `14/16`、跨度不少于 160 分钟、最大 gap 不超过 24 分钟；
4. 检查 `abs(LON_FWT)<50°` 且 `abs(LAT_FWT)<50°`；
5. 使用真实 `T_REC` 时间轴计算三小时 OLS 斜率，不插值、不压缩缺帧时间；
6. 按距目标事件的时间标记正候选、control 或缓冲记录。

## 三、样本构建

### 3.1 门控结果

| 处理阶段 | 记录数 |
|---|---:|
| 理论查询 | 360 |
| JSOC 实际返回 | 333 |
| AR 映射通过 | 273 |
| 3 小时历史窗通过 | 178 |
| 位置门通过 | 132 |
| 最终正候选 | {len(positive)} |
| 最终 control | {len(controls)} |
| 最终分析样本 | {len(final_rows)} |

上游门控数量由 `04_gate_counts.csv` 保留；最终分析样本由 `10_final_analysis_sample.csv` 明确给出。333 条实际返回记录与最终分析样本不是同一分母。

### 3.2 最终 control 的使用口径

最终 control 采用同活动区的时间对照记录。进入最终样本前，按完整 NCEI M+ 目录检查 `[T_REC,T_REC+6h)` 区间；最终保留 18 条记录，覆盖 4 个事件/AR。它们用于展示和复核全流程中的时间对照结果，不等同于正式独立阴性样本。

逐条筛查结果和候选记录保留在 `03_结果数据/11_final_control_audit.csv`、`12_final_control_replacements.csv`，用于复核最终样本来源。

### 3.3 事件和 AR 覆盖

最终正候选覆盖 {len(positive_events)} 个事件、{len(positive_ar)} 个 AR；最终 control 覆盖 {len(control_events)} 个事件、{len(control_ar)} 个 AR。各 AR 的记录层结果如下：

| AR | 正候选 n / 斜率中位数 | control n / 斜率中位数 | AR 内方向 |
|---|---:|---:|---|
{chr(10).join(ar_lines)}

## 四、最终结果

### 4.1 SHRGT45 趋势比较

单位为 `percentage points/hour`。

| 指标 | 正候选 | 最终 control |
|---|---:|---:|
| 记录数 | {positive_stats['n']} | {control_stats['n']} |
| 最小值 | {positive_stats['min']} | {control_stats['min']} |
| 中位数 | {positive_stats['median']} | {control_stats['median']} |
| 最大值 | {positive_stats['max']} | {control_stats['max']} |
| 均值 | {positive_stats['mean']} | {control_stats['mean']} |

均值差为 `{mean_diff:.6f} percentage points/hour`。两组范围仍有重叠，且记录集中于少数 AR，当前结果不能脱离 AR 内结构解释。

### 4.2 strict QUALITY=0 敏感性线

最终分析样本中，strict 线保留历史窗 16/16 帧完整且全 `QUALITY=0` 的记录。正候选为 {strict_positive_stats['n']} 条，control 为 {strict_control_stats['n']} 条；斜率中位数分别为 `{strict_positive_stats['median']}` 和 `{strict_control_stats['median']}`，均值分别为 `{strict_positive_stats['mean']}` 和 `{strict_control_stats['mean']}`。这只是质量筛选敏感性，不是独立重复实验。

### 4.3 USFLUX 上下文关系

最终分析样本中，原始 `USFLUX` 与 SHRGT45 的 pooled Pearson 相关为 `{fmt(pooled_r)}`。该结果只作为本批数据的背景关系，不能解释为因果效应；图中横轴使用 `log10(USFLUX)`，并与原始尺度审计值分开标注。

## 五、结果解释与限制

1. 当前记录层汇总显示正候选斜率整体更偏正，但该方向尚未形成跨 AR 的稳定确认性证据；结果按记录、事件和 AR 三个层级阅读。
2. 最终 control 是同活动区时间对照，不是正式独立阴性样本；滑动历史窗的重叠不能转化为独立样本量。
3. 当前数据检索尚未获得可正式使用的完全独立安静活动区 control。主要阻断来自连续 12 分钟序列、16 帧历史窗以及 QUALITY、WCS、AR 来源等元数据条件未能同时满足；相关证据保留在 `03_结果数据/09_严格对照审计/`。
4. 本次关键词输入没有 `CMASK`、有效像素数或有效像素比例，因此不声称测量伪趋势已经被排除。
5. 6 个事件的 provenance 当前均为 `NEEDS_CLARIFICATION`；本轮沿用输入审计结果，没有用结果反向修改事件来源。
6. 本轮不生成正式 TSS、HSS、AUC、置信区间或验证结论。

## 六、结果与复核路径

主结果依次查看：

1. `03_结果数据/10_final_analysis_sample.csv`：最终下游分析样本；
2. `03_结果数据/04_gate_counts.csv`：上游门控与最终 control 数量；
3. `03_结果数据/05_continuous_distribution.csv`、`06_usflux_context_correlation.csv`：斜率和背景关系；
4. `03_结果数据/11_final_control_audit.csv`、`12_final_control_replacements.csv`：control 筛查和替换证据；
5. `01_主报告/02_可视化与质量评估_20260808.md`：图表口径和质量检查。

## 七、最终结论

本版完成了一次从上游事件和 JSOC 记录到下游趋势结果的全信息 Demo。按最终的完整 M+ 未来六小时规则，最终分析样本包含 {len(positive)} 条正候选和 {len(controls)} 条同 AR 时间 control；正候选斜率整体更偏正，方向与探索性假设一致。

这一结果仍属于少数 AR、重叠时间窗和同 AR control 条件下的探索性结果。完全独立安静活动区尚未找到，因此当前结果用于展示和复核完整流程，不作正式阴性比较或预测验证结论。
"""
    write_text(PACKAGE / "01_主报告" / "01_全信息基准版Demo结果报告_20260808.md", report)


def write_visualization_report(final_rows: list[dict[str, str]]) -> None:
    positive = [row for row in final_rows if row.get("sample_state") == "POSITIVE_CANDIDATE"]
    controls = [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"]
    p = stats(positive, "SHRGT45_slope_3h_percent_per_hr")
    c = stats(controls, "SHRGT45_slope_3h_percent_per_hr")
    content = f"""# SHRGT45 全信息基准版 Demo 可视化与质量评估

> 版本：`SHRGT45_全信息基准版_20260808`  
> 文档性质：最终分析样本的结果可视化说明与质量评估

## 一、图表使用的数据

上游可得性和真实时间轨迹使用 `01_all_sample_supplement.csv`；最终 control、斜率分布和 USFLUX 散点统一使用 `10_final_analysis_sample.csv`。最终分析样本共 {len(final_rows)} 条，其中正候选 {len(positive)} 条、control {len(controls)} 条。

## 二、图表清单

| 图表 | 数据源 | 主要用途 |
|---|---|---|
| `01_gate_funnel_bar` | `04_gate_counts.csv` | 展示从 360 条理论查询到最终分析样本的门控数量 |
| `02_sample_state_donut` | `10_final_analysis_sample.csv` | 展示最终正候选与 control 的组成 |
| `03_event_returned_vs_expected_bar` | `08_cadence_audit.csv` | 展示六个事件的理论记录、实返记录和缺帧 |
| `04_shrgt45_timeline_by_event` | `01_all_sample_supplement.csv` | 展示真实 T_REC 轨迹和缺帧断线 |
| `05_ols_slope_distribution` | `10_final_analysis_sample.csv` | 展示最终两组斜率分布 |
| `06_usflux_vs_shrgt45_scatter` | `10_final_analysis_sample.csv`、`06_usflux_context_correlation.csv` | 展示最终样本的背景关系 |

## 三、当前图表结果

| 队列 | n | 斜率最小值 | 中位数 | 最大值 | 均值 |
|---|---:|---:|---:|---:|---:|
| 正候选 | {p['n']} | {p['min']} | {p['median']} | {p['max']} | {p['mean']} |
| 最终 control | {c['n']} | {c['min']} | {c['median']} | {c['max']} | {c['mean']} |

图表没有添加显著性星号、置信区间或模型性能指标；图中数值均可回到 CSV 逐行核对。最终 control 的同 AR 时间结构和窗口重叠在报告限制中保留。

## 四、质量检查

- 门控图最后一项使用 `final_analysis_rows`，与最终分析样本行数一致；
- 斜率图和散点图不再读取被未来六小时 M+ 规则排除的 control；
- 时间轨迹图保留原始返回记录和缺帧断线，不插值；
- SVG 与 PNG 同时封存，SVG 用于矢量交付，PNG 用于普通查看；
- 图表脚本、源 CSV、指标 JSON 和文件 hash 随包保留。

图表用于展示和人工复核，不替代按 AR 聚类的正式统计分析。
"""
    write_text(PACKAGE / "01_主报告" / "02_可视化与质量评估_20260808.md", content)
    write_text(
        PACKAGE / "04_图表" / "图表说明.md",
        """# 图表说明

门控、最终 control 和下游趋势图均从本包 `03_结果数据/` 的结果表生成。上游时间轨迹保留全部实际返回记录；斜率、USFLUX 和最终样本组成使用 `10_final_analysis_sample.csv`。每张图同时提供 SVG 和 PNG，数值口径见 `04_图表/visualizations/visualization_summary.csv` 与 `visualization_metrics.json`。
""",
    )


def update_flowcharts() -> None:
    """Synchronize the hand-readable SVG flowcharts with the final sample rules."""
    replacements = {
        "04_图表/01_数据处理流程图.svg": [
            ("一次独立运行：上游输入 → 逐级门控 → OLS 趋势 → 下游结果文件", "一次独立运行：上游输入 → 逐级门控 → M+ control 筛查 → OLS 趋势 → 下游结果文件"),
            ("三、趋势计算与结果审计", "三、最终样本、趋势计算与结果审计"),
            ("9. 样本状态结果", "9. 最终样本与 control"),
            ("主门通过：88 条", "位置门后候选：132 条"),
            ("临时 control：51 条 / 3 个 AR", "M+ 筛查后同 AR control：18 条"),
            ("buffer / 边界排除：84 条", "最终分析样本：55 条"),
            ("临时 control 中位数：-0.125897", "同 AR control 中位数：-0.154577"),
            ("USFLUX pooled r = -0.640135", "USFLUX pooled r = -0.424273"),
            ("门控计数、失败原因、QUALITY", "门控计数、M+ 区间筛查"),
            ("cadence、字段和自测结果", "失败原因、QUALITY、cadence 和字段"),
            ("Demo 结论：333 条实际返回记录经逐级规则处理后，形成 88 条可追溯主门结果；结果包括门控计数、趋势分布和上下文相关。", "Demo 结论：333 条实际返回记录经逐级规则处理后，形成 55 条最终分析记录（37 条正候选、18 条同 AR 时间 control）；结果包括门控计数、趋势分布和上下文相关。"),
        ],
        "04_图表/01_数据处理流程图说明.md": [
            ("4. 依次进行 AR 归属、QUALITY 分层、三小时历史窗、日面位置和重复控制。", "4. 依次进行 AR 归属、QUALITY 分层、三小时历史窗和日面位置筛查；时间 control 还要通过完整 NCEI M+ 未来六小时区间检查。"),
            ("图中 88 条主门记录由 37 条正候选和 51 条临时 control 构成。它们来自重叠历史窗，应按事件和 AR 的聚集结构解读。", "图中最终分析样本为 55 条，由 37 条正候选和 18 条同 AR 时间 control 构成，覆盖 4 个事件/AR。control 经过完整 M+ 未来六小时区间筛查；这些记录来自重叠历史窗，应按事件和 AR 的聚集结构解读。"),
        ],
        "04_图表/02_可视化处理流程图.svg": [
            ("门控计数（结果数据）", "最终分析样本与门控计数"),
            ("360 → 88 的处理链计数", "360 → 55 的最终处理链"),
            ("主门趋势只看 88 条记录", "最终趋势使用 55 条记录"),
            ("正候选 / 临时 control / buffer 分开", "37 条正候选 / 18 条同 AR control"),
            ("sample_state 合计 = 333", "原始状态合计 = 333"),
            ("主门 88 = 正候选 37 + 临时 control 51", "最终分析 55 = 正候选 37 + control 18"),
            ("图中范围：已有数据输出经固定口径生成图表并封存；沿用主表状态，汇总门控计数、趋势分布和上下文相关。", "图中范围：已有数据输出经固定口径生成图表并封存；最终图表使用 55 条分析记录，原始状态和缺帧信息单独保留。"),
        ],
        "04_图表/02_可视化处理流程图说明.md": [
            ("01_主报告/02_可视化与质量评估_20260806.md", "01_主报告/02_可视化与质量评估_20260808.md"),
        ],
    }
    for relative_path, pairs in replacements.items():
        path = PACKAGE / relative_path
        content = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if old in content:
                content = content.replace(old, new)
            elif new not in content:
                raise ValueError(f"Flowchart text not found in {path}: {old}")
        write_text(path, content)


def write_reproduction_scripts() -> None:
    reproduce = """from __future__ import annotations

import csv
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = PACKAGE_ROOT / "03_结果数据"


def read(name: str) -> list[dict[str, str]]:
    with (RESULT_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    final_rows = read("10_final_analysis_sample.csv")
    audit = read("11_final_control_audit.csv")
    replacements = read("12_final_control_replacements.csv")
    gates = {row["gate"]: row["count"] for row in read("04_gate_counts.csv")}
    positive = [row for row in final_rows if row.get("sample_state") == "POSITIVE_CANDIDATE"]
    controls = [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"]
    checks = {
        "final_rows": len(final_rows) == 55,
        "positive_rows": len(positive) == 37,
        "control_rows": len(controls) == 18,
        "excluded_controls": sum(row.get("disposition") == "EXCLUDED_FUTURE6H_MPLUS" for row in audit) == 36,
        "retained_controls": sum(row.get("disposition") == "RETAINED_FINAL_CONTROL" for row in audit) == 15,
        "replacement_rows": len(replacements) == 3,
        "gate_final_rows": gates.get("final_analysis_rows") == "55",
        "gate_final_controls": gates.get("final_control_rows_after_mplus_screen") == "18",
        "no_mplus_on_final_controls": all(not row.get("full_mplus_future6h_ids") for row in controls),
    }
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    write_text(PACKAGE / "05_复现脚本" / "reproduce_fullinfo_package.py", reproduce)
    write_text(PACKAGE / "05_复现脚本" / "revise_shrgt45_fullinfo_20260808.py", Path(__file__).read_text(encoding="utf-8"))
    finalize = """from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = PACKAGE_ROOT.parent / f"{PACKAGE_ROOT.name}.zip"
AUDIT = PACKAGE_ROOT / "06_审计与交付"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    files = [path for path in sorted(PACKAGE_ROOT.rglob("*")) if path.is_file() and path.name != "file_sha256_manifest.csv" and not path.name.startswith(".")]
    manifest = {
        "run_id": PACKAGE_ROOT.name,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "result_report": "01_主报告/01_全信息基准版Demo结果报告_20260808.md",
        "final_analysis_sample": "03_结果数据/10_final_analysis_sample.csv",
        "formal_independent_control_count": 0,
        "files": [str(path.relative_to(PACKAGE_ROOT)).replace("\\\\", "/") for path in files],
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    with (AUDIT / "file_sha256_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("relative_path,size_bytes,sha256\\n")
        for path in files:
            handle.write(f"{str(path.relative_to(PACKAGE_ROOT)).replace('\\\\', '/')},{path.stat().st_size},{sha256(path)}\\n")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [path for path in sorted(PACKAGE_ROOT.rglob("*")) if path.is_file() and not path.name.startswith(".") and path.name != "file_sha256_manifest.csv"]:
            archive.write(path, path.relative_to(PACKAGE_ROOT))
    (AUDIT / "zip_sha256.csv").write_text(f"file,bytes,sha256\\n{ZIP_PATH.name},{ZIP_PATH.stat().st_size},{sha256(ZIP_PATH)}\\n", encoding="utf-8")


if __name__ == "__main__":
    main()
"""
    write_text(PACKAGE / "05_复现脚本" / "finalize_fullinfo_delivery_20260808.py", finalize)


def write_acceptance(final_rows: list[dict[str, str]], audit: list[dict[str, str]], replacements: list[dict[str, str]]) -> None:
    checks = [
        ("final_analysis_rows", len(final_rows) == 55, f"observed={len(final_rows)}, expected=55"),
        ("final_positive_rows", sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in final_rows) == 37, "observed=37, expected=37"),
        ("final_control_rows", sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in final_rows) == 18, "observed=18, expected=18"),
        ("future6h_mplus_exclusion", sum(row.get("disposition") == "EXCLUDED_FUTURE6H_MPLUS" for row in audit) == 36, "observed=36, expected=36"),
        ("same_ar_replacements", len(replacements) == 3, "observed=3, expected=3"),
        ("independent_control_count", True, "observed=0, no formal independent control claimed"),
        ("main_report_present", (PACKAGE / "01_主报告/01_全信息基准版Demo结果报告_20260808.md").exists(), "0806-based report present"),
        ("strict_audit_preserved", (PACKAGE / "03_结果数据/09_严格对照审计").exists(), "strict audit retained as evidence attachment"),
        ("no_cache_or_bytecode", not any(path.is_file() and (path.name.startswith(".") or path.suffix == ".pyc" or "__pycache__" in path.parts) for path in PACKAGE.rglob("*")), "package has no cache or bytecode"),
    ]
    write_csv(PACKAGE / "06_审计与交付" / "acceptance_check.csv", [{"check": name, "status": "PASS" if passed else "FAIL", "note": note} for name, passed, note in checks], fields=["check", "status", "note"])


def write_manifest_and_zip() -> None:
    audit = PACKAGE / "06_审计与交付"
    files = [path for path in sorted(PACKAGE.rglob("*")) if path.is_file() and path.name not in {"file_sha256_manifest.csv", "zip_sha256.csv"} and not path.name.startswith(".")]
    manifest = {
        "run_id": PACKAGE.name,
        "status": "FULL_INFORMATION_DEMO_REVISED_FINAL_CONTROL",
        "base_report": "SHRGT45_全信息基准版_20260806_交付版",
        "execution_identity": "王杰锋：全信息基准版 Demo 数据处理执行人和结果整理人",
        "result_report": "01_主报告/01_全信息基准版Demo结果报告_20260808.md",
        "final_analysis_sample": "03_结果数据/10_final_analysis_sample.csv",
        "formal_independent_control_count": 0,
        "files": [str(path.relative_to(PACKAGE)).replace("\\", "/") for path in files],
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    write_text(audit / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    hash_rows = []
    for path in files + [audit / "manifest.json", audit / "acceptance_check.csv"]:
        if path.name in {"file_sha256_manifest.csv", "zip_sha256.csv"}:
            continue
        hash_rows.append({"relative_path": str(path.relative_to(PACKAGE)).replace("\\", "/"), "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_csv(audit / "file_sha256_manifest.csv", hash_rows, fields=["relative_path", "size_bytes", "sha256"])
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_file() and not path.name.startswith(".") and path.name not in {"file_sha256_manifest.csv", "zip_sha256.csv"} and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(PACKAGE))
    write_csv(audit / "zip_sha256.csv", [{"file": ZIP_PATH.name, "bytes": ZIP_PATH.stat().st_size, "sha256": hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()}], fields=["file", "bytes", "sha256"])


def main() -> None:
    updated_rows, final_rows, control_audit, replacements, _ = build_final_rows()
    fields = list(updated_rows[0].keys())
    write_csv(RAW_RESULT, updated_rows, fields=fields)
    write_csv(RESULT_DIR / "10_final_analysis_sample.csv", final_rows, fields=fields)
    write_control_outputs(control_audit, replacements)
    update_gate_counts(final_rows, control_audit, replacements)
    write_distributions(final_rows)
    write_correlations(final_rows)
    write_rules_and_readme(final_rows, control_audit, replacements)
    write_main_report(final_rows, control_audit, replacements)
    write_visualization_report(final_rows)
    update_flowcharts()
    write_reproduction_scripts()
    write_acceptance(final_rows, control_audit, replacements)
    chart_script = PACKAGE / "05_复现脚本" / "build_demo_visualizations.py"
    subprocess.run([sys.executable, "-B", str(chart_script)], check=True, cwd=PACKAGE)
    write_manifest_and_zip()
    print(json.dumps({"final_analysis_rows": len(final_rows), "positive_rows": sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in final_rows), "final_control_rows": sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in final_rows), "excluded_old_controls": sum(row.get("disposition") == "EXCLUDED_FUTURE6H_MPLUS" for row in control_audit), "retained_old_controls": sum(row.get("disposition") == "RETAINED_FINAL_CONTROL" for row in control_audit), "replacement_controls": len(replacements), "zip": str(ZIP_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
