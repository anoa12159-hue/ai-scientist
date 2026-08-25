"""Hash-verified fixed-corpus search and explicit offline fallback."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_scientist_mvp.skills.paper_search import (
    PaperSearchHit,
    PaperSearchProvider,
    PaperSearchQuery,
    PaperSearchValidationError,
)


class PaperSearchUnavailableError(RuntimeError):
    """A provider is temporarily unavailable and may use an offline fallback."""


@dataclass(frozen=True)
class SnapshotDocument:
    paper_id: str
    title: str
    relative_path: str
    sha256: str
    byte_size: int
    year: int | None
    fields_of_study: tuple[str, ...]
    text: str


class SnapshotPaperSearchProvider:
    """Search immutable local text only after validating its manifest and bytes."""

    provider_name = "fixed-corpus-snapshot"

    def __init__(self, project_root: Path, manifest_path: Path) -> None:
        self._project_root = project_root.resolve()
        manifest = _load_manifest(self._project_root, manifest_path)
        self.corpus_version = _required_string(manifest, "snapshot_version")
        self.snapshot_id = _required_string(manifest, "snapshot_id")
        raw_documents = manifest.get("documents")
        if not isinstance(raw_documents, list) or not raw_documents:
            raise PaperSearchValidationError("snapshot documents must be a non-empty list")
        self._documents = tuple(
            _load_document(self._project_root, raw_document) for raw_document in raw_documents
        )
        ids = [document.paper_id for document in self._documents]
        if len(ids) != len(set(ids)):
            raise PaperSearchValidationError("snapshot paper_id values must be unique")

    def search(self, query: PaperSearchQuery) -> Sequence[PaperSearchHit]:
        candidates: list[tuple[int, SnapshotDocument]] = []
        for document in self._documents:
            if not _matches_filters(document, query):
                continue
            searchable = f"{document.title}\n{document.text}".casefold()
            score = sum(searchable.count(term) for term in query.terms)
            if score:
                candidates.append((score, document))
        candidates.sort(key=lambda item: (-item[0], item[1].paper_id))
        return tuple(
            PaperSearchHit(
                paper_id=document.paper_id,
                title=document.title,
                year=document.year,
                venue=self.snapshot_id,
                url=document.relative_path,
                source=f"snapshot:{self.corpus_version}",
            )
            for _, document in candidates[: query.limit]
        )


class FallbackPaperSearchProvider:
    """Use the snapshot only for an explicit provider-unavailable failure."""

    provider_name = "primary-with-snapshot-fallback"

    def __init__(
        self,
        primary: PaperSearchProvider,
        fallback: PaperSearchProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.corpus_version = (
            f"primary={primary.corpus_version};fallback={fallback.corpus_version}"
        )
        self.last_provider: str | None = None

    def search(self, query: PaperSearchQuery) -> Sequence[PaperSearchHit]:
        try:
            hits = self.primary.search(query)
            self.last_provider = self.primary.provider_name
            return hits
        except PaperSearchUnavailableError:
            hits = self.fallback.search(query)
            self.last_provider = self.fallback.provider_name
            return hits


def _load_manifest(project_root: Path, manifest_path: Path) -> Mapping[str, Any]:
    resolved = manifest_path.resolve()
    if not resolved.is_relative_to(project_root):
        raise PaperSearchValidationError("snapshot manifest must stay inside project_root")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperSearchValidationError("snapshot manifest is not readable JSON") from error
    if not isinstance(payload, dict):
        raise PaperSearchValidationError("snapshot manifest must be a JSON object")
    return payload


def _load_document(project_root: Path, raw: object) -> SnapshotDocument:
    if not isinstance(raw, dict):
        raise PaperSearchValidationError("snapshot document must be a JSON object")
    relative_path = _required_string(raw, "relative_path")
    candidate = project_root / relative_path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(project_root) or candidate.is_symlink():
        raise PaperSearchValidationError("snapshot document path escapes project_root")
    try:
        content = resolved.read_bytes()
    except OSError as error:
        raise PaperSearchValidationError("snapshot document is not readable") from error
    expected_size = raw.get("byte_size")
    if not isinstance(expected_size, int) or expected_size < 0 or len(content) != expected_size:
        raise PaperSearchValidationError("snapshot document byte_size mismatch")
    expected_hash = _required_string(raw, "sha256").upper()
    actual_hash = hashlib.sha256(content).hexdigest().upper()
    if actual_hash != expected_hash:
        raise PaperSearchValidationError("snapshot document SHA-256 mismatch")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PaperSearchValidationError("snapshot document must be UTF-8 text") from error
    year = raw.get("year")
    if year is not None and (not isinstance(year, int) or year < 0):
        raise PaperSearchValidationError("snapshot document year must be non-negative")
    raw_fields = raw.get("fields_of_study", [])
    if not isinstance(raw_fields, list) or not all(isinstance(field, str) for field in raw_fields):
        raise PaperSearchValidationError("fields_of_study must be a string list")
    return SnapshotDocument(
        paper_id=_required_string(raw, "paper_id"),
        title=_required_string(raw, "title"),
        relative_path=relative_path,
        sha256=actual_hash,
        byte_size=len(content),
        year=year,
        fields_of_study=tuple(field.casefold() for field in raw_fields),
        text=text,
    )


def _required_string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PaperSearchValidationError(f"snapshot {key} must be a non-empty string")
    return value.strip()


def _matches_filters(document: SnapshotDocument, query: PaperSearchQuery) -> bool:
    if query.year_from is not None and (document.year is None or document.year < query.year_from):
        return False
    if query.year_to is not None and (document.year is None or document.year > query.year_to):
        return False
    available_fields = " ".join(document.fields_of_study)
    return all(field in available_fields for field in query.fields_of_study)
