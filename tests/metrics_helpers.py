from __future__ import annotations

from typing import Any

from trove import metrics


def counter_value(name: str, **labels: Any) -> float:
    return metrics.REGISTRY.get_sample_value(name, labels) or 0.0


def histogram_count(name: str, **labels: Any) -> float:
    return metrics.REGISTRY.get_sample_value(f"{name}_count", labels) or 0.0
