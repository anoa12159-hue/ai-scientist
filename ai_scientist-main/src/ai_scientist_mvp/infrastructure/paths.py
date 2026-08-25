"""Identifier and path safety for the local kernel (T004).

All run/artifact paths are derived from a controlled root plus a validated
identifier; nothing may escape that root or reference an absolute path.
"""
from __future__ import annotations

import re
from pathlib import Path

from ai_scientist_mvp.domain.errors import InvalidIdError, PathEscapeError

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEX64_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def validate_id(value: str) -> str:
    """A safe identifier: alphanumeric start, then alnum/._- only."""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise InvalidIdError(f"illegal identifier: {value!r}")
    return value


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise InvalidIdError(f"illegal content hash: {value!r}")
    return value.lower()


def derive_run_dir(runs_root: Path, run_id: str) -> Path:
    """Return runs/<run_id>/, guaranteeing it stays inside runs_root."""
    validate_id(run_id)
    base = runs_root.resolve()
    run_dir = (base / run_id).resolve()
    if run_dir.parent != base:
        raise PathEscapeError(f"run id escapes root: {run_id!r}")
    return run_dir


def derive_artifact_path(runs_root: Path, run_id: str, content_sha256: str) -> Path:
    """Return a resolved content path that cannot traverse a link outside the Run."""
    content_sha256 = validate_sha256(content_sha256)
    run_dir = derive_run_dir(runs_root, run_id)
    artifact_dir = run_dir / "artifacts"
    candidate = artifact_dir / content_sha256
    if _is_link_like(artifact_dir) or _is_link_like(candidate):
        raise PathEscapeError("artifact storage cannot traverse a symlink or junction")
    resolved_dir = artifact_dir.resolve(strict=False)
    resolved_target = candidate.resolve(strict=False)
    if resolved_dir.parent != run_dir or resolved_target.parent != resolved_dir:
        raise PathEscapeError("artifact path resolves outside the local Run")
    return resolved_target
