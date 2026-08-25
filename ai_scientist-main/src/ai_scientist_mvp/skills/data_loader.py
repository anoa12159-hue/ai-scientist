"""Strict CSV/FITS readers and deterministic SHRGT45 data-quality audits."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from astropy.io import fits
from numpy.typing import NDArray

from ai_scientist_mvp.skills.parameter_registry import (
    ParameterRegistryError,
    default_sharp_parameter_registry,
)

_FITS_HEADER_KEYS = (
    "DATE-OBS",
    "T_REC",
    "HARPNUM",
    "NOAA_AR",
    "BUNIT",
    "CTYPE1",
    "CTYPE2",
    "CUNIT1",
    "CUNIT2",
    "CRPIX1",
    "CRPIX2",
    "CRVAL1",
    "CRVAL2",
    "CDELT1",
    "CDELT2",
)
_WCS_KEYS = (
    "CTYPE1",
    "CTYPE2",
    "CUNIT1",
    "CUNIT2",
    "CRPIX1",
    "CRPIX2",
    "CRVAL1",
    "CRVAL2",
    "CDELT1",
    "CDELT2",
)
_MISSING_TOKENS = {"", "na", "nan", "null", "none"}


class DataLoaderError(ValueError):
    """Base class for deterministic input or quality failures."""


class CsvValidationError(DataLoaderError):
    """CSV bytes or table shape are invalid."""


class FitsValidationError(DataLoaderError):
    """A FITS file is not a supported, auditable image input."""


@dataclass(frozen=True)
class CsvTable:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, str | None], ...]
    source_sha256: str


@dataclass(frozen=True)
class QualityCheck:
    code: str
    status: Literal["PASS", "FAIL"]
    message: str


@dataclass(frozen=True)
class DataQualityPolicy:
    expected_history_frames: int = 16
    min_valid_history_frames: int = 14
    min_span_minutes: float = 160.0
    max_gap_minutes: float = 24.0
    fatal_quality_mask: int = 0xC0000000

    def __post_init__(self) -> None:
        if self.expected_history_frames < 1:
            raise DataLoaderError("expected_history_frames must be positive")
        if not 1 <= self.min_valid_history_frames <= self.expected_history_frames:
            raise DataLoaderError("min_valid_history_frames must fit the expected window")
        if self.min_span_minutes < 0 or self.max_gap_minutes <= 0:
            raise DataLoaderError("span/gap quality thresholds must be non-negative")
        if not 0 <= self.fatal_quality_mask <= 0xFFFFFFFF:
            raise DataLoaderError("fatal_quality_mask must fit an unsigned 32-bit value")


@dataclass(frozen=True)
class HistoryWindowAudit:
    status: Literal["PASS", "FAIL"]
    returned_frames: int
    valid_frames: int
    fatal_quality_frames: int
    nonzero_retained_frames: int
    span_minutes: float
    max_gap_minutes: float
    checks: tuple[QualityCheck, ...]


@dataclass(frozen=True)
class FitsImage:
    segment: str
    date_obs: str
    t_rec: str
    harpnum: int
    noaa_ar: int
    bunit: str
    projection: str
    shape: tuple[int, int]
    wcs_signature: tuple[Any, ...]
    nan_count: int
    inf_count: int
    finite_count: int
    source_sha256: str
    hdu_count: int
    hdu_index: int
    data: NDArray[np.float64] = field(repr=False, compare=False)

    @property
    def total_pixels(self) -> int:
        return self.shape[0] * self.shape[1]

    @property
    def nan_fraction(self) -> float:
        return self.nan_count / self.total_pixels


@dataclass(frozen=True)
class FitsComponentAudit:
    status: Literal["PASS", "FAIL"]
    checks: tuple[QualityCheck, ...]


def load_csv_table(
    path: Path,
    *,
    required_columns: Sequence[str] = (),
    non_nullable_columns: Sequence[str] = (),
) -> CsvTable:
    """Read a strict UTF-8 CSV without coercing missing values or numeric types."""
    source = _read_file_bytes(path, label="CSV")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be valid UTF-8 or UTF-8 with BOM") from exc
    if "\x00" in text:
        raise CsvValidationError("CSV must not contain NUL bytes")
    try:
        parsed_rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise CsvValidationError(f"invalid CSV syntax: {exc}") from exc
    if not parsed_rows:
        raise CsvValidationError("CSV must contain a header row")
    columns = tuple(column.strip() for column in parsed_rows[0])
    if not columns or any(not column for column in columns):
        raise CsvValidationError("CSV header names must be non-empty")
    if len(columns) != len(set(columns)):
        raise CsvValidationError("CSV header names must be unique")
    required = set(required_columns)
    nullable = set(non_nullable_columns)
    if not required.issubset(columns):
        raise CsvValidationError(
            f"CSV missing required columns: {sorted(required - set(columns))}"
        )
    if not nullable.issubset(columns):
        raise CsvValidationError(
            f"CSV non-nullable columns are absent: {sorted(nullable - set(columns))}"
        )

    rows: list[Mapping[str, str | None]] = []
    for line_number, values in enumerate(parsed_rows[1:], start=2):
        if len(values) != len(columns):
            raise CsvValidationError(
                f"CSV row {line_number} has {len(values)} fields; expected {len(columns)}"
            )
        row: dict[str, str | None] = {}
        for column, raw_value in zip(columns, values, strict=True):
            value = raw_value.strip()
            row[column] = None if value.casefold() in _MISSING_TOKENS else value
        missing_required = sorted(column for column in nullable if row[column] is None)
        if missing_required:
            raise CsvValidationError(
                f"CSV row {line_number} has non-nullable missing values: {missing_required}"
            )
        rows.append(row)
    return CsvTable(
        columns=columns,
        rows=tuple(rows),
        source_sha256=hashlib.sha256(source).hexdigest().upper(),
    )


def audit_history_window(
    rows: Sequence[Mapping[str, str | None]],
    *,
    policy: DataQualityPolicy,
    time_column: str = "T_REC_TAI",
    parameter_column: str = "SHRGT45_percent",
    quality_column: str = "QUALITY",
) -> HistoryWindowAudit:
    """Audit one pre-registered 3h window without sorting, interpolation, or imputation."""
    parsed_times: list[datetime] = []
    valid_times: list[datetime] = []
    parse_failures = 0
    fatal_frames = 0
    nonzero_retained_frames = 0
    registry = default_sharp_parameter_registry()

    for row in rows:
        try:
            timestamp = _parse_tai_timestamp(row.get(time_column))
            quality = _parse_quality(row.get(quality_column))
            raw_value = row.get(parameter_column)
            if raw_value is None:
                raise DataLoaderError("SHRGT45 value is missing")
            registry.validate_value("SHRGT45", float(raw_value), declared_unit="percent")
        except (DataLoaderError, ParameterRegistryError, TypeError, ValueError):
            parse_failures += 1
            continue
        parsed_times.append(timestamp)
        if quality & policy.fatal_quality_mask:
            fatal_frames += 1
            continue
        if quality != 0:
            nonzero_retained_frames += 1
        valid_times.append(timestamp)

    chronological = len(parsed_times) == len(rows) and all(
        earlier < later for earlier, later in zip(parsed_times, parsed_times[1:], strict=False)
    )
    span_minutes = _span_minutes(valid_times) if chronological else 0.0
    max_gap_minutes = _max_gap_minutes(valid_times) if chronological else math.inf
    checks = (
        _check(
            "RETURNED_FRAME_BOUND",
            len(rows) <= policy.expected_history_frames,
            f"returned={len(rows)}, expected_at_most={policy.expected_history_frames}",
        ),
        _check(
            "ROW_PARSE_AND_PARAMETER_RANGE",
            parse_failures == 0,
            f"parse_or_missing_failures={parse_failures}",
        ),
        _check("STRICT_TIME_ORDER", chronological, "timestamps must be strictly increasing"),
        _check(
            "VALID_FRAME_COUNT",
            len(valid_times) >= policy.min_valid_history_frames,
            f"valid={len(valid_times)}, required={policy.min_valid_history_frames}",
        ),
        _check(
            "WINDOW_SPAN",
            span_minutes >= policy.min_span_minutes,
            f"span_minutes={span_minutes}, required={policy.min_span_minutes}",
        ),
        _check(
            "MAX_VALID_FRAME_GAP",
            max_gap_minutes <= policy.max_gap_minutes,
            f"max_gap_minutes={max_gap_minutes}, allowed={policy.max_gap_minutes}",
        ),
    )
    return HistoryWindowAudit(
        status=_status(checks),
        returned_frames=len(rows),
        valid_frames=len(valid_times),
        fatal_quality_frames=fatal_frames,
        nonzero_retained_frames=nonzero_retained_frames,
        span_minutes=span_minutes,
        max_gap_minutes=max_gap_minutes,
        checks=checks,
    )


def load_fits_image(
    path: Path, *, hdu_index: int, expected_segment: str
) -> FitsImage:
    """Read one 2-D SHARP FITS image and retain identity/WCS audit metadata."""
    if hdu_index < 0:
        raise FitsValidationError("hdu_index must be non-negative")
    source = _read_file_bytes(path, label="FITS")
    try:
        with fits.open(io.BytesIO(source), memmap=False, checksum=True) as hdus:
            if hdu_index >= len(hdus):
                raise FitsValidationError(
                    f"FITS hdu_index {hdu_index} is absent; hdu_count={len(hdus)}"
                )
            hdu_count = len(hdus)
            hdu = hdus[hdu_index]
            data = hdu.data
            header = hdu.header.copy()
    except FitsValidationError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise FitsValidationError(f"invalid FITS bytes: {exc}") from exc
    if not isinstance(data, np.ndarray) or data.ndim != 2 or not np.issubdtype(
        data.dtype, np.number
    ):
        raise FitsValidationError("FITS HDU must contain a two-dimensional numeric image")
    missing_headers = [key for key in _FITS_HEADER_KEYS if key not in header]
    if missing_headers:
        raise FitsValidationError(f"missing required FITS header keys: {missing_headers}")
    header_segment = header.get("SEGMENT", header.get("CONTENT"))
    if header_segment != expected_segment:
        raise FitsValidationError(
            f"FITS segment mismatch: expected {expected_segment!r}, got {header_segment!r}"
        )
    bunit = str(header["BUNIT"]).strip()
    if bunit.casefold() not in {"gauss", "g"}:
        raise FitsValidationError("FITS BUNIT must be Gauss/G for Br, Bp, or Bt")
    t_rec = str(header["T_REC"]).strip()
    _parse_tai_timestamp(t_rec)
    try:
        harpnum = int(header["HARPNUM"])
        noaa_ar = int(header["NOAA_AR"])
    except (TypeError, ValueError) as exc:
        raise FitsValidationError("FITS HARPNUM and NOAA_AR must be integers") from exc
    image = np.asarray(data, dtype=np.float64)
    nan_count = int(np.isnan(image).sum())
    inf_count = int(np.isinf(image).sum())
    finite_count = int(np.isfinite(image).sum())
    ctype1 = str(header["CTYPE1"]).strip().upper()
    ctype2 = str(header["CTYPE2"]).strip().upper()
    projection = "CEA" if ctype1.endswith("-CEA") and ctype2.endswith("-CEA") else "OTHER"
    return FitsImage(
        segment=expected_segment,
        date_obs=str(header["DATE-OBS"]).strip(),
        t_rec=t_rec,
        harpnum=harpnum,
        noaa_ar=noaa_ar,
        bunit="Gauss",
        projection=projection,
        shape=(int(image.shape[0]), int(image.shape[1])),
        wcs_signature=tuple(header[key] for key in _WCS_KEYS),
        nan_count=nan_count,
        inf_count=inf_count,
        finite_count=finite_count,
        source_sha256=hashlib.sha256(source).hexdigest().upper(),
        hdu_count=hdu_count,
        hdu_index=hdu_index,
        data=image,
    )


def audit_fits_components(
    frames: Sequence[FitsImage], *, max_nan_fraction: float
) -> FitsComponentAudit:
    """Require Br/Bp/Bt to share one HARP/T_REC, image grid, and CEA WCS."""
    if not math.isfinite(max_nan_fraction) or not 0 <= max_nan_fraction <= 1:
        raise FitsValidationError("max_nan_fraction must be within [0, 1]")
    segments = [frame.segment for frame in frames]
    expected_segments = {"Br", "Bp", "Bt"}
    checks = (
        _check(
            "COMPONENT_SET",
            len(segments) == 3 and set(segments) == expected_segments,
            f"segments={segments!r}",
        ),
        _check(
            "SAME_RECORD_IDENTITY",
            _one_value(frame.t_rec for frame in frames)
            and _one_value(frame.harpnum for frame in frames)
            and _one_value(frame.noaa_ar for frame in frames),
            "T_REC, HARPNUM, and NOAA_AR must match",
        ),
        _check(
            "SAME_SHAPE",
            _one_value(frame.shape for frame in frames),
            "all components must share shape",
        ),
        _check(
            "SAME_WCS",
            _one_value(frame.wcs_signature for frame in frames),
            "all components must share exact WCS",
        ),
        _check(
            "CEA_PROJECTION",
            bool(frames) and all(frame.projection == "CEA" for frame in frames),
            "every component must use CEA projection",
        ),
        _check(
            "FINITE_VALUES",
            bool(frames) and all(frame.inf_count == 0 for frame in frames),
            "Inf values are forbidden",
        ),
        _check(
            "NAN_FRACTION",
            bool(frames) and all(
                frame.nan_fraction <= max_nan_fraction for frame in frames
            ),
            f"nan fraction must be <= {max_nan_fraction}",
        ),
    )
    return FitsComponentAudit(status=_status(checks), checks=checks)


def _read_file_bytes(path: Path, *, label: str) -> bytes:
    try:
        if path.is_symlink():
            raise DataLoaderError(f"{label} path must not be a symbolic link")
        source = path.read_bytes()
    except OSError as exc:
        raise DataLoaderError(f"cannot read {label} file") from exc
    if not source:
        raise DataLoaderError(f"{label} file must not be empty")
    return source


def _parse_tai_timestamp(value: str | None) -> datetime:
    if value is None:
        raise DataLoaderError("TAI timestamp is missing")
    try:
        return datetime.strptime(value, "%Y.%m.%d_%H:%M:%S_TAI")
    except ValueError as exc:
        raise DataLoaderError(f"invalid T_REC_TAI timestamp: {value!r}") from exc


def _parse_quality(value: str | None) -> int:
    if value is None:
        raise DataLoaderError("QUALITY is missing")
    try:
        quality = int(value, 0)
    except ValueError as exc:
        raise DataLoaderError(f"invalid QUALITY mask: {value!r}") from exc
    if not 0 <= quality <= 0xFFFFFFFF:
        raise DataLoaderError("QUALITY must fit an unsigned 32-bit mask")
    return quality


def _span_minutes(timestamps: Sequence[datetime]) -> float:
    if len(timestamps) < 2:
        return 0.0
    return (timestamps[-1] - timestamps[0]).total_seconds() / 60.0


def _max_gap_minutes(timestamps: Sequence[datetime]) -> float:
    if len(timestamps) < 2:
        return math.inf
    return max(
        (later - earlier).total_seconds() / 60.0
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
    )


def _check(code: str, passed: bool, message: str) -> QualityCheck:
    return QualityCheck(code=code, status="PASS" if passed else "FAIL", message=message)


def _status(checks: Sequence[QualityCheck]) -> Literal["PASS", "FAIL"]:
    return "FAIL" if any(check.status == "FAIL" for check in checks) else "PASS"


def _one_value(values: Sequence[Any] | Any) -> bool:
    materialized = list(values)
    return bool(materialized) and len(set(materialized)) == 1
