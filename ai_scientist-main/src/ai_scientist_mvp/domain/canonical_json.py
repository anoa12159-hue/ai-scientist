"""Content identity: RFC 8785 JSON Canonicalization Scheme (JCS).

Thin wrapper over the validated ``jcs`` package (v0.2.1), which implements the
full RFC 8785 scheme: ECMAScript ``Number::toString`` serialization (``0.5``,
``1e21`` -> ``1e+21``, ``1e-6`` -> ``0.000001``, ``1e-7`` -> ``1e-7``, ``-0``),
UTF-16 code-unit key ordering (including surrogate pairs), minimal string
escaping, raw non-ASCII UTF-8, and rejection of NaN/Infinity.

Cross-implementation evidence: this wrapper reproduces every ``content_hash``
locked in ``governance/baseline.lock.json`` (D-001..D-008, research-question,
workflow), which were produced by the project owner's independent toolchain.
The official RFC 8785 number/ordering vectors are pinned as fixed expected
bytes in ``tests/contract/test_golden_hash_rfc8785.py``.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, cast

import jcs


def _validate_string(value: str, path: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f"{path}: lone UTF-16 surrogate is not valid I-JSON")


def _validate_json_value(value: Any, path: str, ancestors: set[int]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        _validate_string(value, path)
        return
    if isinstance(value, int):
        try:
            binary64 = float(value)
        except OverflowError as error:
            raise ValueError(f"{path}: integer is outside the finite IEEE-754 range") from error
        if not math.isfinite(binary64) or int(binary64) != value:
            raise ValueError(f"{path}: integer is not exactly representable as IEEE-754 binary64")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: NaN and Infinity are not valid I-JSON numbers")
        return
    if isinstance(value, (list, dict)):
        identity = id(value)
        if identity in ancestors:
            raise ValueError(f"{path}: cyclic containers are not valid JSON")
        ancestors.add(identity)
        try:
            if isinstance(value, list):
                for index, item in enumerate(value):
                    _validate_json_value(item, f"{path}[{index}]", ancestors)
            else:
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise TypeError(f"{path}: JSON object keys must be strings")
                    _validate_string(key, f"{path} key")
                    _validate_json_value(item, f"{path}.{key}", ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON-compatible type")


def canonicalize(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 byte form of value.

    Inputs are validated against the I-JSON data model before serialization.
    ValueError is raised for non-finite numbers, non-binary64-safe integers,
    lone surrogates, and cycles. TypeError is raised for non-JSON types and
    non-string object keys.
    """
    _validate_json_value(value, "$", set())
    return cast(bytes, jcs.canonicalize(value))


def content_hash(value: Any) -> str:
    """SHA-256 (uppercase hex) of the RFC 8785 canonical form."""
    return hashlib.sha256(canonicalize(value)).hexdigest().upper()


def content_hash_excluding(value: dict[str, Any], field: str = "content_hash") -> str:
    """Content hash of a Versioned Object with its own ``content_hash`` removed."""
    stripped = {key: val for key, val in value.items() if key != field}
    return content_hash(stripped)
