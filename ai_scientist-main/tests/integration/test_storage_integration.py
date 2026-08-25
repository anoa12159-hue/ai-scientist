"""Process-reopen and cross-port integration tests for the T004 kernel."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ai_scientist_mvp.application.services import compute_authority_hash
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import (
    ArtifactIdentityConflictError,
    CheckpointIntegrityError,
    MissingParentError,
)
from ai_scientist_mvp.infrastructure.paths import derive_artifact_path
from ai_scientist_mvp.infrastructure.storage import LocalStorage

H = "0" * 64
TS = "2026-08-20T00:00:00Z"


def _source_envelope(artifact_id: str, content: bytes, run_id: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "logical_artifact_id": "logical-" + artifact_id,
        "artifact_type": "SourceDocument",
        "schema_version": "0.1.0",
        "artifact_revision": 1,
        "task_id": "task-1",
        "run_id": run_id,
        "run_mode": "REPLAY",
        "origin_mode": "IMPORTED",
        "authority_mode": "SOURCE_BYTES",
        "content_ref": "artifact-content://" + artifact_id,
        "content_sha256": compute_authority_hash("SOURCE_BYTES", content),
        "producer": {"id": "fixture-adapter", "version": "0.1.0"},
        "created_at": TS,
    }


def _checkpoint(run_id: str, artifact_refs: list[dict], checkpoint_id: str = "cp-1") -> dict:
    checkpoint = {
        "checkpoint_id": checkpoint_id,
        "schema_version": "0.1.0",
        "run_id": run_id,
        "artifact_refs": copy.deepcopy(artifact_refs),
        "created_at": TS,
    }
    checkpoint["content_hash"] = canonical_json.content_hash_excluding(checkpoint)
    return checkpoint


def _put(store: LocalStorage, artifact_id: str, content: bytes) -> dict:
    envelope = _source_envelope(artifact_id, content, store.run_id)
    return store.artifact_store.put(envelope, content, "SOURCE_BYTES")


def test_two_runs_are_physically_and_semantically_isolated(tmp_path: Path) -> None:
    run_a = LocalStorage(tmp_path, "run-a")
    run_b = LocalStorage(tmp_path, "run-b")
    ref_a = _put(run_a, "same-id", b"A")
    ref_b = _put(run_b, "same-id", b"B")
    assert run_a.artifact_store.get_content("same-id") == b"A"
    assert run_b.artifact_store.get_content("same-id") == b"B"
    assert ref_a["content_sha256"] != ref_b["content_sha256"]
    with pytest.raises(CheckpointIntegrityError):
        run_a.checkpoint_store.put(_checkpoint("run-b", []))


def test_reopen_preserves_artifact_and_checkpoint(tmp_path: Path) -> None:
    first = LocalStorage(tmp_path, "run-1")
    ref = _put(first, "art-1", b"persist")
    checkpoint = _checkpoint("run-1", [ref])
    first.checkpoint_store.put(checkpoint)
    first.close()

    reopened = LocalStorage(tmp_path, "run-1")
    reopened.artifact_store.verify_ref(ref)
    assert reopened.artifact_store.get_content("art-1") == b"persist"
    assert reopened.checkpoint_store.latest("run-1") == checkpoint


def test_failed_put_leaves_no_committed_identity_or_fact(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    content = b"child"
    envelope = _source_envelope("child", content, "run-1")
    envelope["parent_refs"] = [
        {"artifact_id": "missing", "content_sha256": H, "schema_version": "0.1.0"}
    ]
    with pytest.raises(MissingParentError):
        store.artifact_store.put(envelope, content, "SOURCE_BYTES")
    assert not store.artifact_store.exists("child")
    assert store.ledger.read("artifact_envelope") == []


def test_identity_conflict_does_not_change_original_after_reopen(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    original = _source_envelope("art-1", b"original", "run-1")
    store.artifact_store.put(original, b"original", "SOURCE_BYTES")
    changed = _source_envelope("art-1", b"changed", "run-1")
    with pytest.raises(ArtifactIdentityConflictError):
        store.artifact_store.put(changed, b"changed", "SOURCE_BYTES")
    store.close()

    reopened = LocalStorage(tmp_path, "run-1")
    assert reopened.artifact_store.get_envelope("art-1") == original
    assert reopened.artifact_store.get_content("art-1") == b"original"


def test_checkpoint_recovery_detects_content_tamper_after_reopen(tmp_path: Path) -> None:
    first = LocalStorage(tmp_path, "run-1")
    ref = _put(first, "art-1", b"authority")
    checkpoint = _checkpoint("run-1", [ref])
    first.checkpoint_store.put(checkpoint)
    content_path = derive_artifact_path(tmp_path, "run-1", ref["content_sha256"])
    first.close()
    content_path.write_bytes(b"tampered")

    reopened = LocalStorage(tmp_path, "run-1")
    with pytest.raises(CheckpointIntegrityError):
        reopened.checkpoint_store.latest("run-1")


def test_checkpoint_recovery_detects_stale_schema_ref(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    ref = _put(store, "art-1", b"authority")
    stale_ref = {**ref, "schema_version": "9.9.9"}
    checkpoint = _checkpoint("run-1", [stale_ref])
    with pytest.raises(CheckpointIntegrityError):
        store.checkpoint_store.put(checkpoint)


def test_envelope_fact_and_identity_are_committed_together(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    _put(store, "art-1", b"data")
    identity_count = store.conn.execute("SELECT COUNT(*) FROM artifact_identity").fetchone()[0]
    fact_count = store.conn.execute(
        "SELECT COUNT(*) FROM facts WHERE kind='artifact_envelope'"
    ).fetchone()[0]
    assert identity_count == fact_count == 1


def test_stage_fact_is_visible_in_ledger_after_atomic_commit(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path, "run-1")
    stage = {
        "run_id": "run-1",
        "stage_id": "S01_CANDIDATE",
        "attempt": 1,
        "schema_version": "0.1.0",
        "stage_configuration_ref": {
            "id": "config-1",
            "schema_version": "0.1.0",
            "content_hash": H,
        },
        "execution_status": "SUCCEEDED",
    }
    stage["content_hash"] = canonical_json.content_hash_excluding(stage)
    store.run_store.put_stage(stage)
    assert store.ledger.read("stage_run") == [stage]
