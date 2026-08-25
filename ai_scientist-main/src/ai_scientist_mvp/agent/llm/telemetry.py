"""Redacted model-call telemetry with no prompt or credential retention."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from ai_scientist_mvp.agent.llm.qwen import TokenUsage


@dataclass(frozen=True)
class ModelCallRecord:
    provider: str
    configured_model: str
    response_model: str | None
    response_id: str | None
    attempts: int
    elapsed_ms: int
    outcome: str
    error_code: str | None
    usage: TokenUsage

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["usage"] = asdict(self.usage)
        return payload


class ModelCallObserver(Protocol):
    def __call__(self, record: ModelCallRecord) -> None:
        """Receive one redacted model-call record."""


class LoggingModelCallObserver:
    """Write only allowlisted model metadata to a standard logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("ai_scientist_mvp.model")

    def __call__(self, record: ModelCallRecord) -> None:
        self.logger.info("model_call", extra={"model_call": record.as_dict()})


def provider_and_model(model: Any) -> tuple[str, str]:
    config = getattr(model, "config", None)
    if config is None:
        return "unknown", "unknown"
    base = str(getattr(config, "api_base", ""))
    provider = "dashscope" if "dashscope" in base else "openai-compatible"
    return provider, str(getattr(config, "model", "unknown"))


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only telemetry-safe fields from an arbitrary mapping."""
    allowed = {
        "provider",
        "configured_model",
        "response_model",
        "response_id",
        "attempts",
        "elapsed_ms",
        "outcome",
        "error_code",
        "usage",
    }
    return {key: value for key, value in payload.items() if key in allowed}
