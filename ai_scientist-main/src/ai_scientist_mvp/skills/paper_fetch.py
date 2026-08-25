"""Offline-safe full-text caching and citation-chain expansion boundaries."""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlparse


class PaperFetchValidationError(ValueError):
    """Raised when a fetch request or returned document fails validation."""


@dataclass(frozen=True)
class PaperFetchRequest:
    paper_id: str
    source_uri: str
    max_bytes: int = 10_000_000
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise PaperFetchValidationError("paper_id must not be empty")
        parsed = urlparse(self.source_uri)
        if (
            parsed.scheme not in {"file", "http", "https"}
            or not parsed.netloc
            and parsed.scheme != "file"
            or parsed.scheme == "file"
            and not parsed.path
        ):
            raise PaperFetchValidationError(
                "source_uri must be an absolute file, HTTP, or HTTPS URI"
            )
        if parsed.username or parsed.password:
            raise PaperFetchValidationError("source_uri must not contain credentials")
        sensitive_query_keys = {"api_key", "apikey", "key", "token", "secret", "password"}
        if any(key.casefold() in sensitive_query_keys for key, _ in parse_qsl(parsed.query)):
            raise PaperFetchValidationError(
                "source_uri must not contain credential query parameters"
            )
        if self.max_bytes < 1:
            raise PaperFetchValidationError("max_bytes must be positive")
        if self.expected_sha256 is not None:
            digest = self.expected_sha256.upper()
            if len(digest) != 64 or any(
                character not in "0123456789ABCDEF" for character in digest
            ):
                raise PaperFetchValidationError("expected_sha256 must be a SHA-256 hex digest")
            object.__setattr__(self, "expected_sha256", digest)


@dataclass(frozen=True)
class PaperDocument:
    paper_id: str
    source_uri: str
    media_type: str
    content: bytes
    sha256: str
    cache_version: str

    @property
    def byte_size(self) -> int:
        return len(self.content)

    def metadata(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "source_uri": self.source_uri,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "cache_version": self.cache_version,
        }


class PaperContentFetcher(Protocol):
    def fetch(self, request: PaperFetchRequest) -> tuple[bytes, str]:
        """Fetch bytes and media type; implementations own I/O policy."""


class PaperDocumentCache(Protocol):
    cache_version: str

    def get(self, key: str) -> PaperDocument | None: ...

    def put(self, key: str, document: PaperDocument) -> None: ...


class CitationProvider(Protocol):
    def citations(self, paper_id: str) -> Sequence[str]:
        """Return direct outgoing citation IDs without mutating the graph."""


class InMemoryPaperDocumentCache:
    """Deterministic cache used by offline runs and tests."""

    def __init__(self, *, cache_version: str = "memory-v1") -> None:
        if not cache_version.strip():
            raise PaperFetchValidationError("cache_version must not be empty")
        self.cache_version = cache_version
        self._documents: dict[str, PaperDocument] = {}

    def get(self, key: str) -> PaperDocument | None:
        return self._documents.get(key)

    def put(self, key: str, document: PaperDocument) -> None:
        self._documents[key] = document


@dataclass(frozen=True)
class PaperFetchResult:
    document: PaperDocument
    cache_hit: bool


@dataclass(frozen=True)
class CitationExpansion:
    seed_ids: tuple[str, ...]
    paper_ids: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    max_depth: int


class PaperFetchSkill:
    """Fetch validated bytes, cache them by request identity, and expand citations."""

    def __init__(
        self,
        fetcher: PaperContentFetcher,
        cache: PaperDocumentCache,
        *,
        cache_version: str | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.cache = cache
        self.cache_version = cache_version or cache.cache_version
        if not self.cache_version.strip():
            raise PaperFetchValidationError("cache_version must not be empty")

    def fetch(self, request: PaperFetchRequest) -> PaperFetchResult:
        key = _request_key(request, self.cache_version)
        cached = self.cache.get(key)
        if cached is not None:
            if cached.cache_version != self.cache_version:
                raise PaperFetchValidationError("cached document version does not match Skill")
            _validate_document(request, cached)
            return PaperFetchResult(document=cached, cache_hit=True)
        content, media_type = self.fetcher.fetch(request)
        if not isinstance(content, bytes):
            raise PaperFetchValidationError("fetcher must return bytes")
        if len(content) > request.max_bytes:
            raise PaperFetchValidationError("fetched paper exceeds max_bytes")
        digest = hashlib.sha256(content).hexdigest().upper()
        if request.expected_sha256 is not None and digest != request.expected_sha256:
            raise PaperFetchValidationError("fetched paper SHA-256 does not match expected_sha256")
        if not media_type.strip():
            raise PaperFetchValidationError("media_type must not be empty")
        document = PaperDocument(
            paper_id=request.paper_id,
            source_uri=request.source_uri,
            media_type=media_type,
            content=content,
            sha256=digest,
            cache_version=self.cache_version,
        )
        self.cache.put(key, document)
        return PaperFetchResult(document=document, cache_hit=False)

    def expand_citations(
        self,
        seed_ids: Sequence[str],
        provider: CitationProvider,
        *,
        max_depth: int = 1,
        max_nodes: int = 100,
    ) -> CitationExpansion:
        if max_depth < 0:
            raise PaperFetchValidationError("max_depth must not be negative")
        if max_nodes < 1:
            raise PaperFetchValidationError("max_nodes must be positive")
        seeds = _unique_ids(seed_ids)
        if not seeds:
            raise PaperFetchValidationError("seed_ids must not be empty")
        visited = set(seeds)
        ordered = list(seeds)
        edges: list[tuple[str, str]] = []
        frontier = list(seeds)
        for _ in range(max_depth):
            next_frontier: list[str] = []
            for paper_id in frontier:
                for cited_id in sorted(set(provider.citations(paper_id))):
                    if not cited_id.strip():
                        continue
                    edges.append((paper_id, cited_id))
                    if cited_id not in visited and len(ordered) < max_nodes:
                        visited.add(cited_id)
                        ordered.append(cited_id)
                        next_frontier.append(cited_id)
            frontier = next_frontier
            if not frontier or len(ordered) >= max_nodes:
                break
        return CitationExpansion(tuple(seeds), tuple(ordered), tuple(edges), max_depth)


def _request_key(request: PaperFetchRequest, cache_version: str) -> str:
    identity = "\x00".join(
        (cache_version, request.paper_id, request.source_uri, request.expected_sha256 or "")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest().upper()


def _validate_document(request: PaperFetchRequest, document: PaperDocument) -> None:
    if document.paper_id != request.paper_id or document.source_uri != request.source_uri:
        raise PaperFetchValidationError("cached document identity does not match request")
    if document.byte_size > request.max_bytes:
        raise PaperFetchValidationError("cached paper exceeds max_bytes")
    if not document.media_type.strip():
        raise PaperFetchValidationError("cached paper media_type must not be empty")
    digest = hashlib.sha256(document.content).hexdigest().upper()
    if digest != document.sha256:
        raise PaperFetchValidationError("cached paper content hash is invalid")
    if request.expected_sha256 is not None and digest != request.expected_sha256:
        raise PaperFetchValidationError("cached paper SHA-256 does not match expected_sha256")


def _unique_ids(ids: Sequence[str]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for paper_id in ids:
        normalized = paper_id.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return tuple(unique)
