from __future__ import annotations

import tomllib

import pytest
from argon2 import PasswordHasher

from trove.cli import main
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
    prepare_home,
)


def _write_config(home, text: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(text, encoding="utf-8")


def test_load_config_creates_config_and_state(tmp_path):
    home = tmp_path / "Trove"

    config = load_config(home=home)

    assert config.home == home.resolve()
    assert config.config_path.is_file()
    assert config.state_path.is_file()
    assert config.config_path.stat().st_mode & 0o777 == 0o600
    assert config.state_path.stat().st_mode & 0o777 == 0o600
    assert config.host == "127.0.0.1"
    assert config.port == 8765
    assert config.llm.enabled is False
    assert config.worker_pools == ("all",)
    assert config.metrics_enabled is True
    assert config.metrics_worker_port == 8766
    assert config.password_hash is None
    assert config.session_secret


def test_config_file_overrides_defaults(tmp_path):
    home = tmp_path / "Trove"
    _write_config(
        home,
        """
[server]
host = "0.0.0.0"
port = 9000
secure_cookies = true
log_console = false

[limits]
max_video_bytes = 123
max_audio_bytes = 456
max_epub_bytes = 789
max_feed_bytes = 1011
max_podcast_bytes = 1213
max_collection_items = 5
max_collection_duration_sec = 60

[asr]
model = "custom-asr"

[worker]
pools = ["download", "asr", "download"]
lease_seconds = 30
heartbeat_seconds = 10
reaper_interval_seconds = 7
shutdown_timeout_seconds = 20

[worker.concurrency]
download = 4
asr = 2
llm = 3
index = 9

[worker.stage_max_attempts]
downloading = 4
transcribing = 2

[intake]
ytdlp_cookies = "cookies.txt"

[metrics]
enabled = false
worker_port = 9101

[llm]
enabled = true
model = "configured-model"
base_url = "https://example.test/v1"
api_key = "sk-configured"
chunk_chars = 1234
max_calls_per_item = 3
max_output_tokens_per_call = 64
max_input_tokens_per_item = 4096
input_cost_per_million = 1.5
output_cost_per_million = 2.5
timeout_seconds = 12.5
""",
    )

    config = load_config(home=home)

    assert config.host == "0.0.0.0"
    assert config.port == 9000
    assert config.force_secure_cookies is True
    assert config.log_console is False
    assert config.max_video_bytes == 123
    assert config.max_audio_bytes == 456
    assert config.max_epub_bytes == 789
    assert config.max_feed_bytes == 1011
    assert config.max_podcast_media_bytes == 1213
    assert config.max_collection_items == 5
    assert config.max_collection_duration_sec == 60
    assert config.asr_model == "custom-asr"
    assert config.worker_pools == ("download", "asr")
    assert config.worker_lease_seconds == 30
    assert config.worker_heartbeat_seconds == 10
    assert config.worker_reaper_interval_seconds == 7
    assert config.worker_shutdown_timeout_seconds == 20
    assert config.worker_concurrency["download"] == 4
    assert config.worker_concurrency["asr"] == 2
    assert config.worker_concurrency["llm"] == 3
    assert config.worker_concurrency["index"] == 1
    assert config.metrics_enabled is False
    assert config.metrics_worker_port == 9101
    assert config.stage_max_attempts["downloading"] == 4
    assert config.stage_max_attempts["transcribing"] == 2
    assert config.stage_max_attempts["organizing"] == 3
    assert config.ytdlp_cookies == (home.resolve() / "cookies.txt")
    assert config.llm == LLMConfig(
        model="configured-model",
        base_url="https://example.test/v1",
        api_key="sk-configured",
        enabled=True,
        chunk_chars=1234,
        max_calls_per_item=3,
        max_output_tokens_per_call=64,
        max_input_tokens_per_item=4096,
        input_cost_per_million=1.5,
        output_cost_per_million=2.5,
        timeout_seconds=12.5,
    )


def test_invalid_toml_fails(tmp_path):
    home = tmp_path / "Trove"
    _write_config(home, "model = [\n")

    with pytest.raises(ConfigError, match="Could not read config"):
        load_config(home=home)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[server]\nport = \"8765\"\n", r"\[server\] port must be an integer"),
        ("[server]\nlog_console = \"yes\"\n", r"\[server\] log_console must be true or false"),
        ("[worker]\npools = [\"bogus\"]\n", r"\[worker\] pools contains unknown pools"),
        ("[worker.concurrency]\nbogus = 2\n", r"\[worker.concurrency\] unknown pools"),
        (
            "[worker.stage_max_attempts]\nbogus = 2\n",
            r"\[worker.stage_max_attempts\] unknown stage",
        ),
        ("[llm]\nenabled = \"yes\"\n", r"\[llm\] enabled must be true or false"),
    ],
)
def test_invalid_config_values_fail(tmp_path, text, message):
    home = tmp_path / "Trove"
    _write_config(home, text)

    with pytest.raises(ConfigError, match=message):
        load_config(home=home)


def test_password_and_session_state_live_in_state_toml(tmp_path):
    home = tmp_path / "Trove"
    config = load_config(home=home)

    config.set_password("first-password")

    assert config.verify_password("first-password")
    assert not config.verify_password("wrong-password")
    state = tomllib.loads(config.state_path.read_text(encoding="utf-8"))
    assert "password_hash" in state
    assert "password_hash" not in config.config_path.read_text(encoding="utf-8")
    first_epoch = config.session_epoch

    config.set_password("second-password")

    assert config.verify_password("second-password")
    assert not config.verify_password("first-password")
    assert config.session_epoch == first_epoch + 1

    config.invalidate_sessions()
    assert config.session_epoch == first_epoch + 2


def test_legacy_auth_fields_migrate_to_state_toml(tmp_path):
    home = tmp_path / "Trove"
    password_hash = PasswordHasher().hash("legacy-password")
    _write_config(
        home,
        "\n".join(
            [
                'password_hash = "' + password_hash + '"',
                'session_secret = "legacy-secret"',
                "session_epoch = 3",
                "",
                "[server]",
                'host = "127.0.0.1"',
            ]
        )
        + "\n",
    )

    config = load_config(home=home)

    assert config.verify_password("legacy-password")
    assert config.session_secret == "legacy-secret"
    assert config.session_epoch == 3
    text = config.config_path.read_text(encoding="utf-8")
    assert "password_hash" not in text
    assert "session_secret" not in text
    assert "session_epoch" not in text
    state = tomllib.loads(config.state_path.read_text(encoding="utf-8"))
    assert state["session_epoch"] == 3


def test_legacy_llm_toml_is_imported_into_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = default_llm_config_path()
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        "\n".join(
            [
                'model = "legacy-model"',
                'base_url = "https://legacy.test/v1"',
                'api_key = "sk-legacy"',
                "chunk_chars = 4321",
            ]
        ),
        encoding="utf-8",
    )
    home = tmp_path / "Trove"
    _write_config(home, '[server]\nport = 8765\n')

    config = load_config(home=home)

    assert config.llm.model == "legacy-model"
    assert config.llm.base_url == "https://legacy.test/v1"
    assert config.llm.api_key == "sk-legacy"
    assert config.llm.chunk_chars == 4321
    assert config.llm.enabled is True
    assert "[llm]" in config.config_path.read_text(encoding="utf-8")


def test_legacy_llm_toml_is_imported_when_config_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = default_llm_config_path()
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        "\n".join(
            [
                'model = "first-run-model"',
                'base_url = "https://first-run.test/v1"',
                'api_key = "sk-first-run"',
            ]
        ),
        encoding="utf-8",
    )
    home = tmp_path / "Trove"

    config = load_config(home=home)

    assert config.llm.model == "first-run-model"
    assert config.llm.base_url == "https://first-run.test/v1"
    assert config.llm.api_key == "sk-first-run"
    assert config.llm.enabled is True
    assert "[llm]" in config.config_path.read_text(encoding="utf-8")


def test_legacy_config_without_server_gets_the_default_server(tmp_path):
    home = tmp_path / "Trove"
    password_hash = PasswordHasher().hash("legacy-password")
    _write_config(
        home,
        f'password_hash = "{password_hash}"\nsession_secret = "legacy-secret"\n',
    )

    config = load_config(home=home)

    assert config.host == "127.0.0.1"
    assert config.port == 8765
    assert "[server]" in config.config_path.read_text(encoding="utf-8")


def test_config_init_adds_server_to_a_legacy_config(tmp_path):
    home = tmp_path / "Trove"
    _write_config(home, 'password_hash = "legacy"\n')

    code = main(
        ["--home", str(home), "config", "init", "--host", "0.0.0.0"]
    )

    assert code == 0
    config = load_config(home=home)
    assert config.host == "0.0.0.0"


def test_legacy_llm_config_loader_defaults_to_disabled(tmp_path):
    llm = load_llm_config(tmp_path / "llm.toml")

    assert llm.model == ""
    assert llm.base_url == ""
    assert llm.api_key == ""
    assert llm.enabled is False
    assert llm.chunk_chars == DEFAULT_LLM_CHUNK_CHARS
    assert llm.max_calls_per_item == DEFAULT_LLM_MAX_CALLS_PER_ITEM
    assert llm.timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS


def test_worker_lease_must_be_longer_than_the_heartbeat(tmp_path):
    with pytest.raises(ConfigError, match="lease_seconds"):
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


def test_config_init_command_writes_host_and_port(tmp_path):
    home = tmp_path / "Trove"

    code = main(
        [
            "--home",
            str(home),
            "config",
            "init",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
        ]
    )

    assert code == 0
    config = load_config(home=home)
    assert config.host == "0.0.0.0"
    assert config.port == 9000


def test_prepare_home_does_not_overwrite_existing_config(tmp_path):
    home = tmp_path / "Trove"
    prepare_home(home)
    config_path = home / "config.toml"
    config_path.write_text('[server]\nport = 9000\n', encoding="utf-8")

    prepare_home(home)

    assert "port = 9000" in config_path.read_text(encoding="utf-8")
