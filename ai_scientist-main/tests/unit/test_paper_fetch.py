from __future__ import annotations

import hashlib

import pytest

from ai_scientist_mvp.skills.paper_fetch import (
    InMemoryPaperDocumentCache,
    PaperFetchRequest,
    PaperFetchSkill,
    PaperFetchValidationError,
)


class FakeFetcher:
    def __init__(self, content: bytes = b"paper") -> None:
        self.content = content
        self.calls = 0

    def fetch(self, request: PaperFetchRequest) -> tuple[bytes, str]:
        self.calls += 1
        return self.content, "text/plain"


class FakeCitationProvider:
    def __init__(self, graph: dict[str, list[str]]) -> None:
        self.graph = graph

    def citations(self, paper_id: str) -> list[str]:
        return self.graph.get(paper_id, [])


def test_fetch_validates_hash_and_reuses_versioned_cache() -> None:
    fetcher = FakeFetcher()
    skill = PaperFetchSkill(fetcher, InMemoryPaperDocumentCache(cache_version="cache-v1"))
    digest = hashlib.sha256(b"paper").hexdigest()
    request = PaperFetchRequest("paper-1", "file:///fixture/paper.txt", expected_sha256=digest)

    first = skill.fetch(request)
    second = skill.fetch(request)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert fetcher.calls == 1
    assert first.document.metadata()["cache_version"] == "cache-v1"


def test_fetch_rejects_hash_mismatch_and_credentials_in_uri() -> None:
    skill = PaperFetchSkill(FakeFetcher(), InMemoryPaperDocumentCache())
    with pytest.raises(PaperFetchValidationError):
        skill.fetch(
            PaperFetchRequest(
                "paper-1", "https://example.test/paper", expected_sha256="0" * 64
            )
        )
    with pytest.raises(PaperFetchValidationError):
        PaperFetchRequest("paper-1", "https://user:password@example.test/paper")


def test_citation_expansion_is_bounded_and_deterministic() -> None:
    skill = PaperFetchSkill(FakeFetcher(), InMemoryPaperDocumentCache())
    provider = FakeCitationProvider(
        {"p1": ["p3", "p2", "p2"], "p2": ["p4"], "p3": ["p4"]}
    )

    expansion = skill.expand_citations(["p1", "p1"], provider, max_depth=2, max_nodes=3)

    assert expansion.seed_ids == ("p1",)
    assert expansion.paper_ids == ("p1", "p2", "p3")
    assert expansion.edges == (("p1", "p2"), ("p1", "p3"))


@pytest.mark.parametrize("max_depth", [-1, 0])
def test_citation_expansion_validates_bounds(max_depth: int) -> None:
    skill = PaperFetchSkill(FakeFetcher(), InMemoryPaperDocumentCache())
    provider = FakeCitationProvider({})
    if max_depth == 0:
        assert skill.expand_citations(["p1"], provider, max_depth=max_depth).paper_ids == ("p1",)
    else:
        with pytest.raises(PaperFetchValidationError):
            skill.expand_citations(["p1"], provider, max_depth=max_depth)
