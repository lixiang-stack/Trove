"""Prometheus metrics for the Host and worker processes.

The module owns one registry for the whole process. Metrics are created at
import time, so repeated ``create_app`` calls never re-register collectors.
Labels stay low-cardinality: run ids and item ids belong on traces, not metrics.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger("trove.metrics")

REGISTRY = CollectorRegistry(auto_describe=True)

STAGE_DURATION = Histogram(
    "trove_stage_duration_seconds",
    "Processing stage wall-clock duration.",
    ["stage", "outcome"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    registry=REGISTRY,
)
STAGE_FAILURES = Counter(
    "trove_stage_failures_total",
    "Stage failures by stable error code.",
    ["stage", "code"],
    registry=REGISTRY,
)
STAGE_RETRIES = Counter(
    "trove_stage_retries_total",
    "Stage tasks requeued by the retry policy or lease reaper.",
    ["stage"],
    registry=REGISTRY,
)
STAGE_DEAD = Counter(
    "trove_stage_dead_total",
    "Stage tasks that exhausted their attempts.",
    ["stage"],
    registry=REGISTRY,
)
QUEUE_DEPTH = Gauge(
    "trove_queue_depth",
    "Queued stage tasks that are ready to claim.",
    ["stage"],
    registry=REGISTRY,
)
WORKER_LEASE_AGE = Gauge(
    "trove_worker_lease_age_seconds",
    "Age of the oldest currently running stage task.",
    registry=REGISTRY,
)
ASR_REALTIME_FACTOR = Histogram(
    "trove_asr_realtime_factor",
    "ASR wall-clock seconds per audio second.",
    buckets=(0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1, 2, 5),
    registry=REGISTRY,
)
LLM_TOKENS = Counter(
    "trove_llm_tokens_total",
    "LLM tokens consumed by successful organization calls.",
    ["kind"],
    registry=REGISTRY,
)
LLM_COST = Counter(
    "trove_llm_cost_usd_total",
    "Estimated LLM cost in US dollars for successful organization calls.",
    registry=REGISTRY,
)
SEARCH_DURATION = Histogram(
    "trove_search_duration_seconds",
    "Search request duration.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
    registry=REGISTRY,
)
SEARCH_RESULTS = Histogram(
    "trove_search_results",
    "Number of Items returned by a search request.",
    buckets=(0, 1, 2, 5, 10, 20, 50, 100, 200),
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "trove_http_request_duration_seconds",
    "HTTP request duration by route template.",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10),
    registry=REGISTRY,
)
EXTERNAL_CACHE_HITS = Counter(
    "trove_external_cache_hits_total",
    "External calls avoided by a content-package cache hit.",
    ["cache"],
    registry=REGISTRY,
)
EXTERNAL_CACHE_MISSES = Counter(
    "trove_external_cache_misses_total",
    "External-call cache lookups that required a real call.",
    ["cache"],
    registry=REGISTRY,
)
EXTERNAL_CACHE_SAVED_ASR_SECONDS = Counter(
    "trove_external_cache_saved_asr_seconds_total",
    "Audio seconds not transcribed because of a cache hit.",
    registry=REGISTRY,
)
EXTERNAL_CACHE_SAVED_TOKENS = Counter(
    "trove_external_cache_saved_tokens_total",
    "LLM tokens not spent because of a cache hit.",
    ["kind"],
    registry=REGISTRY,
)
EXTERNAL_CACHE_SAVED_COST = Counter(
    "trove_external_cache_saved_cost_usd_total",
    "Estimated LLM cost avoided by a cache hit.",
    registry=REGISTRY,
)

_COUNTERS: dict[str, Counter] = {
    "trove_stage_failures_total": STAGE_FAILURES,
    "trove_stage_retries_total": STAGE_RETRIES,
    "trove_stage_dead_total": STAGE_DEAD,
    "trove_llm_tokens_total": LLM_TOKENS,
    "trove_llm_cost_usd_total": LLM_COST,
    "trove_external_cache_hits_total": EXTERNAL_CACHE_HITS,
    "trove_external_cache_misses_total": EXTERNAL_CACHE_MISSES,
    "trove_external_cache_saved_asr_seconds_total": EXTERNAL_CACHE_SAVED_ASR_SECONDS,
    "trove_external_cache_saved_tokens_total": EXTERNAL_CACHE_SAVED_TOKENS,
    "trove_external_cache_saved_cost_usd_total": EXTERNAL_CACHE_SAVED_COST,
}
_HISTOGRAMS: dict[str, Histogram] = {
    "trove_stage_duration_seconds": STAGE_DURATION,
    "trove_asr_realtime_factor": ASR_REALTIME_FACTOR,
    "trove_search_duration_seconds": SEARCH_DURATION,
    "trove_search_results": SEARCH_RESULTS,
    "trove_http_request_duration_seconds": HTTP_DURATION,
}


def record_stage_duration(stage: str, outcome: str, seconds: float) -> None:
    STAGE_DURATION.labels(stage=stage, outcome=outcome).observe(seconds)


def record_stage_failure(stage: str, code: str) -> None:
    STAGE_FAILURES.labels(stage=stage, code=code).inc()


def record_stage_retry(stage: str) -> None:
    STAGE_RETRIES.labels(stage=stage).inc()


def record_stage_dead(stage: str) -> None:
    STAGE_DEAD.labels(stage=stage).inc()


def record_asr_realtime_factor(seconds: float) -> None:
    ASR_REALTIME_FACTOR.observe(seconds)


def record_llm_usage(input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    if input_tokens:
        LLM_TOKENS.labels(kind="input").inc(input_tokens)
    if output_tokens:
        LLM_TOKENS.labels(kind="output").inc(output_tokens)
    if cost_usd:
        LLM_COST.inc(cost_usd)


def record_search(seconds: float, result_count: int) -> None:
    SEARCH_DURATION.observe(seconds)
    SEARCH_RESULTS.observe(result_count)


def record_http_request(
    method: str, route: str, status: int, seconds: float
) -> None:
    HTTP_DURATION.labels(
        method=method, route=route, status=str(status)
    ).observe(seconds)


def record_external_cache_hit(cache: str) -> None:
    EXTERNAL_CACHE_HITS.labels(cache=cache).inc()


def record_external_cache_miss(cache: str) -> None:
    EXTERNAL_CACHE_MISSES.labels(cache=cache).inc()


def render(
    *,
    queue_depths: Mapping[str, int] | None = None,
    lease_age_seconds: float | None = None,
) -> bytes:
    if queue_depths is not None:
        for stage, depth in queue_depths.items():
            QUEUE_DEPTH.labels(stage=stage).set(depth)
    if lease_age_seconds is not None:
        WORKER_LEASE_AGE.set(max(0.0, lease_age_seconds))
    return generate_latest(REGISTRY)


def counter_value(name: str, **labels: Any) -> float:
    counter = _COUNTERS[name]
    child = counter.labels(**labels) if labels else counter
    return child._value.get()


def histogram_count(name: str, **labels: Any) -> float:
    metric = _HISTOGRAMS[name]
    for family in metric.collect():
        for sample in family.samples:
            if not sample.name.endswith("_count"):
                continue
            if all(sample.labels.get(key) == str(value) for key, value in labels.items()):
                return float(sample.value)
    return 0.0


def reset() -> None:
    for metric in (*_COUNTERS.values(), *_HISTOGRAMS.values()):
        metric.clear()
    QUEUE_DEPTH.clear()
    WORKER_LEASE_AGE.clear()


class MetricsServer:
    def __init__(self, server: ThreadingHTTPServer) -> None:
        self._server = server
        self.thread = threading.Thread(
            target=server.serve_forever, name="trove-metrics", daemon=True
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> MetricsServer:
        self.thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self.thread.join(timeout=2)


def start_worker_server(runtime: Any, *, host: str, port: int) -> MetricsServer | None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path.split("?", 1)[0] != "/metrics":
                self.send_error(404)
                return
            body = render(
                queue_depths=runtime.processing.queue_depths(),
                lease_age_seconds=runtime.processing.oldest_lease_age_seconds(),
            )
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            logger.debug("metrics server: " + format, *args)

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        logger.warning(
            "metrics server could not bind %s:%s: %s", host, port, exc
        )
        return None
    return MetricsServer(server)
