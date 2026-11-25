from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from trove.config import Config
from trove.db.engine import create_engine_for, create_session_factory, upgrade_database
from trove.db.models import Run
from trove.errors import IdempotencyInProgressError, IdempotencyKeyReusedError, ValidationError
from trove.services import idempotency as idempotency_module
from trove.services.idempotency import (
    IN_PROGRESS_TTL_MS,
    BeginState,
    IdempotencyService,
    normalize_key,
    request_fingerprint,
)


@pytest.fixture
def service(tmp_path) -> IdempotencyService:
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    sessions = create_session_factory(create_engine_for(config))
    return IdempotencyService(sessions)


def _begin(
    service: IdempotencyService,
    key: str = "key-1",
    *,
    payload: dict | None = None,
):
    payload = payload or {"kind": "url", "url": "https://example.com/a"}
    return service.begin(
        key,
        method="POST",
        path="/api/items",
        request_hash=request_fingerprint("POST", "/api/items", payload),
    )


def test_completed_key_replays_same_response(service):
    first = _begin(service)
    assert first.state is BeginState.STARTED
    assert first.token is not None
    body = {"item": {"id": "item-1"}, "deduplicated": False}
    service.complete("key-1", token=first.token, status_code=201, payload=body)

    replay = _begin(service)
    assert replay.state is BeginState.REPLAY
    assert replay.status_code == 201
    assert replay.payload == body


def test_reused_key_with_different_request_conflicts(service):
    first = _begin(service)
    service.complete(
        "key-1",
        token=first.token,
        status_code=201,
        payload={"item": {"id": "item-1"}, "deduplicated": False},
    )

    with pytest.raises(IdempotencyKeyReusedError) as caught:
        _begin(service, payload={"kind": "url", "url": "https://example.com/b"})
    assert caught.value.code == "idempotency.key_reused"


def test_in_progress_key_conflicts(service):
    _begin(service)
    with pytest.raises(IdempotencyInProgressError) as caught:
        _begin(service)
    assert caught.value.code == "idempotency.in_progress"


def test_abort_releases_key(service):
    first = _begin(service)
    assert first.token is not None
    service.abort("key-1", token=first.token)

    second = _begin(service)
    assert second.state is BeginState.STARTED


def test_stale_in_progress_key_can_restart(service, monkeypatch):
    now = 1_000
    monkeypatch.setattr(idempotency_module, "utc_ms", lambda: now)
    first = _begin(service)
    assert first.state is BeginState.STARTED

    now += IN_PROGRESS_TTL_MS + 1
    second = _begin(service)
    assert second.state is BeginState.STARTED
    assert second.token != first.token


def test_stale_token_cannot_overwrite_new_request(service, monkeypatch):
    now = 1_000
    monkeypatch.setattr(idempotency_module, "utc_ms", lambda: now)
    first = _begin(service)

    now += IN_PROGRESS_TTL_MS + 1
    second = _begin(service)
    assert second.state is BeginState.STARTED

    service.complete(
        "key-1",
        token=first.token,
        status_code=201,
        payload={"item": {"id": "stale"}, "deduplicated": False},
    )
    with pytest.raises(IdempotencyInProgressError):
        _begin(service)

    service.complete(
        "key-1",
        token=second.token,
        status_code=201,
        payload={"item": {"id": "fresh"}, "deduplicated": False},
    )
    replay = _begin(service)
    assert replay.state is BeginState.REPLAY
    assert replay.payload == {"item": {"id": "fresh"}, "deduplicated": False}


def test_concurrent_begin_only_one_starts(service):
    barrier = threading.Barrier(2)

    def attempt() -> str:
        barrier.wait()
        try:
            _begin(service)
            return "started"
        except IdempotencyInProgressError:
            return "busy"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    assert sorted(results) == ["busy", "started"]


def test_normalize_key_rejects_too_long():
    assert normalize_key(None) is None
    assert normalize_key("  ") is None
    with pytest.raises(ValidationError) as caught:
        normalize_key("x" * 256)
    assert caught.value.code == "idempotency.key_invalid"


def test_create_item_replays_same_response(api_host):
    api_host.login()
    payload = {"kind": "url", "url": "https://www.youtube.com/watch?v=idempotent"}
    headers = {"Idempotency-Key": "item-key-1", "X-Request-ID": "req-idem-1"}

    first = api_host.client.post("/api/items", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.headers["x-request-id"] == "req-idem-1"
    with api_host.runtime.sessions() as session:
        runs_before = session.execute(select(func.count()).select_from(Run)).scalar_one()

    replay = api_host.client.post("/api/items", json=payload, headers=headers)
    assert replay.status_code == 201
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json() == first.json()
    with api_host.runtime.sessions() as session:
        assert (
            session.execute(select(func.count()).select_from(Run)).scalar_one()
            == runs_before
        )


def test_create_item_rejects_reused_key_with_different_body(api_host):
    api_host.login()
    headers = {"Idempotency-Key": "item-key-2"}

    first = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=headers,
    )
    assert first.status_code == 201

    second = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=abcdefghijk"},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["code"] == "idempotency.key_reused"
    assert second.json()["request_id"] == second.headers["x-request-id"]


def test_create_item_in_progress_returns_conflict(api_host, monkeypatch):
    api_host.login()
    started = threading.Event()
    release = threading.Event()
    original = api_host.runtime.intake.add_video_url

    def slow_add(url: str):
        started.set()
        assert release.wait(5)
        return original(url)

    monkeypatch.setattr(api_host.runtime.intake, "add_video_url", slow_add)
    payload = {"kind": "url", "url": "https://www.youtube.com/watch?v=concurrent"}
    headers = {"Idempotency-Key": "item-key-concurrent"}

    result: dict = {}

    def create():
        result["response"] = api_host.client.post(
            "/api/items", json=payload, headers=headers
        )

    thread = threading.Thread(target=create)
    thread.start()
    assert started.wait(5)

    second = api_host.client.post("/api/items", json=payload, headers=headers)
    assert second.status_code == 409
    assert second.json()["code"] == "idempotency.in_progress"

    release.set()
    thread.join(10)
    assert result["response"].status_code == 201


def test_failed_create_releases_idempotency_key(api_host):
    api_host.login()
    headers = {"Idempotency-Key": "item-key-retry"}

    failed = api_host.client.post(
        "/api/items", json={"kind": "url"}, headers=headers
    )
    assert failed.status_code == 422

    retried = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=headers,
    )
    assert retried.status_code == 201


def test_request_id_is_echoed_and_in_error_body(api_host):
    headers = {"X-Request-ID": "req.test-123"}
    health = api_host.client.get("/api/health", headers=headers)
    assert health.headers["x-request-id"] == "req.test-123"

    unauthorized = api_host.client.get("/api/items", headers=headers)
    assert unauthorized.status_code == 401
    assert unauthorized.json()["request_id"] == "req.test-123"

    api_host.login()
    invalid = api_host.client.post(
        "/api/items", json={"kind": "url"}, headers=headers
    )
    assert invalid.status_code == 422
    assert invalid.json()["request_id"] == "req.test-123"


def test_invalid_request_id_is_replaced(api_host):
    response = api_host.client.get("/api/health", headers={"X-Request-ID": "bad id"})
    assert response.headers["x-request-id"] != "bad id"
    assert len(response.headers["x-request-id"]) == 32


def test_request_id_is_generated_when_missing(api_host):
    response = api_host.client.get("/api/health")
    assert len(response.headers["x-request-id"]) == 32


def test_request_log_includes_request_id(api_host, caplog):
    with caplog.at_level(logging.INFO, logger="trove.request"):
        api_host.client.get("/api/items", headers={"X-Request-ID": "req-log-1"})

    records = [
        record
        for record in caplog.records
        if record.name == "trove.request"
        and getattr(record, "path", None) == "/api/items"
    ]
    assert records
    assert records[-1].request_id == "req-log-1"
    assert records[-1].status == 401
