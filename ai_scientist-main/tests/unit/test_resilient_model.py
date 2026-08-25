from __future__ import annotations

from urllib.request import Request

import pytest

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    ModelRequestError,
    ModelTransportError,
    QwenChatModel,
    QwenModelConfig,
    RateLimiter,
    ResilientChatModel,
    RetryPolicy,
)


def _model(requester, *, key: str = "test") -> QwenChatModel:
    return QwenChatModel(
        QwenModelConfig(api_base="https://example.test/v1"),
        requester=requester,
        environ={"DASHSCOPE_API_KEY": key},
    )


def _ok_response() -> bytes:
    return (
        b'{"id":"ok","model":"qwen-plus","choices":[{"message":'
        b'{"role":"assistant","content":"ok"},"finish_reason":"stop"}]}'
    )


def test_retry_backoff_then_success() -> None:
    failures = 2
    calls = 0
    sleeps: list[float] = []

    def requester(request: Request, timeout: float) -> bytes:
        nonlocal calls
        calls += 1
        if calls <= failures:
            raise ModelTransportError("busy", status_code=503, retryable=True)
        return _ok_response()

    model = ResilientChatModel(
        _model(requester),
        policy=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=1,
            max_backoff_seconds=4,
            jitter_ratio=0,
        ),
        sleeper=sleeps.append,
    )
    result = model.invoke([ChatMessage("user", "ping")])
    assert result.message.content == "ok"
    assert calls == 3
    assert sleeps == [1, 2]


def test_exhausted_retry_raises_error_artifact() -> None:
    sleeps: list[float] = []

    def requester(request: Request, timeout: float) -> bytes:
        raise ModelTransportError("busy", status_code=429, retryable=True)

    model = ResilientChatModel(
        _model(requester),
        policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0, jitter_ratio=0),
        sleeper=sleeps.append,
    )
    with pytest.raises(ModelRequestError) as error:
        model.invoke([ChatMessage("user", "ping")])
    assert error.value.artifact.category == "RATE_LIMIT"
    assert error.value.artifact.code == "HTTP_429"
    assert error.value.artifact.attempts == 2
    assert error.value.artifact.status_code == 429
    assert sleeps == [0]


def test_nonretryable_configuration_error_fails_without_sleep() -> None:
    sleeps: list[float] = []

    model = ResilientChatModel(
        _model(lambda request, timeout: _ok_response(), key=""),
        policy=RetryPolicy(max_attempts=3),
        sleeper=sleeps.append,
    )
    with pytest.raises(ModelRequestError) as error:
        model.invoke([ChatMessage("user", "ping")])
    assert error.value.artifact.category == "CONFIGURATION"
    assert error.value.artifact.attempts == 1
    assert sleeps == []


def test_rate_limiter_waits_for_minimum_interval() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(2.0, clock=clock, sleeper=sleeper)
    limiter.wait()
    now[0] = 1.0
    limiter.wait()
    assert sleeps == [1.0]
