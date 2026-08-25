from __future__ import annotations

import pytest

from ai_scientist_mvp.skills.paper_search import (
    InMemoryPaperSearchProvider,
    PaperSearchHit,
    PaperSearchQuery,
    PaperSearchSkill,
    PaperSearchValidationError,
)


def _papers() -> list[PaperSearchHit]:
    return [
        PaperSearchHit(
            paper_id="p-1",
            title="Magnetic complexity and flare prediction",
            abstract="A study of magnetic complexity in active regions.",
            authors=("A. Researcher",),
            year=2024,
            venue="solar physics",
            citation_count=12,
        ),
        PaperSearchHit(
            paper_id="p-2",
            title="Solar flare forecasting",
            abstract="Forecasting methods for active regions.",
            year=2022,
            venue="astrophysics",
            citation_count=30,
        ),
        PaperSearchHit(
            paper_id="p-3",
            title="Magnetic fields in quiet stars",
            year=2020,
            venue="stellar physics",
            citation_count=5,
        ),
    ]


def test_search_is_deterministic_and_shapes_safe_metadata() -> None:
    skill = PaperSearchSkill(InMemoryPaperSearchProvider(_papers(), corpus_version="test-v1"))
    result = skill.search(PaperSearchQuery("magnetic complexity", limit=2))

    assert [hit.paper_id for hit in result.hits] == ["p-1", "p-3"]
    assert result.provider == "in-memory"
    assert result.corpus_version == "test-v1"
    assert result.as_dict()["hits"][0]["title"] == "Magnetic complexity and flare prediction"


def test_search_applies_year_and_field_filters() -> None:
    skill = PaperSearchSkill(InMemoryPaperSearchProvider(_papers()))
    result = skill.search(
        PaperSearchQuery(
            "solar",
            year_from=2023,
            fields_of_study=("solar physics",),
        )
    )

    assert [hit.paper_id for hit in result.hits] == ["p-1"]


def test_search_many_deduplicates_first_seen_results() -> None:
    skill = PaperSearchSkill(InMemoryPaperSearchProvider(_papers()))
    hits = skill.search_many(
        [PaperSearchQuery("magnetic"), PaperSearchQuery("flare")],
        limit=3,
    )

    assert [hit.paper_id for hit in hits] == ["p-1", "p-3", "p-2"]


@pytest.mark.parametrize(
    "query_kwargs",
    [{"limit": 0}, {"year_from": 2025, "year_to": 2024}],
)
def test_query_validation_fails_closed(query_kwargs: dict[str, int]) -> None:
    with pytest.raises(PaperSearchValidationError):
        PaperSearchQuery("valid", **query_kwargs)


def test_provider_rejects_duplicate_ids() -> None:
    paper = PaperSearchHit(paper_id="same", title="one")
    with pytest.raises(PaperSearchValidationError):
        InMemoryPaperSearchProvider([paper, paper])
