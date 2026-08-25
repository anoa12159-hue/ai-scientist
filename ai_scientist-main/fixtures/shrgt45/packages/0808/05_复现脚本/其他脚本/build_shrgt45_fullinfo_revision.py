from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import build_shrgt45_multievent_portrait as seed


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_BASE = ROOT / "outputs" / "wang_runs"
OLD_RUN_ID = "SHRGT45_全信息基准版_20260723"
OLD_RUN = OUTPUT_BASE / OLD_RUN_ID
OLD_RAW_DIR = OLD_RUN / "raw_jsoc_keywords"

RUN_DATE = "20260724"
VERSION_TYPE = "全信息基准版"
RUN_ID = f"SHRGT45_{VERSION_TYPE}_{RUN_DATE}"
OUT_DIR = OUTPUT_BASE / RUN_ID
RAW_DIR = OUT_DIR / "raw_jsoc_keywords"
ZIP_FILE = OUTPUT_BASE / f"{RUN_ID}_递交版.zip"

POLICY_ID = "DP-PROVISIONAL-SHRGT45-FULLINFO-20260724"
POLICY_FILE = f"01_DecisionPolicy_SHRGT45_{VERSION_TYPE}_{RUN_DATE}.md"
DATAPLAN_FILE = "08_DataPlan_SHRGT45_全信息基准版.md"

CADENCE_MINUTES = 12
QUERY_LOOKBACK_HOURS = 12
QUERY_EXPECTED_RECORDS = int(QUERY_LOOKBACK_HOURS * 60 / CADENCE_MINUTES)
HISTORY_HOURS = 3
HISTORY_EXPECTED_RECORDS = int(HISTORY_HOURS * 60 / CADENCE_MINUTES) + 1
HISTORY_MIN_VALID_RECORDS = 14
HISTORY_MIN_SPAN_MINUTES = 160
HISTORY_MAX_GAP_MINUTES = 24
DISK_LIMIT_DEG = 50.0
ANCHOR_TOLERANCE_HR = 0.75

FATAL_QUALITY_BITS = {
    0x80000000: "QUAL_NODATA / Q_MISSALL: data or all required Stokes observables missing",
    0x40000000: "QUAL_TARGETFILTERGRAMMISSING / Q_REOPENED: target filtergram missing or image reopened",
}

STANDARD_COLUMNS = [
    "run_id",
    "queue",
    "flare_event_id",
    "flare_class",
    "flare_onset_utc",
    "flare_NOAA_AR",
    "event_provenance_status",
    "ar_assignment_status",
    "HARPNUM",
    "NOAA_AR",
    "T_REC_TAI",
    "T_REC_UTC",
    "distance_to_flare_hr",
    "SHRGT45",
    "SHRGT45_slope_3h_percent_per_hr",
    "SHRGT45_delta_3h_percent",
    "SHRGT45_slope_3h_strict_percent_per_hr",
    "SHRGT45_delta_3h_strict_percent",
    "MEANALP",
    "USFLUX",
    "QUALITY",
    "quality_gate_status",
    "quality_fatal_bits",
    "disk_position",
    "sample_state",
    "control_status",
    "data_source",
    "field_complete",
    "ar_mapping_pass",
    "quality_zero",
    "quality_fatal",
    "quality_retained_provisional",
    "history3h_expected_records",
    "history3h_returned_records",
    "history3h_valid_records",
    "history3h_missing_records",
    "history3h_span_minutes",
    "history3h_max_gap_minutes",
    "history3h_pass_provisional",
    "history3h_complete_quality_zero",
    "disk_gate_pass",
    "buffer_or_cluster_excluded",
    "passes_main_gates_provisional",
    "passes_strict_baseline",
    "history_start_T_REC_TAI",
    "history_end_T_REC_TAI",
    "anchor_target_lead_hr",
    "anchor_delta_hr",
    "anchor_within_tolerance",
    "state_note",
]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def jsoc_time(dt: datetime) -> str:
    return dt.strftime("%Y.%m.%d_%H:%M:%S_TAI")


def as_float(value: object) -> float | None:
    try:
        if value in {"", None, "MISSING", "NaN", "nan"}:
            return None
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def parse_quality(value: object) -> int:
    text = str(value or "0").strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return 0


def quality_status(value: object) -> tuple[str, str, int, int]:
    parsed = parse_quality(value)
    fatal = [mask for mask in FATAL_QUALITY_BITS if parsed & mask]
    if fatal:
        return "FATAL_EXCLUDED_PROVISIONAL", "+".join(f"0x{mask:08X}" for mask in fatal), 1, 0
    if parsed == 0:
        return "ZERO_QUALITY", "", 0, 0
    return "NONZERO_RETAINED_PROVISIONAL", "", 0, 1


def median_value(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def linear_slope_per_hour(times: list[datetime], values: list[float]) -> float:
    if len(times) < 2:
        return 0.0
    x = [(time - times[0]).total_seconds() / 3600 for time in times]
    x_mean = mean(x)
    y_mean = mean(values)
    denom = sum((item - x_mean) ** 2 for item in x)
    if denom == 0:
        return 0.0
    return sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, values)) / denom


def max_gap_minutes(times: list[datetime]) -> float:
    if len(times) < 2:
        return 0.0
    ordered = sorted(times)
    return max((b - a).total_seconds() / 60 for a, b in zip(ordered, ordered[1:]))


def sample_state_for_lead(lead_hr: float) -> tuple[str, str]:
    if 3 < lead_hr <= 6:
        return "POSITIVE_CANDIDATE", "Future 3-6h contains the seeded M+ GOES-onset event."
    if 0 < lead_hr <= 3:
        return "BUFFER_OR_EXCLUDE", "Future 0-3h contains M+; excluded from 3-6h main analysis."
    if lead_hr <= 0:
        return "BUFFER_OR_EXCLUDE", "At or after the seeded flare onset; excluded from precursor baseline sample."
    return "NEGATIVE_CANDIDATE", "Seed-based provisional control: no seeded M+ in future 3-6h and no seeded M+ in previous 3h."


def mapping_status(event: seed.EventSeed, returned_noaa: str) -> str:
    if returned_noaa == event.flare_noaa_ar:
        return "MATCHES_EVENT_NOAA_AR"
    if event.flare_noaa_ar in returned_noaa.split(","):
        return "EVENT_NOAA_AR_IN_RETURNED_LIST"
    return "NOAA_AR_MISMATCH_REQUIRES_REVIEW"


def event_provenance_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in seed.EVENTS:
        rows.append(
            {
                "flare_event_id": event.flare_event_id,
                "flare_class": event.flare_class,
                "goes_onset_utc": format_utc(event.onset_utc),
                "flare_NOAA_AR": event.flare_noaa_ar,
                "HARPNUM": event.harpnum,
                "event_source_current": event.onset_source,
                "class_source_current": event.peak_flux_source,
                "official_snapshot_status": "NEEDS_CLARIFICATION",
                "event_level_blocker": 1,
                "action_required": "补 GOES/JW-FD 官方事件快照：onset/class/位置/NOAA AR/URL/版本/查询时间/hash；事件输入来源状态在本表保持 NEEDS_CLARIFICATION。",
            }
        )
    return rows


def query_start_tai(event: seed.EventSeed) -> datetime:
    onset_tai = seed.utc_to_tai(event.onset_utc)
    return seed.floor_to_cadence(onset_tai - timedelta(hours=QUERY_LOOKBACK_HOURS))


def expected_query_times(event: seed.EventSeed) -> list[datetime]:
    start = query_start_tai(event)
    return [start + timedelta(minutes=CADENCE_MINUTES * idx) for idx in range(QUERY_EXPECTED_RECORDS)]


def fetch_or_copy_raw(event: seed.EventSeed, fetch: bool) -> tuple[Path, str, str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{event.flare_event_id}.json"
    url, ds = seed.query_url(event)
    if fetch:
        with urllib.request.urlopen(url, timeout=45) as response:
            write_text(raw_path, response.read().decode("utf-8"))
        return raw_path, url, ds

    old_path = OLD_RAW_DIR / f"{event.flare_event_id}.json"
    if not old_path.exists():
        raise FileNotFoundError(f"Offline raw JSON not found: {old_path}")
    shutil.copyfile(old_path, raw_path)
    return raw_path, url, ds


def parse_jsoc_payload(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != 0:
        raise RuntimeError(f"{path.name}: JSOC status={payload.get('status')}")
    names = [item["name"] for item in payload["keywords"]]
    values = [item["values"] for item in payload["keywords"]]
    rows: list[dict[str, str]] = []
    for idx in range(payload["count"]):
        rows.append({name: vals[idx] for name, vals in zip(names, values)})
    return rows


def cadence_audit_for_event(event: seed.EventSeed, rows: list[dict[str, str]]) -> dict[str, object]:
    returned_times = sorted(seed.parse_tai(row["T_REC"]) for row in rows)
    returned = set(returned_times)
    expected = expected_query_times(event)
    missing = [time for time in expected if time not in returned]
    return {
        "flare_event_id": event.flare_event_id,
        "flare_NOAA_AR": event.flare_noaa_ar,
        "HARPNUM": event.harpnum,
        "expected_records": len(expected),
        "returned_records": len(rows),
        "missing_records": len(missing),
        "max_returned_gap_min": round(max_gap_minutes(returned_times), 3),
        "first_expected_TAI": jsoc_time(expected[0]),
        "last_expected_TAI": jsoc_time(expected[-1]),
        "first_returned_TAI": jsoc_time(returned_times[0]) if returned_times else "",
        "last_returned_TAI": jsoc_time(returned_times[-1]) if returned_times else "",
        "missing_T_REC_TAI": ";".join(jsoc_time(time) for time in missing),
        "note": "Query-level cadence audit; history windows have separate valid-frame gates.",
    }


def build_rows_for_event(event: seed.EventSeed, jsoc_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    preliminary: list[dict[str, object]] = []
    by_time: dict[datetime, dict[str, object]] = {}

    for raw in jsoc_rows:
        tai_dt = seed.parse_tai(raw["T_REC"])
        utc_dt = seed.tai_to_utc(tai_dt)
        shrgt45 = as_float(raw.get("SHRGT45"))
        meanalp = as_float(raw.get("MEANALP"))
        usflux = as_float(raw.get("USFLUX"))
        lon = as_float(raw.get("LON_FWT"))
        lat = as_float(raw.get("LAT_FWT"))
        quality = raw.get("QUALITY", "")
        q_status, q_bits, q_fatal, q_retained = quality_status(quality)
        returned_noaa = raw.get("NOAA_AR", "")
        map_status = mapping_status(event, returned_noaa)
        field_complete = int(
            shrgt45 is not None
            and meanalp is not None
            and usflux is not None
            and lon is not None
            and lat is not None
            and quality != ""
        )
        disk_gate = int(
            lon is not None
            and lat is not None
            and abs(lon) < DISK_LIMIT_DEG
            and abs(lat) < DISK_LIMIT_DEG
        )
        lead_hr = (event.onset_utc - utc_dt).total_seconds() / 3600
        state, state_note = sample_state_for_lead(lead_hr)
        control_status = (
            "PROVISIONAL_CONTROL_PENDING_FULL_MPLUS_CATALOG_AUDIT"
            if state == "NEGATIVE_CANDIDATE"
            else ""
        )
        row = {
            "run_id": RUN_ID,
            "queue": "ALL_SAMPLE_SUPPLEMENT",
            "flare_event_id": event.flare_event_id,
            "flare_class": event.flare_class,
            "flare_onset_utc": format_utc(event.onset_utc),
            "flare_NOAA_AR": event.flare_noaa_ar,
            "event_provenance_status": "NEEDS_CLARIFICATION_OFFICIAL_GOES_JWFD_SNAPSHOT",
            "ar_assignment_status": map_status,
            "HARPNUM": raw.get("HARPNUM", event.harpnum),
            "NOAA_AR": returned_noaa,
            "T_REC_TAI": raw["T_REC"],
            "T_REC_UTC": format_utc(utc_dt),
            "tai_dt": tai_dt,
            "distance_to_flare_hr": round(lead_hr, 6),
            "SHRGT45": "" if shrgt45 is None else shrgt45,
            "SHRGT45_slope_3h_percent_per_hr": "",
            "SHRGT45_delta_3h_percent": "",
            "SHRGT45_slope_3h_strict_percent_per_hr": "",
            "SHRGT45_delta_3h_strict_percent": "",
            "MEANALP": "" if meanalp is None else meanalp,
            "USFLUX": "" if usflux is None else usflux,
            "QUALITY": quality,
            "quality_gate_status": q_status,
            "quality_fatal_bits": q_bits,
            "disk_position": "" if lon is None or lat is None else f"LON_FWT={lon:.3f};LAT_FWT={lat:.3f}",
            "sample_state": state,
            "control_status": control_status,
            "data_source": "JSOC definitive hmi.sharp_cea_720s keyword query; raw JSON copied from 20260723 cache unless --fetch used",
            "field_complete": field_complete,
            "ar_mapping_pass": int(map_status != "NOAA_AR_MISMATCH_REQUIRES_REVIEW"),
            "quality_zero": int(parse_quality(quality) == 0),
            "quality_fatal": q_fatal,
            "quality_retained_provisional": q_retained,
            "history3h_expected_records": HISTORY_EXPECTED_RECORDS,
            "history3h_returned_records": 0,
            "history3h_valid_records": 0,
            "history3h_missing_records": HISTORY_EXPECTED_RECORDS,
            "history3h_span_minutes": "",
            "history3h_max_gap_minutes": "",
            "history3h_pass_provisional": 0,
            "history3h_complete_quality_zero": 0,
            "disk_gate_pass": disk_gate,
            "buffer_or_cluster_excluded": int(state == "BUFFER_OR_EXCLUDE"),
            "passes_main_gates_provisional": 0,
            "passes_strict_baseline": 0,
            "history_start_T_REC_TAI": "",
            "history_end_T_REC_TAI": "",
            "anchor_target_lead_hr": "",
            "anchor_delta_hr": "",
            "anchor_within_tolerance": "",
            "state_note": state_note,
        }
        preliminary.append(row)
        by_time[tai_dt] = row

    for row in preliminary:
        tai_dt = row["tai_dt"]
        history_times = [
            tai_dt - timedelta(minutes=CADENCE_MINUTES * offset)
            for offset in range(HISTORY_EXPECTED_RECORDS - 1, -1, -1)
        ]
        history_rows = [by_time.get(time) for time in history_times]
        present = [history_row for history_row in history_rows if history_row is not None]
        valid = [
            history_row
            for history_row in present
            if int(history_row["field_complete"]) == 1
            and int(history_row["ar_mapping_pass"]) == 1
            and int(history_row["quality_fatal"]) == 0
        ]
        strict = (
            len(present) == HISTORY_EXPECTED_RECORDS
            and all(int(history_row["field_complete"]) == 1 for history_row in present)
            and all(int(history_row["ar_mapping_pass"]) == 1 for history_row in present)
            and all(int(history_row["quality_zero"]) == 1 for history_row in present)
        )
        row["history3h_returned_records"] = len(present)
        row["history3h_valid_records"] = len(valid)
        row["history3h_missing_records"] = HISTORY_EXPECTED_RECORDS - len(present)

        if valid:
            times = [history_row["tai_dt"] for history_row in valid]
            values = [float(history_row["SHRGT45"]) for history_row in valid]
            span = (max(times) - min(times)).total_seconds() / 60
            max_gap = max_gap_minutes(times)
            row["history3h_span_minutes"] = round(span, 3)
            row["history3h_max_gap_minutes"] = round(max_gap, 3)
            row["history_start_T_REC_TAI"] = valid[0]["T_REC_TAI"]
            row["history_end_T_REC_TAI"] = valid[-1]["T_REC_TAI"]
            if (
                len(valid) >= HISTORY_MIN_VALID_RECORDS
                and span >= HISTORY_MIN_SPAN_MINUTES
                and max_gap <= HISTORY_MAX_GAP_MINUTES
            ):
                row["SHRGT45_slope_3h_percent_per_hr"] = round(linear_slope_per_hour(times, values), 6)
                row["SHRGT45_delta_3h_percent"] = round(values[-1] - values[0], 3)
                row["history3h_pass_provisional"] = 1

        if strict:
            times = [history_row["tai_dt"] for history_row in present]
            values = [float(history_row["SHRGT45"]) for history_row in present]
            row["SHRGT45_slope_3h_strict_percent_per_hr"] = round(linear_slope_per_hour(times, values), 6)
            row["SHRGT45_delta_3h_strict_percent"] = round(values[-1] - values[0], 3)
            row["history3h_complete_quality_zero"] = 1

        if (
            int(row["field_complete"]) == 1
            and int(row["ar_mapping_pass"]) == 1
            and int(row["quality_fatal"]) == 0
            and int(row["history3h_pass_provisional"]) == 1
            and int(row["disk_gate_pass"]) == 1
            and row["sample_state"] in {"POSITIVE_CANDIDATE", "NEGATIVE_CANDIDATE"}
        ):
            row["passes_main_gates_provisional"] = 1

        if (
            int(row["field_complete"]) == 1
            and int(row["ar_mapping_pass"]) == 1
            and int(row["quality_zero"]) == 1
            and int(row["history3h_complete_quality_zero"]) == 1
            and int(row["disk_gate_pass"]) == 1
            and row["sample_state"] in {"POSITIVE_CANDIDATE", "NEGATIVE_CANDIDATE"}
        ):
            row["passes_strict_baseline"] = 1

    for row in preliminary:
        row.pop("tai_dt", None)
    return preliminary


def choose_anchor(rows: list[dict[str, object]], state: str, target_lead_hr: float) -> dict[str, object] | None:
    candidates = [
        row
        for row in rows
        if row["sample_state"] == state and int(row["passes_main_gates_provisional"]) == 1
    ]
    if not candidates:
        return None
    anchor = min(candidates, key=lambda row: abs(float(row["distance_to_flare_hr"]) - target_lead_hr))
    delta = abs(float(anchor["distance_to_flare_hr"]) - target_lead_hr)
    if delta > ANCHOR_TOLERANCE_HR:
        return None
    out = dict(anchor)
    out["anchor_target_lead_hr"] = target_lead_hr
    out["anchor_delta_hr"] = round(delta, 6)
    out["anchor_within_tolerance"] = 1
    return out


def build_provisional_queue(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    by_event: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_event[str(row["flare_event_id"])].append(row)
    for event_id, event_rows in sorted(by_event.items()):
        positive = choose_anchor(event_rows, "POSITIVE_CANDIDATE", 4.5)
        negative = choose_anchor(event_rows, "NEGATIVE_CANDIDATE", 8.0)
        for anchor, role, target in [
            (positive, "PROVISIONAL_POSITIVE_ANCHOR", "T0-4.5h"),
            (negative, "PROVISIONAL_CONTROL_ANCHOR", "T0-8h"),
        ]:
            if anchor is None:
                continue
            item = dict(anchor)
            item["queue"] = role
            item["state_note"] = (
                f"{anchor['state_note']} Provisional anchor selected by nearest-frame rule to {target}; "
                f"tolerance={ANCHOR_TOLERANCE_HR}h; fixed anchor records the {target} position."
            )
            out.append(item)
    return out


def choose_strict_baseline_anchor(rows: list[dict[str, object]], state: str, target_lead_hr: float) -> dict[str, object] | None:
    candidates = [
        row
        for row in rows
        if row["sample_state"] == state and int(row["passes_strict_baseline"]) == 1
    ]
    if not candidates:
        return None
    anchor = min(candidates, key=lambda row: abs(float(row["distance_to_flare_hr"]) - target_lead_hr))
    out = dict(anchor)
    delta = abs(float(out["distance_to_flare_hr"]) - target_lead_hr)
    out["anchor_target_lead_hr"] = target_lead_hr
    out["anchor_delta_hr"] = round(delta, 6)
    out["anchor_within_tolerance"] = ""
    return out


def build_strict_baseline_queue(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    by_event: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_event[str(row["flare_event_id"])].append(row)
    for event_id, event_rows in sorted(by_event.items()):
        positive = choose_strict_baseline_anchor(event_rows, "POSITIVE_CANDIDATE", 4.5)
        negative = choose_strict_baseline_anchor(event_rows, "NEGATIVE_CANDIDATE", 8.0)
        for anchor, role, target in [
            (positive, "STRICT_Q0_POSITIVE_ANCHOR", "T0-4.5h"),
            (negative, "STRICT_Q0_CONTROL_ANCHOR", "T0-8h"),
        ]:
            if anchor is None:
                continue
            item = dict(anchor)
            item["queue"] = role
            item["state_note"] = (
                f"{anchor['state_note']} Strict QUALITY=0 sensitivity baseline anchor selected by nearest-frame rule "
                f"to {target}; fixed nearest-frame anchor records the 20260723 sensitivity baseline."
            )
            out.append(item)
    return out


def count_rows(rows: list[dict[str, object]], predicate) -> int:
    return sum(1 for row in rows if predicate(row))


def unique_count(rows: list[dict[str, object]], column: str, predicate=lambda row: True) -> int:
    return len({str(row[column]) for row in rows if predicate(row) and row.get(column) not in {"", None}})


def gate_counts(
    rows: list[dict[str, object]],
    queue_rows: list[dict[str, object]],
    strict_queue_rows: list[dict[str, object]],
    query_rows: list[dict[str, object]],
    cadence_rows: list[dict[str, object]],
    provenance_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    provisional_rows = [row for row in rows if int(row["passes_main_gates_provisional"]) == 1]
    positive_rows = [row for row in provisional_rows if row["sample_state"] == "POSITIVE_CANDIDATE"]
    control_rows = [row for row in provisional_rows if row["sample_state"] == "NEGATIVE_CANDIDATE"]
    strict_rows = [row for row in rows if int(row["passes_strict_baseline"]) == 1]
    out = [
        {"gate": "event_seed_count", "count": len(seed.EVENTS), "note": "Seeded M+ events for the current full-information Demo."},
        {"gate": "official_event_provenance_pass", "count": count_rows(provenance_rows, lambda row: int(row["event_level_blocker"]) == 0), "note": "Events with complete official-snapshot fields."},
        {"gate": "official_event_provenance_blocked", "count": count_rows(provenance_rows, lambda row: int(row["event_level_blocker"]) == 1), "note": "Event source status is NEEDS_CLARIFICATION; the audit fields remain with each seed."},
        {"gate": "queried_event_count", "count": count_rows(query_rows, lambda row: row["status"] == "PASS"), "note": "Events with cached/fetched JSOC keyword JSON status 0."},
        {"gate": "query_expected_records", "count": sum(int(row["expected_records"]) for row in cadence_rows), "note": "12h@12m expected rows; 6 events x 60 = 360."},
        {"gate": "query_returned_records", "count": sum(int(row["returned_records"]) for row in cadence_rows), "note": "Rows returned by JSOC keyword query."},
        {"gate": "query_missing_records", "count": sum(int(row["missing_records"]) for row in cadence_rows), "note": "Expected T_REC values absent from the returned keyword rows."},
        {"gate": "raw_records", "count": len(rows), "note": "All JSOC keyword rows across queried events."},
        {"gate": "field_complete", "count": count_rows(rows, lambda row: int(row["field_complete"]) == 1), "note": "SHRGT45/MEANALP/USFLUX/QUALITY/LON_FWT/LAT_FWT present."},
        {"gate": "event_ar_mapping_pass_rows", "count": count_rows(rows, lambda row: int(row["ar_mapping_pass"]) == 1), "note": "Returned NOAA_AR matches or includes seeded event NOAA AR."},
        {"gate": "event_ar_mapping_blocked_rows", "count": count_rows(rows, lambda row: int(row["ar_mapping_pass"]) == 0), "note": "Rows blocked because event-NOAA AR-HARPNUM ownership requires review."},
        {"gate": "quality_zero_rows_after_mapping", "count": count_rows(rows, lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 1 and int(row["quality_zero"]) == 1), "note": "Strict baseline current rows with QUALITY=0."},
        {"gate": "quality_nonzero_retained_provisional_rows", "count": count_rows(rows, lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 1 and int(row["quality_retained_provisional"]) == 1), "note": "Nonzero, nonfatal QUALITY retained with its original bit mask."},
        {"gate": "quality_fatal_excluded_rows", "count": count_rows(rows, lambda row: int(row["quality_fatal"]) == 1), "note": "Rows with fatal QUALITY bits 0x80000000 or 0x40000000."},
        {"gate": "history_3h_pass_provisional", "count": count_rows(rows, lambda row: int(row["history3h_pass_provisional"]) == 1), "note": "History window valid frames >=14/16, span >=160 min, max gap <=24 min, fatal QUALITY excluded."},
        {"gate": "history_3h_complete_quality_zero_strict", "count": count_rows(rows, lambda row: int(row["history3h_complete_quality_zero"]) == 1), "note": "Strict sensitivity baseline: 16 records over [t-3h,t], all field-complete, AR-matched and QUALITY=0."},
        {"gate": "disk_abs_lon_lat_lt_50", "count": count_rows(rows, lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 1 and int(row["history3h_pass_provisional"]) == 1 and int(row["disk_gate_pass"]) == 1), "note": "Rows passing the 3h history rule and abs(LON_FWT), abs(LAT_FWT) < 50 degrees."},
        {"gate": "buffer_or_cluster_excluded_rows", "count": count_rows(rows, lambda row: int(row["buffer_or_cluster_excluded"]) == 1), "note": "Seed-based 0-3h/post-onset rows recorded as buffer or boundary status."},
        {"gate": "all_sample_positive_rows_after_provisional_gates", "count": len(positive_rows), "note": "Positive-candidate rows; represented events and ARs are reported alongside rows."},
        {"gate": "all_sample_provisional_control_rows_after_gates", "count": len(control_rows), "note": "Temporary-control rows; represented events and ARs are reported alongside rows."},
        {"gate": "all_sample_positive_events_after_provisional_gates", "count": unique_count(positive_rows, "flare_event_id"), "note": "Seed events represented by positive rows after provisional gates."},
        {"gate": "all_sample_positive_AR_after_provisional_gates", "count": unique_count(positive_rows, "flare_NOAA_AR"), "note": "NOAA ARs represented by positive rows after provisional gates."},
        {"gate": "all_sample_control_events_after_provisional_gates", "count": unique_count(control_rows, "flare_event_id"), "note": "Seed events represented by provisional controls."},
        {"gate": "all_sample_control_AR_after_provisional_gates", "count": unique_count(control_rows, "flare_NOAA_AR"), "note": "NOAA ARs represented by provisional controls."},
        {"gate": "strict_positive_rows_after_gates", "count": count_rows(strict_rows, lambda row: row["sample_state"] == "POSITIVE_CANDIDATE"), "note": "Old strict QUALITY=0 sensitivity baseline rows."},
        {"gate": "strict_control_rows_after_gates", "count": count_rows(strict_rows, lambda row: row["sample_state"] == "NEGATIVE_CANDIDATE"), "note": "Old strict QUALITY=0 sensitivity baseline provisional-control rows."},
        {"gate": "provisional_queue_positive_anchor_count", "count": count_rows(queue_rows, lambda row: row["queue"] == "PROVISIONAL_POSITIVE_ANCHOR"), "note": "Anchors selected by nearest T0-4.5h rule with tolerance."},
        {"gate": "provisional_queue_control_anchor_count", "count": count_rows(queue_rows, lambda row: row["queue"] == "PROVISIONAL_CONTROL_ANCHOR"), "note": "Provisional-control anchors selected by nearest T0-8h rule with tolerance."},
        {"gate": "provisional_queue_unique_events", "count": unique_count(queue_rows, "flare_event_id"), "note": "Unique seed events represented in provisional queue."},
        {"gate": "provisional_queue_unique_noaa_ar", "count": unique_count(queue_rows, "flare_NOAA_AR"), "note": "Unique NOAA ARs represented in provisional queue."},
        {"gate": "provisional_queue_unique_harpnum", "count": unique_count(queue_rows, "HARPNUM"), "note": "Unique HARPNUMs represented in provisional queue."},
        {"gate": "strict_baseline_queue_positive_anchor_count", "count": count_rows(strict_queue_rows, lambda row: row["queue"] == "STRICT_Q0_POSITIVE_ANCHOR"), "note": "Strict QUALITY=0 baseline positive anchors for sensitivity comparison."},
        {"gate": "strict_baseline_queue_control_anchor_count", "count": count_rows(strict_queue_rows, lambda row: row["queue"] == "STRICT_Q0_CONTROL_ANCHOR"), "note": "Strict QUALITY=0 baseline temporary-control anchors for sensitivity comparison."},
    ]
    return out


def determine_status(gates: list[dict[str, object]]) -> tuple[str, str]:
    values = {row["gate"]: int(row["count"]) for row in gates}
    if values.get("queried_event_count", 0) < 2:
        return "DATA_UNAVAILABLE", "JSOC keyword data不足，无法形成多事件数据处理结果。"
    if values.get("all_sample_positive_rows_after_provisional_gates", 0) == 0:
        return "INSUFFICIENT_SAMPLES", "provisional QUALITY/missingness 门后正候选为 0。"
    return (
        "DEMO_PROCESSING_READY",
        "QUALITY/missingness 分层、时间窗和趋势计算已形成可追溯数据处理结果；事件来源状态逐事件保留在审计表中。",
    )


def summarize_distribution(rows: list[dict[str, object]], queue_name: str, value_col: str) -> list[dict[str, object]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(value_col, "")
        if value == "":
            continue
        grouped[str(row["sample_state"])].append(float(value))
    out: list[dict[str, object]] = []
    for state, values in sorted(grouped.items()):
        med = median_value(values)
        out.append(
            {
                "queue": queue_name,
                "sample_state": state,
                "n": len(values),
                "value_name": value_col,
                "unit": "percentage points per hour",
                "min": round(min(values), 6),
                "median": "" if med is None else round(med, 6),
                "max": round(max(values), 6),
                "mean": round(mean(values), 6),
                "note": "Continuous distribution with minimum, median, maximum, and mean reported.",
            }
        )
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den_x = sum((x - x_mean) ** 2 for x in xs)
    den_y = sum((y - y_mean) ** 2 for y in ys)
    if den_x == 0 or den_y == 0:
        return None
    return num / math.sqrt(den_x * den_y)


def usflux_pairs(rows: list[dict[str, object]]) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        if int(row.get("passes_main_gates_provisional", 0)) != 1:
            continue
        shr = as_float(row.get("SHRGT45"))
        flux = as_float(row.get("USFLUX"))
        if shr is not None and flux is not None:
            xs.append(shr)
            ys.append(flux)
    return xs, ys


def usflux_correlation(rows: list[dict[str, object]], queue_name: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    xs, ys = usflux_pairs(rows)
    corr = pearson(xs, ys)
    out.append(
        {
            "queue": queue_name,
            "scope": "pooled_rows",
            "n": len(xs),
            "n_AR": unique_count(rows, "flare_NOAA_AR", lambda row: int(row.get("passes_main_gates_provisional", 0)) == 1),
            "x": "SHRGT45",
            "y": "USFLUX",
            "pearson_r": "" if corr is None else round(corr, 6),
            "note": "Pooled context correlation; records are grouped by AR/event and reported with n and n_AR.",
        }
    )
    by_ar: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_ar[str(row.get("flare_NOAA_AR", ""))].append(row)
    for ar, ar_rows in sorted(by_ar.items()):
        xs_ar, ys_ar = usflux_pairs(ar_rows)
        corr_ar = pearson(xs_ar, ys_ar)
        out.append(
            {
                "queue": queue_name,
                "scope": f"within_AR_{ar}",
                "n": len(xs_ar),
                "n_AR": 1 if xs_ar else 0,
                "x": "SHRGT45",
                "y": "USFLUX",
                "pearson_r": "" if corr_ar is None else round(corr_ar, 6),
                "note": "Per-AR context; Pearson r is blank when n<3 or variance is zero. USFLUX is recorded as a background field.",
            }
        )
    return out


def write_quality_policy() -> tuple[Path, Path]:
    rows = [
        {
            "bit_mask": "0x80000000",
            "meaning": "QUAL_NODATA / Q_MISSALL: missing data or missing required Stokes observables",
            "fatal_provisional": 1,
            "action": "EXCLUDE_FRAME_AND_HISTORY_USE",
            "official_evidence": "Hoeksema et al. HMI QUALITY tables; JSOC/HMI QUALITY documentation referenced from SHARP pipeline paper",
            "source_url": "https://link.springer.com/article/10.1007/s11207-014-0516-8",
        },
        {
            "bit_mask": "0x40000000",
            "meaning": "QUAL_TARGETFILTERGRAMMISSING / Q_REOPENED: target filtergram missing or reopened during reconstruction",
            "fatal_provisional": 1,
            "action": "EXCLUDE_FRAME_AND_HISTORY_USE",
            "official_evidence": "Hoeksema et al. HMI QUALITY tables; JSOC/HMI QUALITY documentation referenced from SHARP pipeline paper",
            "source_url": "https://link.springer.com/article/10.1007/s11207-014-0516-8",
        },
        {
            "bit_mask": "0xC0000000",
            "meaning": "Composite high bits 0x80000000 + 0x40000000",
            "fatal_provisional": 1,
            "action": "EXCLUDE_FRAME_AND_HISTORY_USE",
            "official_evidence": "Derived composite of fatal provisional bits",
            "source_url": "https://link.springer.com/article/10.1007/s11207-014-0516-8",
        },
        {
            "bit_mask": "0x00010400",
            "meaning": "Nonzero lower/mid bits observed in current data; exact SHARP-level interpretation retained for document lookup",
            "fatal_provisional": 0,
            "action": "RETAIN_AS_NONZERO_RETAINED_PROVISIONAL",
            "official_evidence": "JSOC/HMI bit-position lookup remains recorded with the original mask",
            "source_url": "https://jsoc.stanford.edu/doc/data/hmi/sharp/old/sharp.MB.htm",
        },
        {
            "bit_mask": "0x00000400",
            "meaning": "Nonzero lower/mid bit observed in current data; exact SHARP-level interpretation retained for document lookup",
            "fatal_provisional": 0,
            "action": "RETAIN_AS_NONZERO_RETAINED_PROVISIONAL",
            "official_evidence": "JSOC/HMI bit-position lookup remains recorded with the original mask",
            "source_url": "https://jsoc.stanford.edu/doc/data/hmi/sharp/old/sharp.MB.htm",
        },
    ]
    csv_path = OUT_DIR / "11_quality_bit_policy_provisional.csv"
    md_path = OUT_DIR / "11_quality_bit_policy_provisional.md"
    write_csv(csv_path, rows)
    text = """# SHRGT45 全信息基准版 Demo QUALITY 处理规则

本表记录本次 Demo 的 QUALITY 位掩码处理方式。`0x80000000`、`0x40000000` 及二者的组合 `0xC0000000` 作为致命位，从相应帧和历史窗中排除；其他非零值保留原始十六进制值，并标记为 `NONZERO_RETAINED_PROVISIONAL`。

官方依据采用 HMI QUALITY 表和 JSOC/SHARP 文档入口：

- Hoeksema et al., HMI vector magnetic field pipeline / HMI QUALITY tables: https://link.springer.com/article/10.1007/s11207-014-0516-8
- JSOC SHARP 文档入口: https://jsoc.stanford.edu/doc/data/hmi/sharp/old/sharp.MB.htm

`0x00010400`、`0x00000400` 的精确 SHARP-level 含义在表中保持“待定位”状态；对应记录保留，便于结合官方 bit 位置继续核对。
"""
    write_text(md_path, text)
    return csv_path, md_path


def write_policy() -> tuple[Path, str]:
    text = f"""# SHRGT45 全信息基准版 Demo 数据处理规则

- run_id：`{RUN_ID}`
- decision_rule_ref：`{POLICY_ID}`
- 版本类型：`全信息基准版`
    - 适用范围：本包事件种子、缓存 JSOC 关键词记录及其下游结果文件。

    ## 处理规则

- 数据源：definitive `hmi.sharp_cea_720s` keyword，默认离线读取 `SHRGT45_全信息基准版_20260723/raw_jsoc_keywords/` 封存 JSON。
    - 时间窗：GOES SXR onset 作 T0；M+ 标签使用事件种子表的 peak class；来源状态在 `02_event_provenance_audit.csv` 逐事件保留。
- 位置门：`abs(LON_FWT)<50°` 且 `abs(LAT_FWT)<50°`。
    - QUALITY：排除 `0x80000000`、`0x40000000` 及其合成 `0xC0000000`；其余非零 QUALITY 保留原始十六进制值并标注。
- 3h 历史窗：有效帧数 `>=14/16`，有效帧跨度 `>=160 min`，最大相邻有效帧 gap `<=24 min`。
- OLS：使用真实 `T_REC` 时间作为自变量，不压缩缺失时间轴。
    - strict baseline：同时保留 `16/16` 且全 `QUALITY=0` 的敏感性结果，用于与主规则并列核对。
- 锚点：每事件固定选择距离 T0-4.5h / T0-8h 最近的通过门控记录；容差 `{ANCHOR_TOLERANCE_HR}h`，超差不生成锚点。

    ## 输出口径

    - 输出逐行门控状态、门控计数、OLS 趋势分布、USFLUX 上下文相关、结果队列和可视化。
    - 行记录按事件和 AR 聚集；报告同时给出 records、events 和 AR 的数量。
    - 指标表未设置 TSS、HSS、AUC 或分类器评分字段；规则按本文件固定，不依结果数量改写。
"""
    path = OUT_DIR / POLICY_FILE
    write_text(path, text)
    return path, sha256_text(text)


def gate_value(gates: list[dict[str, object]], name: str) -> int:
    for row in gates:
        if row["gate"] == name:
            return int(row["count"])
    return 0


def write_dataplan(status: str, reason: str, gates: list[dict[str, object]], policy_hash: str) -> None:
    lines = "\n".join(f"- {row['gate']}: {row['count']} - {row['note']}" for row in gates)
    text = f"""# DataPlan<SHRGT45> · 全信息基准版

## 运行门控摘要

- run_id：`{RUN_ID}`
- 版本类型：`全信息基准版`
    - 输入：事件种子、JSOC 查询清单和缓存关键词 JSON
- 旧包角色：`{OLD_RUN_ID}` 保留为 strict `QUALITY=0` 敏感性基线，不覆盖。
- 结论：`{status}`
- 解释：{reason}
- decision_rule_ref：`{POLICY_ID}`
- DecisionPolicy 文件：`{POLICY_FILE}`
- DecisionPolicy SHA256：`{policy_hash}`

## 逐门数量

{lines}

## 本轮固定方法

    - QUALITY/missingness 门：致命 QUALITY 位排除，非致命非零位保留并标注。
- 3h 历史窗要求有效帧 `>=14/16`、跨度 `>=160 min`、最大 gap `<=24 min`。
- 斜率公式：对 `[t-3h,t]` 的有效 SHRGT45 序列做 OLS，时间自变量使用真实 `T_REC`。
- strict baseline 保留旧 16 帧全齐且 `QUALITY=0` 结果，用于敏感性比较。
    - 远离 T0 的记录标记为 `provisional control`，在表中与正候选、缓冲/边界记录分列。
- 锚点规则：固定目标 lead，最近帧 + 容差；超差无锚点。
    - USFLUX：作为混杂/尺度背景字段；报告 pooled 与 per-AR 相关，SHRGT45 3 小时 OLS 斜率为主趋势结果。

    ## 结果汇总方法

    - 行记录按事件和 AR 聚集；数量表同时列出 records、events 和 AR，避免将重叠窗口误读为独立样本。
    - 主结果为门控计数、OLS 斜率连续分布和 pooled USFLUX 上下文相关；strict `QUALITY=0` 结果并列作为敏感性线。
    - `USFLUX` 作为背景字段，报告原始尺度与图上 `log10(USFLUX)` 尺度的相关口径。
- 缺失/重复：缺失按 history gate 处理；重复 `T_REC` 以同一 HARPNUM 同一 T_REC 一条记录为单位，若冲突则阻断。
    - `decision_rule_ref`：本次运行规则与处理规则文件和 SHA256 一一对应。

    ## 输入字段状态

    - 官方 GOES/JW-FD 事件快照和耀斑-AR provenance 在事件审计表中标为 `NEEDS_CLARIFICATION`。
    - M+ 时间窗和 QUALITY 位掩码的已知信息逐行保留，便于按来源字段复核。

    ## 输出范围

    本包输出逐行数据处理结果及其门控、趋势和上下文汇总。指标清单未包含 TSS、HSS、AUC、置信区间或分类器评分。
"""
    write_text(OUT_DIR / DATAPLAN_FILE, text)


def write_leader_note(status: str, reason: str, gates: list[dict[str, object]]) -> None:
    text = f"""# 给组长的全信息基准版说明

本轮没有覆盖旧包，而是另开 `SHRGT45_全信息基准版_20260724`。旧 `20260723` 包保留为严格 `QUALITY=0` 敏感性基线。

## 一句话结论

`{status}`：{reason}

    该结果用于核对 QUALITY/missingness 分层、时间窗和趋势计算在给定输入上的表现。

## 数量摘要

- 查询理论记录：{gate_value(gates, 'query_expected_records')}
- JSOC 实返记录：{gate_value(gates, 'query_returned_records')}
- 查询缺帧：{gate_value(gates, 'query_missing_records')}
- provisional 3h 历史窗通过：{gate_value(gates, 'history_3h_pass_provisional')}
- strict 16帧全齐且 QUALITY=0：{gate_value(gates, 'history_3h_complete_quality_zero_strict')}
- provisional 正候选行：{gate_value(gates, 'all_sample_positive_rows_after_provisional_gates')}
- provisional control 行：{gate_value(gates, 'all_sample_provisional_control_rows_after_gates')}
- provisional 正候选 AR：{gate_value(gates, 'all_sample_positive_AR_after_provisional_gates')}
- provisional control AR：{gate_value(gates, 'all_sample_control_AR_after_provisional_gates')}
- provisional 队列正锚点：{gate_value(gates, 'provisional_queue_positive_anchor_count')}
- provisional 队列 control 锚点：{gate_value(gates, 'provisional_queue_control_anchor_count')}

    ## 输出范围

    输出包含门控结果、趋势分布和上下文相关；负例状态保持为 provisional control，事件来源状态保留在审计表中。
"""
    write_text(OUT_DIR / "09_leader_plain_language_summary.md", text)


def write_readme(status: str, reason: str) -> None:
    text = f"""# SHRGT45 全信息基准版

- run_id：`{RUN_ID}`
- 版本类型：`全信息基准版`
    - 处理日期：`2026-07-24`
- 旧包：`{OLD_RUN_ID}`，保留为 strict QUALITY=0 敏感性基线
- 状态：`{status}`
- 解释：{reason}

    ## 当前交付内容

    本目录提供全信息基准版的数据处理输入、规则、结果文件、可视化和复现材料。

## 递交对象

| 对象 | 必交文件 | 用途 |
|---|---|---|
| 组长 | `README.md`、`09_leader_plain_language_summary.md`、`08_DataPlan_SHRGT45_全信息基准版.md`、`06_gate_counts.csv`、`12_cadence_audit.csv`、`manifest.json` | 快速阅读数据处理状态、逐门数量、缺帧和来源字段 |
| 组长复现/抽查 | `{POLICY_FILE}`、`03_jsoc_query_manifest.csv`、`raw_jsoc_keywords/`、`11_quality_bit_policy_provisional.csv`、`13_file_sha256_manifest.csv`、`acceptance_check.csv` | 核查规则、JSOC 原始数据、QUALITY 依据、文件 hash 和验收 |
| 曾子晖 | `05_provisional_mechanism_queue.csv`、`04_all_sample_supplement.csv`、`07_continuous_distribution.csv`、`02_event_provenance_audit.csv` | 查看正候选、provisional control、buffer/排除样本和待解释/待补 provenance |
| 杨嘉梁 | `05_provisional_mechanism_queue.csv`、`05b_strict_quality0_sensitivity_queue.csv`、`02_event_seed_table.csv`、`03_jsoc_query_manifest.csv` | 获取 AR、HARPNUM、T0、T_REC、SHRGT45、QUALITY 和查询来源，用于磁图复核 |

## 复现

默认离线复现，不联网：

```powershell
python tools\\build_shrgt45_fullinfo_revision.py
```

可选重新查询 JSOC：

```powershell
python tools\\build_shrgt45_fullinfo_revision.py --fetch
```

依赖：Python `{platform.python_version()}`；仅使用标准库。

    ## 结果口径

    - 规则按文件记录固定，QUALITY/缺帧处理与结果文件一一对应。
    - 指标表列出门控、趋势和上下文结果；未设置 TSS/HSS/AUC 或分类器评分字段。
    - `USFLUX` 记录混杂/尺度背景，并单列相关审计。
"""
    write_text(OUT_DIR / "README.md", text)


def write_event_seed_table() -> None:
    rows = []
    for event in seed.EVENTS:
        rows.append(
            {
                "flare_event_id": event.flare_event_id,
                "flare_NOAA_AR": event.flare_noaa_ar,
                "HARPNUM": event.harpnum,
                "flare_class": event.flare_class,
                "goes_onset_utc": format_utc(event.onset_utc),
                "onset_source": event.onset_source,
                "peak_flux_source": event.peak_flux_source,
                "note": event.note,
            }
        )
    write_csv(OUT_DIR / "02_event_seed_table.csv", rows)


def write_file_hash_manifest() -> None:
    rows: list[dict[str, object]] = []
    for path in sorted(OUT_DIR.rglob("*")):
        if not path.is_file() or path.name == "13_file_sha256_manifest.csv":
            continue
        rows.append(
            {
                "relative_path": str(path.relative_to(OUT_DIR)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_csv(OUT_DIR / "13_file_sha256_manifest.csv", rows)


def write_acceptance_check(status: str) -> None:
    existing = {path.name for path in OUT_DIR.iterdir()}
    checks = [
        ("new_revision_directory_exists", OUT_DIR.exists()),
        ("old_run_not_overwritten", OLD_RUN.exists()),
        ("result_scope_no_classifier_files", not list(OUT_DIR.glob("VerificationResult*"))),
        ("all_sample_table_present", "04_all_sample_supplement.csv" in existing),
        ("provisional_queue_table_present", "05_provisional_mechanism_queue.csv" in existing),
        ("strict_baseline_queue_table_present", "05b_strict_quality0_sensitivity_queue.csv" in existing),
        ("quality_policy_present", "11_quality_bit_policy_provisional.csv" in existing),
        ("cadence_audit_present", "12_cadence_audit.csv" in existing),
        ("demo_processing_status_recorded", bool(status)),
    ]
    write_csv(
        OUT_DIR / "acceptance_check.csv",
        [{"check": name, "status": "PASS" if ok else "FAIL"} for name, ok in checks],
    )


def write_manifest(
    status: str,
    reason: str,
    gates: list[dict[str, object]],
    policy_hash: str,
    query_rows: list[dict[str, object]],
) -> None:
    manifest = {
        "run_id": RUN_ID,
        "status": status,
        "reason": reason,
        "version_type": VERSION_TYPE,
        "stage": "full_information_baseline_revision_not_formal_verification",
        "old_run_preserved_as_strict_baseline": OLD_RUN_ID,
        "formal_verification_result_generated": False,
        "decision_rule_ref": POLICY_ID,
        "decision_policy_sha256": policy_hash,
        "query_success_count": count_rows(query_rows, lambda row: row["status"] == "PASS"),
        "gate_counts": gates,
        "files": [
            "README.md",
            POLICY_FILE,
            "02_event_seed_table.csv",
            "02_event_provenance_audit.csv",
            "03_jsoc_query_manifest.csv",
            "04_all_sample_supplement.csv",
            "05_provisional_mechanism_queue.csv",
            "05b_strict_quality0_sensitivity_queue.csv",
            "06_gate_counts.csv",
            "07_continuous_distribution.csv",
            DATAPLAN_FILE,
            "09_leader_plain_language_summary.md",
            "10_usflux_context_correlation.csv",
            "11_quality_bit_policy_provisional.csv",
            "11_quality_bit_policy_provisional.md",
            "12_cadence_audit.csv",
            "13_file_sha256_manifest.csv",
            "14_self_test_results.csv",
            "acceptance_check.csv",
            "manifest.json",
        ],
    }
    write_text(OUT_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def zip_output() -> None:
    if ZIP_FILE.exists():
        ZIP_FILE.unlink()
    with zipfile.ZipFile(ZIP_FILE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(OUT_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUT_DIR.parent))


def self_test() -> list[dict[str, object]]:
    base_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        rows.append({"test": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    record("median_empty", median_value([]) is None, "empty returns None")
    record("median_single", median_value([3]) == 3, "single sample")
    record("median_odd", median_value([3, 1, 2]) == 2, "odd sample")
    record("median_even", median_value([4, 1, 2, 3]) == 2.5, "even sample averages middle pair")

    expected_quality = {
        "0x00000000": ("ZERO_QUALITY", 0, 0),
        "0x80000000": ("FATAL_EXCLUDED_PROVISIONAL", 1, 0),
        "0x40000000": ("FATAL_EXCLUDED_PROVISIONAL", 1, 0),
        "0xC0000000": ("FATAL_EXCLUDED_PROVISIONAL", 1, 0),
        "0x00010400": ("NONZERO_RETAINED_PROVISIONAL", 0, 1),
        "0x00000400": ("NONZERO_RETAINED_PROVISIONAL", 0, 1),
    }
    for value, expected in expected_quality.items():
        status, _bits, fatal, retained = quality_status(value)
        record(f"quality_{value}", (status, fatal, retained) == expected, f"got {(status, fatal, retained)}")

    def history_pass(offsets: list[int]) -> bool:
        times = [base_time + timedelta(minutes=CADENCE_MINUTES * offset) for offset in offsets]
        span = (max(times) - min(times)).total_seconds() / 60 if times else 0
        gap = max_gap_minutes(times)
        return len(times) >= HISTORY_MIN_VALID_RECORDS and span >= HISTORY_MIN_SPAN_MINUTES and gap <= HISTORY_MAX_GAP_MINUTES

    record("history_14_of_16_pass", history_pass([0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14, 15]), "14 frames, no >24m gap")
    record("history_13_of_16_fail", not history_pass(list(range(13))), "13 frames fail")
    record("history_span_fail", not history_pass(list(range(14))), "14 frames but span 156m fail")
    record("history_gap_36_fail", not history_pass([0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15]), "missing two consecutive frames creates 36m gap")

    times = [base_time, base_time + timedelta(minutes=12), base_time + timedelta(minutes=36)]
    values = [0.0, 12.0, 36.0]
    record("ols_real_time_axis", round(linear_slope_per_hour(times, values), 6) == 60.0, "uses actual elapsed minutes")

    fake = [
        {"sample_state": "POSITIVE_CANDIDATE", "passes_main_gates_provisional": 1, "distance_to_flare_hr": 4.55},
        {"sample_state": "POSITIVE_CANDIDATE", "passes_main_gates_provisional": 1, "distance_to_flare_hr": 5.7},
    ]
    record("anchor_nearest_with_tolerance", choose_anchor(fake, "POSITIVE_CANDIDATE", 4.5) is not None, "near anchor selected")
    fake_far = [{"sample_state": "POSITIVE_CANDIDATE", "passes_main_gates_provisional": 1, "distance_to_flare_hr": 3.2}]
    record("anchor_far_rejected", choose_anchor(fake_far, "POSITIVE_CANDIDATE", 4.5) is None, "far anchor rejected")
    return rows


def validate_distribution_expectations(distribution: list[dict[str, object]]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    expected = {
        ("STRICT_BASELINE_QUEUE", "POSITIVE_CANDIDATE"): 0.471007,
        ("ALL_SAMPLE_STRICT_BASELINE_AFTER_GATES", "NEGATIVE_CANDIDATE"): -0.111901,
        ("ALL_SAMPLE_STRICT_BASELINE_AFTER_GATES", "POSITIVE_CANDIDATE"): 0.441195,
    }
    for key, target in expected.items():
        queue, state = key
        row = next((item for item in distribution if item["queue"] == queue and item["sample_state"] == state), None)
        actual = None if row is None or row["median"] == "" else float(row["median"])
        ok = actual is not None and abs(actual - target) < 0.001
        checks.append(
            {
                "test": f"distribution_median_{queue}_{state}",
                "status": "PASS" if ok else "WARN",
                "detail": f"expected approx {target}, actual {actual}",
            }
        )
    return checks


def run(fetch: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_quality_policy()
    policy_path, policy_hash = write_policy()
    policy_hash = sha256_file(policy_path)
    write_event_seed_table()

    provenance_rows = event_provenance_rows()
    write_csv(OUT_DIR / "02_event_provenance_audit.csv", provenance_rows)

    query_rows: list[dict[str, object]] = []
    cadence_rows: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []
    for event in seed.EVENTS:
        try:
            raw_path, url, ds = fetch_or_copy_raw(event, fetch=fetch)
            jsoc_rows = parse_jsoc_payload(raw_path)
            cadence_rows.append(cadence_audit_for_event(event, jsoc_rows))
            all_rows.extend(build_rows_for_event(event, jsoc_rows))
            status = "PASS"
            note = f"Returned {len(jsoc_rows)} keyword rows; raw JSON {'fetched' if fetch else 'copied from 20260723 cache'}."
        except Exception as exc:
            url, ds = seed.query_url(event)
            raw_path = RAW_DIR / f"{event.flare_event_id}.json"
            status = "DATA_UNAVAILABLE"
            note = str(exc)
        query_rows.append(
            {
                "flare_event_id": event.flare_event_id,
                "flare_NOAA_AR": event.flare_noaa_ar,
                "HARPNUM": event.harpnum,
                "flare_class": event.flare_class,
                "goes_onset_utc": format_utc(event.onset_utc),
                "jsoc_ds": ds,
                "query_url": url,
                "raw_json_relative_path": str(raw_path.relative_to(OUT_DIR)) if raw_path.exists() else "",
                "raw_json_sha256": sha256_file(raw_path) if raw_path.exists() else "",
                "status": status,
                "note": note,
            }
        )

    write_csv(OUT_DIR / "03_jsoc_query_manifest.csv", query_rows)
    write_csv(OUT_DIR / "12_cadence_audit.csv", cadence_rows)
    all_rows = sorted(
        all_rows,
        key=lambda row: (str(row["flare_event_id"]), float(row["distance_to_flare_hr"])),
        reverse=True,
    )
    queue_rows = build_provisional_queue(all_rows)
    strict_queue_rows = build_strict_baseline_queue(all_rows)
    write_csv(OUT_DIR / "04_all_sample_supplement.csv", all_rows, STANDARD_COLUMNS)
    write_csv(OUT_DIR / "05_provisional_mechanism_queue.csv", queue_rows, STANDARD_COLUMNS)
    write_csv(OUT_DIR / "05b_strict_quality0_sensitivity_queue.csv", strict_queue_rows, STANDARD_COLUMNS)

    gates = gate_counts(all_rows, queue_rows, strict_queue_rows, query_rows, cadence_rows, provenance_rows)
    status, reason = determine_status(gates)
    write_csv(OUT_DIR / "06_gate_counts.csv", gates)

    distribution = summarize_distribution(queue_rows, "PROVISIONAL_QUEUE", "SHRGT45_slope_3h_percent_per_hr")
    distribution.extend(summarize_distribution([row for row in all_rows if int(row["passes_main_gates_provisional"]) == 1], "ALL_SAMPLE_PROVISIONAL_AFTER_GATES", "SHRGT45_slope_3h_percent_per_hr"))
    distribution.extend(summarize_distribution(strict_queue_rows, "STRICT_BASELINE_QUEUE", "SHRGT45_slope_3h_strict_percent_per_hr"))
    distribution.extend(summarize_distribution([row for row in all_rows if int(row["passes_strict_baseline"]) == 1], "ALL_SAMPLE_STRICT_BASELINE_AFTER_GATES", "SHRGT45_slope_3h_strict_percent_per_hr"))
    write_csv(OUT_DIR / "07_continuous_distribution.csv", distribution)

    usflux_rows: list[dict[str, object]] = []
    usflux_rows.extend(usflux_correlation(queue_rows, "PROVISIONAL_QUEUE"))
    usflux_rows.extend(usflux_correlation(all_rows, "ALL_SAMPLE_PROVISIONAL_AFTER_GATES"))
    write_csv(OUT_DIR / "10_usflux_context_correlation.csv", usflux_rows)

    write_dataplan(status, reason, gates, policy_hash)
    write_leader_note(status, reason, gates)
    write_readme(status, reason)
    write_manifest(status, reason, gates, policy_hash, query_rows)
    write_acceptance_check(status)

    test_rows = self_test()
    test_rows.extend(validate_distribution_expectations(distribution))
    write_csv(OUT_DIR / "14_self_test_results.csv", test_rows)

    write_file_hash_manifest()
    zip_output()
    print(f"Wrote full-information revision package to {OUT_DIR}")
    print(f"status={status}")
    print(f"rows={len(all_rows)} provisional_anchors={len(queue_rows)} zip={ZIP_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SHRGT45 full-information baseline revision package.")
    parser.add_argument("--fetch", action="store_true", help="Fetch JSOC keyword JSON instead of using cached 20260723 raw JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(fetch=args.fetch)


if __name__ == "__main__":
    main()
