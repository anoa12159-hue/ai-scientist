"""Bounded retry, backoff, rate limiting and safe model error artifacts."""
from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ai_scientist_mvp.agent.llm.config import RetryPolicy
from ai_scientist_mvp.agent.llm.qwen import (
    ChatMessage,
    ChatResponse,
    ModelConfigurationError,
    ModelError,
    ModelResponseError,
    ModelTransportError,
    TokenUsage,
)
from ai_scientist_mvp.agent.llm.telemetry import (
    ModelCallObserver,
    ModelCallRecord,
    provider_and_model,
)


class ChatModel(Protocol):
    config: Any

    def invoke(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        """Invoke one chat completion."""


@dataclass(frozen=True)
class ModelErrorArtifact:
    artifact_type: str
    category: str
    code: str
    provider: str
    model: str
    attempts: int
    retryable: bool
    status_code: int | None
    message: str


class ModelRequestError(ModelError):
    """A model request failed and produced a safe structured error artifact."""

    def __init__(self, artifact: ModelErrorArtifact) -> None:
        super().__init__(artifact.message)
        self.artifact = artifact


class RateLimiter:
    """Thread-safe minimum-interval limiter with injectable clock and sleeper."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                remaining = self.min_interval_seconds - (now - self._last_request_at)
                if remaining > 0:
                    self._sleeper(remaining)
                    now = self._clock()
            self._last_request_at = now


class ResilientChatModel:
    """Wrap a chat model with bounded retry and typed failure routing."""

    def __init__(
        self,
        model: ChatModel,
        *,
        policy: RetryPolicy,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        limiter: RateLimiter | None = None,
        observer: ModelCallObserver | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not hasattr(model, "invoke"):
            raise TypeError("model must provide invoke(messages, response_format=...)")
        self.model = model
        self.policy = policy
        self._sleeper = sleeper
        self._random_value = random_value
        self._limiter = limiter or RateLimiter(policy.min_interval_seconds, sleeper=sleeper)
        self._observer = observer
        self._clock = clock

    def invoke(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        attempts = 0
        started_at = self._clock()
        provider, configured_model = provider_and_model(self.model)
        while attempts < self.policy.max_attempts:
            attempts += 1
            self._limiter.wait()
            try:
                response = self.model.invoke(messages, response_format=response_format)
                self._notify(
                    ModelCallRecord(
                        provider=provider,
                        configured_model=configured_model,
                        response_model=response.model,
                        response_id=response.response_id,
                        attempts=attempts,
                        elapsed_ms=_elapsed_ms(started_at, self._clock()),
                        outcome="SUCCEEDED",
                        error_code=None,
                        usage=response.usage,
                    )
                )
                return response
            except ModelError as error:
                retryable, status_code, category, code = _failure_details(error)
                if not retryable or attempts >= self.policy.max_attempts:
                    artifact = _error_artifact(
                        self.model,
                        attempts=attempts,
                        retryable=retryable,
                        status_code=status_code,
                        category=category,
                        code=code,
                        message=str(error),
                    )
                    self._notify(
                        ModelCallRecord(
                            provider=provider,
                            configured_model=configured_model,
                            response_model=None,
                            response_id=None,
                            attempts=attempts,
                            elapsed_ms=_elapsed_ms(started_at, self._clock()),
                            outcome="FAILED",
                            error_code=artifact.code,
                            usage=_empty_usage(),
                        )
                    )
                    raise ModelRequestError(
                        artifact
                    ) from error
                self._sleeper(self._backoff_seconds(attempts))
        raise AssertionError("retry loop exited without a result or failure")

    def _notify(self, record: ModelCallRecord) -> None:
        if self._observer is not None:
            self._observer(record)

    def _backoff_seconds(self, attempt: int) -> float:
        base = float(min(
            self.policy.max_backoff_seconds,
            self.policy.initial_backoff_seconds * (2 ** (attempt - 1)),
        ))
        if self.policy.jitter_ratio == 0:
            return base
        random_sample = float(self._random_value())
        factor = 1 + self.policy.jitter_ratio * (2 * random_sample - 1)
        return float(max(0.0, min(self.policy.max_backoff_seconds, base * factor)))


def _failure_details(error: ModelError) -> tuple[bool, int | None, str, str]:
    if isinstance(error, ModelTransportError):
        status = error.status_code
        if status == 429:
            return error.retryable, status, "RATE_LIMIT", "HTTP_429"
        if status is not None and status >= 500:
            return error.retryable, status, "NETWORK", "HTTP_5XX"
        return error.retryable, status, "NETWORK", "REQUEST_FAILED"
    if isinstance(error, ModelConfigurationError):
        return False, None, "CONFIGURATION", "MODEL_CONFIGURATION_ERROR"
    if isinstance(error, ModelResponseError):
        return False, None, "PROVIDER_RESPONSE", "INVALID_MODEL_RESPONSE"
    return False, None, "MODEL", "MODEL_ERROR"


def _elapsed_ms(started_at: float, finished_at: float) -> int:
    return max(0, round((finished_at - started_at) * 1000))


def _empty_usage() -> TokenUsage:
    return TokenUsage()


def _error_artifact(
    model: ChatModel,
    *,
    attempts: int,
    retryable: bool,
    status_code: int | None,
    category: str,
    code: str,
    message: str,
) -> ModelErrorArtifact:
    config = getattr(model, "config", None)
    provider = "unknown"
    model_name = "unknown"
    if config is not None:
        model_name = str(getattr(config, "model", "unknown"))
        provider = (
            "dashscope"
            if "dashscope" in str(getattr(config, "api_base", ""))
            else "openai-compatible"
        )
    return ModelErrorArtifact(
        artifact_type="ModelErrorArtifact",
        category=category,
        code=code,
        provider=provider,
        model=model_name,
        attempts=attempts,
        retryable=retryable,
        status_code=status_code,
        message=" ".join(message.split())[:240],
    )
