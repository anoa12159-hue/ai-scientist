from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = PACKAGE_ROOT / "03_结果数据"
OUT = PACKAGE_ROOT / "04_图表" / "visualizations"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "Microsoft YaHei",
        "axes.unicode_minus": False,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }
)

COLORS = {
    "positive": "#0072B2",
    "negative": "#D55E00",
    "buffer": "#7A7A7A",
    "pass": "#009E73",
    "fail": "#D55E00",
    "expected": "#9CC9E8",
    "returned": "#0072B2",
    "grid": "#D9E2EC",
    "ink": "#102A43",
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (RESULT_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def gate_map() -> dict[str, int]:
    return {row["gate"]: int(row["count"]) for row in read_csv("04_gate_counts.csv")}


def save_figure(fig: plt.Figure, stem: str) -> None:
    fig.savefig(OUT / f"{stem}.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor("#FFFFFF")
    ax.grid(True, color=COLORS["grid"], linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#829AB1")
    ax.spines["bottom"].set_color("#829AB1")


def plot_gate_funnel(gates: dict[str, int], *, compact: bool = False) -> plt.Figure:
    labels = [
        "理论查询",
        "JSOC 实返",
        "关键字段完整",
        "AR 映射通过",
        "3 小时历史窗",
        "位置门通过",
        "Demo 主门通过",
    ]
    keys = [
        "query_expected_records",
        "query_returned_records",
        "field_complete",
        "event_ar_mapping_pass_rows",
        "history_3h_pass_provisional",
        "disk_abs_lon_lat_lt_50",
    ]
    values = [gates[key] for key in keys]
    values.append(gates["final_analysis_rows"])
    fig, ax = plt.subplots(figsize=(8.4, 5.3) if not compact else (5.3, 3.2))
    style_axis(ax)
    y = np.arange(len(labels))
    bars = ax.barh(y, values, color=["#6EA8D7", "#4D91C6", "#76B7B2", "#4C9F70", "#6DBE7B", "#8ACB88", "#2E8B57"], height=0.62)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.16)
    ax.set_xlabel("记录数")
    ax.set_title("全信息 Demo 逐级门控结果")
    for bar, value in zip(bars, values):
        pct = value / values[0] * 100
        ax.text(value + values[0] * 0.015, bar.get_y() + bar.get_height() / 2, f"{value}  ({pct:.1f}%)", va="center", color=COLORS["ink"], fontsize=9 if not compact else 7.5)
    ax.text(0.99, -0.12, "各阶段按处理链顺序展示；记录数按事件和 AR 结构解读。", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#52606D")
    fig.tight_layout()
    return fig


def plot_sample_donut(rows: list[dict[str, str]], *, compact: bool = False) -> plt.Figure:
    order = [
        ("POSITIVE_CANDIDATE", "正候选", COLORS["positive"]),
        ("NEGATIVE_CANDIDATE", "最终 control", COLORS["negative"]),
        ("BUFFER_OR_EXCLUDE", "未进入最终分析", COLORS["buffer"]),
    ]
    counts = [sum(row.get("sample_state") == key for row in rows) for key, _, _ in order]
    labels = [f"{label}\n{count} 条" for (_, label, _), count in zip(order, counts)]
    colors = [color for _, _, color in order]
    fig, ax = plt.subplots(figsize=(6.2, 5.2) if not compact else (4.2, 3.3))
    wedges, _ = ax.pie(counts, colors=colors, startangle=90, counterclock=False, wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2})
    ax.text(0, 0.08, f"n = {sum(counts)}", ha="center", va="center", fontsize=18, fontweight="bold", color=COLORS["ink"])
    ax.text(0, -0.13, "最终分析样本", ha="center", va="center", fontsize=10, color="#52606D")
    ax.legend(wedges, labels, loc="lower center", bbox_to_anchor=(0.5, -0.08), frameon=False, ncol=1, fontsize=9 if not compact else 7.5)
    ax.set_title("最终分析样本组成")
    fig.tight_layout()
    return fig


def plot_event_returned(cadence: list[dict[str, str]], *, compact: bool = False) -> plt.Figure:
    cadence = sorted(cadence, key=lambda row: int(row["flare_NOAA_AR"]))
    labels = [f"AR{row['flare_NOAA_AR']}\n{row['flare_event_id'].split('_')[1]}" for row in cadence]
    expected = [int(row["expected_records"]) for row in cadence]
    returned = [int(row["returned_records"]) for row in cadence]
    missing = [int(row["missing_records"]) for row in cadence]
    x = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8.8, 5.2) if not compact else (5.3, 3.2))
    style_axis(ax)
    ax.bar(x - width / 2, expected, width, color=COLORS["expected"], label="理论记录")
    bars = ax.bar(x + width / 2, returned, width, color=COLORS["returned"], label="实际返回")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 70)
    ax.set_ylabel("记录数")
    ax.set_title("各事件理论记录与实际返回")
    ax.legend(frameon=False, ncol=2, loc="lower left")
    for bar, ret, miss in zip(bars, returned, missing):
        ax.text(bar.get_x() + bar.get_width() / 2, ret + 1.4, f"{ret}\n缺 {miss}", ha="center", va="bottom", fontsize=8 if not compact else 7)
    ax.text(0.99, -0.16, f"合计：理论 {sum(expected)}，实返 {sum(returned)}，缺帧 {sum(missing)}。", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#52606D")
    fig.tight_layout()
    return fig


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def plot_timeline(rows: list[dict[str, str]], *, compact: bool = False) -> plt.Figure:
    events = sorted({row["flare_event_id"] for row in rows})
    fig, axes = plt.subplots(2, 3, figsize=(16, 8.6) if not compact else (8.2, 4.7), sharey=True)
    axes = axes.ravel()
    state_colors = {
        "POSITIVE_CANDIDATE": COLORS["positive"],
        "NEGATIVE_CANDIDATE": COLORS["negative"],
        "BUFFER_OR_EXCLUDE": COLORS["buffer"],
    }
    for ax, event in zip(axes, events):
        subset = [row for row in rows if row["flare_event_id"] == event and number(row, "SHRGT45") is not None]
        subset.sort(key=lambda row: number(row, "distance_to_flare_hr") or 0, reverse=True)
        points = [(number(row, "distance_to_flare_hr"), number(row, "SHRGT45"), parse_time(row["T_REC_UTC"]), row) for row in subset]
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        previous_time: datetime | None = None
        for x_value, y_value, timestamp, _ in points:
            if x_value is None or y_value is None:
                continue
            if previous_time is not None and (timestamp - previous_time).total_seconds() / 60 > 24:
                if current:
                    segments.append(current)
                current = []
            current.append((x_value, y_value))
            previous_time = timestamp
        if current:
            segments.append(current)
        for segment in segments:
            ax.plot([point[0] for point in segment], [point[1] for point in segment], color="#486581", linewidth=1.1, alpha=0.82)
        for state, color in state_colors.items():
            state_points = [(number(row, "distance_to_flare_hr"), number(row, "SHRGT45")) for row in subset if row.get("sample_state") == state]
            if state_points:
                ax.scatter([p[0] for p in state_points], [p[1] for p in state_points], s=12 if not compact else 7, color=color, label=state.replace("_", " "))
        ax.axvspan(3, 6, color=COLORS["positive"], alpha=0.08, zorder=0)
        ax.axvline(3, color="#829AB1", linestyle="--", linewidth=0.8)
        ax.axvline(6, color="#829AB1", linestyle="--", linewidth=0.8)
        ax.invert_xaxis()
        ax.set_title(f"AR {event.split('_')[0].replace('NOAA', '')}  {event.split('_')[1]}", fontsize=10 if not compact else 8)
        ax.set_xlabel("距 T0 小时")
        ax.grid(True, color=COLORS["grid"], linewidth=0.7, alpha=0.7)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel("SHRGT45")
    axes[3].set_ylabel("SHRGT45")
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            ["正候选", "临时 control", "buffer / 边界"],
            loc="upper center",
            bbox_to_anchor=(0.5, 0.045),
            ncol=3,
            frameon=False,
            fontsize=9,
        )
    fig.suptitle("各事件 SHRGT45 随距 T0 时间的变化（缺帧处断线）", y=0.995, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.008, "阴影为 3--6 小时正候选窗口；曲线连接相邻实际返回记录，间隔超过 24 分钟处断线。", ha="center", va="bottom", fontsize=8, color="#52606D")
    fig.tight_layout(rect=(0, 0.085, 1, 0.96))
    return fig


def plot_slope_distribution(rows: list[dict[str, str]], *, compact: bool = False) -> plt.Figure:
    groups = [
        ("POSITIVE_CANDIDATE", "正候选", COLORS["positive"]),
        ("NEGATIVE_CANDIDATE", "临时 control", COLORS["negative"]),
    ]
    values = []
    labels = []
    colors = []
    for state, label, color in groups:
        group = [number(row, "SHRGT45_slope_3h_percent_per_hr") for row in rows if row.get("sample_state") == state]
        group = [value for value in group if value is not None]
        values.append(group)
        labels.append(f"{label}\n(n={len(group)})")
        colors.append(color)
    fig, ax = plt.subplots(figsize=(7.0, 5.2) if not compact else (5.3, 3.2))
    style_axis(ax)
    box = ax.boxplot(values, tick_labels=labels, patch_artist=True, widths=0.48, showfliers=False, medianprops={"color": COLORS["ink"], "linewidth": 2})
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
        patch.set_edgecolor(color)
    rng = np.random.default_rng(20260808)
    for index, (group, color) in enumerate(zip(values, colors), start=1):
        jitter = rng.normal(index, 0.055, size=len(group))
        ax.scatter(jitter, group, s=20 if not compact else 10, color=color, alpha=0.72, edgecolor="white", linewidth=0.35, zorder=3)
        ax.text(
            index,
            float(np.median(group)) + 0.018,
            f"median {np.median(group):.3f}",
            ha="center",
            va="bottom",
            fontsize=8 if not compact else 6.5,
            color=COLORS["ink"],
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 1.0},
            zorder=4,
        )
    ax.axhline(0, color="#829AB1", linestyle="--", linewidth=0.9)
    ax.set_ylabel("OLS slope (percentage points/hour)")
    ax.set_title("Demo 主门结果的 SHRGT45 斜率分布")
    ax.text(0.99, -0.16, f"展示最终分析样本 {len(rows)} 条；数量按事件和 AR 的聚集结构解读。", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#52606D")
    fig.tight_layout()
    return fig


def plot_usflux_scatter(rows: list[dict[str, str]], *, compact: bool = False, reported_correlation: float | None = None) -> tuple[plt.Figure, float, float]:
    groups = [
        ("POSITIVE_CANDIDATE", "正候选", COLORS["positive"]),
        ("NEGATIVE_CANDIDATE", "临时 control", COLORS["negative"]),
    ]
    x_all: list[float] = []
    y_all: list[float] = []
    fig, ax = plt.subplots(figsize=(7.8, 5.2) if not compact else (5.3, 3.2))
    style_axis(ax)
    for state, label, color in groups:
        points = []
        for row in rows:
            if row.get("sample_state") != state:
                continue
            flux = number(row, "USFLUX")
            shrgt45 = number(row, "SHRGT45")
            if flux is None or flux <= 0 or shrgt45 is None:
                continue
            points.append((math.log10(flux), shrgt45))
        if points:
            x = [point[0] for point in points]
            y = [point[1] for point in points]
            x_all.extend(x)
            y_all.extend(y)
            ax.scatter(x, y, s=26 if not compact else 12, color=color, alpha=0.65, edgecolor="white", linewidth=0.35, label=f"{label} (n={len(points)})")
    log_axis_correlation = float(np.corrcoef(x_all, y_all)[0, 1]) if len(x_all) > 1 else float("nan")
    correlation = log_axis_correlation if reported_correlation is None else reported_correlation
    if y_all:
        y_min = min(y_all)
        y_max = max(y_all)
        y_pad = max((y_max - y_min) * 0.12, 0.8)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)
    ax.set_xlabel("log10(USFLUX)")
    ax.set_ylabel("SHRGT45")
    ax.set_title("USFLUX 与 SHRGT45 的上下文关系")
    ax.legend(frameon=False, loc="best", fontsize=8 if not compact else 6.5)
    ax.text(0.27, 0.78, f"原始尺度 pooled r = {correlation:.3f}\nlog10 横轴 r = {log_axis_correlation:.3f}\nAR 内记录有聚集", transform=ax.transAxes, va="top", fontsize=9 if not compact else 7, color=COLORS["ink"], bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#BCCCDC", "alpha": 0.9})
    ax.text(0.99, -0.16, f"相关按原始 USFLUX 审计；横轴为 log10(USFLUX)，最终样本 n={len(rows)}。", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#52606D")
    fig.tight_layout()
    return fig, correlation, log_axis_correlation


def write_dashboard(stems: list[str]) -> None:
    images = [Image.open(OUT / f"{stem}.png").convert("RGB") for stem in stems]
    row_count = (len(images) + 1) // 2
    canvas = Image.new("RGB", (1800, 80 + row_count * 570), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 30)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 24), "SHRGT45 全信息基准版 Demo 可视化总览", fill=COLORS["ink"], font=font)
    cell_width, cell_height = 860, 570
    for index, image in enumerate(images):
        thumb = ImageOps.contain(image, (cell_width - 40, cell_height - 70))
        x = 20 + (index % 2) * cell_width + (cell_width - thumb.width) // 2
        y = 80 + (index // 2) * cell_height + (cell_height - 70 - thumb.height) // 2
        canvas.paste(thumb, (x, y))
    canvas.save(OUT / "00_visualization_dashboard.png", optimize=True)


def main() -> None:
    rows = read_csv("01_all_sample_supplement.csv")
    final_rows = read_csv("10_final_analysis_sample.csv")
    cadence = read_csv("08_cadence_audit.csv")
    context_audit = read_csv("06_usflux_context_correlation.csv")
    gates = gate_map()

    save_figure(plot_gate_funnel(gates), "01_gate_funnel_bar")
    save_figure(plot_sample_donut(final_rows), "02_sample_state_donut")
    save_figure(plot_event_returned(cadence), "03_event_returned_vs_expected_bar")
    save_figure(plot_timeline(rows), "04_shrgt45_timeline_by_event")
    save_figure(plot_slope_distribution(final_rows), "05_ols_slope_distribution")
    reported_correlation = float(next(row["pearson_r"] for row in context_audit if row["queue"] == "FINAL_ANALYSIS" and row["scope"] == "pooled_rows"))
    scatter_fig, correlation, log_axis_correlation = plot_usflux_scatter(final_rows, reported_correlation=reported_correlation)
    save_figure(scatter_fig, "06_usflux_vs_shrgt45_scatter")
    plt.close("all")

    dashboard_stems = [
        "01_gate_funnel_bar",
        "02_sample_state_donut",
        "03_event_returned_vs_expected_bar",
        "04_shrgt45_timeline_by_event",
        "05_ols_slope_distribution",
        "06_usflux_vs_shrgt45_scatter",
    ]
    write_dashboard(dashboard_stems)

    summary_rows = [
        ["01_gate_funnel_bar", "逐级门控柱状图", "03_结果数据/04_gate_counts.csv", "理论 360 条", "各阶段为处理链计数，记录按事件和 AR 结构解读"],
        ["02_sample_state_donut", "最终分析样本组成环图", "03_结果数据/10_final_analysis_sample.csv", "互斥合计 55 条", "最终正候选与最终 control 的组成"],
        ["03_event_returned_vs_expected_bar", "事件理论/实返对比柱状图", "03_结果数据/08_cadence_audit.csv", "6 个事件；360/333 条", "显示缺帧和事件间数据可得性差异"],
        ["04_shrgt45_timeline_by_event", "各事件时间趋势折线图", "03_结果数据/01_all_sample_supplement.csv", "333 条实际记录", "使用真实时间；间隔超过 24 分钟处断线"],
        ["05_ols_slope_distribution", "最终样本 OLS 斜率箱线/散点图", "03_结果数据/10_final_analysis_sample.csv", "55 条最终分析记录", "最终 control 已通过完整 M+ 未来六小时筛查；记录按 AR 聚集"],
        ["06_usflux_vs_shrgt45_scatter", "USFLUX 与 SHRGT45 上下文散点图", "03_结果数据/10_final_analysis_sample.csv / 03_结果数据/06_usflux_context_correlation.csv", "55 条最终分析记录；原始 USFLUX pooled r", "横轴为 log10(USFLUX)；图中标注原始和对数横轴相关口径"],
    ]
    with (OUT / "visualization_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["chart_id", "title", "source", "denominator", "interpretation_note"])
        writer.writerows(summary_rows)

    png_dimensions = {}
    for stem in dashboard_stems:
        with Image.open(OUT / f"{stem}.png") as image:
            png_dimensions[f"{stem}.png"] = list(image.size)
    svg_stems = [f"{stem}.svg" for stem in dashboard_stems]
    metrics = {
        "run_id": "SHRGT45_全信息基准版_20260808",
        "source_rows": len(rows),
        "main_gate_rows": len(final_rows),
        "sample_state_counts": {
            "POSITIVE_CANDIDATE": sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in rows),
            "NEGATIVE_CANDIDATE": sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in rows),
            "BUFFER_OR_EXCLUDE": sum(row.get("sample_state") == "BUFFER_OR_EXCLUDE" for row in rows),
        },
        "gate_counts_used": gates,
        "cadence_expected_total": sum(int(row["expected_records"]) for row in cadence),
        "cadence_returned_total": sum(int(row["returned_records"]) for row in cadence),
        "cadence_missing_total": sum(int(row["missing_records"]) for row in cadence),
        "main_gate_state_counts": {
            "POSITIVE_CANDIDATE": sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in final_rows),
            "NEGATIVE_CANDIDATE": sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in final_rows),
        },
        "pooled_usflux_shrgt45_pearson_r": correlation,
        "log10_usflux_shrgt45_pearson_r_on_plotted_axis": log_axis_correlation,
        "usflux_correlation_scale_note": "Audit r uses raw USFLUX; chart x-axis is log10(USFLUX).",
        "artifacts": {
            "chart_stems": dashboard_stems,
            "png_dimensions_px": png_dimensions,
            "svg_files_present": all((OUT / name).is_file() for name in svg_stems),
            "dashboard_present": (OUT / "00_visualization_dashboard.png").is_file(),
        },
        "checks": {
            "sample_state_sum_equals_source_rows": sum(
                [
                    sum(row.get("sample_state") == "POSITIVE_CANDIDATE" for row in rows),
                    sum(row.get("sample_state") == "NEGATIVE_CANDIDATE" for row in rows),
                    sum(row.get("sample_state") == "BUFFER_OR_EXCLUDE" for row in rows),
                ]
            )
            == len(rows),
            "main_gate_sum_equals_positive_plus_control": len(final_rows) == gates["all_sample_positive_rows_after_provisional_gates"] + gates["final_control_rows_after_mplus_screen"],
            "cadence_sum_matches_gate_counts": sum(int(row["expected_records"]) for row in cadence) == gates["query_expected_records"] and sum(int(row["returned_records"]) for row in cadence) == gates["query_returned_records"],
        },
    }
    (OUT / "visualization_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
