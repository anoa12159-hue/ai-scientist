"""Persistence ports (T004).

Callers depend on these interfaces only, never on SQLite or the filesystem
layout. The MVP local implementations live in ``infrastructure``.
"""
from __future__ import annotations

from typing import Any, Protocol

from ai_scientist_mvp.domain.store_types import Authority, StageAttemptKey
from ai_scientist_mvp.domain.types import (
    ArtifactEnvelope,
    ArtifactRef,
    CheckpointRef,
    RunRecord,
    StageRun,
)


class ArtifactStore(Protocol):
    """Immutable, content-addressed artifact authority store."""

    def put(
        self,
        envelope: ArtifactEnvelope,
        content: bytes | dict[str, Any],
        authority: Authority,
    ) -> ArtifactRef:
        """Freeze an artifact. Idempotent for same id+content; Fail Closed on conflict."""
        ...

    def get_envelope(self, artifact_id: str) -> ArtifactEnvelope:
        ...

    def get_content(self, artifact_id: str) -> bytes:
        ...

    def verify(self, artifact_id: str) -> None:
        """Recompute the authority hash; raise HashMismatchError on drift."""
        ...

    def verify_ref(self, ref: ArtifactRef) -> None:
        """Validate a complete reference against its immutable stored Artifact."""
        ...

    def exists(self, artifact_id: str) -> bool:
        ...


class Ledger(Protocol):
    """Append-only log of versioned facts; no in-place update/delete."""

    def append(self, kind: str, fact: Any) -> None:
        ...

    def read(self, kind: str) -> list[dict[str, Any]]:
        ...

    def has(self, kind: str, identity_key: str) -> bool:
        ...


class RunStore(Protocol):
    """RunRecord / StageRun persistence with StageAttemptKey idempotency."""

    def put_run(self, run: RunRecord) -> None:
        ...

    def get_run(self, run_id: str) -> RunRecord:
        ...

    def put_stage(self, stage: StageRun) -> None:
        ...

    def get_stage(self, key: StageAttemptKey) -> StageRun:
        ...


class CheckpointStore(Protocol):
    """Reference-only checkpoint persistence and recovery."""

    def put(self, checkpoint: CheckpointRef) -> None:
        ...

    def latest(self, run_id: str) -> CheckpointRef | None:
        """Return the last fully committed checkpoint, or None."""
        ...
