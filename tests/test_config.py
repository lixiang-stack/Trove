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
    load_config,
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


def test_worker_lease_must_be_longer_than_the_heartbeat(tmp_path):
    with pytest.raises(ConfigError, match="LEASE_SECONDS"):
        Config(
            home=tmp_path / "Trove",
            worker_lease_seconds=5,
            worker_heartbeat_seconds=5,
        )


def test_stage_max_attempts_default_to_the_retry_policy(tmp_path):
    config = Config(home=tmp_path / "Trove")

    assert config.stage_max_attempts == {
        "downloading": 3,
        "extracting_audio": 3,
        "extracting_text": 3,
        "transcribing": 1,
        "organizing": 3,
        "indexing": 2,
    }


def test_stage_max_attempts_can_be_overridden_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv(
        "TROVE_STAGE_MAX_ATTEMPTS", "downloading=4,transcribing=2"
    )

    config = load_config()

    assert config.stage_max_attempts["downloading"] == 4
    assert config.stage_max_attempts["transcribing"] == 2
    assert config.stage_max_attempts["organizing"] == 3


@pytest.mark.parametrize(
    "value",
    ["downloading=0", "unknown=2", "downloading", "downloading=two"],
)
def test_invalid_stage_max_attempts_fail_at_startup(tmp_path, monkeypatch, value):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv("TROVE_STAGE_MAX_ATTEMPTS", value)

    with pytest.raises(ConfigError, match="TROVE_STAGE_MAX_ATTEMPTS"):
        load_config()
