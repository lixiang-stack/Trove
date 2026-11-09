from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from trove.config import Config


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status", "duration_ms", "client", "run_id", "item_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(config: Config, *, console: bool = True) -> None:
    config.ensure_layout()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = JsonFormatter()
    file_handler = logging.handlers.RotatingFileHandler(
        config.logs_dir / "trove.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def run_log_path(config: Config, run_id: str) -> Path:
    return config.runs_log_dir / f"{run_id}.log"


def append_run_log(config: Config, run_id: str, message: str, level: str = "info") -> None:
    path = run_log_path(config, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"time": _now_iso(), "level": level, "message": message}, ensure_ascii=False
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def tail_run_log(config: Config, run_id: str, *, lines: int = 100) -> list[str]:
    path = run_log_path(config, run_id)
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").splitlines()
    return content[-lines:]


def _now_iso() -> str:
    from trove.clock import now_iso

    return now_iso()
