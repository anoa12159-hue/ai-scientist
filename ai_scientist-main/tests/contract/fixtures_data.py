"""Golden Fixtures for every catalog schema.

``VALID`` holds one minimal valid instance per schema. ``VALID_BRANCHES`` holds
the additional legal branches for schemas with conditional logic. ``INVALID``
holds key failing instances, including every frozen-contract invariant
violation.
"""
from __future__ import annotations

from typing import Any

H = "0" * 64  # 64-char hex digest placeholder (uppercase not required by schema)
TS = "2026-08-20T00:00:00Z"
ACCEPTABLE_REPLAY_CODES = [
    "MECHANISM_V23_VS_HYPOTHESIS_V22_DEPENDENCY",
    "THEIL_SEN_VS_OLS_IMPLEMENTATION",
    "LEAD_WINDOW_BOUNDARY_IMPLEMENTATION_MISMATCH",
    "CONTROL_WINDOW_POLICY_MISMATCH",
    "CONTROL_CATALOG_SPATIAL_ATTRIBUTION_UNFILTERED",
    "HARP_NOAA_MAPPING_PARTIAL_OR_AMBIGUOUS",
    "COUNTEREXAMPLE_INPUT_PACKAGE_IDENTITY_UNVERIFIED",
    "EVENT_SEED_OFFICIAL_PROVENANCE_UNVERIFIED",
    "HISTORICAL_ROWS_NOT_INDEPENDENT_SAMPLES",
    "S04_0808_PACKAGE_INTEGRITY_REFERENCES_MISSING_FROM_TRANSFER",
]
FAIL_CLOSED_CODES = [
    "UNKNOWN_FIXTURE_PATH",
    "MISSING_REQUIRED_MEMBER",
    "SHA256_MISMATCH",
    "MANIFEST_MISMATCH",
    "UNKNOWN_SCHEMA_OR_VERSION",
    "UNKNOWN_SOURCE_OR_PROVENANCE_IDENTITY",
    "CONFIGURATION_HASH_MISMATCH",
    "UNAUTHORIZED_FORMAL_EXECUTION",
    "SECRET_OR_CREDENTIAL_ACCESS",
    "FORBIDDEN_HISTORICAL_SCRIPT_EXECUTION",
    "FORBIDDEN_NESTED_ZIP_EXTRACTION",
    "REQUIRED_S05_OR_S06_BRANCH_FAILURE",
    "REPORT_JOIN_FAILURE",
    "UNBOUND_FINDING_OR_ARTIFACT",
]

VREF: dict[str, Any] = {"id": "ref-1", "schema_version": "0.1.0", "content_hash": H}
AREF: dict[str, Any] = {"artifact_id": "art-1", "content_sha256": H, "schema_version": "0.1.0"}
FREF: dict[str, Any] = {"finding_id": "find-1", "content_hash": H, "schema_version": "0.1.0"}


def _envelope(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "artifact_id": "art-1",
        "logical_artifact_id": "logical-1",
        "artifact_type": "SourceDocument",
        "schema_version": "0.1.0",
        "artifact_revision": 1,
        "task_id": "task-1",
        "run_id": "run-1",
        "run_mode": "REPLAY",
        "origin_mode": "IMPORTED",
        "authority_mode": "SOURCE_BYTES",
        "content_ref": "store://art-1",
        "content_sha256": H,
        "producer": {"id": "replay-adapter", "version": "0.1.0"},
        "created_at": TS,
    }
    base.update(overrides)
    return base


VALID: dict[str, dict[str, Any]] = {
    "versioned-ref": dict(VREF),
    "research-question": {
        "question_id": "RQ-SHRGT45-001",
        "question_version": "0.1.0",
        "schema_version": "0.1.0",
        "parameter": "SHRGT45",
        "scientific_question": "SHRGT45演化能否预测M1.0+耀斑",
        "history_window": {
            "start_offset": "-PT3H",
            "end_offset": "PT0H",
            "boundary": "CLOSED_CLOSED",
        },
        "target_event": "SOLAR_FLARE_M1_0_PLUS",
        "event_anchor": "ONSET_TIME",
        "grading_variable": "PEAK_FLUX",
        "lead_window": {
            "start_offset": "PT3H",
            "end_offset": "PT6H",
            "boundary": "CLOSED_OPEN",
        },
        "same_unit_requirement": "SAME_ANALYSIS_UNIT_REQUIRED",
        "claim_ceiling": {
            "allowed_interpretation": "光球非势性的定量代理",
            "forbidden_claims": ["证明磁重联"],
            "source_refs": [dict(VREF)],
        },
        "content_hash": H,
    },
    "run-configuration-snapshot": {
        "configuration_id": "cfg-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "provider_bindings": {},
        "provider_versions": {},
        "prompt_versions": {},
        "calculator_registry_version": "1.0.0",
        "retry_policy": {},
        "timeout_policy": {},
        "feature_flags": {},
        "created_at": TS,
    },
    "source-asset-ref": {
        "asset_id": "asset-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "role": "S04_HISTORICAL",
        "origin_path": "02_研究流程/04_data.csv",
        "repository_relative_path": "fixtures/shrgt45/04_data.csv",
        "source_version": "V2.2",
        "source_authored_at": TS,
        "ingested_at": TS,
        "media_type": "text/csv",
        "byte_size": 1284797,
        "asset_sha256": H,
        "provenance_status": "VERIFIED",
        "usage_boundary": "DEFAULT_S04_REPLAY_INPUT",
    },
    "source-package-ref": {
        "package_id": "S04-0814",
        "schema_version": "0.1.0",
        "content_hash": H,
        "package_role": "DERIVED_RUNTIME_FIXTURE_PROJECTION",
        "origin_path": "02_研究流程/04_data_and_verification/0814",
        "repository_relative_root": "fixtures/shrgt45/s04/0814",
        "member_asset_refs": [dict(VREF)],
        "member_count": 43,
        "total_bytes": 1284797,
        "tree_hash": H,
        "tree_hash_algorithm": "SHA256",
        "identity_authority": "T003_IMPORT_AUDIT",
        "authored_package_seal_status": "PARTIAL",
        "lineage_edges": [dict(VREF)],
        "runtime_usage_boundary": "DEFAULT_S04_REPLAY_INPUT",
    },
    "replay-case-manifest": {
        "case_id": "SHRGT45-REPLAY-001",
        "manifest_version": "0.1.0",
        "schema_version": "0.1.0",
        "mode": "REPLAY",
        "research_question_ref": dict(VREF),
        "workflow_version": "0.1.0",
        "stage_asset_refs": {},
        "included_asset_refs": [dict(VREF)],
        "excluded_assets": [{"origin_path": "x", "reason": "y", "known_identity": "z"}],
        "declared_finding_specs": [
            {
                "code": "HISTORICAL_ROWS_NOT_INDEPENDENT_SAMPLES",
                "finding_kind": "COMPATIBILITY",
                "replay_policy": "MAY_ACCEPT_WITH_EXACT_HASH_REVIEW",
            }
        ],
        "workflow_graph_ref": dict(VREF),
        "stage_dependencies": {},
        "join_policy": "REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT",
        "acceptance_profile": {
            "acceptable_finding_codes": list(ACCEPTABLE_REPLAY_CODES),
            "fail_closed_finding_codes": list(FAIL_CLOSED_CODES),
            "join_condition": "REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT",
        },
        "content_hash": H,
    },
    "artifact-ref": dict(AREF),
    "artifact-envelope": _envelope(),
    "artifact-lifecycle-event": {
        "event_id": "evt-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "artifact_ref": dict(AREF),
        "from_lifecycle": "DRAFT",
        "to_lifecycle": "REVIEW_REQUIRED",
        "reason": "submitted for review",
        "actor_id": "project_owner_01",
        "created_at": TS,
    },
    "artifact-state-view": {"artifact_ref": dict(AREF), "artifact_lifecycle": "FROZEN"},
    "run-record": {
        "run_id": "run-1",
        "task_id": "task-1",
        "question_ref": dict(VREF),
        "case_ref": dict(VREF),
        "workflow_version": "0.1.0",
        "run_mode": "REPLAY",
        "run_purpose": "HISTORICAL_REPLAY",
        "configuration_ref": dict(VREF),
        "execution_status": "PENDING",
        "stage_runs": [dict(VREF)],
        "created_at": TS,
    },
    "stage-run": {
        "run_id": "run-1",
        "stage_id": "S01_CANDIDATE",
        "attempt": 1,
        "schema_version": "0.1.0",
        "content_hash": H,
        "execution_status": "SUCCEEDED",
    },
    "stage-context": {
        "run_id": "run-1",
        "stage_id": "S01_CANDIDATE",
        "attempt": 1,
        "schema_version": "0.1.0",
        "content_hash": H,
        "stage_configuration_ref": dict(VREF),
        "input_artifact_refs": [dict(AREF)],
    },
    "checkpoint-ref": {
        "checkpoint_id": "ckpt-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "run_id": "run-1",
        "artifact_refs": [dict(AREF)],
        "created_at": TS,
    },
    "failure-record": {
        "failure_id": "fail-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "run_id": "run-1",
        "stage_id": "S04_DATA_AND_VERIFICATION",
        "category": "DATA",
        "code": "SHA256_MISMATCH",
        "message": "hash mismatch",
        "retryable": False,
        "attempt": 1,
        "occurred_at": TS,
    },
    "validation-report": {
        "report_id": "vr-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "target_artifact_ref": dict(AREF),
        "validator_id": "schema-validator",
        "validator_version": "0.1.0",
        "validation_status": "PASS",
        "checks": [{"code": "SCHEMA_VALID", "severity": "INFO", "message": "ok"}],
        "created_at": TS,
    },
    "lineage-edge": {
        "edge_id": "edge-1",
        "logical_edge_id": "logical-edge-1",
        "schema_version": "0.1.0",
        "revision": 1,
        "content_hash": H,
        "upstream_artifact_ref": dict(AREF),
        "downstream_artifact_ref": {
            "artifact_id": "art-2",
            "content_sha256": H,
            "schema_version": "0.1.0",
        },
        "relation_type": "SOURCE_OF",
        "required": True,
        "verification_status": "NOT_CHECKED",
        "created_at": TS,
    },
    "compatibility-finding": {
        "finding_id": "find-1",
        "logical_finding_id": "logical-find-1",
        "schema_version": "0.1.0",
        "revision": 1,
        "content_hash": H,
        "code": "MECHANISM_V23_VS_HYPOTHESIS_V22_DEPENDENCY",
        "severity": "WARNING",
        "initial_status": "OPEN",
        "summary": "V2.3 mechanism brief vs V2.2 hypothesis dependency",
        "impact": "display-only historical seam",
        "required_action": "exact-hash review at FIXTURE_IMPORT_REVIEW",
        "created_at": TS,
    },
    "gap-finding": {
        "finding_id": "find-2",
        "logical_finding_id": "logical-find-2",
        "schema_version": "0.1.0",
        "revision": 1,
        "content_hash": H,
        "stage_id": "S01_CANDIDATE",
        "code": "CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED",
        "severity": "INFO",
        "initial_status": "OPEN",
        "summary": "candidate preselected by expert, not system-ranked",
        "impact": "no ranking module",
        "required_action": "none",
        "created_at": TS,
    },
    "finding-disposition": {
        "disposition_id": "disp-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "finding_ref": dict(FREF),
        "action": "ACCEPT_FOR_REPLAY",
        "decision_ref": dict(VREF),
        "created_at": TS,
    },
    "finding-state-view": {
        "finding_ref": dict(FREF),
        "finding_status": "OPEN",
    },
    "decision-option": {
        "option_id": "A",
        "label": "Option A",
        "description": "faithful historical replay",
        "consequences": "replay-only scope",
        "required_capability": "PROJECT_OWNER_GOVERNANCE",
    },
    "decision-request": {
        "request_id": "D-009",
        "schema_version": "0.1.0",
        "content_hash": H,
        "decision_context": "PROJECT_GOVERNANCE",
        "governance_context_ref": dict(VREF),
        "options": [
            {
                "option_id": "A",
                "label": "A",
                "description": "a",
                "consequences": "c",
                "required_capability": "PROJECT_OWNER_GOVERNANCE",
            }
        ],
        "allowed_scope": "MVP_BASELINE/D-009",
        "allowed_actor_roles": ["project_owner"],
        "requested_at": TS,
    },
    "decision-record": {
        "decision_id": "D-009-A-20260820",
        "schema_version": "0.1.0-draft",
        "content_hash": H,
        "decision_context": "PROJECT_GOVERNANCE",
        "action": "APPROVE",
        "decision_mode": "HUMAN_SELECTED",
        "selected_option_id": "A",
        "actor_id": "project_owner_01",
        "actor_role": "project_owner",
        "reason": "option A selected",
        "scope": "MVP_BASELINE/D-009",
        "created_at": TS,
    },
    "authorization-record": {
        "authorization_id": "auth-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "capability": "FORMAL_DATA_EXECUTION",
        "authorization_status": "NOT_AUTHORIZED",
        "scope": "formal-data-execution",
        "actor_id": "project_owner_01",
        "actor_role": "project_owner",
        "bound_artifact_refs": [dict(AREF)],
        "configuration_ref": dict(VREF),
        "workflow_version": "0.1.0",
        "created_at": TS,
    },
    "project-review-ack": {
        "ack_id": "ack-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "report_artifact_ref": dict(AREF),
        "decision_ref": dict(VREF),
        "status": "ACKNOWLEDGED_FOR_PROJECT_REVIEW",
        "actor_id": "project_owner_01",
        "actor_role": "project_owner",
        "created_at": TS,
    },
    "release-disposition": {
        "release_disposition_id": "rd-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "report_artifact_ref": dict(AREF),
        "release_scope": "READY_FOR_INTERNAL_DEMO",
        "decision_ref": dict(VREF),
        "actor_id": "project_owner_01",
        "actor_role": "project_owner",
        "created_at": TS,
    },
    "release-state-view": {
        "report_artifact_ref": dict(AREF),
        "release_scope": "NOT_READY",
    },
    "candidate-snapshot": {
        "snapshot_id": "snap-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "parameter": "SHRGT45",
        "selection_method": "EXPERT_SEED",
        "ranking_status": "NOT_IMPLEMENTED",
        "limitation_note": "expert preselected seed, not system ranking",
    },
    "mechanism-snapshot": {
        "snapshot_id": "snap-2",
        "schema_version": "0.1.0",
        "content_hash": H,
        "parameter": "SHRGT45",
        "source_version": "V2.3",
        "allowed_interpretation": "photospheric non-potentiality proxy",
        "forbidden_claims": ["证明磁重联"],
        "extraction_completeness": "PARTIAL",
    },
    "hypothesis-snapshot": {
        "snapshot_id": "snap-3",
        "schema_version": "0.1.0",
        "content_hash": H,
        "predictor": "SHRGT45",
        "outcome": "M1.0+ flare",
        "window": "[t+3h,t+6h)",
        "flow3_domain_status": "DRAFT",
        "machine_verifiable": False,
    },
    "verification-snapshot": {
        "snapshot_id": "snap-4",
        "schema_version": "0.1.0",
        "content_hash": H,
        "import_summary": "historical import only",
        "is_formal_execution": False,
    },
    "counterexample-snapshot": {
        "snapshot_id": "snap-5",
        "schema_version": "0.1.0",
        "content_hash": H,
        "scientific_counterexample_candidates": [],
        "data_label_issues": [],
        "not_evaluable_items": [],
        "next_steps": [],
    },
    "magnetogram-qa-snapshot": {
        "snapshot_id": "snap-6",
        "schema_version": "0.1.0",
        "content_hash": H,
        "file_checks": [],
        "frame_checks": [],
        "provenance_checks": [],
        "qa_verdict": "PASS",
        "qa_scope_note": "QA PASS 不等于机制或预测证据",
    },
    "research-summary": {
        "summary_id": "sum-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "execution_result": "import/validation/summary complete",
        "scientific_verdict": "NOT_EVALUATED",
        "result_maturity": "DEVELOPMENTAL",
        "authorization_status": "NOT_AUTHORIZED",
        "release_scope": "NOT_READY",
    },
    "report-manifest": {
        "report_manifest_id": "rm-1",
        "schema_version": "0.1.0",
        "content_hash": H,
        "research_summary_ref": dict(AREF),
        "s05_branch_ref": dict(AREF),
        "s06_branch_ref": dict(AREF),
        "join_status": "REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT",
        "created_at": TS,
    },
    "run-read-model": {
        "read_model_schema_version": "0.1.0",
        "run": dict(VREF),
        "stages": [dict(VREF)],
        "domain_snapshots": [dict(VREF)],
        "artifacts": [dict(AREF)],
        "findings": [dict(VREF)],
        "gates": [{"gate_id": "FIXTURE_IMPORT_REVIEW", "status": "BLOCKING"}],
        "lineage_summary": {"lineage_status": "NOT_CHECKED"},
    },
}


def _envelope_derived_native(origin_mode: str) -> dict[str, Any]:
    branch = _envelope()
    branch.pop("content_ref")
    branch["origin_mode"] = origin_mode
    branch["authority_mode"] = "CANONICAL_JSON"
    branch["payload"] = {}
    if origin_mode == "DERIVED":
        branch["artifact_type"] = "ExtractedDocumentSummary"
        branch["derivation_kind"] = "EXTRACTED_FROM_IMPORTED"
        branch["derived_from_refs"] = [dict(AREF)]
    else:
        branch["artifact_type"] = "CandidateSnapshot"
    return branch


def _drop(instance: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: v for k, v in instance.items() if k not in keys}


def _manifest_profile(acceptable: list[str], fail_closed: list[str]) -> dict[str, Any]:
    return {
        **VALID["replay-case-manifest"],
        "acceptance_profile": {
            "acceptable_finding_codes": acceptable,
            "fail_closed_finding_codes": fail_closed,
            "join_condition": "REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT",
        },
    }


def _manifest_spec(code: str, replay_policy: str) -> dict[str, Any]:
    return {
        **VALID["replay-case-manifest"],
        "declared_finding_specs": [
            {
                "code": code,
                "finding_kind": "COMPATIBILITY",
                "replay_policy": replay_policy,
            }
        ],
    }


def _lifecycle(from_lifecycle: str, to_lifecycle: str) -> dict[str, Any]:
    return {
        **VALID["artifact-lifecycle-event"],
        "from_lifecycle": from_lifecycle,
        "to_lifecycle": to_lifecycle,
    }


VALID_BRANCHES: dict[str, list[dict[str, Any]]] = {
    "artifact-envelope": [
        _envelope_derived_native("DERIVED"),
        _envelope_derived_native("NATIVE"),
    ],
    "artifact-lifecycle-event": [
        _lifecycle("DRAFT", "REJECTED"),
        _lifecycle("REVIEW_REQUIRED", "FROZEN"),
        _lifecycle("REVIEW_REQUIRED", "REJECTED"),
        _lifecycle("FROZEN", "SUPERSEDED"),
    ],
    "finding-disposition": [
        {
            **_drop(VALID["finding-disposition"], "decision_ref"),
            "action": "RESOLVE",
            "resolution_refs": [dict(VREF)],
        },
        {**_drop(VALID["finding-disposition"], "decision_ref"), "action": "REOPEN"},
    ],
    "decision-request": [
        {
            **_drop(VALID["decision-request"], "governance_context_ref"),
            "decision_context": "RUN_GATE",
            "gate_id": "GOV_MVP_SCOPE",
        },
    ],
    "decision-record": [
        {
            **VALID["decision-record"],
            "decision_mode": "SYSTEM_DELEGATED",
            "delegated_scope": "MVP_BASELINE/D-009",
        },
        {
            **VALID["decision-record"],
            "decision_context": "RUN_GATE",
            "decision_request_ref": dict(VREF),
            "gate_id": "GOV_MVP_SCOPE",
            "workflow_version": "0.1.0",
        },
        {**VALID["decision-record"], "action": "TERMINATE", "decision_mode": "HUMAN_SELECTED"},
    ],
    "release-disposition": [
        {
            **VALID["release-disposition"],
            "release_scope": "PUBLIC_OR_COMPETITION",
            "authorization_ref": dict(VREF),
        },
    ],
}


INVALID: list[tuple[str, dict[str, Any]]] = [
    # --- baseline structural violations -------------------------------------
    ("versioned-ref", {"id": "x", "schema_version": "0.1.0"}),
    ("versioned-ref", {**VREF, "content_hash": "not-hex"}),
    ("research-question", {
        **VALID["research-question"],
        "history_window": {
            "start_offset": "-PT3H",
            "end_offset": "PT0H",
            "boundary": "CLOSED_OPEN",
        },
    }),
    ("research-question", {**VALID["research-question"], "grading_variable": "SOMETHING_ELSE"}),
    ("artifact-envelope", {**VALID["artifact-envelope"], "origin_mode": "UNKNOWN"}),
    ("artifact-envelope", {**VALID["artifact-envelope"], "authority_mode": "UNKNOWN_AUTHORITY"}),
    ("candidate-snapshot", {**VALID["candidate-snapshot"], "selection_method": "SYSTEM_RANKED"}),
    ("candidate-snapshot", {**VALID["candidate-snapshot"], "ranking_status": "IMPLEMENTED"}),
    ("report-manifest", _drop(VALID["report-manifest"], "s06_branch_ref")),
    ("report-manifest", _drop(VALID["report-manifest"], "s05_branch_ref")),
    ("report-manifest", {**VALID["report-manifest"], "join_status": "UNKNOWN_JOIN_POLICY"}),
    ("lineage-edge", {**VALID["lineage-edge"], "relation_type": "UNKNOWN_RELATION"}),
    ("failure-record", {**VALID["failure-record"], "category": "UNKNOWN_CATEGORY"}),
    ("run-record", {**VALID["run-record"], "run_purpose": "UNKNOWN_PURPOSE"}),
    ("verification-snapshot", {**VALID["verification-snapshot"], "is_formal_execution": True}),
    ("run-read-model", _drop(VALID["run-read-model"], "lineage_summary")),
    # --- frozen-contract invariant violations ------------------------------
    # ArtifactEnvelope: illegal origin_mode/authority_mode combo
    ("artifact-envelope", {**VALID["artifact-envelope"], "authority_mode": "CANONICAL_JSON"}),
    # ArtifactEnvelope: both payload and content_ref present
    ("artifact-envelope", {**VALID["artifact-envelope"], "payload": {}}),
    # ArtifactEnvelope: neither payload nor content_ref present
    ("artifact-envelope", _drop(VALID["artifact-envelope"], "content_ref")),
    # ArtifactEnvelope: imported source bytes cannot be carried as JSON payload
    ("artifact-envelope", {
        **_drop(VALID["artifact-envelope"], "content_ref"),
        "payload": {},
    }),
    # ArtifactEnvelope: derived canonical content cannot point to source bytes
    ("artifact-envelope", {
        **VALID["artifact-envelope"],
        "origin_mode": "DERIVED",
        "authority_mode": "CANONICAL_JSON",
    }),
    # ArtifactEnvelope: a derived summary requires derivation identity and source refs
    ("artifact-envelope", _drop(_envelope_derived_native("DERIVED"), "derivation_kind")),
    ("artifact-envelope", {
        **_envelope_derived_native("DERIVED"),
        "derived_from_refs": [],
    }),
    # ArtifactLifecycleEvent: illegal transition FROZEN -> DRAFT
    ("artifact-lifecycle-event", _lifecycle("FROZEN", "DRAFT")),
    # FindingDisposition: ACCEPT_FOR_REPLAY without decision_ref
    ("finding-disposition", _drop(VALID["finding-disposition"], "decision_ref")),
    # FindingDisposition: RESOLVE without resolution_refs
    ("finding-disposition", {
        **_drop(VALID["finding-disposition"], "decision_ref"),
        "action": "RESOLVE",
    }),
    # FindingDisposition: fail-closed code can never be ACCEPT_FOR_REPLAY in manifest
    ("replay-case-manifest", {
        **VALID["replay-case-manifest"],
        "declared_finding_specs": [
            {
                "code": "SHA256_MISMATCH",
                "finding_kind": "COMPATIBILITY",
                "replay_policy": "MAY_ACCEPT_WITH_EXACT_HASH_REVIEW",
            }
        ],
    }),
    # D-008 acceptance profile must be the complete, unique frozen classification
    ("replay-case-manifest", _manifest_profile([], [])),
    ("replay-case-manifest", _manifest_profile(
        ACCEPTABLE_REPLAY_CODES[:-1],
        list(FAIL_CLOSED_CODES),
    )),
    ("replay-case-manifest", _manifest_profile(
        [*ACCEPTABLE_REPLAY_CODES[:-1], ACCEPTABLE_REPLAY_CODES[0]],
        list(FAIL_CLOSED_CODES),
    )),
    ("replay-case-manifest", _manifest_profile(
        [*ACCEPTABLE_REPLAY_CODES[:-1], "BRAND_NEW_UNKNOWN_CODE"],
        list(FAIL_CLOSED_CODES),
    )),
    ("replay-case-manifest", _manifest_profile(
        [*ACCEPTABLE_REPLAY_CODES[:-1], "SHA256_MISMATCH"],
        list(FAIL_CLOSED_CODES),
    )),
    # Unknown Finding codes cannot enter the human-acceptable replay route
    ("replay-case-manifest", _manifest_spec(
        "BRAND_NEW_UNKNOWN_CODE",
        "MAY_ACCEPT_WITH_EXACT_HASH_REVIEW",
    )),
    # DecisionRequest: PROJECT_GOVERNANCE without governance_context_ref
    ("decision-request", _drop(VALID["decision-request"], "governance_context_ref")),
    # DecisionRecord: TERMINATE with SYSTEM_DELEGATED
    ("decision-record", {
        **VALID["decision-record"],
        "action": "TERMINATE",
        "decision_mode": "SYSTEM_DELEGATED",
        "delegated_scope": "x",
    }),
    # DecisionRecord: SYSTEM_DELEGATED without delegated_scope
    ("decision-record", {**VALID["decision-record"], "decision_mode": "SYSTEM_DELEGATED"}),
    # DecisionRecord: RUN_GATE requires request, gate, and workflow identity
    ("decision-record", {
        **VALID["decision-record"],
        "decision_context": "RUN_GATE",
        "decision_request_ref": dict(VREF),
        "gate_id": "g",
    }),
    ("decision-record", {
        **VALID["decision-record"],
        "decision_context": "RUN_GATE",
        "gate_id": "g",
        "workflow_version": "0.1.0",
    }),
    ("decision-record", {
        **VALID["decision-record"],
        "decision_context": "RUN_GATE",
        "decision_request_ref": dict(VREF),
        "workflow_version": "0.1.0",
    }),
    # AuthorizationRecord: empty bound_artifact_refs
    ("authorization-record", {**VALID["authorization-record"], "bound_artifact_refs": []}),
    # AuthorizationRecord: missing configuration_ref
    ("authorization-record", _drop(VALID["authorization-record"], "configuration_ref")),
    # ReleaseDisposition: PUBLIC_OR_COMPETITION without authorization_ref
    ("release-disposition", {
        **VALID["release-disposition"],
        "release_scope": "PUBLIC_OR_COMPETITION",
    }),
    # Every ReleaseDisposition is an independent, decision-bound record
    ("release-disposition", _drop(VALID["release-disposition"], "decision_ref")),
    # ReleaseDisposition: NOT_READY is not a legal disposition scope
    ("release-disposition", {**VALID["release-disposition"], "release_scope": "NOT_READY"}),
    # ResearchSummary: scientific_verdict must stay NOT_EVALUATED in Replay
    ("research-summary", {**VALID["research-summary"], "scientific_verdict": "SUPPORTED"}),
    ("research-summary", {**VALID["research-summary"], "result_maturity": "CONFIRMATORY"}),
    ("research-summary", {**VALID["research-summary"], "authorization_status": "AUTHORIZED"}),
    ("research-summary", {**VALID["research-summary"], "release_scope": "READY_FOR_INTERNAL_DEMO"}),
]
