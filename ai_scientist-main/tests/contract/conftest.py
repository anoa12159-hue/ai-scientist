"""Shared fixtures for contract tests: load JSON Schema 2020-12 and build a resolver registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = PROJECT_ROOT / "contracts"

# Authoritative schema list from docs/contracts/SCHEMA_CATALOG.md.
CATALOG_SCHEMA_NAMES = [
    # Foundation
    "versioned-ref", "research-question", "run-configuration-snapshot",
    "source-asset-ref", "source-package-ref", "replay-case-manifest",
    # Artifact And Runtime
    "artifact-ref", "artifact-envelope", "artifact-lifecycle-event",
    "artifact-state-view", "run-record", "stage-run", "stage-context",
    "checkpoint-ref", "failure-record",
    # Validation, Lineage And Findings
    "validation-report", "lineage-edge", "compatibility-finding",
    "gap-finding", "finding-disposition", "finding-state-view",
    # Governance And Release
    "decision-option", "decision-request", "decision-record",
    "authorization-record", "project-review-ack", "release-disposition",
    "release-state-view",
    # Domain And Query Projections
    "candidate-snapshot", "mechanism-snapshot", "hypothesis-snapshot",
    "verification-snapshot", "counterexample-snapshot", "magnetogram-qa-snapshot",
    "research-summary", "report-manifest", "run-read-model",
]


def load_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(CONTRACTS_ROOT.rglob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[schema["$id"]] = schema
    return schemas


def schema_name(schema: dict[str, Any]) -> str:
    return schema["$id"].rstrip("/").split("/")[-1].removesuffix(".schema.json")


@pytest.fixture(scope="session")
def schemas() -> dict[str, dict[str, Any]]:
    return {schema_name(schema): schema for schema in load_schemas().values()}


@pytest.fixture(scope="session")
def registry(schemas: dict[str, dict[str, Any]]) -> Registry:
    resources = [
        (Resource.from_contents(schema).id(), Resource.from_contents(schema))
        for schema in schemas.values()
    ]
    return Registry().with_resources(resources)


def make_validator(schema: dict[str, Any], registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
