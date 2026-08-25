from __future__ import annotations

from copy import deepcopy

import pytest

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.infrastructure.contract_validation import (
    ContractValidator,
    default_contracts_root,
)
from ai_scientist_mvp.skills.research_contracts import (
    ResearchContractError,
    build_validation_report,
    extract_data_plan,
    parse_counterexample_report,
    parse_hypothesis_contract,
    project_counterexample_snapshot,
    project_hypothesis_snapshot,
)


def _valid_hypothesis() -> dict[str, object]:
    five_states = {
        "SUPPORTED": "adequate evidence and positive effect",
        "CONDITIONALLY_SUPPORTED": "positive but limited",
        "NOT_SUPPORTED": "adequate evidence and non-positive effect",
        "INSUFFICIENT_EVIDENCE": "insufficient precision or samples",
        "BLOCKED": "unfrozen rule or unavailable data",
    }
    decision_ids = (
        "PREDICTOR_QUANTIFICATION",
        "PREDICTION_OCCASION",
        "ENDPOINT_AND_COMPARISON",
        "QUALITY_NA_AUDIT",
        "SENSITIVITY_AUXILIARY",
        "CONCLUSION_FIVE_STATE",
    )
    provenance = {
        "parameter_physics": ["E01"],
        "predictor_methods": ["M01"],
        "temporal_or_design_side_support": ["S01"],
        "unverified_project_prior": ["P01"],
        "research_design_boundaries": ["B01"],
    }
    return {
        "schema_version": "2.1.0",
        "identity": {
            "hypothesis_id": "HYP-SHRGT45-IND-03",
            "candidate_parameter": "SHRGT45",
            "role": "primary",
            "status": "DRAFT",
            "mechanismbrief_version": "V2.2",
            "formal_results_seen": False,
        },
        "estimand": {
            "sentence": "Higher beta_TS is associated with greater future M1.0+ risk.",
            "population": "eligible same-unit prediction occasions",
            "analysis_unit": "SHARP_HARP_TIMEPOINT",
            "primary_predictor": "beta_TS",
            "history_window": "[t-3h,t]",
            "target": "M1.0及以上耀斑",
            "lead_window": "[t+3h,t+6h)",
            "expected_direction": "positive",
            "primary_queue": "OPERATIONAL_ROLLING",
        },
        "measurement": {
            "definition_unit_observation_level": "percent at HARP timepoint",
            "directly_measures": "fraction above shear threshold",
            "does_not_measure": "total free energy",
            "qi_evidence_ids": ["E01"],
            "required_raw_fields": ["SHRGT45", "T_REC"],
            "background_fields": ["USFLUX"],
            "audit_fields": ["QUALITY", "CMASK"],
        },
        "predictor": {
            "name": "beta_TS",
            "transformation": "Theil-Sen slope over real timestamps",
            "formula": "median((y_j-y_i)/(t_j-t_i))",
            "unit": "percentage-points/hour",
            "history_window": "[t-3h,t]",
            "timestamp_rule": "use actual T_REC",
            "quality_completeness_rule": "apply frozen quality gate",
            "missing_rule": "NA is distinct from zero, no event, and not observed",
            "auxiliary_outputs": [],
        },
        "target": {
            "event": "M1.0及以上耀斑",
            "primary_target_id": "future_3_6h_same_unit_Mplus",
            "event_anchor": "GOES SXR onset用于事件落窗",
            "grading_variable": "GOES peak flux用于M+定级",
            "lead_window": "[t+3h,t+6h)",
            "same_unit_rule": "same HARP analysis unit",
            "early_window": "[t,t+3h)",
            "endpoint_policy": "t+3h included; t+6h excluded",
        },
        "cohort": {
            "prediction_occasion": "one frozen HARP timepoint",
            "population": "all eligible occasions",
            "independence_boundary": "HARP_EVENT_EPISODE",
            "applicability_scope": "frozen observational scope",
            "common_eligibility": "same gate before labels",
            "primary_queue": "OPERATIONAL_ROLLING",
            "diagnostic_queue": "DIAGNOSTIC_MATCHED",
            "queue_specific_rules": "early events differ by queue",
            "exclusion_rules": [],
        },
        "estimator_boundary": {
            "scientific_association_question": "association after frozen gates",
            "dataplan_owned_items": ["estimator", "confidence interval"],
            "five_state_policy": five_states,
            "values_to_freeze_before_results": {
                "metric": "DataPlan owner",
                "confidence_interval": "DataPlan owner",
                "sample_floor": "DataPlan owner",
                "prediction_metric_and_baseline": "DataPlan owner",
                "minimum_substantive_effect": "DataPlan owner",
                "counterexample_downgrade_threshold": "Counterexample owner",
            },
        },
        "interpretation": {
            "mechanism_summary_from_qi": "photospheric non-potentiality proxy",
            "alternative_explanations": ["mask changes"],
            "claim_ceiling_from_qi": "candidate precursor association only",
            "forbidden_claims_from_qi": ["proved reconnection"],
            "provenance": provenance,
        },
        "operationalization_decisions": [
            {
                "decision_id": decision_id,
                "selected": "A",
                "freeze_status": "proposed",
            }
            for decision_id in decision_ids
        ],
        "dataplan_handoff": {
            "identity_scientific_constraints": {
                "hypothesis_id": "HYP-SHRGT45-IND-03",
                "estimand": "Higher beta_TS is associated with greater future M1.0+ risk.",
                "status_and_version": "DRAFT / V2.2",
            },
            "measurement_data_inputs": {"primary_measurements": ["SHRGT45"]},
            "predictor_layer": {
                "primary_predictor": "beta_TS",
                "predictor_history_window": "[t-3h,t]",
            },
            "target_layer": {
                "event": "M1.0及以上耀斑",
                "lead": "[t+3h,t+6h)",
            },
            "cohort_research_design": {"prediction_occasion": "one frozen timepoint"},
            "estimator_layer": {"five_state_policy": five_states},
            "output_fields": {
                "row_identity_scope": ["Prediction_Row_ID"],
                "measurement_background_audit": ["SHRGT45", "QUALITY"],
                "predictor_outputs": ["beta_TS"],
                "eligibility_queue_target_labels": ["target_label"],
                "target_event_fields": ["event_id"],
            },
            "provenance_exceptions_freeze": {
                "provenance_categories": provenance,
                "exception_returns": {
                    "NEEDS_CLARIFICATION": "unfrozen input; do not execute",
                    "DATA_UNAVAILABLE": "official path failed; do not substitute",
                    "INSUFFICIENT_SAMPLES": "frozen gates too small; do not call unsupported",
                },
                "status_sentence": "当前全信息基准提案，等待团队冻结。",
            },
        },
        "source_ledger": {
            "mechanism": {"source_label": "[齐]", "source_locator": "MB:E01"},
            "constant": {"source_label": "[项目]", "source_locator": "project constants"},
            "decision": {"source_label": "[曾增]", "source_locator": "decision A"},
        },
        "pending_items": [],
    }


def test_parses_hypothesis_and_extracts_eight_layer_dataplan() -> None:
    hypothesis = parse_hypothesis_contract(_valid_hypothesis())
    data_plan = extract_data_plan(hypothesis)

    assert hypothesis.hypothesis_id == "HYP-SHRGT45-IND-03"
    assert hypothesis.parameter == "SHRGT45"
    assert data_plan.hypothesis_id == hypothesis.hypothesis_id
    assert data_plan.predictor_layer["primary_predictor"] == "beta_TS"
    assert data_plan.target_layer["lead"] == "[t+3h,t+6h)"
    assert set(data_plan.output_fields) == {
        "row_identity_scope",
        "measurement_background_audit",
        "predictor_outputs",
        "eligibility_queue_target_labels",
        "target_event_fields",
    }


def test_projects_hypothesis_to_existing_frozen_snapshot() -> None:
    hypothesis = parse_hypothesis_contract(_valid_hypothesis())
    mechanism_ref = {
        "id": "mechanism-v22",
        "schema_version": "0.1.0",
        "content_hash": "A" * 64,
    }

    snapshot = project_hypothesis_snapshot(
        hypothesis,
        snapshot_id="hypothesis-active-draft",
        upstream_mechanism_ref=mechanism_ref,
    )

    ContractValidator(default_contracts_root()).validate("hypothesis-snapshot", snapshot)
    assert snapshot["flow3_domain_status"] == "DRAFT"
    assert snapshot["machine_verifiable"] is True
    assert canonical_json.content_hash_excluding(snapshot) == snapshot["content_hash"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item["identity"].update(formal_results_seen=True), "formal_results_seen"),
        (lambda item: item["target"].update(lead_window="(t+3h,t+6h]"), "lead_window"),
        (
            lambda item: item["dataplan_handoff"].pop("output_fields"),
            "DataPlan handoff layers",
        ),
        (
            lambda item: item["operationalization_decisions"].pop(),
            "operationalization decision IDs",
        ),
    ],
)
def test_hypothesis_contract_fails_closed(mutate: object, message: str) -> None:
    document = _valid_hypothesis()
    mutate(document)  # type: ignore[operator]

    with pytest.raises(ResearchContractError, match=message):
        parse_hypothesis_contract(document)


def test_ready_hypothesis_requires_frozen_unblocked_decisions() -> None:
    document = _valid_hypothesis()
    document["identity"]["status"] = "READY_FOR_DATAPLAN"  # type: ignore[index]

    with pytest.raises(ResearchContractError, match="READY_FOR_DATAPLAN"):
        parse_hypothesis_contract(document)


def test_validation_report_reuses_frozen_public_contract() -> None:
    target_ref = {
        "artifact_id": "artifact-hypothesis-1",
        "content_sha256": "B" * 64,
        "schema_version": "0.1.0",
    }
    report = build_validation_report(
        report_id="validation-hypothesis-1",
        target_artifact_ref=target_ref,
        validator_id="hypothesis-contract-validator",
        validator_version="2.1.0",
        checks=[
            {"code": "STRUCTURE_OK", "severity": "INFO", "message": "DTO is complete"},
            {
                "code": "PENDING_FREEZE",
                "severity": "WARNING",
                "message": "Scientific review is still required",
                "path": "/identity/status",
            },
        ],
        created_at="2026-08-25T00:00:00Z",
    )

    ContractValidator(default_contracts_root()).validate("validation-report", report)
    assert report["validation_status"] == "PASS_WITH_WARNINGS"
    assert "scientific_verdict" not in report
    assert canonical_json.content_hash_excluding(report) == report["content_hash"]


def _valid_counterexample_report() -> dict[str, object]:
    return {
        "report_version": "1.0.0",
        "review_unit": "INDEPENDENT_EVENT_OR_AR",
        "scientific_verdict": "NOT_EVALUATED",
        "result_maturity": "DEVELOPMENTAL",
        "confirmed_scientific_counterexample_count": 0,
        "scientific_counterexample_candidates": ["AR12673 requires clean-data review"],
        "data_label_issues": ["event provenance remains unresolved"],
        "sample_statistical_issues": ["overlapping rows are not independent samples"],
        "research_definition_issues": ["primary estimator remains to be frozen"],
        "not_evaluable_items": ["AR11520", "AR12192"],
        "next_steps": ["freeze provenance", "build independent controls"],
    }


def test_counterexample_report_preserves_categories_and_projects_snapshot() -> None:
    report = parse_counterexample_report(_valid_counterexample_report())

    assert report.confirmed_scientific_counterexample_count == 0
    assert report.sample_statistical_issues
    assert report.research_definition_issues

    snapshot = project_counterexample_snapshot(report, snapshot_id="counterexample-active-draft")
    ContractValidator(default_contracts_root()).validate("counterexample-snapshot", snapshot)
    assert snapshot["scientific_counterexample_candidates"] == [
        "AR12673 requires clean-data review"
    ]
    assert snapshot["data_label_issues"] == ["event provenance remains unresolved"]
    assert canonical_json.content_hash_excluding(snapshot) == snapshot["content_hash"]


def test_counterexample_report_rejects_scientific_status_promotion() -> None:
    document = deepcopy(_valid_counterexample_report())
    document["scientific_verdict"] = "NOT_SUPPORTED"

    with pytest.raises(ResearchContractError, match="NOT_EVALUATED"):
        parse_counterexample_report(document)
