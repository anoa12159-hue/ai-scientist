"""Application use cases over the persistence ports (T004)."""
from __future__ import annotations

import hashlib
from typing import Any

from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import IllegalTransitionError
from ai_scientist_mvp.domain.store_types import LEGAL_TRANSITIONS, Authority
from ai_scientist_mvp.domain.types import ArtifactLifecycleEvent, CheckpointRef


def compute_authority_hash(authority: Authority, content: bytes | dict[str, Any]) -> str:
    """content_sha256 covers only the authority content (CONTRACTS.md 4.1).

    SOURCE_BYTES -> SHA-256 of raw bytes; CANONICAL_JSON -> SHA-256 of the RFC 8785
    canonical bytes. Both are byte-level hashes, returned lowercase, and are
    distinct from the uppercase JCS ``content_hash`` used for Versioned Objects.
    """
    if authority == "SOURCE_BYTES":
        if not isinstance(content, bytes):
            raise TypeError("SOURCE_BYTES authority requires bytes content")
        return hashlib.sha256(content).hexdigest().lower()
    if not isinstance(content, dict):
        raise TypeError("CANONICAL_JSON authority requires a dict payload")
    return hashlib.sha256(canonical_json.canonicalize(content)).hexdigest().lower()


def project_lifecycle(events: list[ArtifactLifecycleEvent]) -> str:
    """Project the current artifact lifecycle from an ordered event list.

    Every transition must be legal (CONTRACTS.md 4.4); an illegal or non-monotonic
    sequence raises IllegalTransitionError. An empty list projects to DRAFT.
    """
    current = "DRAFT"
    for event in events:
        from_lifecycle = event["from_lifecycle"]
        to_lifecycle = event["to_lifecycle"]
        if from_lifecycle != current:
            raise IllegalTransitionError(
                f"non-contiguous lifecycle: expected from={current}, got {from_lifecycle}"
            )
        if (from_lifecycle, to_lifecycle) not in LEGAL_TRANSITIONS:
            raise IllegalTransitionError(f"illegal transition {from_lifecycle} -> {to_lifecycle}")
        current = to_lifecycle
    return current


def verify_checkpoint(checkpoint: CheckpointRef, artifact_store: Any) -> list[str]:
    """Return a list of integrity errors; empty means the checkpoint is sound.

    Each ArtifactRef must exist and its recorded content_sha256 must match the
    stored authority content (CONTRACTS.md 2.5 / ADR-001 4).
    """
    errors: list[str] = []
    for ref in checkpoint.get("artifact_refs", []):
        artifact_id = ref["artifact_id"]
        try:
            if not artifact_store.exists(artifact_id):
                errors.append(f"missing artifact: {artifact_id}")
                continue
            artifact_store.verify_ref(ref)
        except Exception as exc:  # noqa: BLE001 - any integrity failure is reported
            errors.append(f"{artifact_id}: {type(exc).__name__}: {exc}")
    return errors
