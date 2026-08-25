"""Offline paper-search Skill with an injectable provider boundary.

The Skill owns query validation, deterministic result shaping, de-duplication,
and bounded fan-out. Providers own retrieval and may later be backed by a
versioned local corpus or an explicitly authorized online service. The default
provider in this module is an in-memory index, so importing and testing the
Skill never accesses the network or credentials.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

_TERM_PATTERN = re.compile(r"[\w]+", re.UNICODE)


class PaperSearchValidationError(ValueError):
    """Raised when a paper-search query or provider result is invalid."""


@dataclass(frozen=True)
class PaperSearchQuery:
    """A bounded, reproducible search request."""

    text: str
    limit: int = 10
    year_from: int | None = None
    year_to: int | None = None
    fields_of_study: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_text = " ".join(self.text.split())
        if not normalized_text:
            raise PaperSearchValidationError("query text must not be empty")
        if len(normalized_text) > 1000:
            raise PaperSearchValidationError("query text must not exceed 1000 characters")
        if self.limit < 1:
            raise PaperSearchValidationError("limit must be positive")
        if self.year_from is not None and self.year_from < 0:
            raise PaperSearchValidationError("year_from must not be negative")
        if self.year_to is not None and self.year_to < 0:
            raise PaperSearchValidationError("year_to must not be negative")
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise PaperSearchValidationError("year_from must not be after year_to")
        normalized_fields = tuple(
            sorted(_normalize_field(field) for field in self.fields_of_study if field.strip())
        )
        object.__setattr__(self, "text", normalized_text)
        object.__setattr__(self, "fields_of_study", normalized_fields)

    @property
    def terms(self) -> tuple[str, ...]:
        """Return unique case-folded terms in stable lexical order."""

        return tuple(sorted(set(_TERM_PATTERN.findall(self.text.casefold()))))


@dataclass(frozen=True)
class PaperSearchHit:
    """Provider-neutral paper metadata; no full text is stored here."""

    paper_id: str
    title: str
    authors: tuple[str, ...] = ()
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    url: str | None = None
    citation_count: int = 0
    source: str = "offline"

    def __post_init__(self) -> None:
        if not self.paper_id.strip() or not self.title.strip():
            raise PaperSearchValidationError("paper_id and title must not be empty")
        if self.year is not None and self.year < 0:
            raise PaperSearchValidationError("paper year must not be negative")
        if self.citation_count < 0:
            raise PaperSearchValidationError("citation_count must not be negative")


class PaperSearchProvider(Protocol):
    """Retrieval boundary implemented by local or authorized providers."""

    provider_name: str
    corpus_version: str

    def search(self, query: PaperSearchQuery) -> Sequence[PaperSearchHit]:
        """Return candidate metadata for one query without network side effects."""


@dataclass(frozen=True)
class PaperSearchResult:
    """Stable Skill output suitable for an Artifact projection."""

    query: PaperSearchQuery
    hits: tuple[PaperSearchHit, ...]
    provider: str
    corpus_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "query": {
                "text": self.query.text,
                "limit": self.query.limit,
                "year_from": self.query.year_from,
                "year_to": self.query.year_to,
                "fields_of_study": list(self.query.fields_of_study),
            },
            "provider": self.provider,
            "corpus_version": self.corpus_version,
            "hits": [
                {
                    "paper_id": hit.paper_id,
                    "title": hit.title,
                    "authors": list(hit.authors),
                    "abstract": hit.abstract,
                    "year": hit.year,
                    "venue": hit.venue,
                    "url": hit.url,
                    "citation_count": hit.citation_count,
                    "source": hit.source,
                }
                for hit in self.hits
            ],
        }


class InMemoryPaperSearchProvider:
    """Small deterministic index for offline fixtures and tests."""

    provider_name = "in-memory"

    def __init__(
        self, papers: Iterable[PaperSearchHit], *, corpus_version: str = "fixture-1"
    ) -> None:
        entries = tuple(papers)
        paper_ids = [paper.paper_id for paper in entries]
        if len(set(paper_ids)) != len(paper_ids):
            raise PaperSearchValidationError("paper_id values must be unique")
        if not corpus_version.strip():
            raise PaperSearchValidationError("corpus_version must not be empty")
        self._papers = entries
        self.corpus_version = corpus_version

    def search(self, query: PaperSearchQuery) -> Sequence[PaperSearchHit]:
        terms = query.terms
        candidates: list[tuple[int, PaperSearchHit]] = []
        for paper in self._papers:
            if not _matches_filters(paper, query):
                continue
            searchable = " ".join(
                (paper.title, paper.abstract or "", paper.venue or "", " ".join(paper.authors))
            ).casefold()
            score = sum(searchable.count(term) for term in terms)
            if score or not terms:
                candidates.append((score, paper))
        candidates.sort(
            key=lambda item: (
                -item[0],
                -item[1].citation_count,
                -(item[1].year or 0),
                item[1].paper_id,
            )
        )
        return tuple(paper for _, paper in candidates[: query.limit])


class PaperSearchSkill:
    """Compose one or more bounded searches without retaining prompt text."""

    def __init__(self, provider: PaperSearchProvider, *, max_limit: int = 50) -> None:
        if max_limit < 1:
            raise ValueError("max_limit must be positive")
        self.provider = provider
        self.max_limit = max_limit

    def search(self, query: PaperSearchQuery) -> PaperSearchResult:
        if query.limit > self.max_limit:
            raise PaperSearchValidationError(f"limit must not exceed {self.max_limit}")
        hits = _deduplicate(self.provider.search(query))
        return PaperSearchResult(
            query=query,
            hits=tuple(hits[: query.limit]),
            provider=self.provider.provider_name,
            corpus_version=self.provider.corpus_version,
        )

    def search_many(
        self, queries: Sequence[PaperSearchQuery], *, limit: int | None = None
    ) -> tuple[PaperSearchHit, ...]:
        """Merge multi-angle searches with stable first-seen de-duplication."""

        merged: list[PaperSearchHit] = []
        seen: set[str] = set()
        for query in queries:
            result = self.search(query)
            for hit in result.hits:
                if hit.paper_id not in seen:
                    seen.add(hit.paper_id)
                    merged.append(hit)
                    if limit is not None and len(merged) >= limit:
                        return tuple(merged)
        return tuple(merged)


def _matches_filters(paper: PaperSearchHit, query: PaperSearchQuery) -> bool:
    if query.year_from is not None and (paper.year is None or paper.year < query.year_from):
        return False
    if query.year_to is not None and (paper.year is None or paper.year > query.year_to):
        return False
    if query.fields_of_study:
        searchable = " ".join((paper.title, paper.abstract or "", paper.venue or "")).casefold()
        if not all(field in searchable for field in query.fields_of_study):
            return False
    return True


def _normalize_field(field: str) -> str:
    return " ".join(field.split()).casefold()


def _deduplicate(hits: Sequence[PaperSearchHit]) -> list[PaperSearchHit]:
    unique: list[PaperSearchHit] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.paper_id not in seen:
            seen.add(hit.paper_id)
            unique.append(hit)
    return unique
