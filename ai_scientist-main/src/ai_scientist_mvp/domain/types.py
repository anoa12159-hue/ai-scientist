"""Python types mirroring the frozen contract's JSON Schema 2020-12 set.

These TypedDicts are the field-shape surface for the versioned objects in
``contracts/``. They are *not* the semantic source of truth: JSON Schema is.
The CI consistency test recursively checks fields, required sets, arrays,
references, constants, and enums. Cross-field conditionals such as authority
combinations remain Schema-only runtime invariants and have dedicated fixtures;
the broad envelope TypedDict must not be treated as proof of a valid instance.

Shared enumerations and reference shapes are kept here as ``Literal`` aliases
and typed refs so the important semantic boundaries are type-checkable.
"""
from typing import Any, Literal, NotRequired, Required, TypeAlias, TypedDict

Sha256: TypeAlias = str
SemVer: TypeAlias = str
Timestamp: TypeAlias = str

# --- orthogonal state enums (CONTRACTS.md 7) ---------------------------------
RunMode = Literal["REPLAY", "LIVE"]
RunPurpose = Literal["HISTORICAL_REPLAY", "ACTIVE_RESEARCH"]
ExecutionStatus = Literal[
    "PENDING", "RUNNING", "WAITING_HUMAN", "SUCCEEDED", "FAILED", "CANCELLED", "SKIPPED"
]
ValidationStatus = Literal["NOT_RUN", "PASS", "PASS_WITH_WARNINGS", "FAIL"]
OriginMode = Literal["IMPORTED", "DERIVED", "NATIVE"]
AuthorityMode = Literal["SOURCE_BYTES", "CANONICAL_JSON"]
ArtifactLifecycle = Literal["DRAFT", "REVIEW_REQUIRED", "FROZEN", "SUPERSEDED", "REJECTED"]
AuthorizationStatus = Literal["NOT_AUTHORIZED", "AUTHORIZED", "REVOKED", "EXPIRED"]
ScientificVerdict = Literal[
    "NOT_EVALUATED", "SUPPORTED", "CONDITIONALLY_SUPPORTED",
    "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE",
]
LineageStatus = Literal["NOT_CHECKED", "VERIFIED", "PARTIAL", "CONFLICT"]
ResultMaturity = Literal["DEVELOPMENTAL", "CONFIRMATORY"]
ReleaseScope = Literal["NOT_READY", "READY_FOR_INTERNAL_DEMO", "PUBLIC_OR_COMPETITION"]
FindingSeverity = Literal["INFO", "WARNING", "ERROR"]
FailureCategory = Literal[
    "DATA", "NETWORK", "VALIDATION", "PROGRAM", "QUALITY", "LINEAGE", "AUTHORIZATION"
]
AcceptableReplayFindingCode = Literal[
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
FailClosedFindingCode = Literal[
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

# --- Foundation ---------------------------------------------------------------

class VersionedRef(TypedDict):
    id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]


class HistoryWindow(TypedDict):
    start_offset: Required[Literal["-PT3H"]]
    end_offset: Required[Literal["PT0H"]]
    boundary: Required[Literal["CLOSED_CLOSED"]]


class LeadWindow(TypedDict):
    start_offset: Required[Literal["PT3H"]]
    end_offset: Required[Literal["PT6H"]]
    boundary: Required[Literal["CLOSED_OPEN"]]


class ClaimCeiling(TypedDict):
    allowed_interpretation: Required[str]
    forbidden_claims: Required[list[str]]
    source_refs: Required[list[VersionedRef]]


class ResearchQuestionSnapshot(TypedDict):
    question_id: Required[str]
    question_version: Required[SemVer]
    schema_version: Required[SemVer]
    parameter: Required[str]
    scientific_question: Required[str]
    history_window: Required[HistoryWindow]
    target_event: Required[str]
    event_anchor: Required[Literal["ONSET_TIME"]]
    grading_variable: Required[Literal["PEAK_FLUX"]]
    lead_window: Required[LeadWindow]
    same_unit_requirement: Required[Literal["SAME_ANALYSIS_UNIT_REQUIRED"]]
    claim_ceiling: Required[ClaimCeiling]
    supersedes_ref: NotRequired[VersionedRef]
    content_hash: Required[Sha256]


class RunConfigurationSnapshot(TypedDict):
    configuration_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    provider_bindings: Required[dict[str, Any]]
    provider_versions: Required[dict[str, Any]]
    prompt_versions: Required[dict[str, Any]]
    calculator_registry_version: Required[str]
    retry_policy: Required[dict[str, Any]]
    timeout_policy: Required[dict[str, Any]]
    feature_flags: Required[dict[str, Any]]
    created_at: Required[Timestamp]


class SourceAssetRef(TypedDict):
    asset_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    role: Required[str]
    origin_path: Required[str]
    repository_relative_path: Required[str]
    source_version: Required[str]
    source_authored_at: Required[Timestamp]
    ingested_at: Required[Timestamp]
    media_type: Required[str]
    byte_size: Required[int]
    asset_sha256: Required[Sha256]
    provenance_status: Required[str]
    usage_boundary: Required[str]


class SourcePackageRef(TypedDict):
    package_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    package_role: Required[str]
    origin_path: Required[str]
    repository_relative_root: Required[str]
    member_asset_refs: Required[list[VersionedRef]]
    member_count: Required[int]
    total_bytes: Required[int]
    tree_hash: Required[Sha256]
    tree_hash_algorithm: Required[str]
    identity_authority: Required[str]
    authored_package_seal_status: Required[str]
    lineage_edges: Required[list[VersionedRef]]
    runtime_usage_boundary: Required[str]


class ExcludedAsset(TypedDict):
    origin_path: Required[str]
    reason: Required[str]
    known_identity: Required[str]


class DeclaredFindingSpec(TypedDict):
    code: Required[str]
    finding_kind: Required[Literal["COMPATIBILITY", "GAP"]]
    related_stage_ids: NotRequired[list[str]]
    related_asset_roles: NotRequired[list[str]]
    required: NotRequired[bool]
    expected_severity: NotRequired[FindingSeverity]
    replay_policy: Required[Literal["MAY_ACCEPT_WITH_EXACT_HASH_REVIEW", "FAIL_CLOSED"]]
    rationale_source_refs: NotRequired[list[VersionedRef]]


class AcceptanceProfile(TypedDict):
    acceptable_finding_codes: Required[list[AcceptableReplayFindingCode]]
    fail_closed_finding_codes: Required[list[FailClosedFindingCode]]
    join_condition: Required[Literal["REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT"]]


class ReplayCaseManifest(TypedDict):
    case_id: Required[str]
    manifest_version: Required[SemVer]
    schema_version: Required[SemVer]
    mode: Required[Literal["REPLAY"]]
    research_question_ref: Required[VersionedRef]
    workflow_version: Required[str]
    stage_asset_refs: Required[dict[str, Any]]
    included_asset_refs: Required[list[VersionedRef]]
    excluded_assets: Required[list[ExcludedAsset]]
    declared_finding_specs: Required[list[DeclaredFindingSpec]]
    workflow_graph_ref: Required[VersionedRef]
    stage_dependencies: Required[dict[str, Any]]
    join_policy: Required[Literal["REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT"]]
    acceptance_profile: Required[AcceptanceProfile]
    content_hash: Required[Sha256]


# --- Artifact and Runtime -----------------------------------------------------

class ArtifactRef(TypedDict):
    artifact_id: Required[str]
    content_sha256: Required[Sha256]
    schema_version: Required[SemVer]


class Producer(TypedDict):
    id: Required[str]
    version: Required[str]


class ArtifactEnvelope(TypedDict):
    artifact_id: Required[str]
    logical_artifact_id: Required[str]
    artifact_type: Required[str]
    schema_version: Required[SemVer]
    artifact_revision: Required[int]
    task_id: Required[str]
    run_id: Required[str]
    run_mode: Required[RunMode]
    origin_mode: Required[OriginMode]
    authority_mode: Required[AuthorityMode]
    derivation_kind: NotRequired[str]
    derived_from_refs: NotRequired[list[ArtifactRef]]
    payload: NotRequired[dict[str, Any]]
    content_ref: NotRequired[str]
    content_sha256: Required[Sha256]
    parent_refs: NotRequired[list[ArtifactRef]]
    source_asset_refs: NotRequired[list[VersionedRef]]
    producer: Required[Producer]
    source_authored_at: NotRequired[Timestamp]
    ingested_at: NotRequired[Timestamp]
    created_at: Required[Timestamp]
    domain_status: NotRequired[dict[str, Any]]
    supersedes_ref: NotRequired[ArtifactRef]


class ArtifactLifecycleEvent(TypedDict):
    event_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    artifact_ref: Required[ArtifactRef]
    from_lifecycle: Required[ArtifactLifecycle]
    to_lifecycle: Required[ArtifactLifecycle]
    decision_ref: NotRequired[VersionedRef]
    reason: Required[str]
    actor_id: Required[str]
    created_at: Required[Timestamp]


class ArtifactStateView(TypedDict):
    artifact_ref: Required[ArtifactRef]
    artifact_lifecycle: Required[ArtifactLifecycle]
    validation_report_refs: NotRequired[list[VersionedRef]]


class RunRecord(TypedDict):
    run_id: Required[str]
    task_id: Required[str]
    question_ref: Required[VersionedRef]
    case_ref: Required[VersionedRef]
    workflow_version: Required[str]
    run_mode: Required[RunMode]
    run_purpose: Required[RunPurpose]
    configuration_ref: Required[VersionedRef]
    execution_status: Required[ExecutionStatus]
    active_stage_ids: NotRequired[list[str]]
    stage_runs: Required[list[VersionedRef]]
    created_at: Required[Timestamp]
    started_at: NotRequired[Timestamp]
    completed_at: NotRequired[Timestamp]
    checkpoint_ref: NotRequired[VersionedRef]


class StageRun(TypedDict):
    run_id: Required[str]
    stage_id: Required[str]
    attempt: Required[int]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    input_artifact_refs: NotRequired[list[ArtifactRef]]
    output_artifact_refs: NotRequired[list[ArtifactRef]]
    validation_report_refs: NotRequired[list[VersionedRef]]
    finding_refs: NotRequired[list[VersionedRef]]
    lineage_edge_refs: NotRequired[list[VersionedRef]]
    provider: NotRequired[Producer]
    stage_configuration_ref: NotRequired[VersionedRef]
    execution_status: Required[ExecutionStatus]
    started_at: NotRequired[Timestamp]
    completed_at: NotRequired[Timestamp]
    failure_refs: NotRequired[list[VersionedRef]]


class StageContext(TypedDict):
    run_id: Required[str]
    stage_id: Required[str]
    attempt: Required[int]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    stage_configuration_ref: Required[VersionedRef]
    input_artifact_refs: Required[list[ArtifactRef]]


class CheckpointRef(TypedDict):
    checkpoint_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    run_id: Required[str]
    stage_ids: NotRequired[list[str]]
    artifact_refs: Required[list[ArtifactRef]]
    created_at: Required[Timestamp]


class FailureRecord(TypedDict):
    failure_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    run_id: Required[str]
    stage_id: Required[str]
    category: Required[FailureCategory]
    code: Required[str]
    message: Required[str]
    retryable: Required[bool]
    attempt: Required[int]
    input_artifact_refs: NotRequired[list[ArtifactRef]]
    occurred_at: Required[Timestamp]


# --- Validation, Lineage, Findings -------------------------------------------

class ValidationCheck(TypedDict):
    code: Required[str]
    severity: Required[FindingSeverity]
    message: Required[str]
    path: NotRequired[str]


class ValidationReport(TypedDict):
    report_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    target_artifact_ref: Required[ArtifactRef]
    validator_id: Required[str]
    validator_version: Required[str]
    validation_status: Required[ValidationStatus]
    checks: Required[list[ValidationCheck]]
    created_at: Required[Timestamp]


class LineageEdge(TypedDict):
    edge_id: Required[str]
    logical_edge_id: Required[str]
    schema_version: Required[SemVer]
    revision: Required[int]
    content_hash: Required[Sha256]
    upstream_artifact_ref: Required[ArtifactRef]
    downstream_artifact_ref: Required[ArtifactRef]
    relation_type: Required[
        Literal["SOURCE_OF", "DERIVED_FROM", "TRANSFORMED_FROM", "SUMMARIZES", "VALIDATES"]
    ]
    required: Required[bool]
    verification_status: Required[Literal["NOT_CHECKED", "VERIFIED", "PARTIAL", "CONFLICT"]]
    evidence_refs: NotRequired[list[VersionedRef]]
    finding_refs: NotRequired[list[VersionedRef]]
    supersedes_ref: NotRequired[VersionedRef]
    created_at: Required[Timestamp]


class CompatibilityFinding(TypedDict):
    finding_id: Required[str]
    logical_finding_id: Required[str]
    schema_version: Required[SemVer]
    revision: Required[int]
    content_hash: Required[Sha256]
    upstream_artifact_ref: NotRequired[ArtifactRef]
    downstream_artifact_ref: NotRequired[ArtifactRef]
    code: Required[str]
    severity: Required[FindingSeverity]
    initial_status: Required[Literal["OPEN"]]
    summary: Required[str]
    evidence_refs: NotRequired[list[VersionedRef]]
    impact: Required[str]
    required_action: Required[str]
    supersedes_ref: NotRequired[VersionedRef]
    created_at: Required[Timestamp]


class GapFinding(TypedDict):
    finding_id: Required[str]
    logical_finding_id: Required[str]
    schema_version: Required[SemVer]
    revision: Required[int]
    content_hash: Required[Sha256]
    stage_id: Required[str]
    code: Required[str]
    severity: Required[FindingSeverity]
    initial_status: Required[Literal["OPEN"]]
    summary: Required[str]
    evidence_refs: NotRequired[list[VersionedRef]]
    impact: Required[str]
    required_action: Required[str]
    supersedes_ref: NotRequired[VersionedRef]
    created_at: Required[Timestamp]


class FindingRef(TypedDict):
    finding_id: Required[str]
    content_hash: Required[Sha256]
    schema_version: Required[SemVer]


class FindingDisposition(TypedDict):
    disposition_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    finding_ref: Required[FindingRef]
    action: Required[Literal["ACCEPT_FOR_REPLAY", "RESOLVE", "REOPEN"]]
    decision_ref: NotRequired[VersionedRef]
    resolution_refs: NotRequired[list[VersionedRef]]
    created_at: Required[Timestamp]


class FindingStateView(TypedDict):
    finding_ref: Required[FindingRef]
    finding_status: Required[Literal["OPEN", "ACCEPTED_FOR_REPLAY", "RESOLVED"]]


# --- Governance and Release ---------------------------------------------------

class DecisionOption(TypedDict):
    option_id: Required[str]
    label: Required[str]
    description: Required[str]
    consequences: Required[str]
    required_capability: Required[str]


class DecisionRequest(TypedDict):
    request_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    decision_context: Required[Literal["PROJECT_GOVERNANCE", "RUN_GATE"]]
    governance_context_ref: NotRequired[VersionedRef]
    gate_id: NotRequired[str]
    prompt: NotRequired[str]
    context_artifact_refs: NotRequired[list[ArtifactRef]]
    context_finding_refs: NotRequired[list[VersionedRef]]
    context_stage_attempt_keys: NotRequired[list[dict[str, Any]]]
    options: Required[list[DecisionOption]]
    recommended_option_id: NotRequired[str]
    recommendation_reason: NotRequired[str]
    risk_summary: NotRequired[str]
    impact_summary: NotRequired[str]
    allowed_scope: Required[str]
    allowed_actor_roles: Required[list[str]]
    requested_at: Required[Timestamp]
    expires_at: NotRequired[Timestamp]


class DecisionRecord(TypedDict):
    decision_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    decision_context: Required[Literal["PROJECT_GOVERNANCE", "RUN_GATE"]]
    governance_context_ref: NotRequired[VersionedRef]
    decision_request_ref: NotRequired[VersionedRef]
    gate_id: NotRequired[str]
    action: Required[Literal["APPROVE", "REVISE", "REJECT", "TERMINATE"]]
    decision_mode: Required[Literal["HUMAN_SELECTED", "SYSTEM_DELEGATED"]]
    selected_option_id: Required[str]
    actor_id: Required[str]
    actor_role: Required[str]
    reason: Required[str]
    scope: Required[str]
    bound_artifact_refs: NotRequired[list[ArtifactRef]]
    bound_finding_refs: NotRequired[list[VersionedRef]]
    bound_stage_attempt_keys: NotRequired[list[dict[str, Any]]]
    delegated_scope: NotRequired[str]
    workflow_version: NotRequired[str]
    created_at: Required[Timestamp]
    supersedes_ref: NotRequired[VersionedRef]


class AuthorizationRecord(TypedDict):
    authorization_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    capability: Required[Literal["FORMAL_DATA_EXECUTION", "PUBLIC_OR_COMPETITION_RELEASE"]]
    authorization_status: Required[AuthorizationStatus]
    scope: Required[str]
    actor_id: Required[str]
    actor_role: Required[str]
    bound_artifact_refs: Required[list[ArtifactRef]]
    configuration_ref: Required[VersionedRef]
    workflow_version: Required[str]
    created_at: Required[Timestamp]
    expires_at: NotRequired[Timestamp]
    supersedes_ref: NotRequired[VersionedRef]


class ProjectReviewAck(TypedDict):
    ack_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    report_artifact_ref: Required[ArtifactRef]
    decision_ref: Required[VersionedRef]
    status: Required[Literal["ACKNOWLEDGED_FOR_PROJECT_REVIEW"]]
    actor_id: Required[str]
    actor_role: Required[str]
    created_at: Required[Timestamp]


class ReleaseDisposition(TypedDict):
    release_disposition_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    report_artifact_ref: Required[ArtifactRef]
    release_scope: Required[Literal["READY_FOR_INTERNAL_DEMO", "PUBLIC_OR_COMPETITION"]]
    decision_ref: Required[VersionedRef]
    authorization_ref: NotRequired[VersionedRef]
    actor_id: Required[str]
    actor_role: Required[str]
    created_at: Required[Timestamp]
    supersedes_ref: NotRequired[VersionedRef]


class ReleaseStateView(TypedDict):
    report_artifact_ref: Required[ArtifactRef]
    release_scope: Required[ReleaseScope]


# --- Domain and Query projections --------------------------------------------

class CandidateSnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    parameter: Required[str]
    selection_method: Required[Literal["EXPERT_SEED"]]
    ranking_status: Required[Literal["NOT_IMPLEMENTED"]]
    source_refs: NotRequired[list[VersionedRef]]
    limitation_note: Required[str]


class MechanismSnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    parameter: Required[str]
    source_version: Required[str]
    allowed_interpretation: Required[str]
    forbidden_claims: Required[list[str]]
    source_refs: NotRequired[list[VersionedRef]]
    extraction_completeness: Required[str]


class HypothesisSnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    upstream_mechanism_ref: NotRequired[VersionedRef]
    predictor: Required[str]
    outcome: Required[str]
    window: Required[str]
    flow3_domain_status: Required[str]
    machine_verifiable: Required[bool]


class VerificationSnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    import_summary: Required[str]
    is_formal_execution: Required[Literal[False]]
    source_refs: NotRequired[list[VersionedRef]]
    finding_refs: NotRequired[list[VersionedRef]]


class CounterexampleSnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    scientific_counterexample_candidates: Required[list[str]]
    data_label_issues: Required[list[str]]
    not_evaluable_items: Required[list[str]]
    next_steps: Required[list[str]]


class MagnetogramQASnapshot(TypedDict):
    snapshot_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    file_checks: Required[list[str]]
    frame_checks: Required[list[str]]
    provenance_checks: Required[list[str]]
    qa_verdict: Required[str]
    qa_scope_note: Required[str]


class ResearchSummary(TypedDict):
    summary_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    execution_result: Required[str]
    validation_status: NotRequired[ValidationStatus]
    lineage_status: NotRequired[LineageStatus]
    scientific_verdict: Required[Literal["NOT_EVALUATED"]]
    result_maturity: Required[Literal["DEVELOPMENTAL"]]
    authorization_status: Required[Literal["NOT_AUTHORIZED"]]
    release_scope: Required[Literal["NOT_READY"]]
    finding_refs: NotRequired[list[VersionedRef]]


class ReportManifest(TypedDict):
    report_manifest_id: Required[str]
    schema_version: Required[SemVer]
    content_hash: Required[Sha256]
    research_summary_ref: Required[ArtifactRef]
    s05_branch_ref: Required[ArtifactRef]
    s06_branch_ref: Required[ArtifactRef]
    included_artifact_refs: NotRequired[list[ArtifactRef]]
    finding_refs: NotRequired[list[VersionedRef]]
    join_status: Required[Literal["REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT"]]
    created_at: Required[Timestamp]


class GateEntry(TypedDict):
    gate_id: Required[str]
    status: Required[str]


class LineageSummary(TypedDict):
    lineage_status: Required[LineageStatus]


class RunReadModel(TypedDict):
    read_model_schema_version: Required[SemVer]
    run: Required[VersionedRef]
    stages: Required[list[VersionedRef]]
    domain_snapshots: Required[list[VersionedRef]]
    artifacts: Required[list[ArtifactRef]]
    findings: Required[list[VersionedRef]]
    gates: Required[list[GateEntry]]
    lineage_summary: Required[LineageSummary]
    report: NotRequired[VersionedRef]


# Map of schema base name -> TypedDict, consumed by the consistency test.
SCHEMA_TYPE_MAP: dict[str, type] = {
    "versioned-ref": VersionedRef,
    "research-question": ResearchQuestionSnapshot,
    "run-configuration-snapshot": RunConfigurationSnapshot,
    "source-asset-ref": SourceAssetRef,
    "source-package-ref": SourcePackageRef,
    "replay-case-manifest": ReplayCaseManifest,
    "artifact-ref": ArtifactRef,
    "artifact-envelope": ArtifactEnvelope,
    "artifact-lifecycle-event": ArtifactLifecycleEvent,
    "artifact-state-view": ArtifactStateView,
    "run-record": RunRecord,
    "stage-run": StageRun,
    "stage-context": StageContext,
    "checkpoint-ref": CheckpointRef,
    "failure-record": FailureRecord,
    "validation-report": ValidationReport,
    "lineage-edge": LineageEdge,
    "compatibility-finding": CompatibilityFinding,
    "gap-finding": GapFinding,
    "finding-disposition": FindingDisposition,
    "finding-state-view": FindingStateView,
    "decision-option": DecisionOption,
    "decision-request": DecisionRequest,
    "decision-record": DecisionRecord,
    "authorization-record": AuthorizationRecord,
    "project-review-ack": ProjectReviewAck,
    "release-disposition": ReleaseDisposition,
    "release-state-view": ReleaseStateView,
    "candidate-snapshot": CandidateSnapshot,
    "mechanism-snapshot": MechanismSnapshot,
    "hypothesis-snapshot": HypothesisSnapshot,
    "verification-snapshot": VerificationSnapshot,
    "counterexample-snapshot": CounterexampleSnapshot,
    "magnetogram-qa-snapshot": MagnetogramQASnapshot,
    "research-summary": ResearchSummary,
    "report-manifest": ReportManifest,
    "run-read-model": RunReadModel,
}
