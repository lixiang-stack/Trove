from __future__ import annotations

import contextlib
import json
import re
import secrets
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from trove.domain.retry import STAGE_MAX_ATTEMPTS
from trove.domain.worker_pools import ALL_POOL, INDEX_POOL, POOL_NAMES

DEFAULT_HOME = Path("~/Trove")
CONFIG_FILENAME = "config.toml"
STATE_FILENAME = "state.toml"
DB_FILENAME = "trove.db"
LEGACY_LLM_CONFIG_FILENAME = "llm.toml"

MB = 1024 * 1024
GB = 1024 * MB
DEFAULT_MAX_VIDEO_BYTES = 4 * GB
DEFAULT_MAX_AUDIO_BYTES = 500 * MB
DEFAULT_MAX_EPUB_BYTES = 100 * MB
DEFAULT_MAX_FEED_BYTES = 10 * MB
DEFAULT_MAX_PODCAST_MEDIA_BYTES = GB
DEFAULT_MAX_COLLECTION_ITEMS = 100
DEFAULT_MAX_COLLECTION_DURATION_SEC = 100 * 60 * 60
DEFAULT_ASR_MODEL = "paraformer-zh"
DEFAULT_LLM_CHUNK_CHARS = 20_000
DEFAULT_LLM_MAX_CALLS_PER_ITEM = 16
DEFAULT_LLM_MAX_OUTPUT_TOKENS_PER_CALL = 1024
DEFAULT_LLM_MAX_INPUT_TOKENS_PER_ITEM = 200_000
DEFAULT_LLM_INPUT_COST_PER_MILLION = 0.28
DEFAULT_LLM_OUTPUT_COST_PER_MILLION = 0.42
DEFAULT_LLM_TIMEOUT_SECONDS = 90.0
DEFAULT_WORKER_LEASE_SECONDS = 25
DEFAULT_WORKER_HEARTBEAT_SECONDS = 5
DEFAULT_WORKER_REAPER_INTERVAL_SECONDS = 5
DEFAULT_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30
DEFAULT_METRICS_WORKER_PORT = 8766

# The default `trove worker` stays a single serial claimer. Per-pool workers
# use the resource-specific defaults below.
DEFAULT_POOL_CONCURRENCY: dict[str, int] = {
    ALL_POOL: 1,
    "download": 3,
    "asr": 1,
    "llm": 2,
    INDEX_POOL: 1,
}


def clamp_pool_concurrency(pool: str, value: int) -> int:
    return DEFAULT_POOL_CONCURRENCY[INDEX_POOL] if pool == INDEX_POOL else value


def _validate_metrics_worker_port(value: int) -> None:
    if not 1 <= value <= 65535:
        raise ConfigError("[metrics] worker_port must be between 1 and 65535")


def default_llm_config_path() -> Path:
    """Legacy LLM config path imported into config.toml on upgrade."""
    return Path.home() / ".config" / "trove" / LEGACY_LLM_CONFIG_FILENAME


class ConfigError(RuntimeError):
    """Raised when Host configuration cannot be read or written."""


def resolve_home(home: Path | str | None = None) -> Path:
    return (Path(home) if home is not None else DEFAULT_HOME).expanduser().resolve()


@dataclass(slots=True)
class LLMConfig:
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    enabled: bool = True
    chunk_chars: int = DEFAULT_LLM_CHUNK_CHARS
    max_calls_per_item: int = DEFAULT_LLM_MAX_CALLS_PER_ITEM
    max_output_tokens_per_call: int = DEFAULT_LLM_MAX_OUTPUT_TOKENS_PER_CALL
    max_input_tokens_per_item: int = DEFAULT_LLM_MAX_INPUT_TOKENS_PER_ITEM
    input_cost_per_million: float = DEFAULT_LLM_INPUT_COST_PER_MILLION
    output_cost_per_million: float = DEFAULT_LLM_OUTPUT_COST_PER_MILLION
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS


@dataclass(slots=True)
class Config:
    home: Path = DEFAULT_HOME
    host: str = "127.0.0.1"
    port: int = 8765
    log_console: bool = True
    max_video_bytes: int = DEFAULT_MAX_VIDEO_BYTES
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES
    max_epub_bytes: int = DEFAULT_MAX_EPUB_BYTES
    max_feed_bytes: int = DEFAULT_MAX_FEED_BYTES
    max_podcast_media_bytes: int = DEFAULT_MAX_PODCAST_MEDIA_BYTES
    max_collection_items: int = DEFAULT_MAX_COLLECTION_ITEMS
    max_collection_duration_sec: int = DEFAULT_MAX_COLLECTION_DURATION_SEC
    llm: LLMConfig = field(default_factory=lambda: LLMConfig(enabled=False))
    asr_model: str = DEFAULT_ASR_MODEL
    stage_max_attempts: dict[str, int] = field(default_factory=dict)
    worker_lease_seconds: int = DEFAULT_WORKER_LEASE_SECONDS
    worker_heartbeat_seconds: int = DEFAULT_WORKER_HEARTBEAT_SECONDS
    worker_reaper_interval_seconds: int = DEFAULT_WORKER_REAPER_INTERVAL_SECONDS
    worker_shutdown_timeout_seconds: int = DEFAULT_WORKER_SHUTDOWN_TIMEOUT_SECONDS
    worker_pools: tuple[str, ...] = (ALL_POOL,)
    worker_concurrency: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_POOL_CONCURRENCY)
    )
    metrics_enabled: bool = True
    metrics_worker_port: int = DEFAULT_METRICS_WORKER_PORT
    ytdlp_cookies: Path | None = None
    force_secure_cookies: bool = False

    def __post_init__(self) -> None:
        self.home = self.home.expanduser().resolve()
        overrides = self.stage_max_attempts
        unknown_stages = set(overrides) - set(STAGE_MAX_ATTEMPTS)
        if unknown_stages:
            raise ConfigError(
                "[worker.stage_max_attempts] contains unknown stages: "
                + ", ".join(sorted(unknown_stages))
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in overrides.values()
        ):
            raise ConfigError(
                "[worker.stage_max_attempts] values must be positive integers"
            )
        self.stage_max_attempts = {**STAGE_MAX_ATTEMPTS, **overrides}
        if self.worker_heartbeat_seconds <= 0:
            raise ConfigError("[worker] heartbeat_seconds must be positive")
        if self.worker_lease_seconds <= self.worker_heartbeat_seconds:
            raise ConfigError(
                "[worker] lease_seconds must be greater than heartbeat_seconds"
            )
        if self.worker_reaper_interval_seconds <= 0:
            raise ConfigError("[worker] reaper_interval_seconds must be positive")
        if self.worker_shutdown_timeout_seconds <= 0:
            raise ConfigError("[worker] shutdown_timeout_seconds must be positive")
        _validate_metrics_worker_port(self.metrics_worker_port)
        unknown_pools = set(self.worker_pools) - set(POOL_NAMES)
        if unknown_pools:
            raise ConfigError(
                "[worker] pools contains unknown pools: "
                f"{', '.join(sorted(unknown_pools))}; "
                f"choose from: {', '.join(POOL_NAMES)}"
            )
        self.worker_pools = tuple(dict.fromkeys(self.worker_pools)) or (ALL_POOL,)
        unknown_concurrency = set(self.worker_concurrency) - set(DEFAULT_POOL_CONCURRENCY)
        if unknown_concurrency:
            raise ConfigError(
                "[worker.concurrency] contains unknown pools: "
                f"{', '.join(sorted(unknown_concurrency))}; "
                f"choose from: {', '.join(DEFAULT_POOL_CONCURRENCY)}"
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in self.worker_concurrency.values()
        ):
            raise ConfigError("[worker.concurrency] values must be positive integers")
        merged = {**DEFAULT_POOL_CONCURRENCY, **self.worker_concurrency}
        self.worker_concurrency = {
            pool: clamp_pool_concurrency(pool, value)
            for pool, value in merged.items()
        }
        if self.ytdlp_cookies is not None:
            cookies = self.ytdlp_cookies.expanduser()
            self.ytdlp_cookies = (
                cookies if cookies.is_absolute() else (self.home / cookies)
            ).resolve()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.home / CONFIG_FILENAME

    @property
    def state_path(self) -> Path:
        return self.home / STATE_FILENAME

    @property
    def db_path(self) -> Path:
        return self.home / DB_FILENAME

    @property
    def library_dir(self) -> Path:
        return self.home / "library"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def runs_log_dir(self) -> Path:
        return self.logs_dir / "runs"

    @property
    def uploads_dir(self) -> Path:
        return self.cache_dir / "uploads"

    def ensure_layout(self) -> None:
        prepare_home(self.home, default_host=self.host, default_port=self.port)

    # ------------------------------------------------------------------
    # state.toml
    # ------------------------------------------------------------------
    def _read_state(self) -> dict[str, Any]:
        try:
            return _read_toml(self.state_path)
        except FileNotFoundError:
            return {}

    def _write_state(self, values: dict[str, Any]) -> None:
        _atomic_write(self.state_path, _render_flat(values), 0o600)

    def _update_state(self, **values: Any) -> None:
        data = self._read_state()
        data.update(values)
        self._write_state(data)

    # ------------------------------------------------------------------
    # Auth material
    # ------------------------------------------------------------------
    @property
    def password_hash(self) -> str | None:
        value = self._read_state().get("password_hash")
        return str(value) if value else None

    def set_password(self, password: str) -> None:
        if not password:
            raise ConfigError("Password cannot be empty")
        hasher = PasswordHasher()
        self._update_state(
            password_hash=hasher.hash(password),
            session_epoch=self.session_epoch + 1,
        )

    def verify_password(self, password: str) -> bool:
        stored = self.password_hash
        if not stored:
            # Keep the timing of a failed login comparable with a configured Host.
            dummy = (
                "$argon2id$v=19$m=65536,t=3,p=4$"
                "c29tZXNhbHRzb21lc2FsdA$3fP5d0H8bR0nQnJmK1l0sQ"
            )
            with contextlib.suppress(VerifyMismatchError, InvalidHashError):
                PasswordHasher().verify(dummy, password)
            return False
        try:
            return PasswordHasher().verify(stored, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def password_configured(self) -> bool:
        return self.password_hash is not None

    @property
    def session_secret(self) -> str:
        value = self._read_state().get("session_secret")
        if not value:
            value = secrets.token_urlsafe(32)
            self._update_state(session_secret=value)
        return str(value)

    @property
    def session_epoch(self) -> int:
        value = self._read_state().get("session_epoch", 0)
        return int(value)

    def invalidate_sessions(self) -> None:
        self._update_state(session_epoch=self.session_epoch + 1)


def load_llm_config(path: Path | None = None) -> LLMConfig:
    """Load a standalone legacy llm.toml file.

    Runtime configuration lives in config.toml; this helper remains for the
    one-time upgrade import and focused tests.
    """
    config_path = path or default_llm_config_path()
    try:
        values = _read_toml(config_path)
    except FileNotFoundError:
        return LLMConfig(enabled=False)
    return _llm_from_values(values)


def load_config(home: Path | str | None = None) -> Config:
    resolved = resolve_home(home)
    prepare_home(resolved)
    values = _read_toml(resolved / CONFIG_FILENAME)
    server = _section(values, "server")
    limits = _section(values, "limits")
    asr = _section(values, "asr")
    worker = _section(values, "worker")
    metrics = _section(values, "metrics")
    intake = _section(values, "intake")
    llm_values = values.get("llm")
    if llm_values is None:
        llm = LLMConfig(enabled=False)
    elif isinstance(llm_values, dict):
        llm = _llm_from_values(llm_values)
    else:
        raise ConfigError("[llm] must be a TOML table")
    return Config(
        home=resolved,
        host=_get_str(server, "host", "127.0.0.1", section="server"),
        port=_get_int(server, "port", 8765, section="server", minimum=1),
        log_console=_get_bool(server, "log_console", True, section="server"),
        force_secure_cookies=_get_bool(
            server, "secure_cookies", False, section="server"
        ),
        max_video_bytes=_get_int(
            limits,
            "max_video_bytes",
            DEFAULT_MAX_VIDEO_BYTES,
            section="limits",
            minimum=1,
        ),
        max_audio_bytes=_get_int(
            limits,
            "max_audio_bytes",
            DEFAULT_MAX_AUDIO_BYTES,
            section="limits",
            minimum=1,
        ),
        max_epub_bytes=_get_int(
            limits,
            "max_epub_bytes",
            DEFAULT_MAX_EPUB_BYTES,
            section="limits",
            minimum=1,
        ),
        max_feed_bytes=_get_int(
            limits,
            "max_feed_bytes",
            DEFAULT_MAX_FEED_BYTES,
            section="limits",
            minimum=1,
        ),
        max_podcast_media_bytes=_get_int(
            limits,
            "max_podcast_bytes",
            DEFAULT_MAX_PODCAST_MEDIA_BYTES,
            section="limits",
            minimum=1,
        ),
        max_collection_items=_get_int(
            limits,
            "max_collection_items",
            DEFAULT_MAX_COLLECTION_ITEMS,
            section="limits",
            minimum=1,
        ),
        max_collection_duration_sec=_get_int(
            limits,
            "max_collection_duration_sec",
            DEFAULT_MAX_COLLECTION_DURATION_SEC,
            section="limits",
            minimum=1,
        ),
        asr_model=_get_str(asr, "model", DEFAULT_ASR_MODEL, section="asr"),
        stage_max_attempts=_stage_max_attempts_from_values(worker),
        worker_lease_seconds=_get_int(
            worker,
            "lease_seconds",
            DEFAULT_WORKER_LEASE_SECONDS,
            section="worker",
            minimum=1,
        ),
        worker_heartbeat_seconds=_get_int(
            worker,
            "heartbeat_seconds",
            DEFAULT_WORKER_HEARTBEAT_SECONDS,
            section="worker",
            minimum=1,
        ),
        worker_reaper_interval_seconds=_get_int(
            worker,
            "reaper_interval_seconds",
            DEFAULT_WORKER_REAPER_INTERVAL_SECONDS,
            section="worker",
            minimum=1,
        ),
        worker_shutdown_timeout_seconds=_get_int(
            worker,
            "shutdown_timeout_seconds",
            DEFAULT_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
            section="worker",
            minimum=1,
        ),
        worker_pools=_worker_pools_from_values(worker),
        worker_concurrency=_worker_concurrency_from_values(worker),
        metrics_enabled=_get_bool(metrics, "enabled", True, section="metrics"),
        metrics_worker_port=_get_int(
            metrics,
            "worker_port",
            DEFAULT_METRICS_WORKER_PORT,
            section="metrics",
            minimum=1,
        ),
        ytdlp_cookies=_optional_path(
            _get_str(intake, "ytdlp_cookies", "", section="intake")
        ),
        llm=llm,
    )


def prepare_home(
    home: Path | str,
    *,
    default_host: str = "127.0.0.1",
    default_port: int = 8765,
) -> None:
    home = resolve_home(home)
    directories = (
        home,
        home / "library",
        home / "cache",
        home / "logs",
        home / "logs" / "runs",
        home / "cache" / "uploads",
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)

    config_path = home / CONFIG_FILENAME
    state_path = home / STATE_FILENAME
    if not config_path.exists():
        legacy_llm = default_llm_config_path()
        legacy_values = _read_toml(legacy_llm) if legacy_llm.exists() else None
        _atomic_write(
            config_path,
            default_config_text(
                host=default_host, port=default_port, llm=legacy_values
            ),
            0o600,
        )
    else:
        _migrate_legacy_config(config_path, state_path)
        _ensure_server_section(config_path, default_host, default_port)
        config_path.chmod(0o600)
    if not state_path.exists():
        _atomic_write(
            state_path,
            _render_flat(
                {"session_secret": secrets.token_urlsafe(32), "session_epoch": 0}
            ),
            0o600,
        )
    else:
        state_path.chmod(0o600)


def default_config_text(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    llm: dict[str, Any] | None = None,
) -> str:
    return f"""# Trove Host configuration. Restart the API and worker after editing.
# Generated auth state (password hash and session secret) lives in state.toml.

[server]
host = {_toml_value(host)}
port = {port}
# Set to true when serving over HTTPS.
secure_cookies = false
# Also write logs to stderr.
log_console = true

[limits]
max_video_bytes = {DEFAULT_MAX_VIDEO_BYTES}
max_audio_bytes = {DEFAULT_MAX_AUDIO_BYTES}
max_epub_bytes = {DEFAULT_MAX_EPUB_BYTES}
max_feed_bytes = {DEFAULT_MAX_FEED_BYTES}
max_podcast_bytes = {DEFAULT_MAX_PODCAST_MEDIA_BYTES}
max_collection_items = {DEFAULT_MAX_COLLECTION_ITEMS}
max_collection_duration_sec = {DEFAULT_MAX_COLLECTION_DURATION_SEC}

[asr]
model = {_toml_value(DEFAULT_ASR_MODEL)}

[worker]
pools = ["all"]
lease_seconds = {DEFAULT_WORKER_LEASE_SECONDS}
heartbeat_seconds = {DEFAULT_WORKER_HEARTBEAT_SECONDS}
reaper_interval_seconds = {DEFAULT_WORKER_REAPER_INTERVAL_SECONDS}
shutdown_timeout_seconds = {DEFAULT_WORKER_SHUTDOWN_TIMEOUT_SECONDS}

[worker.concurrency]
download = {DEFAULT_POOL_CONCURRENCY["download"]}
asr = {DEFAULT_POOL_CONCURRENCY["asr"]}
llm = {DEFAULT_POOL_CONCURRENCY["llm"]}
index = {DEFAULT_POOL_CONCURRENCY[INDEX_POOL]}

[worker.stage_max_attempts]
downloading = {STAGE_MAX_ATTEMPTS["downloading"]}
extracting_audio = {STAGE_MAX_ATTEMPTS["extracting_audio"]}
extracting_text = {STAGE_MAX_ATTEMPTS["extracting_text"]}
transcribing = {STAGE_MAX_ATTEMPTS["transcribing"]}
organizing = {STAGE_MAX_ATTEMPTS["organizing"]}
indexing = {STAGE_MAX_ATTEMPTS["indexing"]}

[metrics]
# Prometheus endpoint on the worker (the API serves /metrics on its own port).
enabled = true
worker_port = {DEFAULT_METRICS_WORKER_PORT}

[intake]
# Optional Netscape cookies file for yt-dlp. Relative paths are under ~/Trove.
ytdlp_cookies = ""

[llm]
{_llm_section_text(llm)}
"""


def _llm_section_text(values: dict[str, Any] | None) -> str:
    current = values or {}
    enabled = current.get("enabled", values is not None)
    model = current.get("model", "")
    base_url = current.get("base_url", "")
    api_key = current.get("api_key", "")
    chunk_chars = current.get("chunk_chars", DEFAULT_LLM_CHUNK_CHARS)
    max_calls_per_item = current.get(
        "max_calls_per_item", DEFAULT_LLM_MAX_CALLS_PER_ITEM
    )
    max_output_tokens_per_call = current.get(
        "max_output_tokens_per_call", DEFAULT_LLM_MAX_OUTPUT_TOKENS_PER_CALL
    )
    max_input_tokens_per_item = current.get(
        "max_input_tokens_per_item", DEFAULT_LLM_MAX_INPUT_TOKENS_PER_ITEM
    )
    input_cost_per_million = current.get(
        "input_cost_per_million", DEFAULT_LLM_INPUT_COST_PER_MILLION
    )
    output_cost_per_million = current.get(
        "output_cost_per_million", DEFAULT_LLM_OUTPUT_COST_PER_MILLION
    )
    timeout_seconds = current.get("timeout_seconds", DEFAULT_LLM_TIMEOUT_SECONDS)
    lines = []
    if enabled is False:
        lines.append("# Set enabled = true after filling model, base_url, and api_key.")
    lines.extend(
        [
            f"enabled = {_toml_value(enabled)}",
            f"model = {_toml_value(str(model))}",
            f"base_url = {_toml_value(str(base_url))}",
            f"api_key = {_toml_value(str(api_key))}",
            f"chunk_chars = {_toml_value(chunk_chars)}",
            f"max_calls_per_item = {_toml_value(max_calls_per_item)}",
            f"max_output_tokens_per_call = {_toml_value(max_output_tokens_per_call)}",
            f"max_input_tokens_per_item = {_toml_value(max_input_tokens_per_item)}",
            f"input_cost_per_million = {_toml_value(input_cost_per_million)}",
            f"output_cost_per_million = {_toml_value(output_cost_per_million)}",
            f"timeout_seconds = {_toml_value(timeout_seconds)}",
        ]
    )
    return "\n".join(lines)


def _llm_from_values(values: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        model=_get_str(values, "model", "", section="llm"),
        base_url=_get_str(values, "base_url", "", section="llm"),
        api_key=_get_str(values, "api_key", "", section="llm"),
        enabled=_get_bool(values, "enabled", True, section="llm"),
        chunk_chars=_get_int(
            values,
            "chunk_chars",
            DEFAULT_LLM_CHUNK_CHARS,
            section="llm",
            minimum=1,
        ),
        max_calls_per_item=_get_int(
            values,
            "max_calls_per_item",
            DEFAULT_LLM_MAX_CALLS_PER_ITEM,
            section="llm",
            minimum=1,
        ),
        max_output_tokens_per_call=_get_int(
            values,
            "max_output_tokens_per_call",
            DEFAULT_LLM_MAX_OUTPUT_TOKENS_PER_CALL,
            section="llm",
            minimum=1,
        ),
        max_input_tokens_per_item=_get_int(
            values,
            "max_input_tokens_per_item",
            DEFAULT_LLM_MAX_INPUT_TOKENS_PER_ITEM,
            section="llm",
            minimum=1,
        ),
        input_cost_per_million=_get_float(
            values,
            "input_cost_per_million",
            DEFAULT_LLM_INPUT_COST_PER_MILLION,
            section="llm",
        ),
        output_cost_per_million=_get_float(
            values,
            "output_cost_per_million",
            DEFAULT_LLM_OUTPUT_COST_PER_MILLION,
            section="llm",
        ),
        timeout_seconds=_get_float(
            values,
            "timeout_seconds",
            DEFAULT_LLM_TIMEOUT_SECONDS,
            section="llm",
            minimum=0.1,
        ),
    )


def _stage_max_attempts_from_values(worker: dict[str, Any]) -> dict[str, int]:
    table = _section(worker, "stage_max_attempts")
    parsed: dict[str, int] = {}
    for stage, value in table.items():
        if stage not in STAGE_MAX_ATTEMPTS:
            raise ConfigError(
                f"[worker.stage_max_attempts] unknown stage: {stage}; "
                f"choose from: {', '.join(STAGE_MAX_ATTEMPTS)}"
            )
        parsed[stage] = _positive_int(
            value, f"[worker.stage_max_attempts] {stage}"
        )
    return parsed


def _worker_pools_from_values(worker: dict[str, Any]) -> tuple[str, ...]:
    value = worker.get("pools", [ALL_POOL])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError("[worker] pools must be an array of pool names")
    names = [item.strip() for item in value]
    if any(not item for item in names):
        raise ConfigError("[worker] pools must not contain empty names")
    return tuple(names)


def _worker_concurrency_from_values(worker: dict[str, Any]) -> dict[str, int]:
    table = _section(worker, "concurrency")
    unknown = set(table) - set(DEFAULT_POOL_CONCURRENCY)
    if unknown:
        raise ConfigError(
            "[worker.concurrency] unknown pools: "
            f"{', '.join(sorted(unknown))}; "
            f"choose from: {', '.join(DEFAULT_POOL_CONCURRENCY)}"
        )
    return {
        pool: _positive_int(value, f"[worker.concurrency] {pool}")
        for pool, value in table.items()
    }


def _optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{label} must be a positive integer")
    return value


def _get_str(
    table: dict[str, Any], key: str, default: str, *, section: str
) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"[{section}] {key} must be a string")
    return value.strip()


def _get_int(
    table: dict[str, Any],
    key: str,
    default: int,
    *,
    section: str,
    minimum: int | None = None,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"[{section}] {key} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"[{section}] {key} must be at least {minimum}")
    return value


def _get_float(
    table: dict[str, Any],
    key: str,
    default: float,
    *,
    section: str,
    minimum: float | None = None,
) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"[{section}] {key} must be a number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ConfigError(f"[{section}] {key} must be at least {minimum}")
    return result


def _get_bool(
    table: dict[str, Any], key: str, default: bool, *, section: str
) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"[{section}] {key} must be true or false")
    return value


def _section(values: dict[str, Any], name: str) -> dict[str, Any]:
    value = values.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a TOML table")
    return value


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Could not read config {path}: {exc}") from exc


def _migrate_legacy_config(config_path: Path, state_path: Path) -> None:
    values = _read_toml(config_path)
    legacy_state: dict[str, Any] = {
        key: values[key]
        for key in ("password_hash", "session_secret", "session_epoch")
        if key in values
    }
    if legacy_state:
        if not state_path.exists():
            _atomic_write(state_path, _render_flat(legacy_state), 0o600)
        _remove_top_level_keys(config_path, set(legacy_state))
    if "llm" not in values:
        legacy_llm = default_llm_config_path()
        if legacy_llm.exists():
            legacy_values = _read_toml(legacy_llm)
            _append_llm_table(config_path, legacy_values)


def _ensure_server_section(config_path: Path, host: str, port: int) -> None:
    values = _read_toml(config_path)
    if "server" in values:
        return
    text = config_path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    text += (
        "\n[server]\n"
        f"host = {_toml_value(host)}\n"
        f"port = {port}\n"
    )
    _atomic_write(config_path, text, 0o600)


def _append_llm_table(config_path: Path, values: dict[str, Any]) -> None:
    text = config_path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    lines = ["\n[llm]"]
    if "enabled" not in values:
        lines.append("enabled = true")
    for key in (
        "enabled",
        "model",
        "base_url",
        "api_key",
        "chunk_chars",
        "max_calls_per_item",
        "max_output_tokens_per_call",
        "max_input_tokens_per_item",
        "input_cost_per_million",
        "output_cost_per_million",
        "timeout_seconds",
    ):
        if key in values:
            lines.append(f"{key} = {_toml_value(values[key])}")
    text += "\n".join(lines) + "\n"
    _atomic_write(config_path, text, 0o600)


def _remove_top_level_keys(config_path: Path, keys: set[str]) -> None:
    pattern = re.compile(
        r"^(?:" + "|".join(re.escape(key) for key in sorted(keys)) + r")\s*="
    )
    text = config_path.read_text(encoding="utf-8")
    lines = [
        line for line in text.splitlines(keepends=True) if not pattern.match(line)
    ]
    _atomic_write(config_path, "".join(lines), 0o600)


def _render_flat(values: dict[str, Any]) -> str:
    return "".join(
        f"{key} = {_toml_value(values[key])}\n" for key in sorted(values)
    )


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ConfigError(f"Unsupported config value: {value!r}")


def _atomic_write(path: Path, contents: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        temporary.write_text(contents, encoding="utf-8")
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    path.chmod(mode)
