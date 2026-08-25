from __future__ import annotations

import pytest

from ai_scientist_mvp.skills.quote_verifier import (
    QuoteVerificationError,
    QuoteVerificationRequest,
    QuoteVerifier,
)


def test_verifies_exact_quote_numbers_and_position() -> None:
    source = "The rate was 12.5% in 2024."
    quote = "12.5% in 2024"
    result = QuoteVerifier().verify(
        QuoteVerificationRequest(
            "paper-1",
            quote,
            source,
            expected_start=13,
            expected_end=13 + len(quote),
            expected_numbers=("12.50%", "2024"),
        )
    )

    assert result.status == "VERIFIED"
    assert result.start == 13
    assert result.numeric_tokens == ("12.5%", "2024")
    assert "source_text" not in result.as_dict()


def test_missing_or_ambiguous_quote_fails_closed() -> None:
    verifier = QuoteVerifier()
    missing = verifier.verify(QuoteVerificationRequest("paper-1", "missing", "source"))
    ambiguous = verifier.verify(QuoteVerificationRequest("paper-1", "same", "same same"))

    assert missing.status == "NOT_FOUND"
    assert missing.reason == "QUOTE_NOT_FOUND"
    assert ambiguous.status == "NOT_FOUND"
    assert ambiguous.reason == "QUOTE_POSITION_AMBIGUOUS"


def test_wrong_position_and_numbers_fail_closed() -> None:
    verifier = QuoteVerifier()
    wrong_position = verifier.verify(
        QuoteVerificationRequest("paper-1", "12", "value 12", expected_start=0, expected_end=2)
    )
    wrong_numbers = verifier.verify(
        QuoteVerificationRequest("paper-1", "value 12", "value 12", expected_numbers=("13",))
    )

    assert wrong_position.reason == "QUOTE_NOT_FOUND"
    assert wrong_numbers.reason == "NUMERIC_TOKEN_MISMATCH"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expected_start": 1},
        {"expected_start": 3, "expected_end": 2},
    ],
)
def test_request_validates_positions(kwargs: dict[str, int]) -> None:
    with pytest.raises(QuoteVerificationError):
        QuoteVerificationRequest("paper-1", "quote", "source", **kwargs)
