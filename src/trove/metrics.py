from __future__ import annotations

import threading
from typing import Any

_COUNTERS: dict[tuple[str, tuple[tuple[str, Any], ...]], float] = {}
_LOCK = threading.Lock()


def increment(name: str, **labels: Any) -> None:
    add(name, 1, **labels)


def add(name: str, value: float, **labels: Any) -> None:
    key = (name, tuple(sorted(labels.items())))
    with _LOCK:
        _COUNTERS[key] = _COUNTERS.get(key, 0) + value


def counter_value(name: str, **labels: Any) -> float:
    key = (name, tuple(sorted(labels.items())))
    with _LOCK:
        return _COUNTERS.get(key, 0)


def reset() -> None:
    with _LOCK:
        _COUNTERS.clear()
