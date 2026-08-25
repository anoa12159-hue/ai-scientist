"""Schema-validated structured chat output with bounded repair."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from ai_scientist_mvp.agent.llm.qwen import ChatMessage, ChatResponse, ModelError, TokenUsage


class StructuredOutputError(ModelError):
    """Structured output remained invalid after the configured repair limit."""

    def __init__(self, message: str, *, attempts: int, issues: Sequence[str]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.issues = tuple(issues)


@dataclass(frozen=True)
class StructuredOutput:
    value: Any
    attempts: int
    repair_count: int
    response_ids: tuple[str, ...]
    usage: TokenUsage


class StructuredQwenChatModel:
    """Wrap a chat model with JSON Schema validation and finite repair."""

    def __init__(self, model: Any, *, max_repair_rounds: int = 2) -> None:
        if max_repair_rounds < 0:
            raise ValueError("max_repair_rounds must not be negative")
        if not hasattr(model, "invoke"):
            raise TypeError("model must provide invoke(messages, response_format=...)")
        self.model = model
        self.max_repair_rounds = max_repair_rounds

    def invoke(
        self,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
    ) -> StructuredOutput:
        validator = _validator(schema)
        request_messages = list(messages)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_output",
                "strict": True,
                "schema": dict(schema),
            },
        }
        responses: list[ChatResponse] = []
        issues: list[str] = []
        for attempt in range(1, self.max_repair_rounds + 2):
            response = self.model.invoke(request_messages, response_format=response_format)
            responses.append(response)
            parsed, validation_issues = _parse_and_validate(response.message.content, validator)
            if not validation_issues:
                return StructuredOutput(
                    value=parsed,
                    attempts=attempt,
                    repair_count=attempt - 1,
                    response_ids=tuple(item.response_id for item in responses),
                    usage=_sum_usage(responses),
                )
            issues = validation_issues
            if attempt <= self.max_repair_rounds:
                request_messages = [
                    *request_messages,
                    ChatMessage(
                        "user",
                        _repair_prompt(validation_issues),
                    ),
                ]
        raise StructuredOutputError(
            "structured model output failed JSON Schema validation",
            attempts=len(responses),
            issues=issues,
        )


def _validator(schema: Mapping[str, Any]) -> Draft202012Validator:
    if not isinstance(schema, Mapping):
        raise StructuredOutputError(
            "structured output schema must be an object",
            attempts=0,
            issues=("schema is not an object",),
        )
    schema_object = dict(schema)
    try:
        Draft202012Validator.check_schema(schema_object)
    except SchemaError as error:
        raise StructuredOutputError(
            "structured output schema is invalid",
            attempts=0,
            issues=("schema failed Draft 2020-12 validation",),
        ) from error
    return Draft202012Validator(schema_object)


def _parse_and_validate(
    content: str,
    validator: Draft202012Validator,
) -> tuple[Any, list[str]]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None, ["content is not valid JSON"]
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        issues = []
        for error in errors[:5]:
            location = ".".join(str(part) for part in error.path) or "$"
            issues.append(f"{location}: {error.message}")
        return None, issues
    return value, []


def _repair_prompt(issues: Sequence[str]) -> str:
    joined = "; ".join(issues)
    return (
        "Return only a JSON object that satisfies the requested schema. "
        f"Deterministic validation errors: {joined}"
    )


def _sum_usage(responses: Sequence[ChatResponse]) -> TokenUsage:
    values = {
        "prompt_tokens": _sum_optional(item.usage.prompt_tokens for item in responses),
        "completion_tokens": _sum_optional(item.usage.completion_tokens for item in responses),
        "total_tokens": _sum_optional(item.usage.total_tokens for item in responses),
    }
    return TokenUsage(**values)


def _sum_optional(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None
