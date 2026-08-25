from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_scientist_mvp.skills.paper_search import (
    PaperSearchHit,
    PaperSearchQuery,
    PaperSearchSkill,
    PaperSearchValidationError,
)
from ai_scientist_mvp.skills.snapshot_search import (
    FallbackPaperSearchProvider,
    PaperSearchUnavailableError,
    SnapshotPaperSearchProvider,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_MANIFEST = PROJECT_ROOT / "literature" / "shrgt45.snapshot.json"


class PrimaryProvider:
    provider_name = "primary"
    corpus_version = "online-v1"

    def __init__(self, *, unavailable: bool = False, broken: bool = False) -> None:
        self.unavailable = unavailable
        self.broken = broken

    def search(self, query: PaperSearchQuery) -> tuple[PaperSearchHit, ...]:
        if self.unavailable:
            raise PaperSearchUnavailableError("offline")
        if self.broken:
            raise RuntimeError("provider bug")
        return (PaperSearchHit("primary-result", "Primary result", source="primary"),)


def test_real_snapshot_validates_and_searches_without_network() -> None:
    provider = SnapshotPaperSearchProvider(PROJECT_ROOT, SNAPSHOT_MANIFEST)
    result = PaperSearchSkill(provider).search(
        PaperSearchQuery("SHRGT45 magnetic shear", limit=3)
    )

    assert provider.snapshot_id == "shrgt45-literature-fixture"
    assert result.provider == "fixed-corpus-snapshot"
    assert result.hits
    assert result.hits[0].source == "snapshot:2026-08-20"
    assert all(hit.url and not Path(hit.url).is_absolute() for hit in result.hits)


def test_snapshot_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    document = tmp_path / "paper.md"
    document.write_text("fixed corpus", encoding="utf-8")
    manifest = _write_manifest(tmp_path, document, sha256="0" * 64)

    with pytest.raises(PaperSearchValidationError, match="SHA-256 mismatch"):
        SnapshotPaperSearchProvider(tmp_path, manifest)


def test_snapshot_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    manifest = _write_manifest(tmp_path, outside, relative_path="../outside.md")

    with pytest.raises(PaperSearchValidationError, match="escapes project_root"):
        SnapshotPaperSearchProvider(tmp_path, manifest)


def test_fallback_only_handles_explicit_unavailability() -> None:
    snapshot = SnapshotPaperSearchProvider(PROJECT_ROOT, SNAPSHOT_MANIFEST)
    fallback = FallbackPaperSearchProvider(PrimaryProvider(unavailable=True), snapshot)
    hits = fallback.search(PaperSearchQuery("SHRGT45"))

    assert hits
    assert fallback.last_provider == "fixed-corpus-snapshot"

    broken = FallbackPaperSearchProvider(PrimaryProvider(broken=True), snapshot)
    with pytest.raises(RuntimeError, match="provider bug"):
        broken.search(PaperSearchQuery("SHRGT45"))


def test_primary_result_is_preferred_when_available() -> None:
    snapshot = SnapshotPaperSearchProvider(PROJECT_ROOT, SNAPSHOT_MANIFEST)
    provider = FallbackPaperSearchProvider(PrimaryProvider(), snapshot)

    assert provider.search(PaperSearchQuery("anything"))[0].paper_id == "primary-result"
    assert provider.last_provider == "primary"


def _write_manifest(
    root: Path,
    document: Path,
    *,
    sha256: str | None = None,
    relative_path: str = "paper.md",
) -> Path:
    content = document.read_bytes()
    payload = {
        "snapshot_id": "test",
        "snapshot_version": "v1",
        "documents": [
            {
                "paper_id": "paper-1",
                "title": "Paper",
                "relative_path": relative_path,
                "sha256": sha256 or hashlib.sha256(content).hexdigest(),
                "byte_size": len(content),
                "year": 2026,
                "fields_of_study": ["solar physics"],
            }
        ],
    }
    manifest = root / "snapshot.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest
