from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_scientist_mvp.skills.data_loader import DataQualityPolicy, load_csv_table
from ai_scientist_mvp.skills.feature_engineering import (
    EventCatalog,
    FeatureEngineeringError,
    FlareEvent,
    compute_shrgt45_window_features,
    construct_research_target_label,
    slice_history_window,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANCHOR_TAI = "2011.02.14_22:36:00_TAI"


def _rows() -> list[dict[str, str]]:
    start = datetime(2011, 2, 14, 19, 36)
    rows = []
    for index in range(16):
        timestamp = start + timedelta(minutes=12 * index)
        elapsed_hours = index / 5
        rows.append(
            {
                "T_REC_TAI": timestamp.strftime("%Y.%m.%d_%H:%M:%S_TAI"),
                "HARPNUM": "377",
                "SHRGT45_percent": str(20 + 2 * elapsed_hours),
                "QUALITY": "0x00000000",
            }
        )
    return rows


def test_history_slice_uses_closed_three_hour_boundaries() -> None:
    rows = [
        {
            "T_REC_TAI": "2011.02.14_19:24:00_TAI",
            "HARPNUM": "377",
            "SHRGT45_percent": "1",
            "QUALITY": "0",
        },
        *_rows(),
        {
            "T_REC_TAI": "2011.02.14_22:48:00_TAI",
            "HARPNUM": "377",
            "SHRGT45_percent": "1",
            "QUALITY": "0",
        },
    ]

    selected = slice_history_window(rows, anchor_tai=ANCHOR_TAI)

    assert len(selected) == 16
    assert selected[0]["T_REC_TAI"] == "2011.02.14_19:36:00_TAI"
    assert selected[-1]["T_REC_TAI"] == ANCHOR_TAI


def test_ols_uses_real_time_axis_and_reports_observed_delta() -> None:
    rows = _rows()
    del rows[7]

    features = compute_shrgt45_window_features(
        rows,
        anchor_tai=ANCHOR_TAI,
        harpnum=377,
        policy=DataQualityPolicy(),
    )

    assert features.formula_id == "OLS_TRUE_T_REC"
    assert features.ols_slope_percent_per_hour == pytest.approx(2.0)
    assert features.observed_delta_percent == pytest.approx(6.0)
    assert features.three_hour_equivalent_change_percent == pytest.approx(6.0)
    assert features.valid_frames == 15
    assert features.scientific_verdict == "NOT_EVALUATED"
    assert features.result_maturity == "DEVELOPMENTAL"
    assert features.authorization_status == "NOT_AUTHORIZED"


def test_recomputes_frozen_demo_ols_feature() -> None:
    table = load_csv_table(
        PROJECT_ROOT / "fixtures" / "shrgt45" / "assets" / "s06" / (
            "case_keyword_timeseries.csv"
        ),
        required_columns=(
            "case_id",
            "T_REC_TAI",
            "HARPNUM",
            "SHRGT45_percent",
            "QUALITY",
        ),
    )
    case_rows = [
        row
        for row in table.rows
        if row["case_id"] == "AR11158_event_pre_3_to_6h_20110214_2236_TAI"
    ]

    features = compute_shrgt45_window_features(
        case_rows,
        anchor_tai=ANCHOR_TAI,
        harpnum=377,
        policy=DataQualityPolicy(),
    )

    assert features.ols_slope_percent_per_hour == pytest.approx(0.078529, abs=5e-7)
    assert features.observed_delta_percent == pytest.approx(0.033, abs=5e-7)
    assert len(features.parameter_definition_hash) == 64


@pytest.mark.parametrize("mutation", ["order", "duplicate", "harp", "anchor", "quality"])
def test_feature_input_failures_are_closed(mutation: str) -> None:
    rows = _rows()
    if mutation == "order":
        rows[7], rows[8] = rows[8], rows[7]
    elif mutation == "duplicate":
        rows[8]["T_REC_TAI"] = rows[7]["T_REC_TAI"]
    elif mutation == "harp":
        rows[8]["HARPNUM"] = "999"
    elif mutation == "anchor":
        rows.pop()
    else:
        rows[8]["QUALITY"] = "0x80000000"
        rows[9]["QUALITY"] = "0x80000000"
        rows[10]["QUALITY"] = "0x80000000"

    with pytest.raises(FeatureEngineeringError):
        compute_shrgt45_window_features(
            rows,
            anchor_tai=ANCHOR_TAI,
            harpnum=377,
            policy=DataQualityPolicy(),
        )


def test_unfrozen_feature_formula_is_rejected() -> None:
    with pytest.raises(FeatureEngineeringError, match="OLS_TRUE_T_REC"):
        compute_shrgt45_window_features(
            _rows(),
            anchor_tai=ANCHOR_TAI,
            harpnum=377,
            policy=DataQualityPolicy(),
            formula_id="THEIL_SEN",
        )


def _event(event_id: str, onset: datetime, flare_class: str = "M1.0") -> FlareEvent:
    return FlareEvent(
        event_id=event_id,
        analysis_unit_id="377",
        onset_utc=onset.isoformat().replace("+00:00", "Z"),
        peak_class=flare_class,
    )


def _catalog(*events: FlareEvent, completeness: str = "VERIFIED_COMPLETE") -> EventCatalog:
    return EventCatalog(
        analysis_unit_id="377",
        coverage_start_utc="2011-02-14T20:00:00Z",
        coverage_end_utc="2011-02-15T05:00:00Z",
        completeness=completeness,
        events=events,
    )


def test_target_label_uses_onset_m1_threshold_and_nonoverlapping_window() -> None:
    anchor_utc = datetime(2011, 2, 14, 22, 35, 26, tzinfo=UTC)
    catalog = _catalog(
        _event("early", anchor_utc + timedelta(hours=1), "X1.0"),
        _event("target", anchor_utc + timedelta(hours=3), "M1.0"),
        _event("below", anchor_utc + timedelta(hours=4), "C9.9"),
        _event("end", anchor_utc + timedelta(hours=6), "X9.0"),
    )

    label = construct_research_target_label(
        anchor_tai=ANCHOR_TAI,
        analysis_unit_id="377",
        catalog=catalog,
    )

    assert label.target == 1
    assert label.early_mplus is True
    assert label.early_event_ids == ("early",)
    assert label.target_event_ids == ("target",)
    assert label.lead_boundary == "CLOSED_OPEN"


def test_complete_catalog_without_target_event_produces_negative_label() -> None:
    label = construct_research_target_label(
        anchor_tai=ANCHOR_TAI,
        analysis_unit_id="377",
        catalog=_catalog(),
    )

    assert label.target == 0
    assert label.early_mplus is False


@pytest.mark.parametrize("failure", ["incomplete", "unit", "coverage", "duplicate", "class"])
def test_unsafe_label_inputs_fail_closed(failure: str) -> None:
    anchor_utc = datetime(2011, 2, 14, 22, 35, 26, tzinfo=UTC)
    event = _event("event", anchor_utc + timedelta(hours=4))
    catalog = _catalog(event)
    analysis_unit_id = "377"
    if failure == "incomplete":
        catalog = _catalog(event, completeness="INCOMPLETE")
    elif failure == "unit":
        analysis_unit_id = "999"
    elif failure == "coverage":
        catalog = EventCatalog(
            analysis_unit_id="377",
            coverage_start_utc="2011-02-14T22:00:00Z",
            coverage_end_utc="2011-02-15T02:00:00Z",
            completeness="VERIFIED_COMPLETE",
            events=(event,),
        )
    elif failure == "duplicate":
        catalog = _catalog(event, event)
    else:
        catalog = _catalog(_event("event", anchor_utc + timedelta(hours=4), "M"))

    with pytest.raises(FeatureEngineeringError):
        construct_research_target_label(
            anchor_tai=ANCHOR_TAI,
            analysis_unit_id=analysis_unit_id,
            catalog=catalog,
        )
