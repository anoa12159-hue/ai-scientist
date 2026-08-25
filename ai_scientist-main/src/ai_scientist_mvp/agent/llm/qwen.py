"""Qwen adapter for OpenAI-compatible chat completion endpoints.

The adapter has no provider SDK dependency. Network access occurs only when
``invoke`` is called with a configured API key. Tests and offline callers can
inject a request function without making network calls.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"


class ModelError(RuntimeError):
    """Base class for safe, provider-independent model failures."""


class ModelConfigurationError(ModelError):
    """The model configuration is missing or invalid."""


class ModelTransportError(ModelError):
    """The endpoint could not be reached or returned an HTTP failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ModelResponseError(ModelError):
    """The endpoint response is not a valid chat completion."""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def as_payload(self) -> dict[str, str]:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ModelConfigurationError(f"unsupported chat message role: {self.role}")
        if not isinstance(self.content, str):
            raise ModelConfigurationError("chat message content must be a string")
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ChatResponse:
    response_id: str
    model: str
    message: ChatMessage
    finish_reason: str | None
    usage: TokenUsage


@dataclass(frozen=True)
class QwenModelConfig:
    api_base: str = DEFAULT_API_BASE
    model: str = DEFAULT_MODEL
    api_key_env: str = DEFAULT_API_KEY_ENV
    temperature: float = 0.0
    seed: int | None = 42
    timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if not self.api_base.startswith(("https://", "http://")):
            raise ModelConfigurationError("api_base must use http:// or https://")
        if not self.api_base.rstrip("/").split("//", 1)[-1]:
            raise ModelConfigurationError("api_base must include a host")
        if not self.model.strip():
            raise ModelConfigurationError("model must not be empty")
        if not self.api_key_env or not self.api_key_env.isidentifier():
            raise ModelConfigurationError("api_key_env must be a valid environment variable name")
        if not 0 <= self.temperature <= 2:
            raise ModelConfigurationError("temperature must be between 0 and 2")
        if self.seed is not None and not isinstance(self.seed, int):
            raise ModelConfigurationError("seed must be an integer or None")
        if self.timeout_seconds <= 0:
            raise ModelConfigurationError("timeout_seconds must be positive")


class Requester(Protocol):
    def __call__(self, request: Request, timeout: float) -> bytes:
        """Send a request and return response bytes."""


def _default_requester(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return cast(bytes, response.read())


def _safe_error_text(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split())[:240]
    return "provider returned an error"


class OpenAICompatibleChatModel:
    """Small provider-neutral client for Chat Completions compatible APIs."""

    def __init__(
        self,
        config: QwenModelConfig,
        *,
        requester: Requester | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self._requester = requester or _default_requester
        self._environ = environ if environ is not None else os.environ

    @property
    def endpoint(self) -> str:
        return self.config.api_base.rstrip("/") + "/chat/completions"

    def invoke(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        if not messages:
            raise ModelConfigurationError("at least one chat message is required")
        credential = self._environ.get(self.config.api_key_env, "").strip()
        if not credential:
            raise ModelConfigurationError(
                f"missing API key environment variable: {self.config.api_key_env}"
            )

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.as_payload() for message in messages],
            "temperature": self.config.temperature,
        }
        if self.config.seed is not None:
            payload["seed"] = self.config.seed
        if response_format is not None:
            payload["response_format"] = dict(response_format)

        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            body = self._requester(request, self.config.timeout_seconds)
        except HTTPError as error:
            raise ModelTransportError(
                f"model endpoint returned HTTP {error.code}",
                status_code=error.code,
                retryable=error.code == 429 or error.code >= 500,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ModelTransportError("model endpoint request failed", retryable=True) from error

        return self._parse_response(body)

    def _parse_response(self, body: bytes) -> ChatResponse:
        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelResponseError("model endpoint returned invalid JSON") from error
        if not isinstance(document, dict):
            raise ModelResponseError("model endpoint returned a non-object response")

        if "error" in document:
            error_payload = document["error"]
            if isinstance(error_payload, dict):
                message = _safe_error_text(error_payload.get("message"))
            else:
                message = _safe_error_text(error_payload)
            raise ModelResponseError(f"model endpoint error: {message}")

        choices = document.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelResponseError("model response has no valid choices")
        choice = choices[0]
        message_payload = choice.get("message")
        if not isinstance(message_payload, dict):
            raise ModelResponseError("model response choice has no message")
        role = message_payload.get("role")
        content = message_payload.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ModelResponseError("model response message has invalid role or content")

        usage_payload = document.get("usage")
        usage = TokenUsage()
        if isinstance(usage_payload, dict):
            usage = TokenUsage(
                prompt_tokens=_optional_int(usage_payload.get("prompt_tokens")),
                completion_tokens=_optional_int(usage_payload.get("completion_tokens")),
                total_tokens=_optional_int(usage_payload.get("total_tokens")),
            )
        response_id = document.get("id")
        response_model = document.get("model")
        if not isinstance(response_id, str) or not isinstance(response_model, str):
            raise ModelResponseError("model response is missing id or model")
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ModelResponseError("model response has invalid finish_reason")
        return ChatResponse(
            response_id=response_id,
            model=response_model,
            message=ChatMessage(role=role, content=content),
            finish_reason=finish_reason,
            usage=usage,
        )


class QwenChatModel(OpenAICompatibleChatModel):
    """Qwen model binding using the frozen DashScope defaults."""


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelResponseError("model response usage contains a non-integer token count")
    if value < 0:
        raise ModelResponseError("model response usage contains a negative token count")
    return value
