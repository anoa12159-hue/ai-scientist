"""Validated, immutable model runtime configuration loaded from TOML."""
from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_scientist_mvp.agent.llm.qwen import QwenModelConfig


class ModelConfigError(ValueError):
    """A model configuration document is missing or invalid."""


@dataclass(frozen=True)
class ModelBudget:
    max_requests: int = 30
    max_input_tokens: int = 200_000
    max_output_tokens: int = 40_000
    max_cost_cny: float = 10.0

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ModelConfigError("budget.max_requests must be positive")
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0:
            raise ModelConfigError("budget token limits must be positive")
        if self.max_cost_cny <= 0:
            raise ModelConfigError("budget.max_cost_cny must be positive")


@dataclass(frozen=True)
class QwenRuntimeConfig:
    model: QwenModelConfig = QwenModelConfig()
    max_iterations: int = 8
    max_repair_rounds: int = 2
    budget: ModelBudget = ModelBudget()

    def __post_init__(self) -> None:
        if self.max_iterations <= 0:
            raise ModelConfigError("llm.max_iterations must be positive")
        if self.max_repair_rounds < 0:
            raise ModelConfigError("llm.max_repair_rounds must not be negative")

    @classmethod
    def from_toml(cls, path: str | Path) -> QwenRuntimeConfig:
        config_path = Path(path)
        try:
            document = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ModelConfigError(f"cannot read model config: {config_path}") from error
        except tomllib.TOMLDecodeError as error:
            raise ModelConfigError("model config is not valid TOML") from error
        return cls.from_mapping(document)

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any]) -> QwenRuntimeConfig:
        raw_llm = document.get("llm")
        if not isinstance(raw_llm, Mapping):
            raise ModelConfigError("model config requires an [llm] table")
        raw_budget = raw_llm.get("budget", {})
        if not isinstance(raw_budget, Mapping):
            raise ModelConfigError("llm.budget must be a table")

        model = QwenModelConfig(
            api_base=_string(raw_llm, "api_base", QwenModelConfig.api_base),
            model=_string(raw_llm, "model", QwenModelConfig.model),
            api_key_env=_string(raw_llm, "api_key_env", QwenModelConfig.api_key_env),
            temperature=_number(raw_llm, "temperature", QwenModelConfig.temperature),
            seed=_optional_int(raw_llm, "seed", QwenModelConfig.seed),
            timeout_seconds=_number(
                raw_llm, "timeout_seconds", QwenModelConfig.timeout_seconds
            ),
        )
        budget = ModelBudget(
            max_requests=_positive_int(raw_budget, "max_requests", ModelBudget.max_requests),
            max_input_tokens=_positive_int(
                raw_budget, "max_input_tokens", ModelBudget.max_input_tokens
            ),
            max_output_tokens=_positive_int(
                raw_budget, "max_output_tokens", ModelBudget.max_output_tokens
            ),
            max_cost_cny=_positive_number(raw_budget, "max_cost_cny", ModelBudget.max_cost_cny),
        )
        return cls(
            model=model,
            max_iterations=_positive_int(raw_llm, "max_iterations", cls.max_iterations),
            max_repair_rounds=_nonnegative_int(
                raw_llm, "max_repair_rounds", cls.max_repair_rounds
            ),
            budget=budget,
        )


def _string(document: Mapping[str, Any], key: str, default: str) -> str:
    value = document.get(key, default)
    if not isinstance(value, str):
        raise ModelConfigError(f"llm.{key} must be a string")
    return value


def _number(document: Mapping[str, Any], key: str, default: float) -> float:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelConfigError(f"llm.{key} must be numeric")
    return float(value)


def _positive_number(document: Mapping[str, Any], key: str, default: float) -> float:
    value = _number(document, key, default)
    if value <= 0:
        raise ModelConfigError(f"llm.budget.{key} must be positive")
    return value


def _optional_int(document: Mapping[str, Any], key: str, default: int | None) -> int | None:
    value = document.get(key, default)
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ModelConfigError(f"llm.{key} must be an integer or null")
    return value


def _positive_int(document: Mapping[str, Any], key: str, default: int) -> int:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelConfigError(f"llm.{key} must be a positive integer")
    return value


def _nonnegative_int(document: Mapping[str, Any], key: str, default: int) -> int:
    value = document.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelConfigError(f"llm.{key} must be a non-negative integer")
    return value
