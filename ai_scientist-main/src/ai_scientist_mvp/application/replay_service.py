"""Assemble the deterministic SHRGT45 Replay up to its human review gate."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ai_scientist_mvp.application.ports import ArtifactStore, RunStore
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import LedgerIntegrityError
from ai_scientist_mvp.domain.store_types import StageAttemptKey
from ai_scientist_mvp.domain.types import (
    ArtifactRef,
    CompatibilityFinding,
    DecisionRequest,
    GapFinding,
    ReportManifest,
    ResearchSummary,
    RunConfigurationSnapshot,
    RunRecord,
    StageRun,
    ValidationReport,
    VersionedRef,
)
from ai_scientist_mvp.providers.replay_validation import (
    DeterministicValidator,
    DevelopmentalReportRenderer,
    FixtureImportDecisionRequestFactory,
    ReplayFindingFactory,
)
from ai_scientist_mvp.providers.shrgt45_replay import (
    ManifestAssetCatalog,
    ReplayArtifactImporter,
    ReplayCandidateProvider,
    ReplayCounterexampleProvider,
    ReplayDataProvider,
    ReplayHypothesisProvider,
    ReplayMagnetogramQAProvider,
    ReplayMechanismProvider,
)

_FIXED_TS = "2026-08-20T00:00:00Z"
_SCHEMA_VERSION = "0.1.0"
_PROVIDER = {"id": "replay-adapter", "version": "0.1.0"}
_STAGES = (
    "S01_CANDIDATE",
    "S02_MECHANISM",
    "S03_HYPOTHESIS",
    "S04_DATA_AND_VERIFICATION",
    "S05_COUNTEREXAMPLE",
    "S06_MAGNETOGRAM_QA",
)
_SNAPSHOT_TYPES = {
    "S01_CANDIDATE": ("CandidateSnapshot", "candidate-snapshot"),
    "S02_MECHANISM": ("MechanismSnapshot", "mechanism-snapshot"),
    "S03_HYPOTHESIS": ("HypothesisSnapshot", "hypothesis-snapshot"),
    "S04_DATA_AND_VERIFICATION": ("VerificationSnapshot", "verification-snapshot"),
    "S05_COUNTEREXAMPLE": ("CounterexampleSnapshot", "counterexample-snapshot"),
    "S06_MAGNETOGRAM_QA": ("MagnetogramQASnapshot", "magnetogram-qa-snapshot"),
}
_STRUCTURAL_CHECKS = [
    {
        "code": "ARTIFACT_AUTHORITY_VERIFIED",
        "severity": "INFO",
        "message": "ArtifactRef resolves and authority content hash matches.",
    },
    {
        "code": "STRUCTURAL_SCHEMA_VALID",
        "severity": "INFO",
        "message": "Snapshot satisfies its frozen JSON Schema.",
    },
]
_INFO_GAP_STAGES = {
    "CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED": "S01_CANDIDATE",
    "LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE": "S03_HYPOTHESIS",
}


@dataclass(frozen=True)
class ReplayPreparation:
    """Persisted, recoverable state immediately before FIXTURE_IMPORT_REVIEW."""

    configuration: RunConfigurationSnapshot
    configuration_artifact_ref: ArtifactRef
    configuration_ref: VersionedRef
    source_refs: dict[str, ArtifactRef]
    snapshot_refs: dict[str, ArtifactRef]
    validation_reports: dict[str, ValidationReport]
    validation_artifact_refs: dict[str, ArtifactRef]
    findings: list[CompatibilityFinding | GapFinding]
    finding_refs: list[VersionedRef]
    finding_artifact_refs: dict[str, ArtifactRef]
    stage_runs: dict[str, StageRun]
    stage_attempt_keys: list[StageAttemptKey]
    decision_request: DecisionRequest
    decision_request_artifact_ref: ArtifactRef
    run_record: RunRecord


@dataclass(frozen=True)
class StageOutput:
    """Idempotent per-stage persisted result (source imports + snapshot + report)."""

    stage_id: str
    snapshot_ref: ArtifactRef
    report: ValidationReport
    report_ref: ArtifactRef
    source_input_refs: list[ArtifactRef]
    upstream_input_refs: list[ArtifactRef]


@dataclass(frozen=True)
class ReplayReport:
    """Persisted developmental report objects produced by an explicit caller."""

    research_summary: ResearchSummary
    research_summary_ref: ArtifactRef
    report_manifest: ReportManifest
    report_manifest_ref: ArtifactRef


class ReplayService:
    """Offline application service; no graph, authorization, or automatic gate decision."""

    def __init__(
        self,
        artifact_store: ArtifactStore,
        run_store: RunStore,
        fixtures_root: Path,
        run_id: str,
        task_id: str,
    ) -> None:
        self.artifact_store = artifact_store
        self.run_store = run_store
        self.run_id = run_id
        self.task_id = task_id
        self.catalog = ManifestAssetCatalog(fixtures_root)
        # Preflight all Fixture identities before this service can write any Artifact.
        self.catalog.load()
        self.importer = ReplayArtifactImporter(
            artifact_store, self.catalog, run_id, task_id
        )
        self.validator = DeterministicValidator(artifact_store, self.catalog.contracts)
        self.finding_factory = ReplayFindingFactory(self.catalog)
        self.decision_factory = FixtureImportDecisionRequestFactory(
            artifact_store, self.catalog.contracts
        )
        self.renderer = DevelopmentalReportRenderer(self.catalog.contracts)
        self._preparation: ReplayPreparation | None = None

    def import_runtime_sources(self) -> dict[str, ArtifactRef]:
        """Persist exactly the 81 runtime assets; 0808 remains provenance-only."""
        refs: dict[str, ArtifactRef] = {}
        for stage_id in (*_STAGES, "S07_REPORT"):
            for asset in self.catalog.stage_assets(stage_id):
                refs.setdefault(
                    asset["asset_id"], self.importer.import_source(asset["asset_id"])
                )
        if len(refs) != 81:
            raise LedgerIntegrityError("Replay runtime source set must contain exactly 81 assets")
        if any(asset_id.startswith("s04.source0808::") for asset_id in refs):
            raise LedgerIntegrityError("0808 provenance asset entered the runtime import set")
        expected_s04 = {asset["asset_id"] for asset in self.catalog.default_s04_assets()}
        actual_s04 = {key for key in refs if key.startswith("s04.demo0814::")}
        if actual_s04 != expected_s04:
            raise LedgerIntegrityError("runtime S04 source set differs from the 0814 package")
        return refs

    def prepare_configuration(
        self,
    ) -> tuple[RunConfigurationSnapshot, ArtifactRef, VersionedRef]:
        """Persist the frozen RunConfigurationSnapshot and return its references."""
        configuration, configuration_artifact_ref = self._persist_configuration()
        configuration_ref = _object_ref(configuration, "configuration_id")
        return configuration, configuration_artifact_ref, configuration_ref

    def run_stage(
        self,
        stage_id: str,
        configuration_ref: VersionedRef,
        upstream_snapshot_refs: dict[str, ArtifactRef],
    ) -> StageOutput:
        """Persist one stage's derived snapshot and deterministic validation report.

        This method is idempotent: identical inputs and configuration produce
        identical ArtifactRefs and content hashes, and every write is routed
        through the immutable, content-addressed ArtifactStore. It imports the
        stage's own registered source assets internally. It does not write a
        StageRun; StageRun facts are consolidated once Findings exist in
        ``build_gate_context``.
        """
        if stage_id not in _SNAPSHOT_TYPES:
            raise LedgerIntegrityError(f"not a replay stage: {stage_id}")
        assets = self.catalog.stage_assets(stage_id)
        source_inputs = [self.importer.import_source(asset["asset_id"]) for asset in assets]
        artifact_type, schema_name = _SNAPSHOT_TYPES[stage_id]
        payload = self._snapshot_payload(stage_id)
        snapshot_ref = self.importer.import_summary(
            artifact_type,
            schema_name,
            payload,
            [_object_ref(asset, "asset_id") for asset in assets],
            source_inputs,
        )
        report = self.validator.validate(snapshot_ref, _STRUCTURAL_CHECKS)
        report_ref = self.importer.persist_native(
            "ValidationReport",
            "validation-report",
            report["report_id"],
            cast(dict[str, Any], report),
            [snapshot_ref],
        )
        upstream_inputs = [
            upstream_snapshot_refs[upstream]
            for upstream in self.catalog.case_manifest["stage_dependencies"].get(
                stage_id, []
            )
        ]
        return StageOutput(
            stage_id, snapshot_ref, report, report_ref, source_inputs, upstream_inputs
        )

    def build_gate_context(
        self,
        configuration: RunConfigurationSnapshot,
        configuration_artifact_ref: ArtifactRef,
        configuration_ref: VersionedRef,
        source_refs: dict[str, ArtifactRef],
        stage_outputs: dict[str, StageOutput],
    ) -> ReplayPreparation:
        """Consolidate Findings, StageRuns, DecisionRequest, and the RunRecord.

        This is the S05/S06 Join boundary: it must only run after both branches
        have produced their snapshots. It is idempotent and stops the Run in
        ``WAITING_HUMAN``.
        """
        snapshot_refs = {
            stage_id: output.snapshot_ref for stage_id, output in stage_outputs.items()
        }
        reports = {
            stage_id: output.report for stage_id, output in stage_outputs.items()
        }
        report_artifact_refs = {
            stage_id: output.report_ref for stage_id, output in stage_outputs.items()
        }
        if set(snapshot_refs) != set(_STAGES):
            raise LedgerIntegrityError("gate requires all six stage snapshots")
        findings = (
            self.finding_factory.build_acceptable_findings(snapshot_refs)
            + self.finding_factory.build_informational_gaps()
        )
        finding_refs, finding_artifact_refs = self._persist_findings(
            findings, snapshot_refs
        )
        stage_runs, stage_attempt_keys = self._persist_stage_runs(
            configuration_ref,
            source_refs,
            snapshot_refs,
            reports,
            report_artifact_refs,
            findings,
            finding_refs,
        )
        gate_artifacts = _unique_artifact_refs(
            [
                configuration_artifact_ref,
                *source_refs.values(),
                *snapshot_refs.values(),
                *report_artifact_refs.values(),
                *finding_artifact_refs.values(),
            ]
        )
        decision = self.decision_factory.build(
            gate_artifacts, findings, stage_attempt_keys
        )
        decision_ref = self.importer.persist_native(
            "DecisionRequest",
            "decision-request",
            decision["request_id"],
            cast(dict[str, Any], decision),
            gate_artifacts,
        )
        run_record = self._persist_run_record(
            configuration_ref, stage_runs, decision_ref
        )
        return ReplayPreparation(
            configuration=configuration,
            configuration_artifact_ref=configuration_artifact_ref,
            configuration_ref=configuration_ref,
            source_refs=source_refs,
            snapshot_refs=snapshot_refs,
            validation_reports=reports,
            validation_artifact_refs=report_artifact_refs,
            findings=findings,
            finding_refs=finding_refs,
            finding_artifact_refs=finding_artifact_refs,
            stage_runs=stage_runs,
            stage_attempt_keys=stage_attempt_keys,
            decision_request=decision,
            decision_request_artifact_ref=decision_ref,
            run_record=run_record,
        )

    def prepare_fixture_review(self) -> ReplayPreparation:
        """Persist S01-S06 outputs and stop in WAITING_HUMAN at the import gate."""
        if self._preparation is not None:
            self._verify_cached_preparation(self._preparation)
            return self._preparation
        configuration, configuration_artifact_ref, configuration_ref = (
            self.prepare_configuration()
        )
        source_refs = self.import_runtime_sources()
        stage_outputs: dict[str, StageOutput] = {}
        for stage_id in _STAGES:
            upstream_refs = {
                upstream: stage_outputs[upstream].snapshot_ref
                for upstream in self.catalog.case_manifest["stage_dependencies"].get(
                    stage_id, []
                )
            }
            stage_outputs[stage_id] = self.run_stage(
                stage_id, configuration_ref, upstream_refs
            )
        preparation = self.build_gate_context(
            configuration,
            configuration_artifact_ref,
            configuration_ref,
            source_refs,
            stage_outputs,
        )
        self._preparation = preparation
        return preparation

    def build_report(
        self,
        s05_ref: ArtifactRef,
        s06_ref: ArtifactRef,
        finding_refs: list[VersionedRef],
        finding_artifact_refs: list[ArtifactRef],
    ) -> ReplayReport:
        """Persist the S05/S06 join after a later caller has passed the human gate.

        T005 deliberately does not call this method from ``prepare_fixture_review``.
        It creates no DecisionRecord or authorization and preserves all frozen
        developmental status fields.
        """
        self._require_artifact_type(s05_ref, "CounterexampleSnapshot")
        self._require_artifact_type(s06_ref, "MagnetogramQASnapshot")
        self._verify_finding_artifacts(finding_refs, finding_artifact_refs)
        summary = self.renderer.research_summary(finding_refs)
        summary_ref = self.importer.persist_native(
            "ResearchSummary",
            "research-summary",
            summary["summary_id"],
            cast(dict[str, Any], summary),
            [s05_ref, s06_ref, *finding_artifact_refs],
        )
        manifest = self.renderer.report_manifest(
            summary_ref, s05_ref, s06_ref, finding_refs
        )
        manifest_ref = self.importer.persist_native(
            "ReportManifest",
            "report-manifest",
            manifest["report_manifest_id"],
            cast(dict[str, Any], manifest),
            [summary_ref, s05_ref, s06_ref],
        )
        return ReplayReport(summary, summary_ref, manifest, manifest_ref)

    def _snapshot_payload(self, stage_id: str) -> dict[str, Any]:
        if stage_id == "S01_CANDIDATE":
            return cast(
                dict[str, Any], ReplayCandidateProvider(self.catalog).candidate_snapshot()
            )
        if stage_id == "S02_MECHANISM":
            return cast(
                dict[str, Any], ReplayMechanismProvider(self.catalog).mechanism_snapshot()
            )
        if stage_id == "S03_HYPOTHESIS":
            return cast(
                dict[str, Any], ReplayHypothesisProvider(self.catalog).hypothesis_snapshot()
            )
        if stage_id == "S04_DATA_AND_VERIFICATION":
            return cast(
                dict[str, Any], ReplayDataProvider(self.catalog).verification_snapshot()
            )
        if stage_id == "S05_COUNTEREXAMPLE":
            return cast(
                dict[str, Any],
                ReplayCounterexampleProvider(self.catalog).counterexample_snapshot(),
            )
        if stage_id == "S06_MAGNETOGRAM_QA":
            return cast(
                dict[str, Any],
                ReplayMagnetogramQAProvider(self.catalog).magnetogram_qa_snapshot(),
            )
        raise LedgerIntegrityError(f"not a replay stage: {stage_id}")

    def _verify_cached_preparation(self, preparation: ReplayPreparation) -> None:
        """A retry is cheap, but it still proves all persisted authorities resolve."""
        refs = [
            preparation.configuration_artifact_ref,
            *preparation.source_refs.values(),
            *preparation.snapshot_refs.values(),
            *preparation.validation_artifact_refs.values(),
            *preparation.finding_artifact_refs.values(),
            preparation.decision_request_artifact_ref,
        ]
        for ref in refs:
            self.artifact_store.verify_ref(ref)
        for key in preparation.stage_attempt_keys:
            if self.run_store.get_stage(key) != preparation.stage_runs[key["stage_id"]]:
                raise LedgerIntegrityError(f"cached StageRun drift: {key['stage_id']}")
        if self.run_store.get_run(self.run_id) != preparation.run_record:
            raise LedgerIntegrityError("cached RunRecord drift")

    def _verify_finding_artifacts(
        self,
        finding_refs: list[VersionedRef],
        finding_artifact_refs: list[ArtifactRef],
    ) -> None:
        if len(finding_refs) != len(finding_artifact_refs):
            raise LedgerIntegrityError("report Finding refs and Artifacts differ in count")
        bound: list[VersionedRef] = []
        for ref in finding_artifact_refs:
            self.artifact_store.verify_ref(ref)
            envelope = self.artifact_store.get_envelope(ref["artifact_id"])
            if envelope["artifact_type"] not in {"CompatibilityFinding", "GapFinding"}:
                raise LedgerIntegrityError("report Finding parent is not a Finding Artifact")
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                raise LedgerIntegrityError("Finding Artifact is missing canonical payload")
            bound.append(_object_ref(payload, "finding_id"))
        if bound != finding_refs:
            raise LedgerIntegrityError("report Finding refs do not match Finding Artifacts")

    def _persist_configuration(
        self,
    ) -> tuple[RunConfigurationSnapshot, ArtifactRef]:
        configuration: dict[str, Any] = {
            "configuration_id": "replay-config-shrgt45-0.1.0",
            "schema_version": _SCHEMA_VERSION,
            "provider_bindings": {
                "fixture_catalog": "shrgt45-replay",
                "runtime_s04_package": "0814",
                "provenance_only_package": "0808",
            },
            "provider_versions": {"replay-adapter": "0.1.0"},
            "prompt_versions": {},
            "calculator_registry_version": "none",
            "retry_policy": {"max_attempts": 1},
            "timeout_policy": {"network_enabled": False},
            "feature_flags": {
                "offline": True,
                "execute_historical_code": False,
                "formal_scientific_execution": False,
            },
            "created_at": _FIXED_TS,
        }
        configuration["content_hash"] = canonical_json.content_hash_excluding(
            configuration
        )
        self.catalog.contracts.validate("run-configuration-snapshot", configuration)
        typed = cast(RunConfigurationSnapshot, configuration)
        ref = self.importer.persist_native(
            "RunConfigurationSnapshot",
            "run-configuration-snapshot",
            typed["configuration_id"],
            configuration,
        )
        return typed, ref

    def _persist_findings(
        self,
        findings: list[CompatibilityFinding | GapFinding],
        snapshots: dict[str, ArtifactRef],
    ) -> tuple[list[VersionedRef], dict[str, ArtifactRef]]:
        refs: list[VersionedRef] = []
        artifacts: dict[str, ArtifactRef] = {}
        for finding in findings:
            schema_name = "gap-finding" if "stage_id" in finding else "compatibility-finding"
            artifact_type = "GapFinding" if "stage_id" in finding else "CompatibilityFinding"
            parent_refs = self._finding_parent_refs(finding, snapshots)
            artifacts[finding["finding_id"]] = self.importer.persist_native(
                artifact_type,
                schema_name,
                finding["finding_id"],
                cast(dict[str, Any], finding),
                parent_refs,
            )
            refs.append(_object_ref(finding, "finding_id"))
        return refs, artifacts

    def _finding_parent_refs(
        self,
        finding: CompatibilityFinding | GapFinding,
        snapshots: dict[str, ArtifactRef],
    ) -> list[ArtifactRef]:
        code = finding["code"]
        stages = _INFO_GAP_STAGES.get(code)
        if stages is not None:
            return [snapshots[stages]]
        for spec in self.catalog.case_manifest["declared_finding_specs"]:
            if spec["code"] == code:
                return [snapshots[stage] for stage in spec["related_stage_ids"]]
        raise LedgerIntegrityError(f"Finding is not declared by the Fixture: {code}")

    def _persist_stage_runs(
        self,
        configuration_ref: VersionedRef,
        source_refs: dict[str, ArtifactRef],
        snapshots: dict[str, ArtifactRef],
        reports: dict[str, ValidationReport],
        report_artifact_refs: dict[str, ArtifactRef],
        findings: list[CompatibilityFinding | GapFinding],
        finding_refs: list[VersionedRef],
    ) -> tuple[dict[str, StageRun], list[StageAttemptKey]]:
        finding_ref_by_id = {
            finding["finding_id"]: ref
            for finding, ref in zip(findings, finding_refs, strict=True)
        }
        stage_findings: dict[str, list[VersionedRef]] = {
            stage: [] for stage in _STAGES
        }
        for finding in findings:
            for parent in self._finding_parent_refs(finding, snapshots):
                stage_id = next(
                    stage for stage, snapshot in snapshots.items() if snapshot == parent
                )
                stage_findings[stage_id].append(finding_ref_by_id[finding["finding_id"]])

        stage_runs: dict[str, StageRun] = {}
        keys: list[StageAttemptKey] = []
        dependencies = self.catalog.case_manifest["stage_dependencies"]
        for stage_id in _STAGES:
            source_inputs = [
                source_refs[asset["asset_id"]]
                for asset in self.catalog.stage_assets(stage_id)
            ]
            upstream_inputs = [
                snapshots[upstream] for upstream in dependencies.get(stage_id, [])
            ]
            report_ref = _object_ref(reports[stage_id], "report_id")
            stage: dict[str, Any] = {
                "run_id": self.run_id,
                "stage_id": stage_id,
                "attempt": 1,
                "schema_version": _SCHEMA_VERSION,
                "input_artifact_refs": _unique_artifact_refs(
                    [*source_inputs, *upstream_inputs]
                ),
                "output_artifact_refs": [snapshots[stage_id]],
                "validation_report_refs": [report_ref],
                "finding_refs": stage_findings[stage_id],
                "lineage_edge_refs": [],
                "provider": _PROVIDER,
                "stage_configuration_ref": configuration_ref,
                "execution_status": "SUCCEEDED",
                "started_at": _FIXED_TS,
                "completed_at": _FIXED_TS,
                "failure_refs": [],
            }
            stage["content_hash"] = canonical_json.content_hash_excluding(stage)
            self.catalog.contracts.validate("stage-run", stage)
            typed = cast(StageRun, stage)
            self.run_store.put_stage(typed)
            key: StageAttemptKey = {
                "run_id": self.run_id,
                "stage_id": stage_id,
                "attempt": 1,
                "stage_configuration_ref": configuration_ref,
            }
            if self.run_store.get_stage(key) != typed:
                raise LedgerIntegrityError(f"persisted StageRun differs for {stage_id}")
            stage_runs[stage_id] = typed
            keys.append(key)
            self.artifact_store.verify_ref(report_artifact_refs[stage_id])
        return stage_runs, keys

    def _persist_run_record(
        self,
        configuration_ref: VersionedRef,
        stage_runs: dict[str, StageRun],
        decision_request_ref: ArtifactRef,
    ) -> RunRecord:
        self.artifact_store.verify_ref(decision_request_ref)
        case = self.catalog.case_manifest
        run: RunRecord = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "question_ref": case["research_question_ref"],
            "case_ref": {
                "id": case["case_id"],
                "schema_version": case["schema_version"],
                "content_hash": case["content_hash"],
            },
            "workflow_version": case["workflow_version"],
            "run_mode": "REPLAY",
            "run_purpose": "HISTORICAL_REPLAY",
            "configuration_ref": configuration_ref,
            "execution_status": "WAITING_HUMAN",
            "stage_runs": [
                {
                    "id": f"stage-run-{self.run_id}-{stage_id}-1",
                    "schema_version": stage["schema_version"],
                    "content_hash": stage["content_hash"],
                }
                for stage_id, stage in stage_runs.items()
            ],
            "created_at": _FIXED_TS,
            "started_at": _FIXED_TS,
        }
        self.catalog.contracts.validate("run-record", run)
        self.run_store.put_run(run)
        if self.run_store.get_run(self.run_id) != run:
            raise LedgerIntegrityError("persisted RunRecord differs from prepared Run")
        return run

    def _require_artifact_type(self, ref: ArtifactRef, expected: str) -> None:
        self.artifact_store.verify_ref(ref)
        envelope = self.artifact_store.get_envelope(ref["artifact_id"])
        if envelope["artifact_type"] != expected:
            raise LedgerIntegrityError(
                f"report join requires {expected}, got {envelope['artifact_type']}"
            )


def _object_ref(obj: Any, id_field: str) -> VersionedRef:
    return {
        "id": obj[id_field],
        "schema_version": obj["schema_version"],
        "content_hash": obj["content_hash"],
    }


def _unique_artifact_refs(refs: list[ArtifactRef]) -> list[ArtifactRef]:
    unique: dict[str, ArtifactRef] = {}
    for ref in refs:
        existing = unique.setdefault(ref["artifact_id"], ref)
        if existing != ref:
            raise LedgerIntegrityError(
                f"conflicting ArtifactRefs for {ref['artifact_id']}"
            )
    return list(unique.values())
