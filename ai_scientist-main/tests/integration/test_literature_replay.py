from __future__ import annotations

from pathlib import Path

from ai_scientist_mvp.application.literature_replay_service import (
    LiteratureReplayService,
)
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.infrastructure.storage import LocalStorage
from ai_scientist_mvp.providers.shrgt45_replay import (
    ManifestAssetCatalog,
    ReplayArtifactImporter,
)
from ai_scientist_mvp.skills.snapshot_search import SnapshotPaperSearchProvider

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures" / "shrgt45"
SNAPSHOT = PROJECT_ROOT / "literature" / "shrgt45.snapshot.json"


def test_shrgt45_literature_replay_is_offline_auditable_and_idempotent(
    tmp_path: Path,
) -> None:
    catalog = ManifestAssetCatalog(FIXTURES)
    storage = LocalStorage(tmp_path, "literature-replay")
    importer = ReplayArtifactImporter(
        storage.artifact_store,
        catalog,
        "literature-replay",
        "literature-task",
    )
    provider = SnapshotPaperSearchProvider(PROJECT_ROOT, SNAPSHOT)
    service = LiteratureReplayService(catalog, importer, provider)

    first = service.run()
    second = service.run()

    assert first.mechanism_artifact_ref == second.mechanism_artifact_ref
    assert first.audit_hash == second.audit_hash
    assert first.evidence_count == 15
    assert len(first.quote_verifications) == 15
    assert all(result.status == "VERIFIED" for result in first.quote_verifications)
    assert first.network_accessed is False
    assert first.credential_accessed is False
    assert first.scientific_verdict == "NOT_EVALUATED"
    assert first.result_maturity == "DEVELOPMENTAL"
    assert canonical_json.content_hash(first.audit_payload()) == first.audit_hash

    envelope = storage.artifact_store.get_envelope(
        first.mechanism_artifact_ref["artifact_id"]
    )
    assert envelope["artifact_type"] == "MechanismSnapshot"
    assert envelope["origin_mode"] == "DERIVED"
    assert envelope["authority_mode"] == "CANONICAL_JSON"
    assert envelope["source_asset_refs"] == [first.source_ref]
    assert envelope["parent_refs"] == envelope["derived_from_refs"]
    storage.artifact_store.verify_ref(first.mechanism_artifact_ref)
    storage.close()
