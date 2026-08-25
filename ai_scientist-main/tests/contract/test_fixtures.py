"""Minimal valid and key invalid Golden Fixtures for every catalog schema."""
from __future__ import annotations

from conftest import CATALOG_SCHEMA_NAMES, make_validator
from fixtures_data import INVALID, VALID, VALID_BRANCHES


def test_every_catalog_schema_has_a_valid_fixture() -> None:
    missing = [name for name in CATALOG_SCHEMA_NAMES if name not in VALID]
    assert not missing, f"no minimal valid fixture for: {missing}"


def test_valid_instances_validate(schemas: dict, registry) -> None:
    for name, instance in VALID.items():
        validator = make_validator(schemas[name], registry)
        errors = list(validator.iter_errors(instance))
        assert not errors, f"{name}: {[e.message for e in errors]}"


def test_valid_conditional_branches_validate(schemas: dict, registry) -> None:
    for name, branches in VALID_BRANCHES.items():
        validator = make_validator(schemas[name], registry)
        for index, instance in enumerate(branches):
            errors = list(validator.iter_errors(instance))
            assert not errors, f"{name} branch {index}: {[e.message for e in errors]}"


def test_invalid_instances_fail(schemas: dict, registry) -> None:
    for name, instance in INVALID:
        validator = make_validator(schemas[name], registry)
        errors = list(validator.iter_errors(instance))
        assert errors, f"{name}: expected invalid but validated"
