from __future__ import annotations

import pytest

from trove.config import (
    DEFAULT_LLM_CHUNK_CHARS,
    DEFAULT_LLM_MAX_CALLS_PER_ITEM,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    Config,
    ConfigError,
    LLMConfig,
    default_llm_config_path,
    load_llm_config,
)


def test_llm_config_uses_defaults_when_file_is_missing(tmp_path):
    llm = load_llm_config(tmp_path / "llm.toml")

    assert llm.model == ""
    assert llm.base_url == ""
    assert llm.api_key == ""
    assert llm.enabled is True
    assert llm.chunk_chars == DEFAULT_LLM_CHUNK_CHARS
    assert llm.max_calls_per_item == DEFAULT_LLM_MAX_CALLS_PER_ITEM
    assert llm.timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS


def test_llm_config_file_overrides_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_llm_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                'model = "configured-model"',
                'base_url = "https://example.test/v1"',
                'api_key = "sk-configured"',
                "enabled = false",
                "chunk_chars = 1234",
                "max_calls_per_item = 3",
                "max_output_tokens_per_call = 64",
                "max_input_tokens_per_item = 4096",
                "input_cost_per_million = 1.5",
                "output_cost_per_million = 2.5",
                "timeout_seconds = 12.5",
            ]
        ),
        encoding="utf-8",
    )

    config = Config()

    assert config.llm == LLMConfig(
        model="configured-model",
        base_url="https://example.test/v1",
        api_key="sk-configured",
        enabled=False,
        chunk_chars=1234,
        max_calls_per_item=3,
        max_output_tokens_per_call=64,
        max_input_tokens_per_item=4096,
        input_cost_per_million=1.5,
        output_cost_per_million=2.5,
        timeout_seconds=12.5,
    )


def test_llm_config_rejects_invalid_toml(tmp_path):
    path = tmp_path / "llm.toml"
    path.write_text("model = [", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_llm_config(path)
