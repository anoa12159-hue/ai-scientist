from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from ai_scientist_mvp.skills.data_loader import (
    CsvValidationError,
    DataQualityPolicy,
    FitsValidationError,
    audit_fits_components,
    audit_history_window,
    load_csv_table,
    load_fits_image,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_loads_utf8_bom_csv_and_preserves_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("\ufeffid,value,note\n1,3.5,\n2,,missing\n", encoding="utf-8")

    table = load_csv_table(path, required_columns=("id", "value"))

    assert table.columns == ("id", "value", "note")
    assert table.rows[0] == {"id": "1", "value": "3.5", "note": None}
    assert table.rows[1]["value"] is None
    assert len(table.source_sha256) == 64


@pytest.mark.parametrize(
    "content",
    [
        "id,id\n1,2\n",
        "id,value\n1,2,3\n",
        "id,value\n1\n",
    ],
)
def test_csv_shape_errors_fail_closed(tmp_path: Path, content: str) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(CsvValidationError):
        load_csv_table(path, required_columns=("id", "value"))


def test_csv_required_columns_and_non_nullable_values_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    path.write_text("id,value\n1,\n", encoding="utf-8")

    with pytest.raises(CsvValidationError, match="required columns"):
        load_csv_table(path, required_columns=("id", "T_REC"))
    with pytest.raises(CsvValidationError, match="non-nullable"):
        load_csv_table(
            path,
            required_columns=("id", "value"),
            non_nullable_columns=("value",),
        )


def test_reads_frozen_timeseries_fixture_and_audits_one_case() -> None:
    path = PROJECT_ROOT / "fixtures" / "shrgt45" / "assets" / "s06" / (
        "case_keyword_timeseries.csv"
    )
    table = load_csv_table(
        path,
        required_columns=(
            "case_id",
            "relative_to_t_pred_hr",
            "T_REC_TAI",
            "SHRGT45_percent",
            "QUALITY",
        ),
    )
    case_id = "AR11158_event_pre_3_to_6h_20110214_2236_TAI"
    rows = [
        row
        for row in table.rows
        if row["case_id"] == case_id
        and row["relative_to_t_pred_hr"] is not None
        and -3 <= float(row["relative_to_t_pred_hr"]) <= 0
    ]

    audit = audit_history_window(rows, policy=DataQualityPolicy())

    assert len(rows) == 16
    assert audit.status == "PASS"
    assert audit.span_minutes == 180.0


def _history_rows(*, count: int = 16) -> list[dict[str, str]]:
    start = datetime(2011, 2, 14, 19, 36)
    rows = []
    for index in range(count):
        timestamp = start + timedelta(minutes=12 * index)
        rows.append(
            {
                "T_REC_TAI": timestamp.strftime("%Y.%m.%d_%H:%M:%S_TAI"),
                "SHRGT45_percent": str(50 + index / 10),
                "QUALITY": "0x00000000",
            }
        )
    return rows


def test_history_window_passes_frozen_developmental_quality_rules() -> None:
    audit = audit_history_window(_history_rows(), policy=DataQualityPolicy())

    assert audit.status == "PASS"
    assert audit.returned_frames == 16
    assert audit.valid_frames == 16
    assert audit.span_minutes == 180.0
    assert audit.max_gap_minutes == 12.0
    assert audit.fatal_quality_frames == 0


def test_history_window_excludes_fatal_quality_frame_without_interpolation() -> None:
    rows = _history_rows()
    rows[7]["QUALITY"] = "0x80000000"

    audit = audit_history_window(rows, policy=DataQualityPolicy())

    assert audit.status == "PASS"
    assert audit.valid_frames == 15
    assert audit.fatal_quality_frames == 1
    assert audit.max_gap_minutes == 24.0


def test_history_window_retains_uninterpreted_nonfatal_quality_bits() -> None:
    rows = _history_rows()
    rows[7]["QUALITY"] = "0x00010400"

    audit = audit_history_window(rows, policy=DataQualityPolicy())

    assert audit.status == "PASS"
    assert audit.valid_frames == 16
    assert audit.fatal_quality_frames == 0
    assert audit.nonzero_retained_frames == 1


@pytest.mark.parametrize("failure", ["too_few", "large_gap", "duplicate", "missing"])
def test_history_window_quality_failures_are_structured(failure: str) -> None:
    rows = _history_rows()
    if failure == "too_few":
        rows = rows[:13]
    elif failure == "large_gap":
        del rows[7:9]
    elif failure == "duplicate":
        rows[8]["T_REC_TAI"] = rows[7]["T_REC_TAI"]
    else:
        rows[8]["SHRGT45_percent"] = ""

    audit = audit_history_window(rows, policy=DataQualityPolicy())

    assert audit.status == "FAIL"
    assert any(check.status == "FAIL" for check in audit.checks)


def _write_fits(
    path: Path,
    *,
    segment: str,
    t_rec: str = "2011.02.14_22:36:00_TAI",
    harpnum: int = 377,
    shape: tuple[int, int] = (3, 4),
    ctype1: str = "CRLN-CEA",
    nan_at: tuple[int, int] | None = None,
    inf_at: tuple[int, int] | None = None,
) -> None:
    data = np.arange(shape[0] * shape[1], dtype=np.float64).reshape(shape)
    if nan_at is not None:
        data[nan_at] = np.nan
    if inf_at is not None:
        data[inf_at] = np.inf
    image = fits.ImageHDU(data=data)
    image.header.update(
        {
            "SEGMENT": segment,
            "DATE-OBS": "2011-02-14T22:35:26.000",
            "T_REC": t_rec,
            "HARPNUM": harpnum,
            "NOAA_AR": 11158,
            "BUNIT": "Gauss",
            "CTYPE1": ctype1,
            "CTYPE2": "CRLT-CEA",
            "CUNIT1": "degree",
            "CUNIT2": "degree",
            "CRPIX1": 2.5,
            "CRPIX2": 2.0,
            "CRVAL1": 10.0,
            "CRVAL2": -20.0,
            "CDELT1": 0.03,
            "CDELT2": 0.03,
        }
    )
    fits.HDUList([fits.PrimaryHDU(), image]).writeto(path)


def test_loads_fits_image_and_audits_consistent_br_bp_bt(tmp_path: Path) -> None:
    frames = []
    for segment in ("Br", "Bp", "Bt"):
        path = tmp_path / f"{segment}.fits"
        _write_fits(path, segment=segment)
        frames.append(load_fits_image(path, hdu_index=1, expected_segment=segment))

    audit = audit_fits_components(frames, max_nan_fraction=0.0)

    assert audit.status == "PASS"
    assert {frame.segment for frame in frames} == {"Br", "Bp", "Bt"}
    assert all(frame.shape == (3, 4) for frame in frames)
    assert all(frame.projection == "CEA" for frame in frames)


@pytest.mark.parametrize("mutation", ["time", "harp", "shape", "wcs", "nan", "inf"])
def test_fits_component_mismatches_fail_closed(tmp_path: Path, mutation: str) -> None:
    frames = []
    for segment in ("Br", "Bp", "Bt"):
        path = tmp_path / f"{segment}.fits"
        kwargs: dict[str, object] = {"segment": segment}
        if segment == "Bt" and mutation == "time":
            kwargs["t_rec"] = "2011.02.14_22:48:00_TAI"
        if segment == "Bt" and mutation == "harp":
            kwargs["harpnum"] = 999
        if segment == "Bt" and mutation == "shape":
            kwargs["shape"] = (4, 4)
        if segment == "Bt" and mutation == "wcs":
            kwargs["ctype1"] = "HPLN-TAN"
        if segment == "Bt" and mutation == "nan":
            kwargs["nan_at"] = (0, 0)
        if segment == "Bt" and mutation == "inf":
            kwargs["inf_at"] = (0, 0)
        _write_fits(path, **kwargs)  # type: ignore[arg-type]
        frames.append(load_fits_image(path, hdu_index=1, expected_segment=segment))

    audit = audit_fits_components(frames, max_nan_fraction=0.0)

    assert audit.status == "FAIL"


def test_fits_missing_header_wrong_segment_and_non_image_fail_closed(tmp_path: Path) -> None:
    wrong_segment = tmp_path / "wrong.fits"
    _write_fits(wrong_segment, segment="Br")
    with pytest.raises(FitsValidationError, match="segment"):
        load_fits_image(wrong_segment, hdu_index=1, expected_segment="Bt")

    missing_header = tmp_path / "missing.fits"
    image = fits.ImageHDU(data=np.ones((2, 2)))
    fits.HDUList([fits.PrimaryHDU(), image]).writeto(missing_header)
    with pytest.raises(FitsValidationError, match="required FITS header"):
        load_fits_image(missing_header, hdu_index=1, expected_segment="Br")

    table_path = tmp_path / "table.fits"
    table = fits.BinTableHDU.from_columns([fits.Column(name="x", format="D", array=[1.0])])
    fits.HDUList([fits.PrimaryHDU(), table]).writeto(table_path)
    with pytest.raises(FitsValidationError, match="two-dimensional numeric image"):
        load_fits_image(table_path, hdu_index=1, expected_segment="Br")
