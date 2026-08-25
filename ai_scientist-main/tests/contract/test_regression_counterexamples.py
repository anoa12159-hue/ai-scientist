"""Independent regressions for counterexamples found during T002 review."""
from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import make_validator
from fixtures_data import (
    ACCEPTABLE_REPLAY_CODES,
    AREF,
    FAIL_CLOSED_CODES,
    VALID,
    VREF,
)


def _assert_invalid(name: str, instance: dict, schemas: dict, registry) -> None:
    errors = list(make_validator(schemas[name], registry).iter_errors(instance))
    assert errors, f"{name} counterexample unexpectedly validated"


@pytest.mark.parametrize("profile_mutation", ["empty", "partial", "duplicate", "unknown", "cross"])
def test_d008_acceptance_profile_is_the_exact_frozen_partition(
    profile_mutation: str, schemas: dict, registry
) -> None:
    instance = deepcopy(VALID["replay-case-manifest"])
    profile = instance["acceptance_profile"]
    if profile_mutation == "empty":
        profile["acceptable_finding_codes"] = []
        profile["fail_closed_finding_codes"] = []
    elif profile_mutation == "partial":
        profile["acceptable_finding_codes"] = ACCEPTABLE_REPLAY_CODES[:-1]
    elif profile_mutation == "duplicate":
        profile["acceptable_finding_codes"] = [
            *ACCEPTABLE_REPLAY_CODES[:-1],
            ACCEPTABLE_REPLAY_CODES[0],
        ]
    elif profile_mutation == "unknown":
        profile["acceptable_finding_codes"] = [
            *ACCEPTABLE_REPLAY_CODES[:-1],
            "BRAND_NEW_UNKNOWN_CODE",
        ]
    else:
        profile["acceptable_finding_codes"] = [
            *ACCEPTABLE_REPLAY_CODES[:-1],
            FAIL_CLOSED_CODES[0],
        ]
    _assert_invalid("replay-case-manifest", instance, schemas, registry)


def test_d008_profile_is_order_independent_but_complete(schemas: dict, registry) -> None:
    instance = deepcopy(VALID["replay-case-manifest"])
    instance["acceptance_profile"]["acceptable_finding_codes"] = list(
        reversed(ACCEPTABLE_REPLAY_CODES)
    )
    instance["acceptance_profile"]["fail_closed_finding_codes"] = list(
        reversed(FAIL_CLOSED_CODES)
    )
    errors = list(make_validator(schemas["replay-case-manifest"], registry).iter_errors(instance))
    assert not errors


def test_unknown_finding_code_cannot_enter_may_accept_route(schemas: dict, registry) -> None:
    instance = deepcopy(VALID["replay-case-manifest"])
    instance["declared_finding_specs"][0]["code"] = "BRAND_NEW_UNKNOWN_CODE"
    instance["declared_finding_specs"][0]["replay_policy"] = (
        "MAY_ACCEPT_WITH_EXACT_HASH_REVIEW"
    )
    _assert_invalid("replay-case-manifest", instance, schemas, registry)


def test_artifact_authority_is_coupled_to_storage_form(schemas: dict, registry) -> None:
    imported_payload = deepcopy(VALID["artifact-envelope"])
    imported_payload.pop("content_ref")
    imported_payload["payload"] = {}
    _assert_invalid("artifact-envelope", imported_payload, schemas, registry)

    derived_content_ref = deepcopy(VALID["artifact-envelope"])
    derived_content_ref["origin_mode"] = "DERIVED"
    derived_content_ref["authority_mode"] = "CANONICAL_JSON"
    _assert_invalid("artifact-envelope", derived_content_ref, schemas, registry)


def test_derived_artifact_requires_derivation_identity(schemas: dict, registry) -> None:
    derived = deepcopy(VALID["artifact-envelope"])
    derived.pop("content_ref")
    derived.update(
        {
            "artifact_type": "ExtractedDocumentSummary",
            "origin_mode": "DERIVED",
            "authority_mode": "CANONICAL_JSON",
            "derivation_kind": "EXTRACTED_FROM_IMPORTED",
            "derived_from_refs": [dict(AREF)],
            "payload": {},
        }
    )
    validator = make_validator(schemas["artifact-envelope"], registry)
    assert not list(validator.iter_errors(derived))

    without_kind = deepcopy(derived)
    without_kind.pop("derivation_kind")
    _assert_invalid("artifact-envelope", without_kind, schemas, registry)

    without_source = deepcopy(derived)
    without_source["derived_from_refs"] = []
    _assert_invalid("artifact-envelope", without_source, schemas, registry)


def test_release_disposition_is_always_decision_bound(schemas: dict, registry) -> None:
    instance = deepcopy(VALID["release-disposition"])
    instance.pop("decision_ref")
    _assert_invalid("release-disposition", instance, schemas, registry)


@pytest.mark.parametrize("missing", ["decision_request_ref", "gate_id", "workflow_version"])
def test_run_gate_decision_has_exact_context(missing: str, schemas: dict, registry) -> None:
    instance = deepcopy(VALID["decision-record"])
    instance.update(
        {
            "decision_context": "RUN_GATE",
            "decision_request_ref": dict(VREF),
            "gate_id": "FIXTURE_IMPORT_REVIEW",
            "workflow_version": "0.1.0",
        }
    )
    instance.pop(missing)
    _assert_invalid("decision-record", instance, schemas, registry)
