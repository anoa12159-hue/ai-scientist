"""Domain exceptions for the persistence kernel (T004).

These are value/rule failures, not Python plumbing: every Fail-Closed condition in
the ArtifactStore / Ledger / Run / Checkpoint contracts surfaces as one of these.
"""
from __future__ import annotations


class StoreError(Exception):
    """Base class for all persistence-kernel errors."""


class SchemaValidationError(StoreError):
    """A public persistence object violates its frozen JSON Schema."""


class RunIsolationError(StoreError):
    """An object or query targets a Run other than the local storage namespace."""


class InvalidIdError(StoreError):
    """An identifier is empty or contains forbidden characters."""


class PathEscapeError(StoreError):
    """A derived path escapes the controlled run root (absolute, traversal, etc.)."""


class HashMismatchError(StoreError):
    """A stored payload no longer matches its recorded content hash."""


class ArtifactIdentityConflictError(StoreError):
    """The same artifact_id was written again with different content."""


class IllegalTransitionError(StoreError):
    """An ArtifactLifecycleEvent transition is not in the legal set."""


class MissingParentError(StoreError):
    """An ArtifactEnvelope references a parent that does not exist."""


class LedgerIntegrityError(StoreError):
    """A ledger fact fails content-hash or reference validation."""


class CheckpointIntegrityError(StoreError):
    """A checkpoint references a missing or tampered artifact."""


class IdempotencyConflictError(StoreError):
    """A retried idempotency key now carries different content."""
