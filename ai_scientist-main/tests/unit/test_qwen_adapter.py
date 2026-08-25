from __future__ import annotations

import json
from urllib.request import Request

import pytest

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    ModelConfigurationError,
    ModelResponseError,
    QwenChatModel,
    QwenModelConfig,
)


def _response() -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-1",
            "model": "qwen-plus",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
        }
    ).encode()


def test_qwen_defaults_match_frozen_compliance() -> None:
    config = QwenModelConfig()
    assert config.api_base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model == "qwen-plus"
    assert config.api_key_env == "DASHSCOPE_API_KEY"
    assert config.temperature == 0
    assert config.seed == 42
    assert config.timeout_seconds == 180


def test_invoke_serializes_openai_compatible_request() -> None:
    calls: list[tuple[Request, float]] = []

    def requester(request: Request, timeout: float) -> bytes:
        calls.append((request, timeout))
        return _response()

    model = QwenChatModel(
        QwenModelConfig(api_base="https://example.test/v1", timeout_seconds=12),
        requester=requester,
        environ={"DASHSCOPE_API_KEY": "test-key"},
    )
    result = model.invoke(
        [ChatMessage("system", "You are concise."), ChatMessage("user", "ping")],
        response_format={"type": "json_object"},
    )

    assert result.message == ChatMessage("assistant", "pong")
    assert result.usage.total_tokens == 5
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == "https://example.test/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert timeout == 12
    payload = json.loads(request.data)
    assert payload == {
        "model": "qwen-plus",
        "messages": [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "ping"},
        ],
        "temperature": 0,
        "seed": 42,
        "response_format": {"type": "json_object"},
    }


def test_missing_key_fails_before_request() -> None:
    called = False

    def requester(request: Request, timeout: float) -> bytes:
        nonlocal called
        called = True
        return _response()

    model = QwenChatModel(QwenModelConfig(), requester=requester, environ={})
    with pytest.raises(ModelConfigurationError, match="DASHSCOPE_API_KEY"):
        model.invoke([ChatMessage("user", "ping")])
    assert called is False


def test_invalid_response_is_rejected_without_raw_body() -> None:
    secret = "provider-secret-should-not-be-exposed"

    def requester(request: Request, timeout: float) -> bytes:
        return json.dumps({"error": {"message": secret}}).encode()

    model = QwenChatModel(
        QwenModelConfig(), requester=requester, environ={"DASHSCOPE_API_KEY": "x"}
    )
    with pytest.raises(ModelResponseError) as error:
        model.invoke([ChatMessage("user", "ping")])
    assert secret in str(error.value)
    assert "Authorization" not in str(error.value)


def test_empty_messages_and_bad_config_fail_closed() -> None:
    with pytest.raises(ModelConfigurationError):
        QwenChatModel(QwenModelConfig(), environ={"DASHSCOPE_API_KEY": "x"}).invoke([])
    with pytest.raises(ModelConfigurationError):
        QwenModelConfig(temperature=3)
