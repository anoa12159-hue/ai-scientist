"""Public boundaries for the offline Replay adapter layer."""
from __future__ import annotations

from typing import Any, Protocol

from ai_scientist_mvp.domain.store_types import StageAttemptKey
from ai_scientist_mvp.domain.types import (
    ArtifactRef,
    CandidateSnapshot,
    CompatibilityFinding,
    CounterexampleSnapshot,
    DecisionRequest,
    GapFinding,
    HypothesisSnapshot,
    MagnetogramQASnapshot,
    MechanismSnapshot,
    ReportManifest,
    ResearchSummary,
    SourceAssetRef,
    ValidationReport,
    VerificationSnapshot,
    VersionedRef,
)

SCIENTIFIC_VERDICT = "NOT_EVALUATED"
RESULT_MATURITY = "DEVELOPMENTAL"
AUTHORIZATION_STATUS = "NOT_AUTHORIZED"
RELEASE_SCOPE = "NOT_READY"


class ReplayAssetCatalog(Protocol):
    """Validated view over the immutable T003 Fixture."""

    def load(self) -> None: ...

    def asset(self, asset_id: str) -> SourceAssetRef: ...

    def resolve_ref(self, ref: VersionedRef) -> SourceAssetRef: ...

    def default_s04_assets(self) -> list[SourceAssetRef]: ...

    def provenance_assets(self) -> list[SourceAssetRef]: ...

    def stage_assets(self, stage_id: str) -> list[SourceAssetRef]: ...

    def read_bytes(self, asset: SourceAssetRef) -> bytes: ...


class ReplayArtifactImporter(Protocol):
    """Persist source, derived, and native objects through ArtifactStore."""

    def import_source(self, asset_id: str) -> ArtifactRef: ...

    def import_summary(
        self,
        artifact_type: str,
        schema_name: str,
        payload: dict[str, Any],
        source_asset_refs: list[VersionedRef],
        parent_refs: list[ArtifactRef],
    ) -> ArtifactRef: ...

    def persist_native(
        self,
        artifact_type: str,
        schema_name: str,
        logical_id: str,
        payload: dict[str, Any],
        parent_refs: list[ArtifactRef] | None = None,
    ) -> ArtifactRef: ...


class ReplayCandidateProvider(Protocol):
    def candidate_snapshot(self) -> CandidateSnapshot: ...


class ReplayMechanismProvider(Protocol):
    def mechanism_snapshot(self) -> MechanismSnapshot: ...


class ReplayHypothesisProvider(Protocol):
    def hypothesis_snapshot(self) -> HypothesisSnapshot: ...


class ReplayDataProvider(Protocol):
    def verification_snapshot(self) -> VerificationSnapshot: ...


class ReplayCounterexampleProvider(Protocol):
    def counterexample_snapshot(self) -> CounterexampleSnapshot: ...


class ReplayMagnetogramQAProvider(Protocol):
    def magnetogram_qa_snapshot(self) -> MagnetogramQASnapshot: ...


class DeterministicValidator(Protocol):
    def validate(
        self, target_ref: ArtifactRef, checks: list[dict[str, Any]]
    ) -> ValidationReport: ...


class ReplayFindingFactory(Protocol):
    def build_acceptable_findings(
        self, stage_refs: dict[str, ArtifactRef]
    ) -> list[CompatibilityFinding | GapFinding]: ...

    def build_informational_gaps(self) -> list[GapFinding]: ...


class FixtureImportDecisionRequestFactory(Protocol):
    def build(
        self,
        artifact_refs: list[ArtifactRef],
        findings: list[CompatibilityFinding | GapFinding],
        stage_attempt_keys: list[StageAttemptKey],
    ) -> DecisionRequest: ...


class DevelopmentalReportRenderer(Protocol):
    def research_summary(self, finding_refs: list[VersionedRef]) -> ResearchSummary: ...

    def report_manifest(
        self,
        research_summary_ref: ArtifactRef,
        s05_ref: ArtifactRef,
        s06_ref: ArtifactRef,
        finding_refs: list[VersionedRef],
    ) -> ReportManifest: ...
