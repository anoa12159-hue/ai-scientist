"""Auditable offline literature replay over the frozen SHRGT45 Fixture."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.types import ArtifactRef, MechanismSnapshot, VersionedRef
from ai_scientist_mvp.providers.replay_protocols import (
    ReplayArtifactImporter,
    ReplayAssetCatalog,
)
from ai_scientist_mvp.skills.mechanism_brief import (
    EvidenceTable,
    parse_mechanism_brief,
    project_mechanism_snapshot,
)
from ai_scientist_mvp.skills.paper_search import (
    PaperSearchProvider,
    PaperSearchQuery,
    PaperSearchSkill,
)
from ai_scientist_mvp.skills.quote_verifier import (
    QuoteVerificationRequest,
    QuoteVerificationResult,
    QuoteVerifier,
)

_V22_ASSET_ID = "s02.mechanism-brief-v2_2-historical"


@dataclass(frozen=True)
class LiteratureReplayResult:
    replay_id: str
    corpus_version: str
    query: str
    search_hit_ids: tuple[str, ...]
    source_ref: VersionedRef
    source_asset_sha256: str
    evidence_count: int
    quote_verifications: tuple[QuoteVerificationResult, ...]
    mechanism_snapshot: MechanismSnapshot
    mechanism_artifact_ref: ArtifactRef
    network_accessed: Literal[False]
    credential_accessed: Literal[False]
    scientific_verdict: Literal["NOT_EVALUATED"]
    result_maturity: Literal["DEVELOPMENTAL"]
    audit_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            **self.audit_payload(),
            "audit_hash": self.audit_hash,
        }

    def audit_payload(self) -> dict[str, object]:
        return {
            "replay_id": self.replay_id,
            "corpus_version": self.corpus_version,
            "query": self.query,
            "search_hit_ids": list(self.search_hit_ids),
            "source_ref": self.source_ref,
            "source_asset_sha256": self.source_asset_sha256,
            "evidence_count": self.evidence_count,
            "quote_verifications": [result.as_dict() for result in self.quote_verifications],
            "mechanism_snapshot": self.mechanism_snapshot,
            "mechanism_artifact_ref": self.mechanism_artifact_ref,
            "network_accessed": self.network_accessed,
            "credential_accessed": self.credential_accessed,
            "scientific_verdict": self.scientific_verdict,
            "result_maturity": self.result_maturity,
        }


class LiteratureReplayService:
    """Validate, search, quote-audit, project, and persist the V2.2 source."""

    def __init__(
        self,
        catalog: ReplayAssetCatalog,
        importer: ReplayArtifactImporter,
        search_provider: PaperSearchProvider,
    ) -> None:
        self.catalog = catalog
        self.importer = importer
        self.search_provider = search_provider

    def run(self, *, query: str = "SHRGT45 mechanism evidence") -> LiteratureReplayResult:
        self.catalog.load()
        source_asset = self.catalog.asset(_V22_ASSET_ID)
        source_bytes = self.catalog.read_bytes(source_asset)
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("MechanismBrief source must be UTF-8") from error
        brief = parse_mechanism_brief(source_text)
        search_result = PaperSearchSkill(self.search_provider).search(
            PaperSearchQuery(query, limit=10)
        )
        search_hit_ids = tuple(hit.paper_id for hit in search_result.hits)
        if _V22_ASSET_ID not in search_hit_ids:
            raise ValueError("fixed corpus search did not recover the bound V2.2 source")
        verifications = _verify_evidence_rows(brief.evidence_tables, source_text)
        source_ref: VersionedRef = {
            "id": source_asset["asset_id"],
            "schema_version": source_asset["schema_version"],
            "content_hash": source_asset["content_hash"],
        }
        snapshot = project_mechanism_snapshot(
            brief,
            snapshot_id="mechanism-shrgt45-v22-literature-replay",
            source_version="V2.2",
            source_refs=[source_ref],
        )
        parent_ref = self.importer.import_source(source_asset["asset_id"])
        mechanism_ref = self.importer.import_summary(
            "MechanismSnapshot",
            "mechanism-snapshot",
            dict(snapshot),
            [source_ref],
            [parent_ref],
        )
        audit_payload: dict[str, object] = {
            "replay_id": "shrgt45-v22-literature-replay",
            "corpus_version": search_result.corpus_version,
            "query": search_result.query.text,
            "search_hit_ids": list(search_hit_ids),
            "source_ref": source_ref,
            "source_asset_sha256": source_asset["asset_sha256"].upper(),
            "evidence_count": brief.evidence_count,
            "quote_verifications": [result.as_dict() for result in verifications],
            "mechanism_snapshot": snapshot,
            "mechanism_artifact_ref": mechanism_ref,
            "network_accessed": False,
            "credential_accessed": False,
            "scientific_verdict": "NOT_EVALUATED",
            "result_maturity": "DEVELOPMENTAL",
        }
        return LiteratureReplayResult(
            replay_id="shrgt45-v22-literature-replay",
            corpus_version=search_result.corpus_version,
            query=search_result.query.text,
            search_hit_ids=search_hit_ids,
            source_ref=source_ref,
            source_asset_sha256=source_asset["asset_sha256"].upper(),
            evidence_count=brief.evidence_count,
            quote_verifications=verifications,
            mechanism_snapshot=snapshot,
            mechanism_artifact_ref=mechanism_ref,
            network_accessed=False,
            credential_accessed=False,
            scientific_verdict="NOT_EVALUATED",
            result_maturity="DEVELOPMENTAL",
            audit_hash=canonical_json.content_hash(audit_payload),
        )


def _verify_evidence_rows(
    tables: tuple[EvidenceTable, ...], source_text: str
) -> tuple[QuoteVerificationResult, ...]:
    verifier = QuoteVerifier()
    results: list[QuoteVerificationResult] = []
    for table in tables:
        for row in table.rows:
            markdown_quote = row.summary.replace("|", r"\|")
            result = verifier.verify(
                QuoteVerificationRequest(
                    paper_id=f"{_V22_ASSET_ID}:{row.evidence_id}",
                    quote=markdown_quote,
                    source_text=source_text,
                )
            )
            if result.status != "VERIFIED":
                raise ValueError(f"evidence row not found exactly: {row.evidence_id}")
            results.append(result)
    return tuple(results)
