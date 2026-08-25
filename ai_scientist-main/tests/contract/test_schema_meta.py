"""JSON Schema 2020-12 meta-validation of every contract schema."""
from __future__ import annotations

from conftest import CATALOG_SCHEMA_NAMES
from jsonschema import Draft202012Validator


def test_every_catalog_schema_exists(schemas: dict) -> None:
    missing = [name for name in CATALOG_SCHEMA_NAMES if name not in schemas]
    assert not missing, f"catalog schemas missing on disk: {missing}"


def test_no_unexpected_schemas(schemas: dict) -> None:
    extra = set(schemas) - set(CATALOG_SCHEMA_NAMES) - {"definitions"}
    assert not extra, f"unexpected schema files: {extra}"


def test_schemas_declare_draft_2020_12_and_id(schemas: dict) -> None:
    for name, schema in schemas.items():
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", name
        assert schema.get("$id"), name


def test_all_schemas_meta_validate(schemas: dict) -> None:
    errors = []
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - report all failures, not just the first
            errors.append(f"{name}: {exc}")
    assert not errors, "\n".join(errors)
