"""Exact quote, numeric-token, and source-position verification."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

QuoteStatus = Literal["VERIFIED", "NOT_FOUND"]
_NUMBER_PATTERN = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")


class QuoteVerificationError(ValueError):
    """Raised when a quote verification request is malformed."""


@dataclass(frozen=True)
class QuoteVerificationRequest:
    paper_id: str
    quote: str
    source_text: str
    expected_start: int | None = None
    expected_end: int | None = None
    expected_numbers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise QuoteVerificationError("paper_id must not be empty")
        if not self.quote:
            raise QuoteVerificationError("quote must not be empty")
        if (self.expected_start is None) != (self.expected_end is None):
            raise QuoteVerificationError(
                "expected_start and expected_end must be provided together"
            )
        if self.expected_start is not None and self.expected_start < 0:
            raise QuoteVerificationError("expected_start must not be negative")
        if self.expected_end is not None and self.expected_end < 0:
            raise QuoteVerificationError("expected_end must not be negative")
        if (
            self.expected_start is not None
            and self.expected_end is not None
            and self.expected_start > self.expected_end
        ):
            raise QuoteVerificationError("expected_start must not be after expected_end")
        normalized_numbers = tuple(
            number.strip() for number in self.expected_numbers if number.strip()
        )
        object.__setattr__(self, "expected_numbers", normalized_numbers)


@dataclass(frozen=True)
class QuoteVerificationResult:
    paper_id: str
    status: QuoteStatus
    start: int | None
    end: int | None
    quote_sha256: str
    numeric_tokens: tuple[str, ...]
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "status": self.status,
            "start": self.start,
            "end": self.end,
            "quote_sha256": self.quote_sha256,
            "numeric_tokens": list(self.numeric_tokens),
            "reason": self.reason,
        }


class QuoteVerifier:
    """Verify exact source bytes represented as Python text positions."""

    def verify(self, request: QuoteVerificationRequest) -> QuoteVerificationResult:
        quote_digest = _sha256_text(request.quote)
        numeric_tokens = tuple(_NUMBER_PATTERN.findall(request.quote))
        offsets = _candidate_offsets(request)
        if len(offsets) != 1:
            reason = "QUOTE_NOT_FOUND" if not offsets else "QUOTE_POSITION_AMBIGUOUS"
            return QuoteVerificationResult(
                paper_id=request.paper_id,
                status="NOT_FOUND",
                start=None,
                end=None,
                quote_sha256=quote_digest,
                numeric_tokens=numeric_tokens,
                reason=reason,
            )
        start, end = offsets[0]
        matched_numbers = tuple(_NUMBER_PATTERN.findall(request.source_text[start:end]))
        if request.expected_numbers and not _same_numbers(
            request.expected_numbers, matched_numbers
        ):
            return QuoteVerificationResult(
                paper_id=request.paper_id,
                status="NOT_FOUND",
                start=start,
                end=end,
                quote_sha256=quote_digest,
                numeric_tokens=matched_numbers,
                reason="NUMERIC_TOKEN_MISMATCH",
            )
        return QuoteVerificationResult(
            paper_id=request.paper_id,
            status="VERIFIED",
            start=start,
            end=end,
            quote_sha256=quote_digest,
            numeric_tokens=matched_numbers,
        )

    def verify_many(
        self, requests: Sequence[QuoteVerificationRequest]
    ) -> tuple[QuoteVerificationResult, ...]:
        return tuple(self.verify(request) for request in requests)


def _candidate_offsets(request: QuoteVerificationRequest) -> list[tuple[int, int]]:
    if request.expected_start is not None and request.expected_end is not None:
        start, end = request.expected_start, request.expected_end
        if end > len(request.source_text) or request.source_text[start:end] != request.quote:
            return []
        return [(start, end)]
    offsets: list[tuple[int, int]] = []
    start = 0
    while True:
        found = request.source_text.find(request.quote, start)
        if found < 0:
            return offsets
        offsets.append((found, found + len(request.quote)))
        start = found + 1


def _same_numbers(expected: Sequence[str], actual: Sequence[str]) -> bool:
    if len(expected) != len(actual):
        return False
    return all(
        _number_key(left) == _number_key(right)
        for left, right in zip(expected, actual, strict=True)
    )


def _number_key(value: str) -> tuple[Decimal, bool] | None:
    percent = value.endswith("%")
    numeric = value[:-1] if percent else value
    try:
        return Decimal(numeric), percent
    except InvalidOperation:
        return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()
