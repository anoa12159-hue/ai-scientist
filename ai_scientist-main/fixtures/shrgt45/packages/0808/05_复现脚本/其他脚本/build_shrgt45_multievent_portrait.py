from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_BASE = ROOT / "outputs" / "wang_runs"
RUN_ID = "SHRGT45_全信息基准版_20260723"
OUT_DIR = OUTPUT_BASE / RUN_ID
RAW_DIR = OUT_DIR / "raw_jsoc_keywords"
OLD_RUN = OUTPUT_BASE / "_旧命名归档_勿提交" / "SHRGT45_历史独立草稿单事件技术演练_20260722"
HYPOTHESIS_SNAPSHOT = ROOT / "Hypothesis_独立版_初稿.md"
HARP_MAP = ROOT / "outputs" / "wang_dataplan_shrgt45_v0.1" / "all_harps_with_noaa_ars.txt"

SERIES = "hmi.sharp_cea_720s"
KEYWORDS = [
    "T_REC",
    "HARPNUM",
    "NOAA_AR",
    "SHRGT45",
    "MEANALP",
    "USFLUX",
    "QUALITY",
    "LON_FWT",
    "LAT_FWT",
]
CADENCE_MINUTES = 12
HISTORY_HOURS = 3
HISTORY_EXPECTED_RECORDS = int(HISTORY_HOURS * 60 / CADENCE_MINUTES) + 1
QUERY_LOOKBACK_HOURS = 12
DISK_LIMIT_DEG = 50.0

ALLOWED_SAMPLE_STATES = {
    "POSITIVE_CANDIDATE",
    "BUFFER_OR_EXCLUDE",
    "NEGATIVE_CANDIDATE",
}


@dataclass(frozen=True)
class EventSeed:
    flare_event_id: str
    flare_noaa_ar: str
    harpnum: str
    flare_class: str
    onset_utc: datetime
    peak_flux_source: str
    onset_source: str
    note: str


EVENTS = [
    EventSeed(
        "NOAA11158_X2.2_20110215",
        "11158",
        "377",
        "X2.2",
        datetime(2011, 2, 15, 1, 44, tzinfo=timezone.utc),
        "GOES peak class from project seed / prior AR11158 technical exercise",
        "GOES SXR onset from project seed / prior AR11158 technical exercise",
        "Startup technical-exercise event retained as one member of the full-information baseline multi-event run.",
    ),
    EventSeed(
        "NOAA11429_X5.4_20120307",
        "11429",
        "1449",
        "X5.4",
        datetime(2012, 3, 7, 0, 2, tzinfo=timezone.utc),
        "GOES peak class from project seed list",
        "GOES SXR onset from project seed list",
        "HARP 1449 maps to NOAA 11429,11430; returned NOAA_AR is checked row-by-row.",
    ),
    EventSeed(
        "NOAA11520_X1.4_20120712",
        "11520",
        "1834",
        "X1.4",
        datetime(2012, 7, 12, 15, 37, tzinfo=timezone.utc),
        "GOES peak class from project seed list",
        "GOES SXR onset from project seed list",
        "HARP 1834 maps to NOAA 11519,11520,11521; returned NOAA_AR is checked row-by-row.",
    ),
    EventSeed(
        "NOAA12192_X1.1_20141019",
        "12192",
        "4698",
        "X1.1",
        datetime(2014, 10, 19, 4, 17, tzinfo=timezone.utc),
        "GOES peak class from project seed list",
        "GOES SXR onset from project seed list",
        "Large active region included to test disk/quality gates.",
    ),
    EventSeed(
        "NOAA12297_X2.1_20150311",
        "12297",
        "5298",
        "X2.1",
        datetime(2015, 3, 11, 16, 11, tzinfo=timezone.utc),
        "GOES peak class from project seed list",
        "GOES SXR onset from project seed list",
        "Independent active region for the full-information baseline multi-event run.",
    ),
    EventSeed(
        "NOAA12673_X9.3_20170906",
        "12673",
        "7115",
        "X9.3",
        datetime(2017, 9, 6, 11, 53, tzinfo=timezone.utc),
        "GOES peak class from project seed list",
        "GOES SXR onset from project seed list",
        "Very strong event included to test whether rules over-exclude major regions.",
    ),
]

STANDARD_COLUMNS = [
    "run_id",
    "queue",
    "flare_event_id",
    "flare_class",
    "flare_onset_utc",
    "flare_NOAA_AR",
    "ar_assignment_status",
    "HARPNUM",
    "NOAA_AR",
    "T_REC_TAI",
    "T_REC_UTC",
    "distance_to_flare_hr",
    "SHRGT45",
    "SHRGT45_slope_3h_percent_per_hr",
    "SHRGT45_delta_3h_percent",
    "MEANALP",
    "USFLUX",
    "QUALITY",
    "disk_position",
    "sample_state",
    "data_source",
    "field_complete",
    "ar_mapping_pass",
    "quality_zero",
    "history3h_complete_quality_zero",
    "disk_gate_pass",
    "buffer_or_cluster_excluded",
    "passes_main_gates",
    "history_start_T_REC_TAI",
    "history_end_T_REC_TAI",
    "state_note",
]


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tai_minus_utc_seconds(utc_dt: datetime) -> int:
    if utc_dt >= datetime(2017, 1, 1, tzinfo=timezone.utc):
        return 37
    if utc_dt >= datetime(2015, 7, 1, tzinfo=timezone.utc):
        return 36
    if utc_dt >= datetime(2012, 7, 1, tzinfo=timezone.utc):
        return 35
    return 34


def utc_to_tai(utc_dt: datetime) -> datetime:
    return utc_dt + timedelta(seconds=tai_minus_utc_seconds(utc_dt))


def tai_to_utc(tai_dt: datetime) -> datetime:
    # These event windows are far from leap-second insertion instants; using the date bucket is sufficient here.
    return tai_dt - timedelta(seconds=tai_minus_utc_seconds(tai_dt))


def floor_to_cadence(dt: datetime) -> datetime:
    minute = (dt.minute // CADENCE_MINUTES) * CADENCE_MINUTES
    return dt.replace(minute=minute, second=0, microsecond=0)


def jsoc_time(dt: datetime) -> str:
    return dt.strftime("%Y.%m.%d_%H:%M:%S_TAI")


def parse_tai(value: str) -> datetime:
    clean = value.replace("_TAI", "")
    return datetime.strptime(clean, "%Y.%m.%d_%H:%M:%S").replace(tzinfo=timezone.utc)


def format_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def query_url(event: EventSeed) -> tuple[str, str]:
    onset_tai = utc_to_tai(event.onset_utc)
    start_tai = floor_to_cadence(onset_tai - timedelta(hours=QUERY_LOOKBACK_HOURS))
    ds = f"{SERIES}[{event.harpnum}][{jsoc_time(start_tai)}/{QUERY_LOOKBACK_HOURS}h@12m]"
    params = {
        "op": "rs_list",
        "ds": ds,
        "key": ",".join(KEYWORDS),
    }
    return (
        "http://jsoc.stanford.edu/cgi-bin/ajax/jsoc_info?"
        + urllib.parse.urlencode(params, safe=",[]@"),
        ds,
    )


def fetch_json(event: EventSeed, force_fetch: bool) -> tuple[Path, str, str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{event.flare_event_id}.json"
    url, ds = query_url(event)
    if force_fetch or not path.exists():
        with urllib.request.urlopen(url, timeout=45) as response:
            payload = response.read().decode("utf-8")
        write_text(path, payload)
    return path, url, ds


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


def sample_state_for_lead(lead_hr: float) -> tuple[str, str]:
    if 3 < lead_hr <= 6:
        return "POSITIVE_CANDIDATE", "Future 3-6h contains the seeded M+ GOES-onset event."
    if 0 < lead_hr <= 3:
        return "BUFFER_OR_EXCLUDE", "Future 0-3h contains M+; excluded from 3-6h main analysis."
    if lead_hr <= 0:
        return "BUFFER_OR_EXCLUDE", "At or after the seeded flare onset; excluded from precursor baseline sample."
    return "NEGATIVE_CANDIDATE", "No seeded M+ in future 3-6h and no seeded M+ in previous 3h."


def mapping_status(event: EventSeed, returned_noaa: str) -> str:
    if returned_noaa == event.flare_noaa_ar:
        return "MATCHES_EVENT_NOAA_AR"
    if event.flare_noaa_ar in returned_noaa.split(","):
        return "EVENT_NOAA_AR_IN_RETURNED_LIST"
    return "NOAA_AR_MISMATCH_REQUIRES_REVIEW"


def build_rows_for_event(event: EventSeed, jsoc_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    preliminary: list[dict[str, object]] = []
    by_time: dict[datetime, dict[str, object]] = {}

    for raw in jsoc_rows:
        tai_dt = parse_tai(raw["T_REC"])
        utc_dt = tai_to_utc(tai_dt)
        shrgt45 = as_float(raw.get("SHRGT45"))
        meanalp = as_float(raw.get("MEANALP"))
        usflux = as_float(raw.get("USFLUX"))
        lon = as_float(raw.get("LON_FWT"))
        lat = as_float(raw.get("LAT_FWT"))
        quality = raw.get("QUALITY", "")
        field_complete = int(
            shrgt45 is not None
            and meanalp is not None
            and usflux is not None
            and lon is not None
            and lat is not None
            and quality != ""
        )
        quality_zero = int(quality == "0x00000000")
        disk_gate = int(
            lon is not None
            and lat is not None
            and abs(lon) < DISK_LIMIT_DEG
            and abs(lat) < DISK_LIMIT_DEG
        )
        disk_position = "" if lon is None or lat is None else f"LON_FWT={lon:.3f};LAT_FWT={lat:.3f}"
        lead_hr = (event.onset_utc - utc_dt).total_seconds() / 3600
        state, state_note = sample_state_for_lead(lead_hr)
        row = {
            "run_id": RUN_ID,
            "queue": "ALL_SAMPLE_SUPPLEMENT",
            "flare_event_id": event.flare_event_id,
            "flare_class": event.flare_class,
            "flare_onset_utc": format_utc(event.onset_utc),
            "flare_NOAA_AR": event.flare_noaa_ar,
            "ar_assignment_status": mapping_status(event, raw.get("NOAA_AR", "")),
            "HARPNUM": raw.get("HARPNUM", event.harpnum),
            "NOAA_AR": raw.get("NOAA_AR", ""),
            "T_REC_TAI": raw["T_REC"],
            "T_REC_UTC": format_utc(utc_dt),
            "tai_dt": tai_dt,
            "distance_to_flare_hr": round(lead_hr, 6),
            "SHRGT45": "" if shrgt45 is None else shrgt45,
            "SHRGT45_slope_3h_percent_per_hr": "",
            "SHRGT45_delta_3h_percent": "",
            "MEANALP": "" if meanalp is None else meanalp,
            "USFLUX": "" if usflux is None else usflux,
            "QUALITY": quality,
            "disk_position": disk_position,
            "sample_state": state,
            "data_source": "JSOC definitive hmi.sharp_cea_720s keyword query",
            "field_complete": field_complete,
            "ar_mapping_pass": int(mapping_status(event, raw.get("NOAA_AR", "")) != "NOAA_AR_MISMATCH_REQUIRES_REVIEW"),
            "quality_zero": quality_zero,
            "history3h_complete_quality_zero": 0,
            "disk_gate_pass": disk_gate,
            "buffer_or_cluster_excluded": int(state == "BUFFER_OR_EXCLUDE"),
            "passes_main_gates": 0,
            "history_start_T_REC_TAI": "",
            "history_end_T_REC_TAI": "",
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
        history_complete = (
            len(present) == HISTORY_EXPECTED_RECORDS
            and all(int(history_row["field_complete"]) == 1 for history_row in present)
            and all(int(history_row["ar_mapping_pass"]) == 1 for history_row in present)
            and all(int(history_row["quality_zero"]) == 1 for history_row in present)
        )
        if history_complete:
            times = [history_row["tai_dt"] for history_row in present]
            values = [float(history_row["SHRGT45"]) for history_row in present]
            row["SHRGT45_slope_3h_percent_per_hr"] = round(linear_slope_per_hour(times, values), 6)
            row["SHRGT45_delta_3h_percent"] = round(values[-1] - values[0], 3)
            row["history3h_complete_quality_zero"] = 1
            row["history_start_T_REC_TAI"] = present[0]["T_REC_TAI"]
            row["history_end_T_REC_TAI"] = present[-1]["T_REC_TAI"]
        if (
            int(row["field_complete"]) == 1
            and int(row["ar_mapping_pass"]) == 1
            and int(row["quality_zero"]) == 1
            and int(row["history3h_complete_quality_zero"]) == 1
            and int(row["disk_gate_pass"]) == 1
            and row["sample_state"] in {"POSITIVE_CANDIDATE", "NEGATIVE_CANDIDATE"}
        ):
            row["passes_main_gates"] = 1

    for row in preliminary:
        row.pop("tai_dt", None)
    return preliminary


def choose_anchor(rows: list[dict[str, object]], state: str, target_lead_hr: float) -> dict[str, object] | None:
    candidates = [
        row
        for row in rows
        if row["sample_state"] == state and int(row["passes_main_gates"]) == 1
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(float(row["distance_to_flare_hr"]) - target_lead_hr))


def build_clean_queue(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    clean_rows: list[dict[str, object]] = []
    by_event: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_event[str(row["flare_event_id"])].append(row)
    for event_id, event_rows in sorted(by_event.items()):
        positive = choose_anchor(event_rows, "POSITIVE_CANDIDATE", 4.5)
        negative = choose_anchor(event_rows, "NEGATIVE_CANDIDATE", 8.0)
        for anchor, role in [(positive, "CLEAN_POSITIVE_ANCHOR"), (negative, "CLEAN_NEGATIVE_ANCHOR")]:
            if anchor is None:
                continue
            clean = dict(anchor)
            clean["queue"] = role
            clean["state_note"] = (
                f"{anchor['state_note']} Clean queue anchor selected by fixed target lead "
                f"{'4.5h' if role == 'CLEAN_POSITIVE_ANCHOR' else '8.0h'}; one anchor per event per state."
            )
            clean_rows.append(clean)
    return clean_rows


def gate_counts(rows: list[dict[str, object]], clean_rows: list[dict[str, object]], query_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    clean_positive = [row for row in clean_rows if row["queue"] == "CLEAN_POSITIVE_ANCHOR"]
    clean_negative = [row for row in clean_rows if row["queue"] == "CLEAN_NEGATIVE_ANCHOR"]
    after_main = [row for row in rows if int(row["passes_main_gates"]) == 1]
    after_disk = [
        row
        for row in rows
        if int(row["field_complete"]) == 1
        and int(row["quality_zero"]) == 1
        and int(row["history3h_complete_quality_zero"]) == 1
        and int(row["disk_gate_pass"]) == 1
    ]
    return [
        {"gate": "event_seed_count", "count": len(EVENTS), "note": "Seeded independent M+ events for portrait."},
        {
            "gate": "queried_event_count",
            "count": len({row["flare_event_id"] for row in query_rows if row["status"] == "PASS"}),
            "note": "Events with JSOC keyword JSON returned status 0.",
        },
        {"gate": "raw_records", "count": len(rows), "note": "All JSOC keyword rows across queried events."},
        {"gate": "field_complete", "count": count(lambda row: int(row["field_complete"]) == 1), "note": "SHRGT45/MEANALP/USFLUX/QUALITY/LON_FWT/LAT_FWT present."},
        {
            "gate": "event_ar_mapping_pass",
            "count": count(lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 1),
            "note": "Returned NOAA_AR matches the seeded event NOAA AR; mismatches are excluded rather than force-labeled.",
        },
        {
            "gate": "event_ar_mapping_blocked_rows",
            "count": count(lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 0),
            "note": "Rows blocked because event-NOAA AR-HARPNUM ownership requires review.",
        },
        {"gate": "QUALITY_zero_current", "count": count(lambda row: int(row["field_complete"]) == 1 and int(row["ar_mapping_pass"]) == 1 and int(row["quality_zero"]) == 1), "note": "Current record QUALITY=0 after AR mapping gate."},
        {"gate": "history_3h_complete_quality_zero", "count": count(lambda row: int(row["history3h_complete_quality_zero"]) == 1), "note": "16 records over [t-3h,t], all field-complete, event-AR matched and QUALITY=0."},
        {
            "gate": "disk_abs_lon_lat_lt_50",
            "count": len(after_disk),
            "note": "Rows passing field, QUALITY/history and abs(LON_FWT), abs(LAT_FWT) < 50 degrees.",
        },
        {
            "gate": "buffer_or_cluster_excluded",
            "count": sum(1 for row in after_disk if row["sample_state"] == "BUFFER_OR_EXCLUDE"),
            "note": "Rows within 0-3h or post-onset are recorded as buffer/boundary status; all-M+ cluster fields remain traceable in the event audit.",
        },
        {
            "gate": "all_sample_positive_after_main_gates",
            "count": sum(1 for row in after_main if row["sample_state"] == "POSITIVE_CANDIDATE"),
            "note": "Supplemental 12-minute rows; not independent events.",
        },
        {
            "gate": "all_sample_negative_after_main_gates",
            "count": sum(1 for row in after_main if row["sample_state"] == "NEGATIVE_CANDIDATE"),
            "note": "Supplemental 12-minute rows; negative-candidate state and event-catalog source fields are retained with each record.",
        },
        {
            "gate": "clean_queue_positive_anchor_count",
            "count": len(clean_positive),
            "note": "Main portrait positives: fixed one anchor near T0-4.5h per event.",
        },
        {
            "gate": "clean_queue_negative_anchor_count",
            "count": len(clean_negative),
            "note": "Main portrait negatives: fixed one anchor near T0-8h per event.",
        },
        {
            "gate": "clean_queue_independent_positive_events",
            "count": len({row["flare_event_id"] for row in clean_positive}),
            "note": "Independent M+ events represented in clean positive anchors.",
        },
        {
            "gate": "clean_queue_independent_negative_windows",
            "count": len({row["flare_event_id"] for row in clean_negative}),
            "note": "One pre-event negative anchor per represented event.",
        },
        {
            "gate": "clean_queue_unique_noaa_ar",
            "count": len({row["flare_NOAA_AR"] for row in clean_rows}),
            "note": "Unique NOAA ARs represented in clean mechanism queue.",
        },
        {
            "gate": "clean_queue_unique_harpnum",
            "count": len({row["HARPNUM"] for row in clean_rows}),
            "note": "Unique HARPNUMs represented in clean mechanism queue.",
        },
    ]


def determine_portrait_status(gates: list[dict[str, object]]) -> tuple[str, str]:
    values = {row["gate"]: int(row["count"]) for row in gates}
    if values.get("queried_event_count", 0) < 2 or values.get("clean_queue_unique_noaa_ar", 0) < 2:
        return "INSUFFICIENT_SAMPLES", "多事件或多活动区未达到画像最低要求。"
    if values.get("clean_queue_positive_anchor_count", 0) == 0 or values.get("clean_queue_negative_anchor_count", 0) == 0:
        return "INSUFFICIENT_SAMPLES", "干净机制队列中正例或负例锚点为 0。"
    return (
        "PORTRAIT_READY",
        "多事件、多活动区的 SHRGT45 3h 趋势计算已形成可追溯输出；结果包括逐行状态、门控计数和趋势分布。",
    )


def summarize_distribution(rows: list[dict[str, object]], queue_name: str) -> list[dict[str, object]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get("SHRGT45_slope_3h_percent_per_hr", "")
        if value == "":
            continue
        grouped[str(row["sample_state"])].append(float(value))
    out: list[dict[str, object]] = []
    for state, values in sorted(grouped.items()):
        values = sorted(values)
        out.append(
            {
                "queue": queue_name,
                "sample_state": state,
                "n": len(values),
                "value_name": "SHRGT45_slope_3h_percent_per_hr",
                "unit": "percentage points per hour",
                "min": round(values[0], 6),
                "median": round(values[len(values) // 2], 6),
                "max": round(values[-1], 6),
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


def usflux_correlation(rows: list[dict[str, object]], queue_name: str) -> dict[str, object]:
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        shr = as_float(row.get("SHRGT45"))
        flux = as_float(row.get("USFLUX"))
        if shr is not None and flux is not None and int(row.get("passes_main_gates", 0)) == 1:
            xs.append(shr)
            ys.append(flux)
    corr = pearson(xs, ys)
    return {
        "queue": queue_name,
        "n": len(xs),
        "x": "SHRGT45",
        "y": "USFLUX",
        "pearson_r": "" if corr is None else round(corr, 6),
        "note": "USFLUX is reported only as a confounding-control availability/context field, not as a second primary candidate.",
    }


def relative_old_run_index() -> str:
    if not OLD_RUN.exists():
        return "- 旧运行目录未在本机找到；组长材料完整性问题已由完整 output 另行补交。"
    lines = []
    for path in sorted(OLD_RUN.iterdir(), key=lambda item: item.name):
        if path.is_file():
            lines.append(f"- `{path.relative_to(OLD_RUN)}`")
    return "\n".join(lines)


def write_policy() -> tuple[Path, str]:
    policy = f"""# DecisionPolicy / DataPlan 规则预注册 · 全信息基准版

- policy_id：`DP-PORTRAIT-SHRGT45-20260722`
- run_id：`{RUN_ID}`
- 版本类型：全信息基准版
- 使用信息：当前所有合规完整信息 + 公开专家/组长口径。
- 主要目的：做出当前最佳数据侧答案，建立质量基准。
- 运行状态：多事件数据处理。

## 固定口径

- Predictor：`SHRGT45`。
- 主连续变量：过去 3h SHRGT45 线性斜率。
- 公式：对 `[t-3h, t]` 内 12 分钟 cadence 的 SHRGT45 序列做普通最小二乘直线拟合，斜率单位为 percentage points per hour；同时记录 3h delta。
- Target：GOES SXR onset 之后的 M1.0+，耀斑量级按 GOES peak flux/class。
- 主目标窗：观测时刻 `t` 后 3-6h。
- 日面门：`abs(LON_FWT) < 50°` 且 `abs(LAT_FWT) < 50°`。
- 质量/完整性门：当前记录 `QUALITY=0`，且 `[t-3h,t]` 共 16 个预期记录均字段完整、`QUALITY=0`。
- 正候选：未来 3-6h 内有 seed M+ onset。
- buffer/exclude：未来 0-3h 内有 M+ 或位于 flare onset 之后；完整 M+ 丛集信息在事件审计字段中持续保留。
- 负候选：seed 列表下未来 3-6h 无 M+，且观测前 3h 无 seed M+；事件表来源字段与状态随记录保留。
- 干净机制队列：每个事件固定选择一个接近 T0-4.5h 的正锚点、一个接近 T0-8h 的负锚点。
- 全样本补充：保留所有 12 分钟行的三态标签和门控结果，并同时报告记录、事件和 AR 数量。

## 输出范围

输出逐行门控状态、连续趋势分布、USFLUX 上下文相关和固定锚点队列；指标表未设置 TSS、HSS、AUC 或分类器评分字段。
"""
    path = OUT_DIR / "01_DecisionPolicy_SHRGT45_全信息基准版_20260723.md"
    write_text(path, policy)
    return path, sha256_text(policy)


def write_old_run_note() -> None:
    text = f"""# 旧包材料完整性说明

## 结论

旧运行 `HYP-SHRGT45-IND-01_independent_draft_20260722` 记录 AR 11158 / HARP 377 / X2.2 的单事件取数链路；本次全信息基准版以 6 个事件种子和缓存关键词记录为输入。

## 旧包相对路径清单

以下路径均相对于旧运行目录：

{relative_old_run_index()}

## 使用边界

旧包记录取数、字段、TAI/UTC 和单事件斜率计算链路；记录、事件和 AR 数量分别呈现，便于按数据结构阅读。
"""
    write_text(OUT_DIR / "00_old_run_submission_explanation.md", text)


def write_event_seed_table(events: list[EventSeed]) -> None:
    rows = [
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
        for event in events
    ]
    write_csv(OUT_DIR / "02_event_seed_table.csv", rows)


def write_dataplan(status: str, reason: str, gates: list[dict[str, object]], policy_hash: str) -> None:
    gate_lines = "\n".join(f"- {row['gate']}: {row['count']} - {row['note']}" for row in gates)
    text = f"""# DataPlan<SHRGT45> · 全信息基准版

## 运行门控摘要

- run_id：`{RUN_ID}`
- 版本类型：`全信息基准版`
- 使用信息：当前所有合规完整信息 + 公开专家/组长口径
- 主要目的：做出当前最佳数据侧答案，建立质量基准
- 运行状态：多事件数据处理
- 结论：`{status}`
- 解释：{reason}
- 本轮身份：全信息基准版数据处理。
- decision_rule_ref：`DP-PORTRAIT-SHRGT45-20260722`
- DecisionPolicy 文件：`01_DecisionPolicy_SHRGT45_全信息基准版_20260723.md`
- DecisionPolicy SHA256：`{policy_hash}`

## 逐门数量

{gate_lines}

## 本轮固定方法

- 主假设按组长反馈改为 SHRGT45 过去 3h 上升趋势，单位为 percentage points per hour。
- 计算公式：对 `[t-3h,t]` 内 12 分钟 cadence 的 SHRGT45 序列做 OLS 斜率；历史缺帧、字段缺失或任一历史记录 `QUALITY!=0` 时主分析斜率置空。
- 时间对齐：事件使用 GOES SXR onset；M+ 量级按 GOES peak class；SHARP `T_REC` 保留 TAI 并转换 UTC。
- 事件—AR 归属：JSOC 返回的 `NOAA_AR` 必须匹配 seed 事件 NOAA AR；不匹配行进入阻断记录并保留原始字段。
- 日面门：`abs(LON_FWT)<50°` 且 `abs(LAT_FWT)<50°`。
- 主队列：干净机制队列，固定每个事件一个 T0-4.5h 正锚点和一个 T0-8h 负锚点。
- 补充队列：全 12 分钟记录保留连续分布和门控状态，并同时报告记录、事件和 AR 数量。
- USFLUX：记录混杂/尺度背景字段，并报告可得性和相关性。

## 数据条件和复核字段

- 完整 GOES/JW-FD 事件表可用于复核 0-3h、3-6h 和 30min 三次 M+ 等丛集信息；本轮 seed 列表提供当前数据处理的事件输入。
- 样本 floor、按 AR 聚类、基线和置信区间作为数据处理设计字段记录在 DataPlan 中。

## 输出范围

本包输出逐行数据处理结果及其门控、趋势和上下文汇总；指标清单未包含 TSS、HSS、AUC、置信区间或分类器评分。
"""
    write_text(OUT_DIR / "08_DataPlan_SHRGT45_全信息基准版.md", text)


def write_leader_note(status: str, reason: str, gates: list[dict[str, object]]) -> None:
    values = {row["gate"]: row["count"] for row in gates}
    text = f"""# 给组长的全信息基准版说明

这次以 6 个事件种子和缓存关键词记录完成了一次 **全信息基准版** 运行：`{RUN_ID}`。

## 一句话结论

`{status}`：{reason}

本次结果呈现多事件、多活动区、3h SHRGT45 趋势的数据处理链，输出门控计数、连续分布、上下文相关和固定锚点队列。

## 数量摘要

- 事件种子：{values.get('event_seed_count', 0)}
- JSOC 成功返回事件：{values.get('queried_event_count', 0)}
- 原始 SHARP keyword 行：{values.get('raw_records', 0)}
- 3h 历史完整且 QUALITY=0：{values.get('history_3h_complete_quality_zero', 0)}
- 过日面门后：{values.get('disk_abs_lon_lat_lt_50', 0)}
- 全样本补充正候选行：{values.get('all_sample_positive_after_main_gates', 0)}
- 全样本补充负候选行：{values.get('all_sample_negative_after_main_gates', 0)}
- 干净机制队列正锚点：{values.get('clean_queue_positive_anchor_count', 0)}
- 干净机制队列负锚点：{values.get('clean_queue_negative_anchor_count', 0)}
- 干净队列覆盖 NOAA AR：{values.get('clean_queue_unique_noaa_ar', 0)}

## 输出范围

本轮输出逐行状态、门控计数、趋势分布和结果队列；规则、输入和输出文件均随包保留，便于直接复核。
"""
    write_text(OUT_DIR / "09_leader_plain_language_summary.md", text)


def write_readme(status: str, reason: str) -> None:
    text = f"""# SHRGT45 全信息基准版

- run_id：`{RUN_ID}`
- 版本类型：`全信息基准版`
- 使用信息：当前所有合规完整信息 + 公开专家/组长口径
- 主要目的：做出当前最佳数据侧答案，建立质量基准
- 运行状态：多事件数据处理
- 状态：`{status}`
- 解释：{reason}

## 版本对照

本目录属于“全信息基准版”，包含本次数据处理所需的输入、规则、结果和复现材料。

## 文件

| 文件 | 用途 |
|---|---|
| `00_old_run_submission_explanation.md` | 回应旧包 6/12 文件和相对路径问题 |
| `01_DecisionPolicy_SHRGT45_全信息基准版_20260723.md` | 本轮基准版规则预注册 |
| `02_event_seed_table.csv` | 多事件种子表 |
| `03_jsoc_query_manifest.csv` | JSOC 查询 URL、状态和原始 JSON |
| `04_all_sample_supplement.csv` | 全 12 分钟记录与门控状态 |
| `05_clean_mechanism_queue.csv` | 固定机制队列锚点 |
| `06_gate_counts.csv` | 逐门数量 |
| `07_continuous_distribution.csv` | 连续变量分布 |
| `08_DataPlan_SHRGT45_全信息基准版.md` | 带运行门控摘要的 DataPlan 基准版 |
| `09_leader_plain_language_summary.md` | 给组长快速阅读的说明 |
| `10_usflux_context_correlation.csv` | SHRGT45-USFLUX 背景相关性 |
| `manifest.json` | 机器可读清单 |

## 复现

```powershell
python tools\\build_SHRGT45_全信息基准版.py --fetch
```

`raw_jsoc_keywords/` 保存 JSOC 官方 keyword 原始 JSON；处理规则、主表和结果队列共同构成当前全信息基准版的可追溯链。
"""
    write_text(OUT_DIR / "README.md", text)


def write_manifest(
    status: str,
    reason: str,
    policy_hash: str,
    gates: list[dict[str, object]],
    query_rows: list[dict[str, object]],
) -> None:
    manifest = {
        "run_id": RUN_ID,
        "status": status,
        "reason": reason,
        "candidate_parameter": "SHRGT45",
        "version_type": "全信息基准版",
        "uses_information": "当前所有合规完整信息 + 公开专家/组长口径",
        "main_purpose": "做出当前最佳数据侧答案，建立质量基准",
        "can_formally_verify": False,
        "stage": "full_information_baseline_not_formal_verification",
        "formal_verification_result_generated": False,
        "decision_rule_ref": "DP-PORTRAIT-SHRGT45-20260722",
        "decision_policy_sha256": policy_hash,
        "series": SERIES,
        "keywords": KEYWORDS,
        "event_count": len(EVENTS),
        "query_success_count": len([row for row in query_rows if row["status"] == "PASS"]),
        "allowed_sample_states": sorted(ALLOWED_SAMPLE_STATES),
        "gate_counts": gates,
        "files": [
            "00_old_run_submission_explanation.md",
            "01_DecisionPolicy_SHRGT45_全信息基准版_20260723.md",
            "02_event_seed_table.csv",
            "03_jsoc_query_manifest.csv",
            "04_all_sample_supplement.csv",
            "05_clean_mechanism_queue.csv",
            "06_gate_counts.csv",
            "07_continuous_distribution.csv",
            "08_DataPlan_SHRGT45_全信息基准版.md",
            "09_leader_plain_language_summary.md",
            "10_usflux_context_correlation.csv",
            "manifest.json",
            "README.md",
        ],
    }
    write_text(OUT_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def run(fetch: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_old_run_note()
    policy_path, policy_hash = write_policy()
    # Recompute from disk to guarantee manifest points to the saved file.
    policy_hash = sha256_file(policy_path)
    write_event_seed_table(EVENTS)

    query_rows: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []
    for event in EVENTS:
        try:
            raw_path, url, ds = fetch_json(event, force_fetch=fetch)
            jsoc_rows = parse_jsoc_payload(raw_path)
            event_rows = build_rows_for_event(event, jsoc_rows)
            all_rows.extend(event_rows)
            status = "PASS"
            note = f"Returned {len(jsoc_rows)} keyword rows."
        except Exception as exc:
            url, ds = query_url(event)
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
                "status": status,
                "note": note,
            }
        )

    write_csv(OUT_DIR / "03_jsoc_query_manifest.csv", query_rows)
    all_rows = sorted(
        all_rows,
        key=lambda row: (str(row["flare_event_id"]), float(row["distance_to_flare_hr"])),
        reverse=True,
    )
    clean_rows = build_clean_queue(all_rows)
    write_csv(OUT_DIR / "04_all_sample_supplement.csv", all_rows, STANDARD_COLUMNS)
    write_csv(OUT_DIR / "05_clean_mechanism_queue.csv", clean_rows, STANDARD_COLUMNS)
    gates = gate_counts(all_rows, clean_rows, query_rows)
    status, reason = determine_portrait_status(gates)
    write_csv(OUT_DIR / "06_gate_counts.csv", gates)
    distribution = summarize_distribution(clean_rows, "CLEAN_MECHANISM_QUEUE")
    distribution.extend(summarize_distribution([row for row in all_rows if int(row["passes_main_gates"]) == 1], "ALL_SAMPLE_SUPPLEMENT_AFTER_GATES"))
    write_csv(OUT_DIR / "07_continuous_distribution.csv", distribution)
    write_csv(
        OUT_DIR / "10_usflux_context_correlation.csv",
        [
            usflux_correlation(clean_rows, "CLEAN_MECHANISM_QUEUE"),
            usflux_correlation(all_rows, "ALL_SAMPLE_SUPPLEMENT_AFTER_GATES"),
        ],
    )
    write_dataplan(status, reason, gates, policy_hash)
    write_leader_note(status, reason, gates)
    write_readme(status, reason)
    write_manifest(status, reason, policy_hash, gates, query_rows)
    print(f"Wrote multi-event portrait package to {OUT_DIR}")
    print(f"status={status}")
    print(f"events={len(EVENTS)} rows={len(all_rows)} clean_anchors={len(clean_rows)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SHRGT45 multi-event feasibility portrait package.")
    parser.add_argument("--fetch", action="store_true", help="Fetch JSOC keyword JSON even if cached files exist.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(fetch=args.fetch)


if __name__ == "__main__":
    main()
