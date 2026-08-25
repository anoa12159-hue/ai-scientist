"""Internal active-research DTOs and projections to frozen public contracts."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.types import (
    ArtifactRef,
    CounterexampleSnapshot,
    HypothesisSnapshot,
    ValidationCheck,
    ValidationReport,
    VersionedRef,
)

_HYPOTHESIS_SCHEMA_VERSION = "2.1.0"
_PUBLIC_SCHEMA_VERSION = "0.1.0"
_PACKAGE_STATES = {
    "DRAFT",
    "READY_FOR_DATAPLAN",
    "NEEDS_CLARIFICATION",
    "PROJECT_CONFLICT",
}
_DECISION_IDS = {
    "PREDICTOR_QUANTIFICATION",
    "PREDICTION_OCCASION",
    "ENDPOINT_AND_COMPARISON",
    "QUALITY_NA_AUDIT",
    "SENSITIVITY_AUXILIARY",
    "CONCLUSION_FIVE_STATE",
}
_FIVE_STATES = {
    "SUPPORTED",
    "CONDITIONALLY_SUPPORTED",
    "NOT_SUPPORTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
}
_HANDOFF_LAYERS = {
    "identity_scientific_constraints",
    "measurement_data_inputs",
    "predictor_layer",
    "target_layer",
    "cohort_research_design",
    "estimator_layer",
    "output_fields",
    "provenance_exceptions_freeze",
}
_OUTPUT_GROUPS = {
    "row_identity_scope",
    "measurement_background_audit",
    "predictor_outputs",
    "eligibility_queue_target_labels",
    "target_event_fields",
}
_PROVENANCE_GROUPS = {
    "parameter_physics",
    "predictor_methods",
    "temporal_or_design_side_support",
    "unverified_project_prior",
    "research_design_boundaries",
}
_EXCEPTION_RETURNS = {
    "NEEDS_CLARIFICATION",
    "DATA_UNAVAILABLE",
    "INSUFFICIENT_SAMPLES",
}
_SOURCE_LABELS = {"[齐]", "[项目]", "[曾增]", "[待确认]"}
_STATUS_SENTENCES = {
    "DRAFT": "当前全信息基准提案，等待团队冻结。",
    "READY_FOR_DATAPLAN": "已冻结并可移交 DataPlan。",
    "NEEDS_CLARIFICATION": "当前存在关键待确认项，不得执行或移交 DataPlan。",
    "PROJECT_CONFLICT": "MechanismBrief 与项目固定口径冲突，等待项目裁决。",
}
_FIXED_VALUES = {
    "target_event": "M1.0及以上耀斑",
    "primary_target_id": "future_3_6h_same_unit_Mplus",
    "event_anchor": "GOES SXR onset用于事件落窗",
    "grading_variable": "GOES peak flux用于M+定级",
    "lead_window": "[t+3h,t+6h)",
    "primary_queue": "OPERATIONAL_ROLLING",
    "diagnostic_queue": "DIAGNOSTIC_MATCHED",
}


class ResearchContractError(ValueError):
    """An internal DTO violates its frozen source or public projection boundary."""


@dataclass(frozen=True)
class HypothesisContractV21:
    schema_version: str
    identity: Mapping[str, Any]
    estimand: Mapping[str, Any]
    measurement: Mapping[str, Any]
    predictor: Mapping[str, Any]
    target: Mapping[str, Any]
    cohort: Mapping[str, Any]
    estimator_boundary: Mapping[str, Any]
    interpretation: Mapping[str, Any]
    operationalization_decisions: tuple[Mapping[str, Any], ...]
    dataplan_handoff: Mapping[str, Any]
    source_ledger: Mapping[str, Any]
    pending_items: tuple[Any, ...]

    @property
    def hypothesis_id(self) -> str:
        return cast(str, self.identity["hypothesis_id"])

    @property
    def parameter(self) -> str:
        return cast(str, self.identity["candidate_parameter"])

    @property
    def status(self) -> str:
        return cast(str, self.identity["status"])


@dataclass(frozen=True)
class DataPlan:
    contract_version: str
    hypothesis_id: str
    identity_scientific_constraints: Mapping[str, Any]
    measurement_data_inputs: Mapping[str, Any]
    predictor_layer: Mapping[str, Any]
    target_layer: Mapping[str, Any]
    cohort_research_design: Mapping[str, Any]
    estimator_layer: Mapping[str, Any]
    output_fields: Mapping[str, Any]
    provenance_exceptions_freeze: Mapping[str, Any]


@dataclass(frozen=True)
class CounterexampleReport:
    report_version: str
    review_unit: str
    scientific_verdict: str
    result_maturity: str
    confirmed_scientific_counterexample_count: int
    scientific_counterexample_candidates: tuple[str, ...]
    data_label_issues: tuple[str, ...]
    sample_statistical_issues: tuple[str, ...]
    research_definition_issues: tuple[str, ...]
    not_evaluable_items: tuple[str, ...]
    next_steps: tuple[str, ...]


def parse_hypothesis_contract(document: Mapping[str, Any]) -> HypothesisContractV21:
    """Validate and copy the transfer project's V2.1 hypothesis DTO."""
    if document.get("schema_version") != _HYPOTHESIS_SCHEMA_VERSION:
        raise ResearchContractError("expected Hypothesis contract schema_version 2.1.0")

    identity = _required_mapping(document, "identity")
    estimand = _required_mapping(document, "estimand")
    measurement = _required_mapping(document, "measurement")
    predictor = _required_mapping(document, "predictor")
    target = _required_mapping(document, "target")
    cohort = _required_mapping(document, "cohort")
    estimator_boundary = _required_mapping(document, "estimator_boundary")
    interpretation = _required_mapping(document, "interpretation")
    dataplan_handoff = _required_mapping(document, "dataplan_handoff")
    source_ledger = _required_mapping(document, "source_ledger")
    pending_items = _required_sequence(document, "pending_items")
    decisions = _mapping_sequence(document.get("operationalization_decisions"), "decisions")

    _validate_identity(identity)
    _validate_required_fields(estimand, {
        "sentence", "population", "analysis_unit", "primary_predictor", "history_window",
        "target", "lead_window", "expected_direction", "primary_queue",
    }, "estimand")
    _validate_required_fields(measurement, {
        "definition_unit_observation_level", "directly_measures", "does_not_measure",
        "qi_evidence_ids", "required_raw_fields", "audit_fields",
    }, "measurement")
    _validate_required_fields(predictor, {
        "name", "transformation", "formula", "unit", "history_window", "timestamp_rule",
        "quality_completeness_rule", "missing_rule",
    }, "predictor")
    _validate_required_fields(target, {
        "event", "primary_target_id", "event_anchor", "grading_variable", "lead_window",
        "same_unit_rule", "early_window", "endpoint_policy",
    }, "target")
    _validate_required_fields(cohort, {
        "prediction_occasion", "population", "independence_boundary", "applicability_scope",
        "common_eligibility", "primary_queue", "diagnostic_queue", "queue_specific_rules",
    }, "cohort")
    _validate_hypothesis_consistency(
        identity, estimand, predictor, target, cohort, estimator_boundary, interpretation
    )
    _validate_decisions(decisions, cast(str, identity["status"]))
    _validate_dataplan_handoff(dataplan_handoff, identity, estimand, predictor, target)
    _validate_source_ledger(source_ledger, pending_items)

    return HypothesisContractV21(
        schema_version=_HYPOTHESIS_SCHEMA_VERSION,
        identity=deepcopy(identity),
        estimand=deepcopy(estimand),
        measurement=deepcopy(measurement),
        predictor=deepcopy(predictor),
        target=deepcopy(target),
        cohort=deepcopy(cohort),
        estimator_boundary=deepcopy(estimator_boundary),
        interpretation=deepcopy(interpretation),
        operationalization_decisions=tuple(deepcopy(decision) for decision in decisions),
        dataplan_handoff=deepcopy(dataplan_handoff),
        source_ledger=deepcopy(source_ledger),
        pending_items=tuple(deepcopy(pending_items)),
    )


def extract_data_plan(hypothesis: HypothesisContractV21) -> DataPlan:
    """Extract the eight-layer DataPlan handoff without adding scientific claims."""
    handoff = hypothesis.dataplan_handoff
    return DataPlan(
        contract_version="hypothesis-dataplan-handoff/2.1.0",
        hypothesis_id=hypothesis.hypothesis_id,
        identity_scientific_constraints=deepcopy(
            _required_mapping(handoff, "identity_scientific_constraints")
        ),
        measurement_data_inputs=deepcopy(_required_mapping(handoff, "measurement_data_inputs")),
        predictor_layer=deepcopy(_required_mapping(handoff, "predictor_layer")),
        target_layer=deepcopy(_required_mapping(handoff, "target_layer")),
        cohort_research_design=deepcopy(_required_mapping(handoff, "cohort_research_design")),
        estimator_layer=deepcopy(_required_mapping(handoff, "estimator_layer")),
        output_fields=deepcopy(_required_mapping(handoff, "output_fields")),
        provenance_exceptions_freeze=deepcopy(
            _required_mapping(handoff, "provenance_exceptions_freeze")
        ),
    )


def project_hypothesis_snapshot(
    hypothesis: HypothesisContractV21,
    *,
    snapshot_id: str,
    upstream_mechanism_ref: VersionedRef,
) -> HypothesisSnapshot:
    """Project the full internal DTO to the frozen minimum public summary."""
    _validate_snapshot_id(snapshot_id)
    _validate_versioned_ref(upstream_mechanism_ref)
    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "schema_version": _PUBLIC_SCHEMA_VERSION,
        "upstream_mechanism_ref": dict(upstream_mechanism_ref),
        "predictor": hypothesis.predictor["name"],
        "outcome": hypothesis.target["event"],
        "window": (
            f"{hypothesis.predictor['history_window']} -> {hypothesis.target['lead_window']}"
        ),
        "flow3_domain_status": hypothesis.status,
        "machine_verifiable": True,
    }
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return cast(HypothesisSnapshot, payload)


def build_validation_report(
    *,
    report_id: str,
    target_artifact_ref: ArtifactRef,
    validator_id: str,
    validator_version: str,
    checks: Sequence[Mapping[str, Any]],
    created_at: str,
) -> ValidationReport:
    """Build the existing public ValidationReport without scientific promotion."""
    for label, value in (
        ("report_id", report_id),
        ("validator_id", validator_id),
        ("validator_version", validator_version),
        ("created_at", created_at),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ResearchContractError(f"{label} must be a non-empty string")
    _validate_artifact_ref(target_artifact_ref)

    validated_checks: list[ValidationCheck] = []
    severities: set[str] = set()
    for index, check in enumerate(checks):
        code = check.get("code")
        severity = check.get("severity")
        message = check.get("message")
        if not all(isinstance(value, str) and value.strip() for value in (code, message)):
            raise ResearchContractError(f"validation check {index} needs code and message")
        if severity not in {"INFO", "WARNING", "ERROR"}:
            raise ResearchContractError(f"validation check {index} has invalid severity")
        validated: dict[str, Any] = {
            "code": code,
            "severity": severity,
            "message": message,
        }
        if "path" in check:
            path = check["path"]
            if not isinstance(path, str):
                raise ResearchContractError(f"validation check {index} path must be a string")
            validated["path"] = path
        validated_checks.append(cast(ValidationCheck, validated))
        severities.add(cast(str, severity))

    validation_status = (
        "FAIL"
        if "ERROR" in severities
        else "PASS_WITH_WARNINGS"
        if "WARNING" in severities
        else "PASS"
    )
    payload: dict[str, Any] = {
        "report_id": report_id,
        "schema_version": _PUBLIC_SCHEMA_VERSION,
        "target_artifact_ref": dict(target_artifact_ref),
        "validator_id": validator_id,
        "validator_version": validator_version,
        "validation_status": validation_status,
        "checks": validated_checks,
        "created_at": created_at,
    }
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return cast(ValidationReport, payload)


def parse_counterexample_report(document: Mapping[str, Any]) -> CounterexampleReport:
    """Validate the internal five-category counterexample review DTO."""
    report_version = _required_string(document, "report_version")
    review_unit = _required_string(document, "review_unit")
    if review_unit != "INDEPENDENT_EVENT_OR_AR":
        raise ResearchContractError("counterexample review_unit must be INDEPENDENT_EVENT_OR_AR")
    scientific_verdict = _required_string(document, "scientific_verdict")
    if scientific_verdict != "NOT_EVALUATED":
        raise ResearchContractError("counterexample scientific_verdict must remain NOT_EVALUATED")
    result_maturity = _required_string(document, "result_maturity")
    if result_maturity != "DEVELOPMENTAL":
        raise ResearchContractError("counterexample result_maturity must remain DEVELOPMENTAL")
    confirmed_count = document.get("confirmed_scientific_counterexample_count")
    if confirmed_count != 0:
        raise ResearchContractError(
            "confirmed scientific counterexamples must remain zero before authorized review"
        )
    return CounterexampleReport(
        report_version=report_version,
        review_unit=review_unit,
        scientific_verdict=scientific_verdict,
        result_maturity=result_maturity,
        confirmed_scientific_counterexample_count=0,
        scientific_counterexample_candidates=_string_tuple(
            document, "scientific_counterexample_candidates"
        ),
        data_label_issues=_string_tuple(document, "data_label_issues"),
        sample_statistical_issues=_string_tuple(document, "sample_statistical_issues"),
        research_definition_issues=_string_tuple(document, "research_definition_issues"),
        not_evaluable_items=_string_tuple(document, "not_evaluable_items"),
        next_steps=_string_tuple(document, "next_steps"),
    )


def project_counterexample_snapshot(
    report: CounterexampleReport, *, snapshot_id: str
) -> CounterexampleSnapshot:
    """Project only fields explicitly present in the frozen public summary."""
    _validate_snapshot_id(snapshot_id)
    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "schema_version": _PUBLIC_SCHEMA_VERSION,
        "scientific_counterexample_candidates": list(
            report.scientific_counterexample_candidates
        ),
        "data_label_issues": list(report.data_label_issues),
        "not_evaluable_items": list(report.not_evaluable_items),
        "next_steps": list(report.next_steps),
    }
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return cast(CounterexampleSnapshot, payload)


def _validate_identity(identity: Mapping[str, Any]) -> None:
    _validate_required_fields(
        identity,
        {
            "hypothesis_id",
            "candidate_parameter",
            "role",
            "status",
            "mechanismbrief_version",
        },
        "identity",
    )
    if identity.get("formal_results_seen") is not False:
        raise ResearchContractError("formal_results_seen must be exactly false")
    if identity["role"] != "primary":
        raise ResearchContractError("Hypothesis role must be primary")
    if identity["status"] not in _PACKAGE_STATES:
        raise ResearchContractError("invalid Hypothesis package status")


def _validate_hypothesis_consistency(
    identity: Mapping[str, Any],
    estimand: Mapping[str, Any],
    predictor: Mapping[str, Any],
    target: Mapping[str, Any],
    cohort: Mapping[str, Any],
    estimator_boundary: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> None:
    expected_pairs = (
        (estimand["primary_predictor"], predictor["name"], "primary predictor"),
        (estimand["history_window"], predictor["history_window"], "history window"),
        (estimand["target"], _FIXED_VALUES["target_event"], "estimand target"),
        (target["event"], _FIXED_VALUES["target_event"], "target event"),
        (estimand["lead_window"], _FIXED_VALUES["lead_window"], "estimand lead_window"),
        (target["lead_window"], _FIXED_VALUES["lead_window"], "target lead_window"),
        (target["primary_target_id"], _FIXED_VALUES["primary_target_id"], "target ID"),
        (target["event_anchor"], _FIXED_VALUES["event_anchor"], "event anchor"),
        (target["grading_variable"], _FIXED_VALUES["grading_variable"], "grading variable"),
        (estimand["primary_queue"], _FIXED_VALUES["primary_queue"], "estimand queue"),
        (cohort["primary_queue"], _FIXED_VALUES["primary_queue"], "primary queue"),
        (cohort["diagnostic_queue"], _FIXED_VALUES["diagnostic_queue"], "diagnostic queue"),
    )
    for actual, expected, label in expected_pairs:
        if actual != expected:
            raise ResearchContractError(f"Hypothesis {label} conflict: expected {expected!r}")
    if not cast(str, identity["mechanismbrief_version"]).strip():
        raise ResearchContractError("mechanismbrief_version must not be empty")

    five_state_policy = _required_mapping(estimator_boundary, "five_state_policy")
    if set(five_state_policy) != _FIVE_STATES or any(
        not isinstance(value, str) or not value.strip() for value in five_state_policy.values()
    ):
        raise ResearchContractError("five-state policy must define exactly five non-empty states")
    freeze_values = _required_mapping(estimator_boundary, "values_to_freeze_before_results")
    required_freeze_values = {
        "metric",
        "confidence_interval",
        "sample_floor",
        "prediction_metric_and_baseline",
        "minimum_substantive_effect",
        "counterexample_downgrade_threshold",
    }
    _validate_required_fields(freeze_values, required_freeze_values, "freeze responsibilities")
    provenance = _required_mapping(interpretation, "provenance")
    if set(provenance) != _PROVENANCE_GROUPS:
        raise ResearchContractError("interpretation provenance must preserve all five groups")


def _validate_decisions(decisions: list[Mapping[str, Any]], status: str) -> None:
    decision_ids = [decision.get("decision_id") for decision in decisions]
    if len(decision_ids) != len(set(decision_ids)) or set(decision_ids) != _DECISION_IDS:
        raise ResearchContractError("operationalization decision IDs must contain the six cards")
    for decision in decisions:
        if decision.get("freeze_status") not in {"proposed", "reviewed", "frozen", "disabled"}:
            raise ResearchContractError("operationalization decision has invalid freeze_status")
        selected = decision.get("selected")
        if not isinstance(selected, str) or not selected:
            raise ResearchContractError("operationalization decision must select a candidate")
    if status == "READY_FOR_DATAPLAN" and any(
        decision["freeze_status"] != "frozen" or decision["selected"] == "BLOCKED"
        for decision in decisions
    ):
        raise ResearchContractError(
            "READY_FOR_DATAPLAN requires every decision frozen and unblocked"
        )


def _validate_dataplan_handoff(
    handoff: Mapping[str, Any],
    identity: Mapping[str, Any],
    estimand: Mapping[str, Any],
    predictor: Mapping[str, Any],
    target: Mapping[str, Any],
) -> None:
    if set(handoff) != _HANDOFF_LAYERS:
        raise ResearchContractError("DataPlan handoff layers must contain exactly eight layers")
    identity_layer = _required_mapping(handoff, "identity_scientific_constraints")
    predictor_layer = _required_mapping(handoff, "predictor_layer")
    target_layer = _required_mapping(handoff, "target_layer")
    output_fields = _required_mapping(handoff, "output_fields")
    provenance_layer = _required_mapping(handoff, "provenance_exceptions_freeze")

    expected_pairs = (
        (identity_layer.get("hypothesis_id"), identity["hypothesis_id"], "hypothesis ID"),
        (identity_layer.get("estimand"), estimand["sentence"], "estimand"),
        (predictor_layer.get("primary_predictor"), predictor["name"], "predictor"),
        (
            predictor_layer.get("predictor_history_window"),
            predictor["history_window"],
            "history window",
        ),
        (target_layer.get("event"), target["event"], "target event"),
        (target_layer.get("lead"), target["lead_window"], "target lead window"),
    )
    for actual, expected, label in expected_pairs:
        if actual != expected:
            raise ResearchContractError(f"DataPlan handoff {label} conflicts with Hypothesis")
    if set(output_fields) != _OUTPUT_GROUPS:
        raise ResearchContractError("DataPlan output fields must preserve all five groups")
    provenance = _required_mapping(provenance_layer, "provenance_categories")
    if set(provenance) != _PROVENANCE_GROUPS:
        raise ResearchContractError("DataPlan provenance must preserve all five groups")
    exception_returns = _required_mapping(provenance_layer, "exception_returns")
    if set(exception_returns) != _EXCEPTION_RETURNS:
        raise ResearchContractError("DataPlan exception returns must preserve all three states")
    expected_sentence = _STATUS_SENTENCES[cast(str, identity["status"])]
    if provenance_layer.get("status_sentence") != expected_sentence:
        raise ResearchContractError("DataPlan status sentence conflicts with Hypothesis status")


def _validate_source_ledger(
    source_ledger: Mapping[str, Any], pending_items: Sequence[Any]
) -> None:
    labels: set[str] = set()
    for key, item in source_ledger.items():
        if not isinstance(item, Mapping):
            raise ResearchContractError(f"source ledger entry {key!r} must be an object")
        label = item.get("source_label")
        locator = item.get("source_locator")
        if label not in _SOURCE_LABELS or not isinstance(locator, str) or not locator.strip():
            raise ResearchContractError(f"source ledger entry {key!r} is incomplete")
        labels.add(cast(str, label))
    if not {"[齐]", "[项目]", "[曾增]"}.issubset(labels):
        raise ResearchContractError(
            "source ledger must represent Qi, project, and hypothesis sources"
        )
    if pending_items and "[待确认]" not in labels:
        raise ResearchContractError("pending items require a [待确认] source ledger entry")


def _required_mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, Mapping) or not value:
        raise ResearchContractError(f"{key} must be a non-empty object")
    return value


def _required_sequence(document: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = document.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ResearchContractError(f"{key} must be an array")
    return value


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ResearchContractError(f"{label} must be an array")
    if not value or any(not isinstance(item, Mapping) for item in value):
        raise ResearchContractError(f"{label} must contain objects")
    return [cast(Mapping[str, Any], item) for item in value]


def _validate_required_fields(
    document: Mapping[str, Any], required: set[str], label: str
) -> None:
    missing = sorted(
        key
        for key in required
        if key not in document
        or document[key] is None
        or isinstance(document[key], str) and not cast(str, document[key]).strip()
    )
    if missing:
        raise ResearchContractError(f"{label} missing required fields: {missing}")


def _required_string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResearchContractError(f"{key} must be a non-empty string")
    return value


def _string_tuple(document: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _required_sequence(document, key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ResearchContractError(f"{key} must contain only non-empty strings")
    return tuple(cast(str, value) for value in values)


def _validate_snapshot_id(snapshot_id: str) -> None:
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise ResearchContractError("snapshot_id must be a non-empty string")


def _validate_versioned_ref(reference: VersionedRef) -> None:
    if set(reference) != {"id", "schema_version", "content_hash"}:
        raise ResearchContractError("upstream mechanism ref must be a complete VersionedRef")
    if not all(isinstance(value, str) and value for value in reference.values()):
        raise ResearchContractError("upstream mechanism ref fields must be non-empty strings")


def _validate_artifact_ref(reference: ArtifactRef) -> None:
    if set(reference) != {"artifact_id", "content_sha256", "schema_version"}:
        raise ResearchContractError("target_artifact_ref must be a complete ArtifactRef")
    if not all(isinstance(value, str) and value for value in reference.values()):
        raise ResearchContractError("target_artifact_ref fields must be non-empty strings")
