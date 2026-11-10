from __future__ import annotations

import contextlib
import json
import os
import secrets
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

DEFAULT_HOME = Path("~/Trove")
CONFIG_FILENAME = "config.toml"
ENV_FILENAME = ".env"
DB_FILENAME = "trove.db"

MB = 1024 * 1024
GB = 1024 * MB
DEFAULT_MAX_VIDEO_BYTES = 4 * GB
DEFAULT_MAX_AUDIO_BYTES = 500 * MB
DEFAULT_MAX_EPUB_BYTES = 100 * MB
DEFAULT_MAX_FEED_BYTES = 10 * MB
DEFAULT_MAX_PODCAST_MEDIA_BYTES = GB
DEFAULT_ASR_MODEL = "mlx-community/whisper-large-v3-turbo"


class ConfigError(RuntimeError):
    """Raised when Host configuration cannot be read or written."""


def _default_home() -> Path:
    return Path(os.environ.get("TROVE_HOME", DEFAULT_HOME))


@dataclass(slots=True)
class Config:
    home: Path = field(default_factory=_default_home)
    host: str = "127.0.0.1"
    port: int = 8765
    max_video_bytes: int = DEFAULT_MAX_VIDEO_BYTES
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES
    max_epub_bytes: int = DEFAULT_MAX_EPUB_BYTES
    max_feed_bytes: int = DEFAULT_MAX_FEED_BYTES
    max_podcast_media_bytes: int = DEFAULT_MAX_PODCAST_MEDIA_BYTES
    llm_enabled: bool = True
    asr_model: str = DEFAULT_ASR_MODEL
    ytdlp_cookies: Path | None = None
    force_secure_cookies: bool = False

    def __post_init__(self) -> None:
        self.home = self.home.expanduser().resolve()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.home / CONFIG_FILENAME

    @property
    def env_path(self) -> Path:
        return self.home / ENV_FILENAME

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

    @property
    def worker_heartbeat_path(self) -> Path:
        return self.cache_dir / "worker.json"

    def ensure_layout(self) -> None:
        directories = (
            self.home,
            self.library_dir,
            self.cache_dir,
            self.logs_dir,
            self.runs_log_dir,
            self.uploads_dir,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o700)
        self.home.chmod(0o700)

        if not self.config_path.exists():
            self._write_config({"session_secret": secrets.token_urlsafe(32), "session_epoch": 0})
        else:
            self.config_path.chmod(0o600)
        if not self.env_path.exists():
            self._write_env("")
        else:
            self.env_path.chmod(0o600)

    # ------------------------------------------------------------------
    # config.toml
    # ------------------------------------------------------------------
    def _read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            with self.config_path.open("rb") as handle:
                return tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"Could not read config {self.config_path}: {exc}") from exc

    def _write_config(self, values: dict[str, Any]) -> None:
        lines = []
        for key in sorted(values):
            value = values[key]
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, int):
                rendered = str(value)
            else:
                rendered = json.dumps(str(value), ensure_ascii=False)
            lines.append(f"{key} = {rendered}\n")
        self._atomic_write(self.config_path, "".join(lines), 0o600)

    def _update_config(self, **values: Any) -> None:
        data = self._read_config()
        data.update(values)
        self._write_config(data)

    def _write_env(self, contents: str) -> None:
        self._atomic_write(self.env_path, contents, 0o600)

    @staticmethod
    def _atomic_write(path: Path, contents: str, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            temporary.write_text(contents, encoding="utf-8")
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        path.chmod(mode)

    # ------------------------------------------------------------------
    # Auth material
    # ------------------------------------------------------------------
    @property
    def password_hash(self) -> str | None:
        value = self._read_config().get("password_hash")
        return str(value) if value else None

    def set_password(self, password: str) -> None:
        if not password:
            raise ConfigError("Password cannot be empty")
        hasher = PasswordHasher()
        self._update_config(password_hash=hasher.hash(password))

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
        value = self._read_config().get("session_secret")
        if not value:
            value = secrets.token_urlsafe(32)
            self._update_config(session_secret=value)
        return str(value)

    @property
    def session_epoch(self) -> int:
        value = self._read_config().get("session_epoch", 0)
        return int(value)

    def invalidate_sessions(self) -> None:
        self._update_config(session_epoch=self.session_epoch + 1)

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    def load_dotenv(self) -> None:
        if not self.env_path.exists():
            return
        try:
            for raw in self.env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            return


def load_config(home: Path | str | None = None) -> Config:
    if home is not None:
        os.environ["TROVE_HOME"] = str(Path(home).expanduser().resolve())
    config = Config(
        host=os.environ.get("TROVE_BIND", "127.0.0.1"),
        port=int(os.environ.get("TROVE_PORT", "8765")),
        max_video_bytes=int(
            os.environ.get("TROVE_MAX_VIDEO_BYTES", str(DEFAULT_MAX_VIDEO_BYTES))
        ),
        max_audio_bytes=int(
            os.environ.get("TROVE_MAX_AUDIO_BYTES", str(DEFAULT_MAX_AUDIO_BYTES))
        ),
        max_epub_bytes=int(
            os.environ.get("TROVE_MAX_EPUB_BYTES", str(DEFAULT_MAX_EPUB_BYTES))
        ),
        max_feed_bytes=int(
            os.environ.get("TROVE_MAX_FEED_BYTES", str(DEFAULT_MAX_FEED_BYTES))
        ),
        max_podcast_media_bytes=int(
            os.environ.get("TROVE_MAX_PODCAST_BYTES", str(DEFAULT_MAX_PODCAST_MEDIA_BYTES))
        ),
        llm_enabled=os.environ.get("TROVE_LLM_ENABLED", "true").lower() not in {"0", "false", "no"},
        asr_model=os.environ.get("TROVE_ASR_MODEL", DEFAULT_ASR_MODEL),
        force_secure_cookies=os.environ.get("TROVE_SECURE_COOKIES", "").lower()
        in {"1", "true", "yes"},
    )
    cookies = os.environ.get("TROVE_YTDLP_COOKIES")
    if cookies:
        config.ytdlp_cookies = Path(cookies).expanduser().resolve()
    config.ensure_layout()
    config.load_dotenv()
    return config
