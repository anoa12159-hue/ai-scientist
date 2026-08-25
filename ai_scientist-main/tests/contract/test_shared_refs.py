"""Shared $ref reuse: enums and primitives must be defined once and referenced, not duplicated."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def _walk(node: Any) -> Iterator[list[str]]:
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            yield list(node["enum"])
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_shared_enums_not_inlined_in_concrete_schemas(schemas: dict) -> None:
    shared_defs = schemas["definitions"]["$defs"]
    shared_enums = {
        name: list(defn["enum"])
        for name, defn in shared_defs.items()
        if isinstance(defn, dict) and isinstance(defn.get("enum"), list)
    }
    duplicates: list[tuple[str, str]] = []
    for name, schema in schemas.items():
        if name == "definitions":
            continue
        for inline in _walk(schema):
            for def_name, shared_enum in shared_enums.items():
                if inline == shared_enum:
                    duplicates.append((name, def_name))
    assert not duplicates, f"shared enums duplicated inline (use $ref): {duplicates}"


def test_d008_classification_lists_are_pinned_and_disjoint(schemas: dict) -> None:
    defs = schemas["definitions"]["$defs"]
    acceptable = defs["acceptable_replay_finding_code"]["enum"]
    fail_closed = defs["fail_closed_finding_code"]["enum"]
    assert len(acceptable) == 10, "acceptable-replay list must stay frozen at 10 codes"
    assert len(fail_closed) == 14, "fail-closed list must stay frozen at 14 codes"
    assert set(acceptable).isdisjoint(set(fail_closed)), (
        "acceptable and fail-closed Finding codes must be disjoint"
    )


def test_d008_enums_are_referenced_not_orphaned(schemas: dict) -> None:
    import json

    concrete = json.dumps({name: schemas[name] for name in schemas if name != "definitions"})
    for def_name in ("acceptable_replay_finding_code", "fail_closed_finding_code"):
        assert f"$defs/{def_name}" in concrete, (
            f"{def_name} is an orphaned definition; it must be $ref-constrained by a schema"
        )


def test_preset_finding_code_lists_match_frozen_contract(schemas: dict) -> None:
    defs = schemas["definitions"]["$defs"]
    assert set(defs["compatibility_finding_code"]["enum"]) == {
        "MECHANISM_V23_VS_HYPOTHESIS_V22_DEPENDENCY",
        "THEIL_SEN_VS_OLS_IMPLEMENTATION",
        "COUNTEREXAMPLE_INPUT_PACKAGE_IDENTITY_UNVERIFIED",
        "LEAD_WINDOW_BOUNDARY_IMPLEMENTATION_MISMATCH",
        "CONTROL_WINDOW_POLICY_MISMATCH",
        "CONTROL_CATALOG_SPATIAL_ATTRIBUTION_UNFILTERED",
        "HARP_NOAA_MAPPING_PARTIAL_OR_AMBIGUOUS",
    }
    assert set(defs["gap_finding_code"]["enum"]) == {
        "CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED",
        "LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE",
        "EVENT_SEED_OFFICIAL_PROVENANCE_UNVERIFIED",
        "HISTORICAL_ROWS_NOT_INDEPENDENT_SAMPLES",
    }
