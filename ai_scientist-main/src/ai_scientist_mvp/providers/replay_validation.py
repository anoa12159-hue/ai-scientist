"""Deterministic validation, Finding, gate-request, and report factories."""
from __future__ import annotations

import hashlib
from typing import Any, cast

from ai_scientist_mvp.application.ports import ArtifactStore
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import LedgerIntegrityError
from ai_scientist_mvp.domain.store_types import StageAttemptKey
from ai_scientist_mvp.domain.types import (
    ArtifactRef,
    CompatibilityFinding,
    DecisionOption,
    DecisionRequest,
    GapFinding,
    ReportManifest,
    ResearchSummary,
    ValidationReport,
    VersionedRef,
)
from ai_scientist_mvp.infrastructure.contract_validation import ContractValidator
from ai_scientist_mvp.providers.shrgt45_replay import ManifestAssetCatalog

_FIXED_TS = "2026-08-20T00:00:00Z"
_SCHEMA_VERSION = "0.1.0"
_VALIDATOR_ID = "replay-deterministic-validator"
_VALIDATOR_VERSION = "0.1.0"


def _content_hash(payload: dict[str, Any]) -> str:
    return canonical_json.content_hash_excluding(payload)


def _object_ref(obj: dict[str, Any], id_field: str) -> VersionedRef:
    return {
        "id": obj[id_field],
        "schema_version": obj["schema_version"],
        "content_hash": obj["content_hash"],
    }


class DeterministicValidator:
    """Validate the target reference before describing any checks as passing."""

    def __init__(self, store: ArtifactStore, contracts: ContractValidator) -> None:
        self.store = store
        self.contracts = contracts

    def validate(self, target_ref: ArtifactRef, checks: list[dict[str, Any]]) -> ValidationReport:
        self.store.verify_ref(target_ref)
        severities = {check.get("severity") for check in checks}
        if "ERROR" in severities:
            status = "FAIL"
        elif "WARNING" in severities:
            status = "PASS_WITH_WARNINGS"
        else:
            status = "PASS"
        report: dict[str, Any] = {
            "report_id": "vr-" + hashlib.sha256(
                canonical_json.canonicalize(target_ref)
            ).hexdigest()[:16],
            "schema_version": _SCHEMA_VERSION,
            "target_artifact_ref": target_ref,
            "validator_id": _VALIDATOR_ID,
            "validator_version": _VALIDATOR_VERSION,
            "validation_status": status,
            "checks": checks,
            "created_at": _FIXED_TS,
        }
        report["content_hash"] = _content_hash(report)
        self.contracts.validate("validation-report", report)
        return cast(ValidationReport, report)


class ReplayFindingFactory:
    """Materialize Findings from the frozen Case/Audit instead of copied constants."""

    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog
        self.contracts = catalog.contracts

    def build_acceptable_findings(
        self, stage_refs: dict[str, ArtifactRef]
    ) -> list[CompatibilityFinding | GapFinding]:
        profile_codes = set(
            self.catalog.case_manifest["acceptance_profile"]["acceptable_finding_codes"]
        )
        specs = self.catalog.case_manifest["declared_finding_specs"]
        if {spec["code"] for spec in specs} != profile_codes:
            raise LedgerIntegrityError("declared Finding specs do not match acceptance profile")
        findings: list[CompatibilityFinding | GapFinding] = []
        for spec in specs:
            if spec["replay_policy"] != "MAY_ACCEPT_WITH_EXACT_HASH_REVIEW":
                raise LedgerIntegrityError(
                    f"non-acceptable policy in replay Finding: {spec['code']}"
                )
            stages = spec.get("related_stage_ids", [])
            if not stages or any(stage not in stage_refs for stage in stages):
                raise LedgerIntegrityError(f"Finding has unbound related stage: {spec['code']}")
            base: dict[str, Any] = {
                "finding_id": "finding-" + hashlib.sha256(
                    canonical_json.canonicalize({
                        "code": spec["code"],
                        "stage_refs": [stage_refs[stage] for stage in stages],
                    })
                ).hexdigest()[:20],
                "logical_finding_id": spec["code"],
                "schema_version": _SCHEMA_VERSION,
                "revision": 1,
                "code": spec["code"],
                "severity": spec["expected_severity"],
                "initial_status": "OPEN",
                "summary": spec["code"],
                "evidence_refs": spec.get("rationale_source_refs", []),
                "impact": "历史兼容性或来源限制；不改变科学结论。",
                "required_action": "仅可在 FIXTURE_IMPORT_REVIEW 中按精确哈希逐项接受。",
                "created_at": _FIXED_TS,
            }
            if spec["finding_kind"] == "COMPATIBILITY":
                if len(stages) >= 2:
                    base["upstream_artifact_ref"] = stage_refs[stages[0]]
                    base["downstream_artifact_ref"] = stage_refs[stages[-1]]
                else:
                    base["upstream_artifact_ref"] = stage_refs[stages[0]]
                schema_name = "compatibility-finding"
                findings.append(cast(CompatibilityFinding, base))
            elif spec["finding_kind"] == "GAP":
                base["stage_id"] = stages[0]
                schema_name = "gap-finding"
                findings.append(cast(GapFinding, base))
            else:
                raise LedgerIntegrityError(f"unknown Finding kind: {spec['finding_kind']}")
            finding = findings[-1]
            finding["content_hash"] = _content_hash(cast(dict[str, Any], finding))
            self.contracts.validate(schema_name, finding)
        return findings

    def build_informational_gaps(self) -> list[GapFinding]:
        stage_by_code = {
            "CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED": "S01_CANDIDATE",
            "LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE": "S03_HYPOTHESIS",
        }
        gaps: list[GapFinding] = []
        for spec in self.catalog.import_audit["informational_gap_findings"]:
            code = spec["code"]
            if code not in stage_by_code or spec.get("finding_kind") != "GAP":
                raise LedgerIntegrityError(f"unknown informational Gap: {code}")
            gap: dict[str, Any] = {
                "finding_id": "finding-" + hashlib.sha256(code.encode("utf-8")).hexdigest()[:20],
                "logical_finding_id": code,
                "schema_version": _SCHEMA_VERSION,
                "revision": 1,
                "stage_id": stage_by_code[code],
                "code": code,
                "severity": "INFO",
                "initial_status": "OPEN",
                "summary": code,
                "impact": "能力或材料缺口，仅作开发性展示。",
                "required_action": "由后续独立任务补齐；本次 Replay 不补造输入。",
                "created_at": _FIXED_TS,
            }
            gap["content_hash"] = _content_hash(gap)
            self.contracts.validate("gap-finding", gap)
            gaps.append(cast(GapFinding, gap))
        return gaps


class FixtureImportDecisionRequestFactory:
    def __init__(self, store: ArtifactStore, contracts: ContractValidator) -> None:
        self.store = store
        self.contracts = contracts

    def build(
        self,
        artifact_refs: list[ArtifactRef],
        findings: list[CompatibilityFinding | GapFinding],
        stage_attempt_keys: list[StageAttemptKey],
    ) -> DecisionRequest:
        if not artifact_refs or not findings or not stage_attempt_keys:
            raise LedgerIntegrityError(
                "FIXTURE_IMPORT_REVIEW requires bound artifacts, Findings, and stages"
            )
        for ref in artifact_refs:
            self.store.verify_ref(ref)
        finding_refs = [
            _object_ref(cast(dict[str, Any], finding), "finding_id")
            for finding in findings
        ]
        for finding in findings:
            schema_name = (
                "gap-finding" if "stage_id" in finding else "compatibility-finding"
            )
            self.contracts.validate(schema_name, finding)
            if _content_hash(cast(dict[str, Any], finding)) != finding["content_hash"]:
                raise LedgerIntegrityError(f"stale Finding content_hash: {finding['finding_id']}")
        run_ids = {key.get("run_id") for key in stage_attempt_keys}
        if len(run_ids) != 1:
            raise LedgerIntegrityError("StageAttemptKeys must belong to exactly one Run")
        serialized_keys: set[bytes] = set()
        serialized_configs: set[bytes] = set()
        for key in stage_attempt_keys:
            if set(key) != {"run_id", "stage_id", "attempt", "stage_configuration_ref"}:
                raise LedgerIntegrityError("malformed StageAttemptKey")
            if (
                not isinstance(key["run_id"], str)
                or not key["run_id"]
                or not isinstance(key["stage_id"], str)
                or not key["stage_id"]
                or not isinstance(key["attempt"], int)
                or isinstance(key["attempt"], bool)
                or key["attempt"] < 1
            ):
                raise LedgerIntegrityError("malformed StageAttemptKey value")
            config = key["stage_configuration_ref"]
            if config is None or set(config) != {"id", "schema_version", "content_hash"}:
                raise LedgerIntegrityError("StageAttemptKey requires a complete configuration ref")
            self.contracts.validate("versioned-ref", config)
            serialized_keys.add(canonical_json.canonicalize(key))
            serialized_configs.add(canonical_json.canonicalize(config))
        if len(serialized_keys) != len(stage_attempt_keys):
            raise LedgerIntegrityError("FIXTURE_IMPORT_REVIEW contains duplicate StageAttemptKey")
        if len(serialized_configs) != 1:
            raise LedgerIntegrityError("StageAttemptKeys bind different Run configurations")

        options: list[DecisionOption] = [
            {
                "option_id": "ACCEPT",
                "label": "接受并继续历史回放",
                "description": "对精确绑定的 Finding 逐项 ACCEPT_FOR_REPLAY。",
                "consequences": "仅允许历史 Replay 继续，不适用于 Live Run、正式统计或发布。",
                "required_capability": "PROJECT_OWNER_GOVERNANCE",
            },
            {
                "option_id": "REVISE",
                "label": "拒绝并返回修正",
                "description": "拒绝当前 Fixture 导入审核。",
                "consequences": "回放停在 S07 前，等待人工修正。",
                "required_capability": "PROJECT_OWNER_GOVERNANCE",
            },
        ]
        context = {
            "artifact_refs": artifact_refs,
            "finding_refs": finding_refs,
            "stage_attempt_keys": stage_attempt_keys,
        }
        request: dict[str, Any] = {
            "request_id": "fixture-import-review-" + hashlib.sha256(
                canonical_json.canonicalize(context)
            ).hexdigest()[:20],
            "schema_version": _SCHEMA_VERSION,
            "decision_context": "RUN_GATE",
            "gate_id": "FIXTURE_IMPORT_REVIEW",
            "prompt": "对已登记的 SHRGT45 历史兼容性与来源限制逐项审核。",
            "context_artifact_refs": artifact_refs,
            "context_finding_refs": finding_refs,
            "context_stage_attempt_keys": stage_attempt_keys,
            "options": options,
            "recommended_option_id": "ACCEPT",
            "recommendation_reason": "仅建议允许精确绑定的历史回放继续。",
            "risk_summary": "不构成科学、正式执行或发布授权。",
            "impact_summary": "只影响当前历史 Replay 是否可进入 S07。",
            "allowed_scope": "FIXTURE_IMPORT_REVIEW",
            "allowed_actor_roles": ["project_owner"],
            "requested_at": _FIXED_TS,
        }
        request["content_hash"] = _content_hash(request)
        self.contracts.validate("decision-request", request)
        return cast(DecisionRequest, request)


class DevelopmentalReportRenderer:
    def __init__(self, contracts: ContractValidator) -> None:
        self.contracts = contracts

    def research_summary(self, finding_refs: list[VersionedRef]) -> ResearchSummary:
        summary: dict[str, Any] = {
            "summary_id": "research-summary-shrgt45",
            "schema_version": _SCHEMA_VERSION,
            "execution_result": "历史回放导入与结构校验完成；不构成科学评估。",
            "validation_status": "PASS_WITH_WARNINGS",
            "lineage_status": "PARTIAL",
            "scientific_verdict": "NOT_EVALUATED",
            "result_maturity": "DEVELOPMENTAL",
            "authorization_status": "NOT_AUTHORIZED",
            "release_scope": "NOT_READY",
            "finding_refs": finding_refs,
        }
        summary["content_hash"] = _content_hash(summary)
        self.contracts.validate("research-summary", summary)
        return cast(ResearchSummary, summary)

    def report_manifest(
        self,
        research_summary_ref: ArtifactRef,
        s05_ref: ArtifactRef,
        s06_ref: ArtifactRef,
        finding_refs: list[VersionedRef],
    ) -> ReportManifest:
        manifest: dict[str, Any] = {
            "report_manifest_id": "report-manifest-shrgt45",
            "schema_version": _SCHEMA_VERSION,
            "research_summary_ref": research_summary_ref,
            "s05_branch_ref": s05_ref,
            "s06_branch_ref": s06_ref,
            "included_artifact_refs": [research_summary_ref, s05_ref, s06_ref],
            "finding_refs": finding_refs,
            "join_status": "REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT",
            "created_at": _FIXED_TS,
        }
        manifest["content_hash"] = _content_hash(manifest)
        self.contracts.validate("report-manifest", manifest)
        return cast(ReportManifest, manifest)
