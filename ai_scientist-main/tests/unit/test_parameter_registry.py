from __future__ import annotations

import math

import pytest

from ai_scientist_mvp.skills.parameter_registry import (
    AmbiguousParameterAliasError,
    ParameterDefinitionError,
    ParameterFormulaError,
    ParameterUnitError,
    ParameterValueError,
    SharpParameterDefinition,
    SharpParameterRegistry,
    UnknownParameterError,
    default_sharp_parameter_registry,
)


def test_default_registry_freezes_shrgt45_definition() -> None:
    definition = default_sharp_parameter_registry().resolve("SHRGT45")

    assert definition.keyword == "SHRGT45"
    assert definition.long_name == "Fraction of Area with Shear > 45°"
    assert definition.formula_id == "AREA_FRACTION_SHEAR_GT_45"
    assert definition.canonical_unit == "percent"
    assert definition.valid_range == (0.0, 100.0)
    assert definition.observation_level == "SHARP_HARP_PATCH"
    assert definition.data_series == "hmi.sharp_cea_720s"
    assert definition.cadence == "PT12M"
    assert "CMASK" in definition.supporting_keywords
    assert definition.definition_hash == definition.compute_definition_hash()


@pytest.mark.parametrize(
    "alias",
    [
        "shrgt45",
        "  SHRGT45  ",
        "Fraction of Area with Shear > 45°",
        "percentage of pixels with shear angle greater than 45 degrees",
        "剪切角大于45度的有效像素面积百分比",
    ],
)
def test_resolves_only_semantically_safe_aliases(alias: str) -> None:
    assert default_sharp_parameter_registry().resolve(alias).keyword == "SHRGT45"


@pytest.mark.parametrize(
    "alias",
    [
        "MEANSHR",
        "mean shear angle",
        "shear angle",
        "percentage of pixels with mean shear angle greater than 45 degrees",
        "平均剪切角",
    ],
)
def test_rejects_aliases_that_collapse_shrgt45_into_meanshr(alias: str) -> None:
    with pytest.raises(AmbiguousParameterAliasError, match="SHRGT45.*MEANSHR"):
        default_sharp_parameter_registry().resolve(alias)


def test_rejects_unknown_parameter() -> None:
    with pytest.raises(UnknownParameterError, match="TOTUSJH"):
        default_sharp_parameter_registry().resolve("TOTUSJH")


@pytest.mark.parametrize("unit", ["percent", "%", "percentage", "pct"])
def test_validates_percent_values_without_changing_scale(unit: str) -> None:
    registry = default_sharp_parameter_registry()

    assert registry.validate_value("SHRGT45", 0, declared_unit=unit).value == 0.0
    assert registry.validate_value("SHRGT45", 37.5, declared_unit=unit).value == 37.5
    assert registry.validate_value("SHRGT45", 100, declared_unit=unit).value == 100.0


@pytest.mark.parametrize("unit", ["fraction", "0-1", "degree", "degrees"])
def test_rejects_incompatible_units_instead_of_silent_conversion(unit: str) -> None:
    with pytest.raises(ParameterUnitError, match="percent"):
        default_sharp_parameter_registry().validate_value(
            "SHRGT45", 0.5, declared_unit=unit
        )


@pytest.mark.parametrize("value", [-0.1, 100.1, math.nan, math.inf, -math.inf, True])
def test_rejects_nonfinite_boolean_and_out_of_range_values(value: float) -> None:
    with pytest.raises(ParameterValueError):
        default_sharp_parameter_registry().validate_value(
            "SHRGT45", value, declared_unit="percent"
        )


def test_formula_id_must_match_registered_definition() -> None:
    registry = default_sharp_parameter_registry()

    registry.validate_formula("SHRGT45", "AREA_FRACTION_SHEAR_GT_45")
    with pytest.raises(ParameterFormulaError, match="AREA_FRACTION_SHEAR_GT_45"):
        registry.validate_formula("SHRGT45", "MEAN_SHEAR_ANGLE")


def test_registry_rejects_alias_collisions() -> None:
    original = default_sharp_parameter_registry().resolve("SHRGT45")
    colliding = SharpParameterDefinition(
        keyword="TESTPARM",
        long_name="Test parameter",
        definition="Test only",
        formula_id="TEST_FORMULA",
        formula="x",
        canonical_unit="arb",
        unit_aliases=("arb",),
        valid_range=None,
        observation_level="SHARP_HARP_PATCH",
        data_series="test.series",
        cadence="PT12M",
        aliases=("SHRGT45",),
        rejected_aliases={},
        supporting_keywords=(),
        pixel_selection_rule="not applicable",
        source_citations=("test:fixture",),
    )

    with pytest.raises(ParameterDefinitionError, match="alias collision"):
        SharpParameterRegistry([original, colliding])


def test_definition_requires_canonical_unit_alias_and_sources() -> None:
    with pytest.raises(ParameterDefinitionError, match="canonical unit"):
        SharpParameterDefinition(
            keyword="TESTPARM",
            long_name="Test parameter",
            definition="Test only",
            formula_id="TEST_FORMULA",
            formula="x",
            canonical_unit="arb",
            unit_aliases=("unitless",),
            valid_range=None,
            observation_level="SHARP_HARP_PATCH",
            data_series="test.series",
            cadence="PT12M",
            aliases=(),
            rejected_aliases={},
            supporting_keywords=(),
            pixel_selection_rule="not applicable",
            source_citations=(),
        )
