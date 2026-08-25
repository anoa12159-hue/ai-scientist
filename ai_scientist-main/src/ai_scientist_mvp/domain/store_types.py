"""T004 kernel value types that extend (not modify) the frozen ``types.py`` surface."""
from __future__ import annotations

from typing import Literal, TypedDict

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.types import VersionedRef

# Authority mode for artifact content identity (CONTRACTS.md 4.1).
Authority = Literal["SOURCE_BYTES", "CANONICAL_JSON"]

# Legal ArtifactLifecycleEvent transitions (CONTRACTS.md 4.4).
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("DRAFT", "REVIEW_REQUIRED"),
        ("DRAFT", "REJECTED"),
        ("REVIEW_REQUIRED", "FROZEN"),
        ("REVIEW_REQUIRED", "REJECTED"),
        ("FROZEN", "SUPERSEDED"),
    }
)


class StageAttemptKey(TypedDict):
    """Stable execution identity {run_id, stage_id, attempt, stage_configuration_ref}."""

    run_id: str
    stage_id: str
    attempt: int
    stage_configuration_ref: VersionedRef | None


def attempt_key_string(key: StageAttemptKey) -> str:
    """Deterministic, collision-free string form of a StageAttemptKey."""
    return canonical_json.canonicalize(key).decode("utf-8")
