"""Deterministic SHARP parameter definitions, aliases, formulas, and units."""
from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ai_scientist_mvp.domain import canonical_json

_KEYWORD_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ParameterRegistryError(ValueError):
    """Base class for deterministic parameter-registry failures."""


class ParameterDefinitionError(ParameterRegistryError):
    """A registered definition is incomplete or collides with another definition."""


class UnknownParameterError(ParameterRegistryError):
    """A name is not registered."""


class AmbiguousParameterAliasError(ParameterRegistryError):
    """A known unsafe alias would collapse distinct parameter semantics."""


class ParameterUnitError(ParameterRegistryError):
    """A declared unit does not match the registered raw parameter unit."""


class ParameterFormulaError(ParameterRegistryError):
    """A formula ID differs from the registered deterministic definition."""


class ParameterValueError(ParameterRegistryError):
    """A value is non-finite, boolean, or outside the registered range."""


@dataclass(frozen=True)
class SharpParameterDefinition:
    keyword: str
    long_name: str
    definition: str
    formula_id: str
    formula: str
    canonical_unit: str
    unit_aliases: tuple[str, ...]
    valid_range: tuple[float, float] | None
    observation_level: str
    data_series: str
    cadence: str
    aliases: tuple[str, ...]
    rejected_aliases: Mapping[str, str]
    supporting_keywords: tuple[str, ...]
    pixel_selection_rule: str
    source_citations: tuple[str, ...]

    def __post_init__(self) -> None:
        tuple_fields = ("unit_aliases", "aliases", "supporting_keywords", "source_citations")
        for field_name in tuple_fields:
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(
            self,
            "rejected_aliases",
            MappingProxyType(dict(self.rejected_aliases)),
        )
        required_strings = {
            "keyword": self.keyword,
            "long_name": self.long_name,
            "definition": self.definition,
            "formula_id": self.formula_id,
            "formula": self.formula,
            "canonical_unit": self.canonical_unit,
            "observation_level": self.observation_level,
            "data_series": self.data_series,
            "cadence": self.cadence,
            "pixel_selection_rule": self.pixel_selection_rule,
        }
        missing = sorted(name for name, value in required_strings.items() if not value.strip())
        if missing:
            raise ParameterDefinitionError(f"definition has empty fields: {missing}")
        if _KEYWORD_PATTERN.fullmatch(self.keyword) is None:
            raise ParameterDefinitionError("canonical keyword must be uppercase SHARP syntax")
        normalized_units = {_normalize_unit(unit) for unit in self.unit_aliases}
        if _normalize_unit(self.canonical_unit) not in normalized_units:
            raise ParameterDefinitionError("unit aliases must include the canonical unit")
        if not self.source_citations or any(
            not citation.strip() for citation in self.source_citations
        ):
            raise ParameterDefinitionError("definition requires non-empty source citations")
        if self.valid_range is not None:
            lower, upper = self.valid_range
            if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
                raise ParameterDefinitionError("valid_range must be finite and ordered")
        if any(not reason.strip() for reason in self.rejected_aliases.values()):
            raise ParameterDefinitionError("every rejected alias requires a reason")

    @property
    def definition_hash(self) -> str:
        return self.compute_definition_hash()

    def compute_definition_hash(self) -> str:
        return canonical_json.content_hash(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "long_name": self.long_name,
            "definition": self.definition,
            "formula_id": self.formula_id,
            "formula": self.formula,
            "canonical_unit": self.canonical_unit,
            "unit_aliases": list(self.unit_aliases),
            "valid_range": list(self.valid_range) if self.valid_range is not None else None,
            "observation_level": self.observation_level,
            "data_series": self.data_series,
            "cadence": self.cadence,
            "aliases": list(self.aliases),
            "rejected_aliases": dict(sorted(self.rejected_aliases.items())),
            "supporting_keywords": list(self.supporting_keywords),
            "pixel_selection_rule": self.pixel_selection_rule,
            "source_citations": list(self.source_citations),
        }


@dataclass(frozen=True)
class ParameterValue:
    keyword: str
    value: float
    canonical_unit: str
    definition_hash: str


class SharpParameterRegistry:
    """Resolve safe aliases and validate raw SHARP scalar values."""

    def __init__(self, definitions: Iterable[SharpParameterDefinition]) -> None:
        self._definitions: dict[str, SharpParameterDefinition] = {}
        self._accepted_names: dict[str, SharpParameterDefinition] = {}
        self._rejected_names: dict[str, str] = {}
        for definition in definitions:
            if definition.keyword in self._definitions:
                raise ParameterDefinitionError(f"duplicate keyword: {definition.keyword}")
            self._definitions[definition.keyword] = definition
            for name in (definition.keyword, definition.long_name, *definition.aliases):
                self._register_accepted_name(name, definition)
            for name, reason in definition.rejected_aliases.items():
                self._register_rejected_name(name, reason)
        if not self._definitions:
            raise ParameterDefinitionError("parameter registry must not be empty")

    def resolve(self, name: str) -> SharpParameterDefinition:
        normalized = _normalize_name(name)
        definition = self._accepted_names.get(normalized)
        if definition is not None:
            return definition
        reason = self._rejected_names.get(normalized)
        if reason is not None:
            raise AmbiguousParameterAliasError(reason)
        raise UnknownParameterError(f"unknown SHARP parameter or alias: {name!r}")

    def validate_formula(self, name: str, formula_id: str) -> None:
        definition = self.resolve(name)
        if formula_id != definition.formula_id:
            raise ParameterFormulaError(
                f"{definition.keyword} requires formula_id={definition.formula_id!r}"
            )

    def validate_value(
        self, name: str, value: int | float, *, declared_unit: str
    ) -> ParameterValue:
        definition = self.resolve(name)
        normalized_units = {_normalize_unit(unit) for unit in definition.unit_aliases}
        if _normalize_unit(declared_unit) not in normalized_units:
            raise ParameterUnitError(
                f"{definition.keyword} raw values require unit {definition.canonical_unit!r}; "
                "no implicit conversion is allowed"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParameterValueError("parameter value must be a real number, not boolean")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ParameterValueError("parameter value must be finite")
        if definition.valid_range is not None:
            lower, upper = definition.valid_range
            if numeric < lower or numeric > upper:
                raise ParameterValueError(
                    f"{definition.keyword} value must be within [{lower}, {upper}]"
                )
        return ParameterValue(
            keyword=definition.keyword,
            value=numeric,
            canonical_unit=definition.canonical_unit,
            definition_hash=definition.definition_hash,
        )

    def _register_accepted_name(
        self, name: str, definition: SharpParameterDefinition
    ) -> None:
        normalized = _normalize_name(name)
        existing = self._accepted_names.get(normalized)
        if existing is not None and existing.keyword != definition.keyword:
            raise ParameterDefinitionError(
                f"alias collision: {name!r} maps to {existing.keyword} and {definition.keyword}"
            )
        if normalized in self._rejected_names:
            raise ParameterDefinitionError(f"alias collision: {name!r} is also rejected")
        self._accepted_names[normalized] = definition

    def _register_rejected_name(self, name: str, reason: str) -> None:
        normalized = _normalize_name(name)
        if normalized in self._accepted_names:
            raise ParameterDefinitionError(f"alias collision: {name!r} is accepted and rejected")
        existing = self._rejected_names.get(normalized)
        if existing is not None and existing != reason:
            raise ParameterDefinitionError(f"rejected alias collision: {name!r}")
        self._rejected_names[normalized] = reason


def _normalize_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UnknownParameterError("parameter name must be a non-empty string")
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().casefold().split())


def _normalize_unit(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParameterUnitError("declared unit must be a non-empty string")
    return unicodedata.normalize("NFKC", value).strip().casefold()


_MEANSHR_REJECTION = (
    "SHRGT45 is an area percentage above a 45-degree threshold; MEANSHR is the "
    "mean shear angle. These parameters are not aliases."
)

_SHRGT45 = SharpParameterDefinition(
    keyword="SHRGT45",
    long_name="Fraction of Area with Shear > 45°",
    definition=(
        "Percentage of valid HARP pixels whose three-dimensional shear angle between "
        "the observed vector magnetic field and the potential field exceeds 45 degrees."
    ),
    formula_id="AREA_FRACTION_SHEAR_GT_45",
    formula=(
        "SHRGT45 = 100 * count(phi_i > 45 deg) / CMASK; "
        "phi_i = arccos((B_obs_i dot B_pot_i) / (|B_obs_i| * |B_pot_i|))"
    ),
    canonical_unit="percent",
    unit_aliases=("percent", "%", "percentage", "pct"),
    valid_range=(0.0, 100.0),
    observation_level="SHARP_HARP_PATCH",
    data_series="hmi.sharp_cea_720s",
    cadence="PT12M",
    aliases=(
        "percentage of pixels with shear angle greater than 45 degrees",
        "剪切角大于45度的有效像素面积百分比",
    ),
    rejected_aliases={
        "MEANSHR": _MEANSHR_REJECTION,
        "mean shear angle": _MEANSHR_REJECTION,
        "shear angle": _MEANSHR_REJECTION,
        "percentage of pixels with mean shear angle greater than 45 degrees": (
            _MEANSHR_REJECTION
        ),
        "平均剪切角": _MEANSHR_REJECTION,
    },
    supporting_keywords=("CMASK", "QUALITY", "T_REC", "BITMAP", "CONF_DISAMBIG"),
    pixel_selection_rule="BITMAP >= 33 and CONF_DISAMBIG == 90; denominator is CMASK",
    source_citations=(
        "doi:10.1007/s11207-014-0529-3#Table3",
        "fixture:s02.mechanism-brief-v2_3#section-1",
    ),
)

_DEFAULT_REGISTRY = SharpParameterRegistry([_SHRGT45])


def default_sharp_parameter_registry() -> SharpParameterRegistry:
    return _DEFAULT_REGISTRY
