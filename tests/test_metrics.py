from __future__ import annotations

import argparse
import json
import re
import socket
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from trove import cli, metrics
from trove.clock import utc_ms
from trove.config import Config
from trove.db.engine import upgrade_database
from trove.db.models import RunStep

from .conftest import seed_item
from .metrics_helpers import counter_value, histogram_count

EXPECTED_METRICS = {
    "trove_stage_duration_seconds",
    "trove_stage_failures_total",
    "trove_stage_retries_total",
    "trove_stage_dead_total",
    "trove_queue_depth",
    "trove_worker_lease_age_seconds",
    "trove_asr_realtime_factor",
    "trove_llm_tokens_total",
    "trove_llm_cost_usd_total",
    "trove_search_duration_seconds",
    "trove_search_results",
    "trove_http_request_duration_seconds",
    "trove_external_cache_hits_total",
    "trove_external_cache_misses_total",
}


def _add_queued_item(api_host) -> tuple[str, str]:
    api_host.login()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=metricsitem"},
    )
    assert response.status_code == 201, response.text
    item = response.json()["item"]
    return item["id"], item["run"]["id"]


def _gauge(text: str, name: str, **labels: str) -> float:
    if labels:
        selector = ",".join(f'{key}="{value}"' for key, value in labels.items())
        pattern = rf"^{name}\{{{re.escape(selector)}\}} ([0-9.e+-]+)$"
    else:
        pattern = rf"^{name} ([0-9.e+-]+)$"
    match = re.search(pattern, text, re.MULTILINE)
    assert match, f"{name}{labels} missing from metrics"
    return float(match.group(1))


def test_metrics_endpoint_requires_authentication(api_host):
    response = api_host.client.get("/metrics")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.required"


def test_metrics_expose_expected_series_and_no_high_cardinality_labels(api_host):
    item_id, run_id = _add_queued_item(api_host)

    response = api_host.client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text

    for name in EXPECTED_METRICS:
        assert name in text, name
    assert _gauge(text, "trove_queue_depth", stage="downloading") == 1.0
    assert _gauge(text, "trove_worker_lease_age_seconds") >= 0.0
    api_host.client.get(f"/api/items/{item_id}")
    text = api_host.client.get("/metrics").text
    assert 'route="/api/items"' in text
    assert 'route="/api/items/{item_id}"' in text
    assert 'status="201"' in text

    for label in ("item_id", "run_id", "query", "path", "request_id"):
        assert not re.search(rf'\b{label}="', text), label
    assert item_id not in text
    assert run_id not in text

    api_host.client.get("/api/search", params={"q": "unique-secret-query"})
    text = api_host.client.get("/metrics").text
    assert "unique-secret-query" not in text


def test_metrics_track_queue_depth_and_oldest_lease(api_host):
    _, run_id = _add_queued_item(api_host)
    queued = api_host.client.get("/metrics").text
    assert _gauge(queued, "trove_queue_depth", stage="downloading") == 1.0

    assert api_host.runtime.processing.claim_next(worker_id="metrics-worker") == run_id
    with api_host.runtime.sessions() as session:
        task = session.execute(
            select(RunStep).where(RunStep.run_id == run_id)
        ).scalars().one()
        task.started_at = utc_ms() - 5_000
        session.commit()

    text = api_host.client.get("/metrics").text
    assert _gauge(text, "trove_queue_depth", stage="downloading") == 0.0
    assert _gauge(text, "trove_worker_lease_age_seconds") >= 4.0


def test_metrics_record_search_latency_and_result_count(host):
    seed_item(host, title="Metrics Searchable Item")
    host.login()
    before_count = histogram_count("trove_search_duration_seconds")
    before_results = histogram_count("trove_search_results")

    response = host.client.get("/api/search", params={"q": "metrics"})
    assert response.status_code == 200

    assert histogram_count("trove_search_duration_seconds") == before_count + 1
    assert histogram_count("trove_search_results") == before_results + 1


@pytest.mark.ffmpeg
def test_complete_item_records_stage_and_external_call_metrics(host):
    host.login()
    response = host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=metrics-pipeline"},
    )
    assert response.status_code == 201, response.text
    payload = host.wait_for_item(response.json()["item"]["id"])
    assert payload["run"]["state"] == "completed"

    text = host.client.get("/metrics").text
    for stage in (
        "downloading",
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ):
        assert re.search(
            rf'trove_stage_duration_seconds_count\{{'
            rf'(?=[^}}]*outcome="success")'
            rf'(?=[^}}]*stage="{stage}")[^}}]*\}}',
            text,
        ), stage
    assert histogram_count("trove_asr_realtime_factor") > 0
    assert counter_value("trove_llm_tokens_total", kind="input") > 0
    assert counter_value("trove_llm_tokens_total", kind="output") > 0
    assert counter_value("trove_llm_cost_usd_total") > 0


def test_stage_failure_metric_uses_stable_error_code(api_host):
    api_host.stack.downloader.fail_code = "download.login_required"
    _, run_id = _add_queued_item(api_host)
    assert api_host.runtime.processing.claim_next(worker_id="metrics-worker") == run_id

    api_host.runtime.processing.process(run_id, "metrics-worker")

    text = api_host.client.get("/metrics").text
    assert re.search(
        r'trove_stage_failures_total\{'
        r'(?=[^}]*code="download.login_required")'
        r'(?=[^}]*stage="downloading")[^}]*\} 1.0',
        text,
    )


def test_worker_metrics_server_serves_the_same_registry(api_host):
    server = metrics.start_worker_server(api_host.runtime, host="127.0.0.1", port=0)
    assert server is not None
    try:
        response = httpx.get(f"http://127.0.0.1:{server.port}/metrics", timeout=5)
        assert response.status_code == 200
        assert "trove_queue_depth" in response.text
        assert httpx.get(f"http://127.0.0.1:{server.port}/nope", timeout=5).status_code == 404
    finally:
        server.stop()


def test_worker_command_starts_and_stops_the_metrics_listener(tmp_path, monkeypatch):
    port = _free_port()
    config = Config(home=tmp_path / "Trove", metrics_worker_port=port)
    config.ensure_layout()
    upgrade_database(config)
    monkeypatch.setattr("trove.cli.signal.signal", lambda *_args: None)
    seen: list[int] = []

    def fake_run_worker(_runtime, _stop_event, *, pools=None):
        response = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=5)
        seen.append(response.status_code)

    monkeypatch.setattr("trove.cli.run_worker", fake_run_worker)
    args = argparse.Namespace(pool=[], stages=None, concurrency=None)

    assert cli._worker(config, args) == 0
    assert seen == [200]
    with pytest.raises(httpx.TransportError):
        httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=1)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_grafana_dashboard_uses_the_documented_metrics():
    path = Path(__file__).resolve().parent.parent / "docs" / "observability" / (
        "trove-dashboard.json"
    )
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    expressions = " ".join(
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    )
    for metric_name in (
        "trove_http_request_duration_seconds",
        "trove_stage_duration_seconds",
        "trove_queue_depth",
        "trove_stage_failures_total",
        "trove_asr_realtime_factor",
        "trove_llm_cost_usd_total",
        "trove_search_duration_seconds",
    ):
        assert metric_name in expressions
    assert dashboard["templating"]["list"][0]["name"] == "DS_PROMETHEUS"
