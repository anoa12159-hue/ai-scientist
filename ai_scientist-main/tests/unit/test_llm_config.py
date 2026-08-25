from __future__ import annotations

from pathlib import Path

import pytest

from ai_scientist_mvp.agent.llm import ModelConfigError, QwenRuntimeConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_example_config_matches_frozen_defaults() -> None:
    config = QwenRuntimeConfig.from_toml(PROJECT_ROOT / "config.example.toml")
    assert config.model.model == "qwen-plus"
    assert config.model.temperature == 0
    assert config.model.seed == 42
    assert config.model.timeout_seconds == 180
    assert config.max_iterations == 8
    assert config.max_repair_rounds == 2
    assert config.budget.max_requests == 30
    assert config.budget.max_input_tokens == 200_000
    assert config.budget.max_output_tokens == 40_000
    assert config.budget.max_cost_cny == 10


def test_config_rejects_invalid_budget() -> None:
    with pytest.raises(ModelConfigError, match="max_requests"):
        QwenRuntimeConfig.from_mapping({"llm": {"budget": {"max_requests": 0}}})


def test_config_rejects_missing_llm_table() -> None:
    with pytest.raises(ModelConfigError, match=r"\[llm\]"):
        QwenRuntimeConfig.from_mapping({})
