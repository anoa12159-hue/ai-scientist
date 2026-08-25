from __future__ import annotations

import json
from urllib.request import Request

import pytest

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    QwenChatModel,
    QwenModelConfig,
    StructuredOutputError,
    StructuredQwenChatModel,
)

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _response(content: str, response_id: str) -> bytes:
    return json.dumps(
        {
            "id": response_id,
            "model": "qwen-plus",
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
    ).encode()


def test_structured_output_repairs_once_and_aggregates_usage() -> None:
    responses = iter(
        [
            _response('{"answer": 7}', "first"),
            _response('{"answer": "ok"}', "second"),
        ]
    )
    calls: list[dict] = []

    def requester(request: Request, timeout: float) -> bytes:
        calls.append(json.loads(request.data))
        return next(responses)

    model = StructuredQwenChatModel(
        QwenChatModel(
            QwenModelConfig(api_base="https://example.test/v1"),
            requester=requester,
            environ={"DASHSCOPE_API_KEY": "test"},
        ),
        max_repair_rounds=2,
    )
    result = model.invoke([ChatMessage("user", "answer")], SCHEMA)

    assert result.value == {"answer": "ok"}
    assert result.attempts == 2
    assert result.repair_count == 1
    assert result.response_ids == ("first", "second")
    assert result.usage.total_tokens == 6
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert "Deterministic validation errors" in calls[1]["messages"][-1]["content"]


def test_structured_output_exhausts_finite_repairs() -> None:
    def requester(request: Request, timeout: float) -> bytes:
        return _response("not-json", "bad")

    model = StructuredQwenChatModel(
        QwenChatModel(
            QwenModelConfig(api_base="https://example.test/v1"),
            requester=requester,
            environ={"DASHSCOPE_API_KEY": "test"},
        ),
        max_repair_rounds=1,
    )
    with pytest.raises(StructuredOutputError) as error:
        model.invoke([ChatMessage("user", "answer")], SCHEMA)
    assert error.value.attempts == 2
    assert error.value.issues == ("content is not valid JSON",)


def test_structured_output_rejects_invalid_schema() -> None:
    model = StructuredQwenChatModel(
        QwenChatModel(
            QwenModelConfig(api_base="https://example.test/v1"),
            requester=lambda request, timeout: b"{}",
            environ={"DASHSCOPE_API_KEY": "test"},
        ),
        max_repair_rounds=0,
    )
    with pytest.raises(StructuredOutputError, match="schema"):
        model.invoke([ChatMessage("user", "answer")], {"type": "unknown"})
