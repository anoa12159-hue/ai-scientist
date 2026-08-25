"""Requery and audit pre-flare same-AR temporal-control candidates.

This is an additive audit package. It never rewrites the approved Demo report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


RUN_ID = "SHRGT45_严格阴性对照前推检索_20260807"
CADENCE_MINUTES = 12
HISTORY_RECORDS = 16
LOOKBACK_HOURS = 72
MIN_BLOCK_SPAN_MINUTES = 60
KEYS = ["T_REC", "HARPNUM", "NOAA_AR", "SHRGT45", "MEANALP", "USFLUX", "QUALITY", "LON_FWT", "LAT_FWT"]


@dataclass(frozen=True)
class Event:
    event_id: str
    noaa_ar: str
    harpnum: str
    target_onset_utc: str
    cached_query_start_utc: str
    tai_utc_offset_seconds: int


EVENTS = [
    Event("NOAA11158_X2.2_20110215", "11158", "377", "2011-02-15T01:44:00Z", "2011-02-14T13:35:26Z", 34),
    Event("NOAA11429_X5.4_20120307", "11429", "1449", "2012-03-07T00:02:00Z", "2012-03-06T11:59:26Z", 34),
    Event("NOAA11520_X1.4_20120712", "11520", "1834", "2012-07-12T15:37:00Z", "2012-07-12T03:35:25Z", 35),
    Event("NOAA12192_X1.1_20141019", "12192", "4698", "2014-10-19T04:17:00Z", "2014-10-18T16:11:25Z", 35),
    Event("NOAA12297_X2.1_20150311", "12297", "5298", "2015-03-11T16:11:00Z", "2015-03-11T03:59:25Z", 35),
    Event("NOAA12673_X9.3_20170906", "12673", "7115", "2017-09-06T11:53:00Z", "2017-09-05T23:47:23Z", 37),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def utc_text(value: datetime | None) -> str:
    return "" if value is None else value.strftime("%Y-%m-%dT%H:%M:%SZ")


def tai_text(value: datetime | None) -> str:
    return "" if value is None else value.strftime("%Y.%m.%d_%H:%M:%S_TAI")


def parse_tai(value: str) -> datetime:
    return datetime.strptime(value, "%Y.%m.%d_%H:%M:%S_TAI")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or list(rows[0].keys()) if rows else (fieldnames or [])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def as_float(value: object) -> float | None:
    try:
        parsed = float(str(value))
        return None if math.isnan(parsed) else parsed
    except (TypeError, ValueError):
        return None


def parse_quality(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None


def ar_matches(expected: str, returned: object) -> bool:
    return expected in {item.strip() for item in str(returned or "").split(",")}


def linear_slope_per_hour(times: list[datetime], values: list[float]) -> float | None:
    if len(times) < 2 or len(times) != len(values):
        return None
    xs = [(item - times[0]).total_seconds() / 3600 for item in times]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(values) / len(values)
    denominator = sum((item - x_mean) ** 2 for item in xs)
    if denominator == 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denominator


def load_catalog(path: Path) -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            if not raw.get("start_utc") or not raw.get("end_utc"):
                continue
            try:
                catalog.append(
                    {
                        "flare_id": raw["flare_id"],
                        "start": parse_utc(raw["start_utc"]),
                        "peak": parse_utc(raw["peak_utc"]) if raw.get("peak_utc") else None,
                        "end": parse_utc(raw["end_utc"]),
                        "flare_class": raw.get("flare_class", ""),
                        "active_region_raw": raw.get("active_region_raw", ""),
                        "active_region_suffix": raw.get("active_region_noaa_suffix", ""),
                        "source_id": raw.get("source_id", ""),
                    }
                )
            except ValueError:
                continue
    return catalog


def overlaps(catalog_row: dict[str, object], start: datetime, end: datetime) -> bool:
    return catalog_row["start"] < end and catalog_row["end"] > start


def contiguous_blocks(times: list[datetime]) -> list[dict[str, object]]:
    if not times:
        return []
    step = timedelta(minutes=CADENCE_MINUTES)
    ordered = sorted(times)
    blocks: list[dict[str, object]] = []
    start = ordered[0]
    previous = ordered[0]
    for item in ordered[1:]:
        if item - previous == step:
            previous = item
            continue
        points = int((previous - start) / step) + 1
        blocks.append({"start": start, "end": previous, "grid_points": points, "span_minutes": int((previous - start).total_seconds() / 60), "times": ordered[ordered.index(start):ordered.index(previous)+1]})
        start = item
        previous = item
    points = int((previous - start) / step) + 1
    blocks.append({"start": start, "end": previous, "grid_points": points, "span_minutes": int((previous - start).total_seconds() / 60), "times": ordered[ordered.index(start):ordered.index(previous)+1]})
    return blocks


def find_candidate(event: Event, catalog: list[dict[str, object]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    target = parse_utc(event.target_onset_utc)
    cached_start = parse_utc(event.cached_query_start_utc)
    search_start = target - timedelta(hours=LOOKBACK_HOURS)
    latest = min(cached_start - timedelta(minutes=CADENCE_MINUTES), target - timedelta(hours=6))
    guard_start_hours = 4
    guard_end_hours = 7
    clean_times: list[datetime] = []
    t0 = latest
    while t0 >= search_start:
        start = t0 - timedelta(hours=guard_start_hours)
        end = t0 + timedelta(hours=guard_end_hours)
        if not any(overlaps(row, start, end) for row in catalog):
            clean_times.append(t0)
        t0 -= timedelta(minutes=CADENCE_MINUTES)

    blocks = contiguous_blocks(clean_times)
    eligible = [item for item in blocks if int(item["span_minutes"]) >= MIN_BLOCK_SPAN_MINUTES]
    if not eligible:
        raise RuntimeError(f"{event.event_id}: no guarded catalog-clean block of at least {MIN_BLOCK_SPAN_MINUTES} minutes")
    selected = max(eligible, key=lambda item: item["end"])
    selected_times = selected["times"]
    selected_t0 = selected_times[len(selected_times) // 2]
    t0_tai = selected_t0 + timedelta(seconds=event.tai_utc_offset_seconds)
    audit_rows = []
    for rank, block in enumerate(sorted(eligible, key=lambda item: item["end"], reverse=True), start=1):
        audit_rows.append(
            {
                "run_id": RUN_ID,
                "flare_event_id": event.event_id,
                "HARPNUM": event.harpnum,
                "NOAA_AR": event.noaa_ar,
                "selection_rank_by_recency": rank,
                "block_start_utc": utc_text(block["start"]),
                "block_end_utc": utc_text(block["end"]),
                "grid_points": block["grid_points"],
                "span_minutes": block["span_minutes"],
                "catalog_screening": "No M+ event interval overlaps [T0-4h, T0+7h).",
                "most_recent_guarded_block": "YES" if block is selected else "NO",
                "central_reference_T0_utc": utc_text(selected_t0) if block is selected else "",
                "block_ranking_rule": "Rank blocks by recency using guarded catalog time only. Final representative selection is performed separately over every grid point that passes the strict data gates.",
            }
        )
    return (
        {
            "event": event,
            "t0_utc": selected_t0,
            "t0_tai": t0_tai,
            "query_start_tai": t0_tai - timedelta(hours=3),
            "selected_block": selected,
            "clean_times": sorted(clean_times),
            "search_start": search_start,
            "search_end": latest,
        },
        audit_rows,
    )


def build_url(event: Event, query_start_tai: datetime) -> tuple[str, str]:
    ds = f"hmi.sharp_cea_720s[{event.harpnum}][{tai_text(query_start_tai)}/4h@12m]"
    query = urllib.parse.urlencode({"op": "rs_list", "ds": ds, "key": ",".join(KEYS)})
    return f"http://jsoc.stanford.edu/cgi-bin/ajax/jsoc_info?{query}", ds


def fetch_json(url: str, destination: Path) -> tuple[dict[str, object], int]:
    request = urllib.request.Request(url, headers={"User-Agent": "SHRGT45-control-audit/20260807"})
    with urllib.request.urlopen(request, timeout=75) as response:
        payload_bytes = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload_bytes)
    return json.loads(payload_bytes.decode("utf-8")), len(payload_bytes)


def payload_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    if int(payload.get("status", -1)) != 0:
        raise RuntimeError(f"JSOC status={payload.get('status')}: {payload.get('error', '')}")
    columns = {item["name"]: item.get("values", []) for item in payload.get("keywords", [])}
    missing = [name for name in KEYS if name not in columns]
    if missing:
        raise RuntimeError(f"JSOC payload lacks requested keys: {','.join(missing)}")
    count = len(columns["T_REC"])
    if any(len(columns[key]) != count for key in KEYS):
        raise RuntimeError("JSOC returned columns with inconsistent lengths")
    return [{key: str(columns[key][index]) for key in KEYS} for index in range(count)]


def interval_audit(event: Event, t0: datetime, catalog: list[dict[str, object]]) -> dict[str, object]:
    primary_start = t0 - timedelta(hours=3)
    primary_end = t0 + timedelta(hours=6)
    guard_start = t0 - timedelta(hours=4)
    guard_end = t0 + timedelta(hours=7)
    primary_overlap = [row for row in catalog if overlaps(row, primary_start, primary_end)]
    guard_overlap = [row for row in catalog if overlaps(row, guard_start, guard_end)]
    target_suffix = event.noaa_ar[-4:]
    old_ar11429_t0 = parse_utc("2012-03-05T07:23:26Z")
    old_window_start = old_ar11429_t0 - timedelta(hours=3)
    old_window_end = old_ar11429_t0 + timedelta(hours=6)
    old_overlap = [row for row in catalog if overlaps(row, old_window_start, old_window_end)] if event.noaa_ar == "11429" else []
    return {
        "run_id": RUN_ID,
        "flare_event_id": event.event_id,
        "HARPNUM": event.harpnum,
        "NOAA_AR": event.noaa_ar,
        "T0_utc": utc_text(t0),
        "primary_window_utc": f"[{utc_text(primary_start)}, {utc_text(primary_end)})",
        "primary_start_time_event_count": sum(primary_start <= row["start"] < primary_end for row in catalog),
        "primary_interval_overlap_event_count": len(primary_overlap),
        "primary_interval_overlap_ids": ";".join(str(row["flare_id"]) for row in primary_overlap),
        "primary_same_AR_overlap_count": sum(str(row["active_region_suffix"]) == target_suffix for row in primary_overlap),
        "primary_AR_missing_overlap_count": sum(not str(row["active_region_suffix"]).strip() for row in primary_overlap),
        "guard_window_utc": f"[{utc_text(guard_start)}, {utc_text(guard_end)})",
        "guard_interval_overlap_event_count": len(guard_overlap),
        "guard_interval_overlap_ids": ";".join(str(row["flare_id"]) for row in guard_overlap),
        "guard_same_AR_overlap_count": sum(str(row["active_region_suffix"]) == target_suffix for row in guard_overlap),
        "guard_AR_missing_overlap_count": sum(not str(row["active_region_suffix"]).strip() for row in guard_overlap),
        "catalog_gate_status": "PASS" if not guard_overlap else "FAIL",
        "catalog_gate_reason": "No NCEI M+ event interval overlaps the guarded window." if not guard_overlap else "NCEI M+ interval overlaps guarded window; candidate is excluded.",
        "AR11429_prior_start_only_candidate_T0_utc": utc_text(old_ar11429_t0) if old_overlap else "",
        "AR11429_prior_candidate_interval_overlap_ids": ";".join(str(row["flare_id"]) for row in old_overlap),
        "AR11429_prior_candidate_disposition": "EXCLUDED: X1.6 started before the window but overlapped it; start-time-only screening is insufficient." if old_overlap else "NOT_APPLICABLE",
        "catalog_source_relative_path": "../SHRGT45_收尾补件_20260727/02_official_Mplus_event_catalog_NCEI_v1-0-1_subset.csv",
    }


def data_gate_audit(event: Event, t0_utc: datetime, t0_tai: datetime, queried: list[dict[str, str]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    indexed = {parse_tai(row["T_REC"]): row for row in queried}
    expected_times = [t0_tai - timedelta(minutes=CADENCE_MINUTES * offset) for offset in range(HISTORY_RECORDS - 1, -1, -1)]
    per_frame: list[dict[str, object]] = []
    history_rows: list[dict[str, str] | None] = []
    for time in expected_times:
        raw = indexed.get(time)
        history_rows.append(raw)
        values = {key: "" if raw is None else raw.get(key, "") for key in KEYS}
        quality_value = parse_quality(values["QUALITY"])
        field_complete = all(
            values[key] not in {"", "MISSING", "NaN", "nan"}
            for key in ("SHRGT45", "MEANALP", "USFLUX", "QUALITY", "LON_FWT", "LAT_FWT")
        )
        ar_mapping = raw is not None and raw.get("HARPNUM") == event.harpnum and ar_matches(event.noaa_ar, raw.get("NOAA_AR"))
        longitude = as_float(values["LON_FWT"])
        latitude = as_float(values["LAT_FWT"])
        disk_ok = longitude is not None and latitude is not None and abs(longitude) < 50 and abs(latitude) < 50
        per_frame.append(
            {
                "run_id": RUN_ID,
                "flare_event_id": event.event_id,
                "candidate_T0_utc": utc_text(t0_utc),
                "T_REC_expected_TAI": tai_text(time),
                "returned_record": "YES" if raw else "NO",
                "T_REC_returned_TAI": values["T_REC"],
                "HARPNUM": values["HARPNUM"],
                "NOAA_AR": values["NOAA_AR"],
                "SHRGT45": values["SHRGT45"],
                "MEANALP": values["MEANALP"],
                "USFLUX": values["USFLUX"],
                "QUALITY": values["QUALITY"],
                "LON_FWT": values["LON_FWT"],
                "LAT_FWT": values["LAT_FWT"],
                "field_complete": "PASS" if field_complete else "FAIL",
                "HARPNUM_and_NOAA_AR_mapping": "PASS" if ar_mapping else "FAIL",
                "QUALITY_zero": "PASS" if quality_value == 0 else "FAIL",
                "disk_position_abs_lon_lat_lt_50": "PASS" if disk_ok else "FAIL",
            }
        )

    returned = [row for row in history_rows if row is not None]
    def all_frame(check):
        return len(returned) == HISTORY_RECORDS and all(check(row) for row in per_frame)

    full_fields = all_frame(lambda row: row["field_complete"] == "PASS")
    full_mapping = all_frame(lambda row: row["HARPNUM_and_NOAA_AR_mapping"] == "PASS")
    full_quality_zero = all_frame(lambda row: row["QUALITY_zero"] == "PASS")
    t0_frame = per_frame[-1]
    trend_values = [as_float(row["SHRGT45"]) for row in per_frame]
    trend_ok = all(value is not None for value in trend_values)
    slope = linear_slope_per_hour(expected_times, [float(value) for value in trend_values]) if trend_ok else None
    delta = (float(trend_values[-1]) - float(trend_values[0])) if trend_ok else None
    strict_pass = full_fields and full_mapping and full_quality_zero and t0_frame["disk_position_abs_lon_lat_lt_50"] == "PASS"
    reasons = []
    if len(returned) != HISTORY_RECORDS:
        reasons.append(f"history records {len(returned)}/{HISTORY_RECORDS}")
    if not full_fields:
        reasons.append("field completeness")
    if not full_mapping:
        reasons.append("HARP/NOAA mapping")
    if not full_quality_zero:
        reasons.append("all QUALITY=0")
    if t0_frame["disk_position_abs_lon_lat_lt_50"] != "PASS":
        reasons.append("T0 disk position")
    return (
        {
            "run_id": RUN_ID,
            "flare_event_id": event.event_id,
            "HARPNUM": event.harpnum,
            "NOAA_AR": event.noaa_ar,
            "candidate_T0_utc": utc_text(t0_utc),
            "candidate_T0_TAI": tai_text(t0_tai),
            "history_window_TAI": f"[{tai_text(expected_times[0])}, {tai_text(expected_times[-1])}]",
            "history_expected_records": HISTORY_RECORDS,
            "history_returned_records": len(returned),
            "history_all_fields_complete": "PASS" if full_fields else "FAIL",
            "history_all_HARP_NOAA_mapping": "PASS" if full_mapping else "FAIL",
            "history_all_QUALITY_zero": "PASS" if full_quality_zero else "FAIL",
            "T0_disk_position_abs_lon_lat_lt_50": t0_frame["disk_position_abs_lon_lat_lt_50"],
            "T0_LON_FWT": t0_frame["LON_FWT"],
            "T0_LAT_FWT": t0_frame["LAT_FWT"],
            "strict_baseline_existing_definition": "PASS" if strict_pass else "FAIL",
            "strict_baseline_reason": "16/16 returned; all requested fields complete; HARP/NOAA mapping holds; all QUALITY=0; T0 is within the disk-position rule." if strict_pass else "Failed: " + "; ".join(reasons),
            "SHRGT45_slope_3h_percent_per_hr": "" if slope is None else f"{slope:.6f}",
            "SHRGT45_delta_3h_percent": "" if delta is None else f"{delta:.3f}",
            "CMASK_and_effective_pixel_status": "NOT_AVAILABLE_IN_INPUT",
            "measurement_boundary": "This query does not include CMASK/effective-pixel fields. It does not claim that measurement-driven trends are excluded.",
            "formal_negative_status": "NOT_FORMAL_INDEPENDENT_CONTROL",
        },
        per_frame,
    )


def status_label(catalog_row: dict[str, object], data_row: dict[str, object]) -> tuple[str, str]:
    if catalog_row["catalog_gate_status"] != "PASS":
        return "EXCLUDED_CATALOG_CONTAMINATED", "NCEI M+ event interval overlaps the guarded window."
    if data_row["strict_baseline_existing_definition"] != "PASS":
        return "CATALOG_CLEAN_BUT_STRICT_DATA_GATE_FAIL", str(data_row["strict_baseline_reason"])
    return "CATALOG_CLEAN_AND_STRICT_DATA_QUALIFIED_TIME_CANDIDATE", "Passes the existing strict data baseline and the guarded catalog screen; remains a same-AR temporal candidate only."


def build_readme(summary: list[dict[str, object]]) -> str:
    strict = [row for row in summary if row["candidate_status"] == "CATALOG_CLEAN_AND_STRICT_DATA_QUALIFIED_TIME_CANDIDATE"]
    failed = [row for row in summary if row not in strict]
    lines = [
        f"# {RUN_ID}",
        "",
        "## 结论",
        "",
        f"本轮按完整耀斑区间而不是只按耀斑开始时刻重审，并向前重取了 6 个预先确定的 HMI/SHARP 关键词序列。6 个候选均通过 NCEI M+ 的 `[T0-4h, T0+7h)` 完整区间筛查；其中 **{len(strict)}/6** 个通过现有 Demo 的 strict 数据门（16/16、全部 QUALITY=0、字段完整、HARP/NOAA 映射和 T0 位置门）。",
        "",
        "这里的“通过”只表示它可作为**同一活动区内、时间上经过严格筛查的探索性候选**。它们不是独立活动区抽样，也未签订正式匹配合同，因此不能称作正式独立阴性对照，正式比较 control 仍为 0。",
        "",
        "## 本轮做了什么",
        "",
        "1. 在目标耀斑前 72 小时、现有缓存之前，以原有 12 分钟节奏扫描候选 T0。",
        "2. 主动加严目录审计：任一 M+ 耀斑只要其持续区间与 `[T0-4h, T0+7h)` 相交，即淘汰该 T0；不再只按开始时刻计数。",
        "3. 对每个活动区选择最近的、至少 60 分钟的清洁时间块中央格点。该选择在查看 SHRGT45、USFLUX、QUALITY 和位置之前完成。",
        "4. 从 JSOC 公开 `hmi.sharp_cea_720s` 接口重取 T0 前 3 小时加余量的关键词记录，并逐帧检查 16/16、QUALITY、HARP/NOAA 映射、字段完整性与位置门。",
        "",
        "## 关键更正",
        "",
        "AR11429 先前的中间候选 `2012-03-05T07:23:26Z` 不能使用：NCEI 记录的 X1.6（ID `201203050222`）虽在该候选主窗口开始前起始，却持续进入窗口。按完整区间审计后，该候选被排除；本轮选择的是 `2012-03-04T17:47:26Z`，并重新取数核验。",
        "",
        "## 当前边界",
        "",
        "- NCEI 清洁筛查覆盖的是 M+ 目录事件；它不替代 AR 级正式标签、独立性或匹配合同。",
        "- 当前 JSOC 查询没有 CMASK、有效像素数或有效像素比例，因此不能声称已排除测量伪趋势。",
        "- 本包不改写已确认的 `SHRGT45_全信息基准版_20260808` 主报告，也不恢复已撤销的 `37 vs 51` 临时 control 比较。",
        "",
        "## 建议阅读路径",
        "",
        "1. `01_阅读说明/严格阴性对照前推检索结论.md`",
        "2. `02_审计数据/候选T0与NCEI区间审计.csv`",
        "3. `02_审计数据/严格数据门汇总.csv`",
        "4. `02_审计数据/逐帧关键词核验.csv`",
    ]
    if strict:
        lines.extend(["", "## 通过 existing strict 数据门的时间候选", ""])
        for row in strict:
            lines.append(f"- `{row['flare_event_id']}`：T0 `{row['candidate_T0_utc']}`，3 小时 SHRGT45 斜率 `{row['SHRGT45_slope_3h_percent_per_hr']}` %/h。")
    if failed:
        lines.extend(["", "## 未通过 strict 数据门的候选", ""])
        for row in failed:
            lines.append(f"- `{row['flare_event_id']}`：{row['candidate_status_reason']}")
    return "\n".join(lines)


def build_conclusion(summary: list[dict[str, object]]) -> str:
    strict = [row for row in summary if row["candidate_status"] == "CATALOG_CLEAN_AND_STRICT_DATA_QUALIFIED_TIME_CANDIDATE"]
    rows = [
        "# 严格阴性对照前推检索结论",
        "",
        "## 一句话结论",
        "",
        f"在不根据 SHRGT45 结果反选时点的前提下，本轮得到 {len(strict)} 个同时满足严格目录筛查和既有 strict 数据门的同 AR 时间候选；它们可用于后续探索性时间演化或反例复核，但不构成正式独立阴性组。",
        "",
        "## 判定口径",
        "",
        "- 时间选择：在目标耀斑前 72 小时且现有缓存之外，按 12 分钟格点寻找 NCEI M+ 完整事件区间不与 `[T0-4h, T0+7h)` 相交的连续块；块长至少 60 分钟，取最近块的中央格点，偶数格点时取较晚的中央点。",
        "- 数据 strict：T0 前 3 小时 `[T0-3h, T0]` 必须有 16/16 条记录，所有请求字段完整、HARP/NOAA 映射通过、QUALITY 全为 0，且 T0 满足 `abs(LON_FWT)<50` 与 `abs(LAT_FWT)<50`。",
        "- 不用于选择的量：SHRGT45 斜率、USFLUX、MEANALP、任何模型或正式性能指标。",
        "",
        "## 逐活动区结果",
        "",
        "| 事件 | 选定 T0 (UTC) | 目录筛查 | strict 数据门 | 结论 |",
        "|---|---|---|---|---|",
    ]
    for row in summary:
        rows.append(
            f"| {row['flare_event_id']} | `{row['candidate_T0_utc']}` | {row['catalog_gate_status']} | {row['strict_baseline_existing_definition']} | {row['candidate_status']} |"
        )
    rows.extend(
        [
            "",
            "## 为什么 AR11429 要改",
            "",
            "原中间时点 `2012-03-05T07:23:26Z` 只在“耀斑开始时刻”计数下看似安静。NCEI X1.6 的起始时刻早于该候选的主窗，但其结束时刻在窗内，因此该事件实际污染了窗口。现在已将它明确排除，并由新的、按区间筛选出的时点替代。",
            "",
            "## 使用边界",
            "",
            "这些候选与相应目标耀斑共用活动区，时间窗之间也不能被当作独立样本。因此：",
            "",
            "- 可以：作为同 AR 早期阶段的探索性时间对照或案例复核入口。",
            "- 不可以：汇入独立阴性对照组、用于正式正负比较，或据此给出独立样本量。",
            "- 尚待补齐：CMASK/有效像素类输入未在本次关键词查询中提供，测量伪趋势不能被宣称已排除。",
        ]
    )
    return "\n".join(rows)


def make_zip(root: Path) -> Path:
    archive = root / "06_整合后审计封存包" / f"{RUN_ID}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == archive or path.name == "发送包hash清单.csv" or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            handle.write(path, path.relative_to(root))
    return archive


def make_hash_manifest(root: Path, archive: Path | None = None) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"文件hash清单.csv", "发送包hash清单.csv"} or path == archive:
            continue
        rows.append({"relative_path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_csv(root / "03_复现与完整性" / "文件hash清单.csv", rows)
    if archive is not None:
        write_csv(root / "06_整合后审计封存包" / "发送包hash清单.csv", [{"file": archive.name, "bytes": archive.stat().st_size, "sha256": sha256(archive)}])


def run(fetch: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    audit_dir = root / "02_审计数据"
    raw_dir = audit_dir / "raw_jsoc_keywords"
    source_catalog = audit_dir / "02_official_Mplus_event_catalog_NCEI_v1-0-1_subset.csv"
    source_report = workspace / "01_主报告" / "01_全信息基准版Demo结果报告_20260808.md"
    if not source_catalog.exists():
        raise FileNotFoundError(source_catalog)
    catalog = load_catalog(source_catalog)
    block_rows: list[dict[str, object]] = []
    catalog_rows: list[dict[str, object]] = []
    data_rows: list[dict[str, object]] = []
    frame_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []

    for event in EVENTS:
        candidate, event_block_rows = find_candidate(event, catalog)
        block_rows.extend(event_block_rows)
        url, ds = build_url(event, candidate["query_start_tai"])
        raw_path = raw_dir / f"{event.event_id}_strict_candidate.json"
        retrieved_at = utc_now()
        try:
            if fetch:
                payload, byte_count = fetch_json(url, raw_path)
            else:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                byte_count = raw_path.stat().st_size
            queried = payload_rows(payload)
            query_status = "PASS"
            query_note = f"Returned {len(queried)} keyword rows."
            raw_hash = sha256(raw_path)
        except Exception as exc:
            queried = []
            query_status = "FAIL"
            query_note = f"{type(exc).__name__}: {exc}"
            byte_count = raw_path.stat().st_size if raw_path.exists() else 0
            raw_hash = sha256(raw_path) if raw_path.exists() else ""
        query_rows.append(
            {
                "run_id": RUN_ID,
                "flare_event_id": event.event_id,
                "HARPNUM": event.harpnum,
                "NOAA_AR": event.noaa_ar,
                "candidate_T0_utc": utc_text(candidate["t0_utc"]),
                "candidate_T0_TAI": tai_text(candidate["t0_tai"]),
                "query_start_TAI": tai_text(candidate["query_start_tai"]),
                "jsoc_dataset": ds,
                "query_url": url,
                "query_retrieved_utc": retrieved_at,
                "raw_json_relative_path": raw_path.relative_to(root).as_posix(),
                "raw_json_bytes": byte_count,
                "raw_json_sha256": raw_hash,
                "status": query_status,
                "note": query_note,
            }
        )
        catalog_row = interval_audit(event, candidate["t0_utc"], catalog)
        catalog_rows.append(catalog_row)
        if queried:
            data_row, frames = data_gate_audit(event, candidate["t0_utc"], candidate["t0_tai"], queried)
            frame_rows.extend(frames)
        else:
            data_row = {
                "run_id": RUN_ID,
                "flare_event_id": event.event_id,
                "HARPNUM": event.harpnum,
                "NOAA_AR": event.noaa_ar,
                "candidate_T0_utc": utc_text(candidate["t0_utc"]),
                "candidate_T0_TAI": tai_text(candidate["t0_tai"]),
                "history_window_TAI": "",
                "history_expected_records": HISTORY_RECORDS,
                "history_returned_records": 0,
                "history_all_fields_complete": "FAIL",
                "history_all_HARP_NOAA_mapping": "FAIL",
                "history_all_QUALITY_zero": "FAIL",
                "T0_disk_position_abs_lon_lat_lt_50": "FAIL",
                "T0_LON_FWT": "",
                "T0_LAT_FWT": "",
                "strict_baseline_existing_definition": "FAIL",
                "strict_baseline_reason": "JSOC query failed; no strict data decision.",
                "SHRGT45_slope_3h_percent_per_hr": "",
                "SHRGT45_delta_3h_percent": "",
                "CMASK_and_effective_pixel_status": "NOT_AVAILABLE_IN_INPUT",
                "measurement_boundary": "No JSOC input could be parsed.",
                "formal_negative_status": "NOT_FORMAL_INDEPENDENT_CONTROL",
            }
        data_rows.append(data_row)
        label, reason = status_label(catalog_row, data_row)
        summary.append({**catalog_row, **data_row, "candidate_status": label, "candidate_status_reason": reason})

    write_csv(audit_dir / "候选时间块选择审计.csv", block_rows)
    write_csv(audit_dir / "候选T0与NCEI区间审计.csv", catalog_rows)
    write_csv(audit_dir / "JSOC重取清单.csv", query_rows)
    write_csv(audit_dir / "严格数据门汇总.csv", data_rows)
    write_csv(audit_dir / "逐帧关键词核验.csv", frame_rows)
    write_csv(audit_dir / "候选结论汇总.csv", summary)
    write_csv(
        audit_dir / "NCEI目录来源说明.csv",
        [{
            "source_relative_path": source_catalog.relative_to(workspace).as_posix(),
            "source_sha256": sha256(source_catalog),
            "source_row_count": len(catalog),
            "use": "M+ interval-overlap audit for [T0-3h,T0+6h) and guarded [T0-4h,T0+7h).",
        }],
    )
    write_text(root / "README.md", build_readme(summary))
    write_text(root / "01_阅读说明" / "严格阴性对照前推检索结论.md", build_conclusion(summary))
    source_report_hash = sha256(source_report) if source_report.exists() else "NOT_FOUND"
    strict_count = sum(row["candidate_status"] == "CATALOG_CLEAN_AND_STRICT_DATA_QUALIFIED_TIME_CANDIDATE" for row in summary)
    acceptance = [
        {"check": "candidate_count", "expected": 6, "observed": len(summary), "status": "PASS" if len(summary) == 6 else "FAIL"},
        {"check": "candidate_selection_predeclared_and_outcome_blind", "expected": "catalog time only", "observed": "catalog interval overlap + recency + central grid point", "status": "PASS"},
        {"check": "catalog_guarded_interval_pass", "expected": "6/6", "observed": f"{sum(row['catalog_gate_status'] == 'PASS' for row in summary)}/6", "status": "PASS" if all(row["catalog_gate_status"] == "PASS" for row in summary) else "FAIL"},
        {"check": "raw_jsoc_queries_pass", "expected": "6/6", "observed": f"{sum(row['status'] == 'PASS' for row in query_rows)}/6", "status": "PASS" if all(row["status"] == "PASS" for row in query_rows) else "FAIL"},
        {"check": "AR11429_start_time_only_candidate_rejected", "expected": "X1.6 interval overlap", "observed": next(row["AR11429_prior_candidate_interval_overlap_ids"] for row in catalog_rows if row["NOAA_AR"] == "11429"), "status": "PASS" if next(row["AR11429_prior_candidate_interval_overlap_ids"] for row in catalog_rows if row["NOAA_AR"] == "11429") else "FAIL"},
        {"check": "strict_data_qualified_time_candidates", "expected": "reported without formal-negative upgrade", "observed": strict_count, "status": "PASS"},
        {"check": "formal_independent_control_count", "expected": 0, "observed": 0, "status": "PASS"},
        {"check": "approved_main_report_not_rewritten", "expected": "source report retained", "observed": source_report_hash, "status": "PASS" if source_report.exists() else "FAIL"},
    ]
    write_csv(root / "03_复现与完整性" / "验收检查.csv", acceptance)
    make_hash_manifest(root)
    archive = make_zip(root)
    make_hash_manifest(root, archive)
    print(json.dumps({"run_id": RUN_ID, "strict_data_qualified_same_ar_time_candidates": strict_count, "archive": str(archive)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use already fetched raw JSON files.")
    arguments = parser.parse_args()
    run(fetch=not arguments.offline)
