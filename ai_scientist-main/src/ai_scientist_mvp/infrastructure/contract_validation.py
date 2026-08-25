"""Runtime validation against the accepted JSON Schema 2020-12 contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from ai_scientist_mvp.domain.errors import SchemaValidationError

SUPPORTED_SCHEMA_VERSION = "0.1.0"


class ContractValidator:
    """Load the contract registry once and validate named public objects."""

    def __init__(self, contracts_root: Path) -> None:
        root = contracts_root.resolve()
        schemas: dict[str, dict[str, Any]] = {}
        for path in sorted(root.rglob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            schemas[schema["$id"]] = schema
        if not schemas:
            raise SchemaValidationError(f"no JSON Schemas found under {root}")
        resources = []
        for schema in schemas.values():
            resource = Resource.from_contents(schema)
            resource_id = resource.id()
            if resource_id is None:
                raise SchemaValidationError("contract schema is missing $id")
            resources.append((resource_id, resource))
        self._registry = Registry().with_resources(resources)
        self._schemas = {
            schema_id.rstrip("/").split("/")[-1].removesuffix(".schema.json"): schema
            for schema_id, schema in schemas.items()
        }

    def validate(self, schema_name: str, instance: Any) -> None:
        schema = self._schemas.get(schema_name)
        if schema is None:
            raise SchemaValidationError(f"unknown contract schema: {schema_name}")
        try:
            Draft202012Validator(
                schema,
                registry=self._registry,
                format_checker=FormatChecker(),
            ).validate(instance)
        except ValidationError as exc:
            location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
            raise SchemaValidationError(
                f"{schema_name} violates contract at {location}: {exc.message}"
            ) from exc
        if isinstance(instance, dict) and "schema_version" in instance:
            actual = instance["schema_version"]
            if actual != SUPPORTED_SCHEMA_VERSION:
                raise SchemaValidationError(
                    f"unsupported {schema_name} schema_version: {actual!r}"
                )


def default_contracts_root() -> Path:
    """Locate repository contract assets without a machine-specific path."""
    return Path(__file__).resolve().parents[3] / "contracts"
