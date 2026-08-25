"""Deterministic SHRGT45 history features and same-unit research labels."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, Literal

from ai_scientist_mvp.skills.data_loader import (
    DataQualityPolicy,
    HistoryWindowAudit,
    audit_history_window,
)
from ai_scientist_mvp.skills.parameter_registry import (
    ParameterRegistryError,
    default_sharp_parameter_registry,
)

_erfa: Any = import_module("erfa")
_OLS_FORMULA_ID = "OLS_TRUE_T_REC"
_RESEARCH_TASK_ID = "SHRGT45_FUTURE_3_6H_SAME_UNIT_MPLUS"
_GOES_CLASS_PATTERN = re.compile(r"^([ABCMX])(\d+(?:\.\d+)?)$")
_GOES_FLUX_SCALE = {
    "A": 1e-8,
    "B": 1e-7,
    "C": 1e-6,
    "M": 1e-5,
    "X": 1e-4,
}


class FeatureEngineeringError(ValueError):
    """Input cannot produce an auditable feature or target label."""


@dataclass(frozen=True)
class Shrgt45WindowFeatures:
    analysis_unit_id: str
    anchor_tai: str
    history_start_tai: str
    history_end_tai: str
    first_valid_tai: str
    last_valid_tai: str
    formula_id: str
    parameter_definition_hash: str
    valid_frames: int
    elapsed_hours: float
    ols_slope_percent_per_hour: float
    observed_delta_percent: float
    three_hour_equivalent_change_percent: float
    quality_audit: HistoryWindowAudit
    scientific_verdict: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    result_maturity: Literal["DEVELOPMENTAL"] = "DEVELOPMENTAL"
    authorization_status: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"


@dataclass(frozen=True)
class FlareEvent:
    event_id: str
    analysis_unit_id: str
    onset_utc: str
    peak_class: str


@dataclass(frozen=True)
class EventCatalog:
    analysis_unit_id: str
    coverage_start_utc: str
    coverage_end_utc: str
    completeness: Literal["VERIFIED_COMPLETE", "INCOMPLETE"]
    events: tuple[FlareEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))


@dataclass(frozen=True)
class ResearchTargetLabel:
    task_id: str
    analysis_unit_id: str
    anchor_tai: str
    anchor_utc: str
    early_window_start_utc: str
    early_window_end_utc: str
    lead_window_start_utc: str
    lead_window_end_utc: str
    lead_boundary: Literal["CLOSED_OPEN"]
    event_anchor: Literal["ONSET_TIME"]
    grading_variable: Literal["PEAK_FLUX_CLASS"]
    target: Literal[0, 1]
    early_mplus: bool
    early_event_ids: tuple[str, ...]
    target_event_ids: tuple[str, ...]
    scientific_verdict: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    result_maturity: Literal["DEVELOPMENTAL"] = "DEVELOPMENTAL"
    authorization_status: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"


def slice_history_window(
    rows: Sequence[Mapping[str, str | None]],
    *,
    anchor_tai: str,
    time_column: str = "T_REC_TAI",
) -> tuple[Mapping[str, str | None], ...]:
    """Select the closed ``[T0-3h,T0]`` window without sorting input rows."""
    anchor = _parse_tai(anchor_tai)
    start = anchor - timedelta(hours=3)
    parsed: list[tuple[datetime, Mapping[str, str | None]]] = []
    for row in rows:
        parsed.append((_parse_tai(row.get(time_column)), row))
    if any(
        earlier >= later
        for (earlier, _), (later, _) in zip(parsed, parsed[1:], strict=False)
    ):
        raise FeatureEngineeringError("input timestamps must be strictly increasing")
    selected = tuple(row for timestamp, row in parsed if start <= timestamp <= anchor)
    if not selected:
        raise FeatureEngineeringError("history window contains no observations")
    return selected


def compute_shrgt45_window_features(
    rows: Sequence[Mapping[str, str | None]],
    *,
    anchor_tai: str,
    harpnum: int,
    policy: DataQualityPolicy,
    formula_id: str = _OLS_FORMULA_ID,
    time_column: str = "T_REC_TAI",
    harp_column: str = "HARPNUM",
    parameter_column: str = "SHRGT45_percent",
    quality_column: str = "QUALITY",
) -> Shrgt45WindowFeatures:
    """Compute the frozen true-time OLS SHRGT45 feature for one HARP window."""
    if formula_id != _OLS_FORMULA_ID:
        raise FeatureEngineeringError(
            f"Research Mode requires formula_id={_OLS_FORMULA_ID!r}"
        )
    if isinstance(harpnum, bool) or not isinstance(harpnum, int) or harpnum < 1:
        raise FeatureEngineeringError("harpnum must be a positive integer")
    for row in rows:
        try:
            row_harpnum = int(_required(row.get(harp_column), harp_column))
        except ValueError as exc:
            raise FeatureEngineeringError("HARPNUM values must be integers") from exc
        if row_harpnum != harpnum:
            raise FeatureEngineeringError("feature input must contain exactly one HARP")

    selected = slice_history_window(rows, anchor_tai=anchor_tai, time_column=time_column)
    audit = audit_history_window(
        selected,
        policy=policy,
        time_column=time_column,
        parameter_column=parameter_column,
        quality_column=quality_column,
    )
    if audit.status != "PASS":
        raise FeatureEngineeringError("history window failed the deterministic quality gate")

    anchor = _parse_tai(anchor_tai)
    selected_times = [_parse_tai(row.get(time_column)) for row in selected]
    if selected_times[-1] != anchor:
        raise FeatureEngineeringError("history window requires an observation at T0")

    registry = default_sharp_parameter_registry()
    valid_points: list[tuple[datetime, float]] = []
    for timestamp, row in zip(selected_times, selected, strict=True):
        quality = _parse_quality(row.get(quality_column))
        if quality & policy.fatal_quality_mask:
            continue
        raw_value = _required(row.get(parameter_column), parameter_column)
        try:
            value = registry.validate_value(
                "SHRGT45", float(raw_value), declared_unit="percent"
            ).value
        except (ParameterRegistryError, ValueError) as exc:
            raise FeatureEngineeringError("invalid SHRGT45 feature value") from exc
        valid_points.append((timestamp, value))
    if not valid_points or valid_points[-1][0] != anchor:
        raise FeatureEngineeringError("T0 must have a valid non-fatal SHRGT45 observation")
    if len(valid_points) < 2:
        raise FeatureEngineeringError("OLS requires at least two valid observations")

    first_time = valid_points[0][0]
    x_values = [
        (timestamp - first_time).total_seconds() / 3600.0
        for timestamp, _ in valid_points
    ]
    y_values = [value for _, value in valid_points]
    slope = _ols_slope(x_values, y_values)
    definition = registry.resolve("SHRGT45")
    elapsed_hours = x_values[-1]
    return Shrgt45WindowFeatures(
        analysis_unit_id=str(harpnum),
        anchor_tai=anchor_tai,
        history_start_tai=_format_tai(anchor - timedelta(hours=3)),
        history_end_tai=anchor_tai,
        first_valid_tai=_format_tai(valid_points[0][0]),
        last_valid_tai=_format_tai(valid_points[-1][0]),
        formula_id=formula_id,
        parameter_definition_hash=definition.definition_hash,
        valid_frames=len(valid_points),
        elapsed_hours=elapsed_hours,
        ols_slope_percent_per_hour=slope,
        observed_delta_percent=y_values[-1] - y_values[0],
        three_hour_equivalent_change_percent=3.0 * slope,
        quality_audit=audit,
    )


def construct_research_target_label(
    *,
    anchor_tai: str,
    analysis_unit_id: str,
    catalog: EventCatalog,
) -> ResearchTargetLabel:
    """Build the same-unit M1.0+ target for the closed-open 3--6h lead window."""
    if not analysis_unit_id or catalog.analysis_unit_id != analysis_unit_id:
        raise FeatureEngineeringError("event catalog must match the exact analysis unit")
    if catalog.completeness != "VERIFIED_COMPLETE":
        raise FeatureEngineeringError("negative-safe labels require a verified complete catalog")

    anchor_utc = _tai_to_utc(anchor_tai)
    early_end = anchor_utc + timedelta(hours=3)
    lead_end = anchor_utc + timedelta(hours=6)
    coverage_start = _parse_utc(catalog.coverage_start_utc)
    coverage_end = _parse_utc(catalog.coverage_end_utc)
    if coverage_start > anchor_utc or coverage_end < lead_end:
        raise FeatureEngineeringError("event catalog does not cover the full 0--6h horizon")

    event_ids = [event.event_id for event in catalog.events]
    if any(not event_id for event_id in event_ids) or len(event_ids) != len(set(event_ids)):
        raise FeatureEngineeringError("event IDs must be non-empty and unique")

    early_events: list[str] = []
    target_events: list[str] = []
    for event in catalog.events:
        if event.analysis_unit_id != analysis_unit_id:
            raise FeatureEngineeringError("catalog contains an event from another analysis unit")
        onset = _parse_utc(event.onset_utc)
        is_mplus = _goes_peak_flux(event.peak_class) >= 1e-5
        if not is_mplus:
            continue
        if anchor_utc <= onset < early_end:
            early_events.append(event.event_id)
        elif early_end <= onset < lead_end:
            target_events.append(event.event_id)

    return ResearchTargetLabel(
        task_id=_RESEARCH_TASK_ID,
        analysis_unit_id=analysis_unit_id,
        anchor_tai=anchor_tai,
        anchor_utc=_format_utc(anchor_utc),
        early_window_start_utc=_format_utc(anchor_utc),
        early_window_end_utc=_format_utc(early_end),
        lead_window_start_utc=_format_utc(early_end),
        lead_window_end_utc=_format_utc(lead_end),
        lead_boundary="CLOSED_OPEN",
        event_anchor="ONSET_TIME",
        grading_variable="PEAK_FLUX_CLASS",
        target=1 if target_events else 0,
        early_mplus=bool(early_events),
        early_event_ids=tuple(early_events),
        target_event_ids=tuple(target_events),
    )


def _ols_slope(x_values: Sequence[float], y_values: Sequence[float]) -> float:
    x_mean = math.fsum(x_values) / len(x_values)
    y_mean = math.fsum(y_values) / len(y_values)
    denominator = math.fsum((value - x_mean) ** 2 for value in x_values)
    if denominator <= 0 or not math.isfinite(denominator):
        raise FeatureEngineeringError("OLS time axis has no finite variation")
    numerator = math.fsum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values, strict=True)
    )
    slope = numerator / denominator
    if not math.isfinite(slope):
        raise FeatureEngineeringError("OLS slope is non-finite")
    return slope


def _parse_tai(value: str | None) -> datetime:
    if value is None:
        raise FeatureEngineeringError("TAI timestamp is missing")
    try:
        return datetime.strptime(value, "%Y.%m.%d_%H:%M:%S_TAI")
    except ValueError as exc:
        raise FeatureEngineeringError(f"invalid TAI timestamp: {value!r}") from exc


def _tai_to_utc(value: str) -> datetime:
    parsed = _parse_tai(value)
    try:
        tai_part1, tai_part2 = _erfa.dtf2d(
            "TAI",
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            float(parsed.second),
        )
        utc_part1, utc_part2 = _erfa.taiutc(tai_part1, tai_part2)
        year, month, day, hmsf = _erfa.d2dtf("UTC", 6, utc_part1, utc_part2)
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hmsf["h"]),
            int(hmsf["m"]),
            int(hmsf["s"]),
            int(hmsf["f"]),
            tzinfo=UTC,
        )
    except (ValueError, _erfa.ErfaError) as exc:
        raise FeatureEngineeringError("TAI timestamp cannot be converted to UTC") from exc


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FeatureEngineeringError("UTC timestamp must be a non-empty string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FeatureEngineeringError(f"invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FeatureEngineeringError("event timestamps must be explicitly UTC")
    return parsed.astimezone(UTC)


def _goes_peak_flux(value: str) -> float:
    if not isinstance(value, str):
        raise FeatureEngineeringError("GOES peak class must be a string")
    match = _GOES_CLASS_PATTERN.fullmatch(value.strip().upper())
    if match is None:
        raise FeatureEngineeringError(f"invalid GOES peak class: {value!r}")
    magnitude = float(match.group(2))
    if not math.isfinite(magnitude) or magnitude <= 0:
        raise FeatureEngineeringError("GOES peak class magnitude must be positive")
    return _GOES_FLUX_SCALE[match.group(1)] * magnitude


def _parse_quality(value: str | None) -> int:
    raw_value = _required(value, "QUALITY")
    try:
        quality = int(raw_value, 0)
    except ValueError as exc:
        raise FeatureEngineeringError(f"invalid QUALITY mask: {raw_value!r}") from exc
    if not 0 <= quality <= 0xFFFFFFFF:
        raise FeatureEngineeringError("QUALITY must fit an unsigned 32-bit mask")
    return quality


def _required(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise FeatureEngineeringError(f"{label} is missing")
    return value.strip()


def _format_tai(value: datetime) -> str:
    return value.strftime("%Y.%m.%d_%H:%M:%S_TAI")


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
