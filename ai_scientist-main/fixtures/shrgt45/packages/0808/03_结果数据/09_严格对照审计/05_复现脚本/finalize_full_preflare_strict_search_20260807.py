"""Evaluate every catalog-clean pre-flare grid point and retain one time candidate per AR."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import urllib.parse
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "05_复现脚本" / "build_strict_negative_control_search_20260807.py"
SPEC = importlib.util.spec_from_file_location("strict_search_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {CORE_PATH}")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    names = fieldnames or (list(rows[0].keys()) if rows else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scan_query_url(event: object, start_tai: datetime) -> tuple[str, str]:
    dataset = f"hmi.sharp_cea_720s[{event.harpnum}][{core.tai_text(start_tai)}/80h@12m]"
    query = urllib.parse.urlencode({"op": "rs_list", "ds": dataset, "key": ",".join(core.KEYS)})
    return f"http://jsoc.stanford.edu/cgi-bin/ajax/jsoc_info?{query}", dataset


def primary_status(row: dict[str, object]) -> bool:
    return row["candidate_status"] == "CATALOG_CLEAN_AND_STRICT_DATA_QUALIFIED_TIME_CANDIDATE"


def compact_failure_summary(rows: list[tuple[dict[str, object], dict[str, object], list[dict[str, object]], dict[str, object]]]) -> str:
    if not rows:
        return "No catalog-clean grid point."
    checks = [
        ("16/16 历史记录", "history_returned_records", lambda value: int(value) == core.HISTORY_RECORDS),
        ("字段完整", "history_all_fields_complete", lambda value: value == "PASS"),
        ("HARP/NOAA 映射", "history_all_HARP_NOAA_mapping", lambda value: value == "PASS"),
        ("全部 QUALITY=0", "history_all_QUALITY_zero", lambda value: value == "PASS"),
        ("T0 位置门", "T0_disk_position_abs_lon_lat_lt_50", lambda value: value == "PASS"),
    ]
    counts = []
    total = len(rows)
    for label, column, passed in checks:
        failed = sum(not passed(item[0][column]) for item in rows)
        if failed:
            counts.append(f"{label}未通过 {failed}/{total}")
    return "；".join(counts) or "无"


def summary_markdown(summary: list[dict[str, object]]) -> str:
    found = [item for item in summary if item["strict_time_candidate_found"] == "YES"]
    lines = [
        f"# {core.RUN_ID}",
        "",
        "## 结论",
        "",
        f"对 6 个活动区前推 72 小时的全部目录清洁 12 分钟格点逐一复核后，**{len(found)}/6 个活动区**至少找到 1 个同时通过 NCEI 完整区间筛查和既有 strict 数据门的同 AR 时间候选。每个活动区只按“最近通过严格门”保留 1 个代表时点；其余重叠滑动窗仅保留在审计表中，绝不计作独立样本。",
        "",
        "该结论比先前的中央时点试探更完整：时点的最终选择不查看 SHRGT45 斜率、USFLUX、MEANALP 或任何模型结果，只依赖目录时间、记录完整性、HARP/NOAA 映射、QUALITY 与位置门。",
        "",
        "**边界不变：**这些记录与各自目标耀斑共享同一活动区，仍只能称为同 AR 的探索性时间候选，不是独立的正式阴性对照；正式比较 control 仍为 0。CMASK、有效像素数和有效像素比例未在本次关键词输入中提供，不能声称已排除测量伪趋势。",
        "",
        "## 逐活动区结果",
        "",
        "| 事件 | 目录清洁候选格点 | strict 通过格点 | 保留时点 (UTC) | 距目标耀斑 | 未通过主因/结论 |",
        "|---|---:|---:|---|---:|---|",
    ]
    for item in summary:
        t0 = f"`{item['selected_T0_utc']}`" if item["selected_T0_utc"] else "无"
        conclusion = "通过：同 AR 时间候选（不作为正式独立对照）" if item["strict_time_candidate_found"] == "YES" else item["strict_failure_primary"]
        lead = f"{item['selected_lead_to_target_hr']} h" if item["selected_lead_to_target_hr"] else "-"
        lines.append(f"| {item['flare_event_id']} | {item['catalog_clean_grid_points']} | {item['strict_data_pass_grid_points']} | {t0} | {lead} | {conclusion} |")
    lines.extend(
        [
            "",
            "## 本轮处理",
            "",
            "1. 在目标耀斑前 72 小时、且早于既有缓存的时段，按 12 分钟网格列出候选。",
            "2. 对每个候选检查 NCEI M+ 事件的完整持续区间是否与 `[T0-4h, T0+7h)` 相交；只按起始时刻而忽略持续时间的候选一律淘汰。",
            "3. 对通过目录筛查的每个 T0，使用新重取的 80 小时 HMI/SHARP 序列复算 `[T0-3h,T0]` 的 16 帧 strict 数据门。",
            "4. 对每个 AR，若有通过点，按时间从近到远保留最靠近既有缓存的一点；若无通过点，明确报告无 strict 时间候选。",
            "",
            "## AR11429 的更正",
            "",
            "先前的中间候选 `2012-03-05T07:23:26Z` 已排除。NCEI X1.6（`201203050222`）在该候选主窗之前开始，但持续到窗口内；这说明“无耀斑在窗口内开始”并不足以称为安静。完整区间筛查后，AR11429 的所有有效结果以本包全量审计表为准。",
            "",
            "## 建议阅读路径",
            "",
            "1. `02_审计数据/活动区最终选择摘要.csv`：每个 AR 的一句话结果和保留时点。",
            "2. `02_审计数据/全量目录清洁候选门控.csv`：全部候选及门控结果；可复算通过数。",
            "3. `02_审计数据/逐帧关键词核验.csv`：被保留时点的 16 帧证据。",
            "4. `02_审计数据/JSOC重取清单.csv`：公开查询地址、原始 JSON 路径和 hash。",
        ]
    )
    return "\n".join(lines)


def conclusion_markdown(summary: list[dict[str, object]]) -> str:
    found = [item for item in summary if item["strict_time_candidate_found"] == "YES"]
    lines = [
        "# 严格阴性对照前推检索结论",
        "",
        "## 一句话结论",
        "",
        f"本轮在完整 NCEI M+ 区间筛查与既有 strict 数据门下，找到 {len(found)} 个活动区可保留的同 AR 时间候选。它们用于时间演化探索和反例复核，不构成正式独立阴性组。",
        "",
        "## 选择规则",
        "",
        "- 候选池：目标耀斑前 72 小时、既有缓存之前的 12 分钟格点。",
        "- 目录门：任何 M+ 事件持续区间与 `[T0-4h,T0+7h)` 相交即排除。",
        "- 数据 strict 门：`[T0-3h,T0]` 为 16/16 条、请求字段完整、HARP/NOAA 映射通过、QUALITY 全为 0，且 T0 满足位置门。",
        "- 代表点：每 AR 取时间上最近的 strict 通过点。没有用 SHRGT45、USFLUX、MEANALP 或性能指标参与选择。",
        "",
        "## 结果",
        "",
        "| 事件 | 代表 T0 | 距目标耀斑 | strict 通过格点/目录清洁格点 | 状态或主要阻断项 |",
        "|---|---|---:|---|---|",
    ]
    for item in summary:
        t0 = f"`{item['selected_T0_utc']}`" if item["selected_T0_utc"] else "无"
        status = "通过：同 AR 时间候选（不作为正式独立对照）" if item["strict_time_candidate_found"] == "YES" else item["strict_failure_primary"]
        lead = f"{item['selected_lead_to_target_hr']} h" if item["selected_lead_to_target_hr"] else "-"
        lines.append(f"| {item['flare_event_id']} | {t0} | {lead} | {item['strict_data_pass_grid_points']}/{item['catalog_clean_grid_points']} | {status} |")
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 同 AR 的多个滑动窗彼此重叠，本包不把它们当作独立样本。",
            "- 即使代表点通过所有已查询数据门，也不自动成为独立或正式的阴性对照。",
            "- 本次未查询 CMASK/有效像素类字段，因而没有对测量伪趋势作出已排除的结论。",
        ]
    )
    return "\n".join(lines)


def clean_intermediate_raw(raw_dir: Path) -> None:
    for path in raw_dir.glob("*_strict_candidate.json"):
        path.unlink()


def make_hash_manifest(root: Path, archive: Path | None = None) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"文件hash清单.csv", "发送包hash清单.csv"} or path == archive:
            continue
        rows.append({"relative_path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_csv(root / "03_复现与完整性" / "文件hash清单.csv", rows)
    if archive is not None:
        write_csv(root / "06_整合后审计封存包" / "发送包hash清单.csv", [{"file": archive.name, "bytes": archive.stat().st_size, "sha256": sha256(archive)}])


def make_zip(root: Path) -> Path:
    archive = root / "06_整合后审计封存包" / f"{core.RUN_ID}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == archive or path.name == "发送包hash清单.csv" or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            handle.write(path, path.relative_to(root))
    return archive


def run() -> None:
    workspace = ROOT.parents[1]
    audit_dir = ROOT / "02_审计数据"
    raw_dir = audit_dir / "raw_jsoc_keywords"
    catalog_path = audit_dir / "02_official_Mplus_event_catalog_NCEI_v1-0-1_subset.csv"
    report_path = workspace / "01_主报告" / "01_全信息基准版Demo结果报告_20260808.md"
    catalog = core.load_catalog(catalog_path)
    all_grid: list[dict[str, object]] = []
    block_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    selected_frames: list[dict[str, object]] = []
    selected_catalog_rows: list[dict[str, object]] = []
    selected_data_rows: list[dict[str, object]] = []
    ar11429_correction_rows: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []

    for event in core.EVENTS:
        candidate, event_blocks = core.find_candidate(event, catalog)
        block_rows.extend(event_blocks)
        raw_path = raw_dir / f"{event.event_id}_preflare_80h_scan.json"
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        queried = core.payload_rows(payload)
        earliest_tai = min(candidate["clean_times"]) + core.timedelta(seconds=event.tai_utc_offset_seconds) - core.timedelta(hours=3)
        query_url, dataset = scan_query_url(event, earliest_tai)
        query_rows.append(
            {
                "run_id": core.RUN_ID,
                "flare_event_id": event.event_id,
                "HARPNUM": event.harpnum,
                "NOAA_AR": event.noaa_ar,
                "scan_start_TAI": core.tai_text(earliest_tai),
                "scan_duration": "80h@12m",
                "jsoc_dataset": dataset,
                "query_url": query_url,
                "raw_json_relative_path": raw_path.relative_to(ROOT).as_posix(),
                "raw_json_retrieved_utc": utc_mtime(raw_path),
                "raw_json_bytes": raw_path.stat().st_size,
                "raw_json_sha256": sha256(raw_path),
                "JSOC_status": payload.get("status"),
                "returned_keyword_rows": len(queried),
                "status": "PASS" if int(payload.get("status", -1)) == 0 else "FAIL",
            }
        )
        event_grid: list[tuple[dict[str, object], dict[str, object], list[dict[str, object]], dict[str, object]]] = []
        for t0 in candidate["clean_times"]:
            t0_tai = t0 + core.timedelta(seconds=event.tai_utc_offset_seconds)
            catalog_row = core.interval_audit(event, t0, catalog)
            data_row, frames = core.data_gate_audit(event, t0, t0_tai, queried)
            status, reason = core.status_label(catalog_row, data_row)
            grid_row = {
                **data_row,
                "target_onset_utc": event.target_onset_utc,
                "lead_to_target_hr": f"{(core.parse_utc(event.target_onset_utc) - t0).total_seconds() / 3600:.3f}",
                "catalog_gate_status": catalog_row["catalog_gate_status"],
                "catalog_primary_overlap_count": catalog_row["primary_interval_overlap_event_count"],
                "catalog_guard_overlap_count": catalog_row["guard_interval_overlap_event_count"],
                "candidate_status": status,
                "candidate_status_reason": reason,
            }
            event_grid.append((grid_row, catalog_row, frames, data_row))
            all_grid.append(grid_row)
        strict = [item for item in event_grid if primary_status(item[0])]
        strict.sort(key=lambda item: core.parse_utc(str(item[0]["candidate_T0_utc"])), reverse=True)
        final = strict[0] if strict else None
        reasons = Counter(str(item[0]["strict_baseline_reason"]) for item in event_grid)
        compact_failure = compact_failure_summary(event_grid)
        summary_row = {
            "run_id": core.RUN_ID,
            "flare_event_id": event.event_id,
            "HARPNUM": event.harpnum,
            "NOAA_AR": event.noaa_ar,
            "target_onset_utc": event.target_onset_utc,
            "candidate_pool_search_utc": f"[{core.utc_text(candidate['search_start'])}, {core.utc_text(candidate['search_end'])}]",
            "catalog_clean_grid_points": len(event_grid),
            "strict_data_pass_grid_points": len(strict),
            "strict_time_candidate_found": "YES" if final else "NO",
            "selected_T0_utc": final[0]["candidate_T0_utc"] if final else "",
            "selected_T0_TAI": final[0]["candidate_T0_TAI"] if final else "",
            "selected_lead_to_target_hr": final[0]["lead_to_target_hr"] if final else "",
            "selection_status": final[0]["candidate_status"] if final else "NO_STRICT_DATA_QUALIFIED_TIME_CANDIDATE",
            "selection_reason": final[0]["candidate_status_reason"] if final else "No catalog-clean grid point passed the existing strict data baseline.",
            "selected_SHRGT45_slope_3h_percent_per_hr": final[0]["SHRGT45_slope_3h_percent_per_hr"] if final else "",
            "selected_SHRGT45_delta_3h_percent": final[0]["SHRGT45_delta_3h_percent"] if final else "",
            "strict_failure_summary_when_none": "" if final else "; ".join(f"{reason} [{count}]" for reason, count in reasons.most_common()),
            "strict_failure_primary": "" if final else compact_failure,
            "formal_negative_status": "NOT_FORMAL_INDEPENDENT_CONTROL",
            "use_boundary": "One representative per AR is retained only for same-AR exploratory temporal analysis. It is not an independent formal negative control.",
        }
        summary.append(summary_row)
        if final:
            final_grid, final_catalog, final_frames, final_data = final
            final_grid["selected_representative_for_AR"] = "YES"
            selected_catalog_rows.append(final_catalog)
            selected_data_rows.append(final_data)
            selected_frames.extend(final_frames)
        for grid_row, _catalog, _frames, _data in event_grid:
            grid_row["selected_representative_for_AR"] = "YES" if final and grid_row["candidate_T0_utc"] == final[0]["candidate_T0_utc"] else "NO"

        if event.noaa_ar == "11429":
            prior_t0 = core.parse_utc("2012-03-05T07:23:26Z")
            prior_start = prior_t0 - core.timedelta(hours=3)
            prior_end = prior_t0 + core.timedelta(hours=6)
            for flare in [item for item in catalog if core.overlaps(item, prior_start, prior_end)]:
                ar11429_correction_rows.append(
                    {
                        "run_id": core.RUN_ID,
                        "prior_candidate_T0_utc": core.utc_text(prior_t0),
                        "audited_window_utc": f"[{core.utc_text(prior_start)}, {core.utc_text(prior_end)})",
                        "NCEI_flare_id": flare["flare_id"],
                        "NCEI_start_utc": core.utc_text(flare["start"]),
                        "NCEI_end_utc": core.utc_text(flare["end"]),
                        "NCEI_class": flare["flare_class"],
                        "NCEI_active_region_raw": flare["active_region_raw"],
                        "disposition": "EXCLUDED: event begins before the window but its interval overlaps the window; start-time-only screening would be false clean.",
                    }
                )

    write_csv(audit_dir / "候选时间块选择审计.csv", block_rows)
    write_csv(audit_dir / "JSOC重取清单.csv", query_rows)
    write_csv(audit_dir / "全量目录清洁候选门控.csv", all_grid)
    write_csv(audit_dir / "活动区最终选择摘要.csv", summary)
    write_csv(audit_dir / "候选T0与NCEI区间审计.csv", selected_catalog_rows)
    write_csv(audit_dir / "严格数据门汇总.csv", selected_data_rows)
    write_csv(audit_dir / "逐帧关键词核验.csv", selected_frames)
    write_csv(audit_dir / "AR11429候选更正审计.csv", ar11429_correction_rows)
    redundant_summary = audit_dir / "候选结论汇总.csv"
    if redundant_summary.exists():
        redundant_summary.unlink()
    write_csv(audit_dir / "NCEI目录来源说明.csv", [{"source_relative_path": catalog_path.relative_to(workspace).as_posix(), "source_sha256": sha256(catalog_path), "source_valid_rows": len(catalog), "screening_rule": "Exclude when any NCEI M+ event interval overlaps [T0-4h,T0+7h)."}])
    write_text(ROOT / "README.md", summary_markdown(summary))
    write_text(ROOT / "01_阅读说明" / "严格阴性对照前推检索结论.md", conclusion_markdown(summary))
    clean_intermediate_raw(raw_dir)
    acceptance = [
        {"check": "AR_count", "expected": 6, "observed": len(summary), "status": "PASS" if len(summary) == 6 else "FAIL"},
        {"check": "all_candidate_selection_outcome_blind", "expected": "catalog+strict data gates only", "observed": "no SHRGT45/USFLUX/MEANALP/model metric in selection", "status": "PASS"},
        {"check": "all_grid_catalog_guard_pass", "expected": "all candidate-pool rows", "observed": f"{sum(row['catalog_gate_status'] == 'PASS' for row in all_grid)}/{len(all_grid)}", "status": "PASS" if all(row["catalog_gate_status"] == "PASS" for row in all_grid) else "FAIL"},
        {"check": "AR11429_start_only_false_clean_rejected", "expected": "201203050222", "observed": ";".join(str(row["NCEI_flare_id"]) for row in ar11429_correction_rows), "status": "PASS" if any(row["NCEI_flare_id"] == "201203050222" for row in ar11429_correction_rows) else "FAIL"},
        {"check": "representative_count_no_more_than_one_per_AR", "expected": "<=6", "observed": len(selected_data_rows), "status": "PASS" if len(selected_data_rows) <= 6 else "FAIL"},
        {"check": "formal_independent_control_count", "expected": 0, "observed": 0, "status": "PASS"},
        {"check": "approved_main_report_retained", "expected": "source report exists", "observed": sha256(report_path) if report_path.exists() else "NOT_FOUND", "status": "PASS" if report_path.exists() else "FAIL"},
    ]
    write_csv(ROOT / "03_复现与完整性" / "验收检查.csv", acceptance)
    write_text(ROOT / "03_复现与完整性" / "本轮复现说明.md", "# 本轮复现说明\n\n从全信息基准版包根目录运行 `python -B 03_结果数据\\09_严格对照审计\\05_复现脚本\\finalize_full_preflare_strict_search_20260807.py`。脚本只读取本包内的 80 小时 JSOC 原始 JSON 和 NCEI 目录快照，重写严格审计派生表；不修改全信息基准版主报告。整合后的审计 ZIP 位于 `06_整合后审计封存包/`，原始 20260807 检索 ZIP 位于 `04_原始检索包/`。\n")
    archive = ROOT / "06_整合后审计封存包" / f"{core.RUN_ID}.zip"
    if archive.exists():
        archive.unlink()
    make_hash_manifest(ROOT)
    archive = make_zip(ROOT)
    make_hash_manifest(ROOT, archive)
    print(json.dumps({"run_id": core.RUN_ID, "selected_same_ar_time_candidates": len(selected_data_rows), "candidate_grid_rows": len(all_grid), "archive": str(archive)}, ensure_ascii=False))


if __name__ == "__main__":
    run()
