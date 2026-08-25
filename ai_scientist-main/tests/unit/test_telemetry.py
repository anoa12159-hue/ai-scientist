from __future__ import annotations

import json
from urllib.request import Request

from ai_scientist_mvp.agent.llm import (
    ChatMessage,
    ModelCallRecord,
    QwenChatModel,
    QwenModelConfig,
    ResilientChatModel,
    RetryPolicy,
    TokenUsage,
    redact_mapping,
)


def test_success_call_emits_redacted_model_and_token_metadata() -> None:
    records: list[ModelCallRecord] = []

    def requester(request: Request, timeout: float) -> bytes:
        return json.dumps(
            {
                "id": "response-1",
                "model": "qwen-plus-2025",
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}}
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            }
        ).encode()

    model = ResilientChatModel(
        QwenChatModel(
            QwenModelConfig(api_base="https://example.test/v1"),
            requester=requester,
            environ={"DASHSCOPE_API_KEY": "secret"},
        ),
        policy=RetryPolicy(max_attempts=1),
        observer=records.append,
    )
    model.invoke([ChatMessage("user", "do not log this")])

    assert len(records) == 1
    record = records[0]
    assert record.provider == "openai-compatible"
    assert record.configured_model == "qwen-plus"
    assert record.response_model == "qwen-plus-2025"
    assert record.response_id == "response-1"
    assert record.usage == TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5)
    serialized = json.dumps(record.as_dict())
    assert "do not log this" not in serialized
    assert "secret" not in serialized


def test_redact_mapping_drops_prompt_and_credential_fields() -> None:
    result = redact_mapping(
        {
            "provider": "dashscope",
            "prompt": "private",
            "Authorization": "Bearer secret",
            "usage": {"total_tokens": 4},
        }
    )
    assert result == {"provider": "dashscope", "usage": {"total_tokens": 4}}
