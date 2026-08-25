"""Small, reference-only LangGraph state for the SHRGT45 Replay workflow (T006).

The graph state carries only versioned references and small routing fields.
It never holds Markdown, CSV tables, image bytes, whole Fixture objects, or raw
source bytes: those remain authority content in the T004 ArtifactStore and are
addressed exclusively through ``ArtifactRef`` / ``VersionedRef``.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from ai_scientist_mvp.domain.types import ArtifactRef, VersionedRef

# Run-mode and gate-routing literals used by the graph. These are routing only
# and are intentionally not scientific state.
RUN_MODE_REPLAY = "REPLAY"
GATE_PENDING = "PENDING"
GATE_APPROVED = "APPROVED"
GATE_REJECTED = "REJECTED"
FINAL_REVIEW_AVAILABLE = "AVAILABLE_FOR_PROJECT_REVIEW"
FINAL_REVIEW_ACKNOWLEDGED = "ACKNOWLEDGED_FOR_PROJECT_REVIEW"


def merge_dict(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge reducer for parallel-branch channels (S05 and S06 write distinct keys)."""
    if left is None:
        return dict(right or {})
    if right is None:
        return dict(left)
    merged = dict(left)
    merged.update(right)
    return merged


def merge_list(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """Append reducer for failure references produced by independent nodes."""
    return [*(left or []), *(right or [])]


class ReplayGraphState(TypedDict, total=False):
    # Stable identity and workflow routing (small strings only).
    run_id: str
    task_id: str
    workflow_version: str
    run_mode: str

    # Frozen RunConfigurationSnapshot reference.
    configuration_ref: VersionedRef

    # Per-stage derived snapshot references. S05 and S06 write distinct keys in
    # parallel, so this channel must merge rather than last-write-wins.
    stage_snapshot_refs: Annotated[dict[str, ArtifactRef], merge_dict]
    stage_status: Annotated[dict[str, str], merge_dict]

    # Gate context (written by the S05/S06 Join node).
    finding_refs: list[VersionedRef]
    decision_request_ref: ArtifactRef
    gate_decision_ref: VersionedRef
    gate_decision: str
    gate_error: str

    # Report and final review state (written by S07 and FINAL_REPLAY_REVIEW).
    report_summary_ref: ArtifactRef
    report_manifest_ref: ArtifactRef
    final_review_status: str

    # Structured failure routing and bounded per-node retry accounting.
    failure_refs: Annotated[list[VersionedRef], merge_list]
    retry_counts: Annotated[dict[str, int], merge_dict]
    completed: bool
