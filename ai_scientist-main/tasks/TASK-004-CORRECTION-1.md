# TASK-004-CORRECTION-1: Persistence Contract And Integrity Corrections

> Status: `COMPLETED`
>
> Authorized by: `project_owner_01`
>
> Authorization context: the execution colleague performs each module's initial build;
> the primary agent reviews and directly corrects that implementation.

## Goal

Correct T004 so every public persistence and recovery boundary enforces the accepted
JSON Schema contracts, per-Run isolation, immutable Artifact identity, complete
ArtifactRef verification, and Fail-Closed recovery.

The frozen RunRecord Schema has no `content_hash`. Its append-only Ledger identity is
therefore an internal SHA256 over RFC8785 canonical bytes; the digest is not injected
into the public RunRecord.

## Allowed changes

```text
src/ai_scientist_mvp/domain/**
src/ai_scientist_mvp/application/**
src/ai_scientist_mvp/infrastructure/**
tests/unit/**
tests/integration/**
tests/smoke/test_project_structure.py
pyproject.toml
tasks/TASK-004-CORRECTION-1.md
```

`pyproject.toml` may only move and pin the already-used `jsonschema` package as a
runtime dependency. This correction introduces no online service or new scientific
dependency.

## Forbidden changes

- Do not modify `contracts/**`, `docs/contracts/**`, accepted ADRs, governance records,
  Fixture bytes/manifests, baseline locks, T003 outputs, or T005+ code.
- Do not add LangGraph, Replay adapters, API, frontend, network, secrets, or historical
  script execution.
- Do not close T004, create a CompletionRecord, or start T005.

## Acceptance

1. Schema-valid RunRecord, ArtifactEnvelope, StageRun, and CheckpointRef objects persist.
2. Schema-invalid, unsupported-version, foreign-Run, stale-ref, or illegal-lifecycle
   objects fail before append.
3. Artifact retries require the complete immutable Envelope; content-addressed byte
   drift is never silently overwritten.
4. Checkpoint write and recovery validate their own identity and every ArtifactRef.
5. StageAttemptKey contains the complete canonical `stage_configuration_ref`.
6. Unit/integration tests use Schema-valid Golden objects and cover rehashed semantic
   counterexamples.

## Completion evidence

- Every public persistence write validates its accepted JSON Schema and supported
  `schema_version`; `jsonschema==4.26.0` is now an explicit runtime dependency.
- Artifact reads recompute authority hashes, complete immutable Envelopes are bound to
  identity rows, and incomplete dual-record commits fail closed instead of self-repairing.
- Ledger kinds and stable identities are closed; ArtifactEnvelope and StageRun can only
  be committed atomically through their owning stores.
- Stage attempts retain the complete configuration VersionedRef. Checkpoint write and
  recovery validate local Run binding, self-identity, every ArtifactRef, and malformed
  stored JSON.
- Path derivation rejects escapes, symlinks, and junctions at the Artifact boundary.
- Verification: full suite `171 passed`; focused storage suite `42 passed`; ruff, mypy,
  import check, unified verification script, `git diff --check`, frozen baseline, and
  Fixture identity tests all passed.

This correction does not formally close T004, create a CompletionRecord, or authorize
T005. Project-owner acceptance remains a separate step.
