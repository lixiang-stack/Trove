from __future__ import annotations

import errno
import json
import uuid

import pytest
from sqlalchemy import select

from trove.clock import utc_ms
from trove.db.models import AiResult, Run, RunStep
from trove.domain.retry import (
    RETRY_DELAYS_MS,
    is_retryable,
    is_transient_os_error,
    max_attempts_for,
    retry_delay_ms,
)

from .conftest import seed_item
from .metrics_helpers import counter_value


def _create_item(api_host, slug: str) -> tuple[str, str]:
    api_host.login()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": f"https://www.youtube.com/watch?v={slug}"},
    )
    assert response.status_code == 201, response.text
    item = response.json()["item"]
    return item["id"], item["run"]["id"]


def _task(api_host, run_id: str, task_id: int) -> RunStep:
    with api_host.runtime.sessions() as session:
        task = session.get(RunStep, task_id)
        assert task is not None
        return task


def _latest_task(api_host, run_id: str) -> RunStep:
    with api_host.runtime.sessions() as session:
        return session.execute(
            select(RunStep)
            .where(RunStep.run_id == run_id)
            .order_by(RunStep.id.desc())
        ).scalars().first()


def _queued_task(api_host, run_id: str) -> RunStep | None:
    with api_host.runtime.sessions() as session:
        return session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id, RunStep.state == "queued"
            )
        ).scalars().first()


def _drain(api_host, run_id: str, worker_id: str = "worker-test") -> Run:
    for _ in range(20):
        with api_host.runtime.sessions() as session:
            run = session.get(Run, run_id)
            assert run is not None
            if run.state in {"completed", "failed", "cancelled"}:
                return run
            for task in session.execute(
                select(RunStep).where(
                    RunStep.run_id == run_id, RunStep.state == "queued"
                )
            ).scalars():
                task.available_at = utc_ms()
            session.commit()
        claimed = api_host.runtime.processing.claim_next(worker_id=worker_id)
        assert claimed == run_id
        api_host.runtime.processing.process(claimed, worker_id)
    raise AssertionError("run did not reach a terminal state")


def _add_failed_organizing_run(api_host, item_id: str) -> str:
    run_id = str(uuid.uuid4())
    now = utc_ms() + 1
    with api_host.runtime.sessions() as session:
        session.add(
            Run(
                id=run_id,
                item_id=item_id,
                state="failed",
                current_stage="organizing",
                created_at=now,
                finished_at=now,
            )
        )
        for stage in ("downloading", "extracting_audio", "transcribing"):
            session.add(
                RunStep(
                    run_id=run_id,
                    stage=stage,
                    state="completed",
                    attempt=1,
                    started_at=now,
                    finished_at=now,
                )
            )
        session.add(
            RunStep(
                run_id=run_id,
                stage="organizing",
                state="failed",
                attempt=1,
                error_code="llm.failed",
                started_at=now,
                finished_at=now,
            )
        )
        session.commit()
    return run_id


@pytest.mark.parametrize(
    "code",
    ["download.network"],
)
def test_transient_errors_are_retryable(code):
    assert is_retryable(code) is True


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        (None, True),
        ({"status": 429}, True),
        ({"status": 500}, True),
        ({"status": 503}, True),
        ({"status": 400}, False),
        ({"status": 404}, False),
    ],
)
def test_llm_failures_depend_on_the_http_status(details, expected):
    assert is_retryable("llm.failed", details) is expected


@pytest.mark.parametrize(
    "code",
    [
        "download.unsupported",
        "download.login_required",
        "download.geo_restricted",
        "epub.invalid",
        "epub.drm",
        "epub.fixed_layout",
        "llm.not_configured",
        "asr.not_configured",
        "asr.model_missing",
        "internal.error",
    ],
)
def test_permanent_errors_are_not_retryable(code):
    assert is_retryable(code) is False


def test_asr_failed_is_only_retryable_when_marked_transient():
    assert is_retryable("asr.failed") is False
    assert is_retryable("asr.failed", {"transient": True}) is True


def test_storage_error_is_only_retryable_when_marked_transient():
    assert is_retryable("storage.error") is False
    assert is_retryable("storage.error", {"transient": True}) is True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileNotFoundError(errno.ENOENT, "missing"), False),
        (PermissionError(errno.EACCES, "denied"), False),
        (OSError(errno.EBUSY, "busy"), True),
        (OSError(errno.ETIMEDOUT, "timeout"), True),
        (OSError(errno.ENOSPC, "disk full"), True),
    ],
)
def test_only_identifiable_os_errors_are_transient(error, expected):
    assert is_transient_os_error(error) is expected


@pytest.mark.parametrize(
    ("stage", "attempts"),
    [
        ("downloading", 3),
        ("extracting_audio", 3),
        ("extracting_text", 3),
        ("transcribing", 1),
        ("organizing", 3),
        ("indexing", 2),
        ("unknown", 3),
    ],
)
def test_stage_attempt_defaults(stage, attempts):
    assert max_attempts_for(stage) == attempts


def test_stage_attempts_can_be_overridden():
    assert max_attempts_for("transcribing", {"transcribing": 2}) == 2


def test_retry_delays_are_exponential():
    assert retry_delay_ms(1, jitter=lambda: 0.5) == RETRY_DELAYS_MS[0]
    assert retry_delay_ms(2, jitter=lambda: 0.5) == RETRY_DELAYS_MS[1]
    assert retry_delay_ms(3, jitter=lambda: 0.5) == RETRY_DELAYS_MS[2]
    assert retry_delay_ms(4, jitter=lambda: 0.5) == RETRY_DELAYS_MS[2]


def test_retry_delay_jitter_stays_within_bounds():
    low = retry_delay_ms(1, jitter=lambda: 0.0)
    high = retry_delay_ms(1, jitter=lambda: 1.0)
    assert low == int(RETRY_DELAYS_MS[0] * 0.8)
    assert high == int(RETRY_DELAYS_MS[0] * 1.2)


@pytest.mark.ffmpeg
def test_retryable_error_is_requeued_with_backoff_and_succeeds(api_host):
    _, run_id = _create_item(api_host, "retry-backoff")
    api_host.stack.downloader.fail_code = "download.network"
    retries_before = counter_value("trove_stage_retries_total", stage="downloading")

    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    first = _latest_task(api_host, run_id)
    api_host.runtime.processing.process(run_id, "worker-1")

    assert counter_value("trove_stage_retries_total", stage="downloading") == retries_before + 1

    first = _task(api_host, run_id, first.id)
    assert (first.state, first.attempt, first.error_code) == (
        "failed",
        1,
        "download.network",
    )
    queued = _queued_task(api_host, run_id)
    assert queued is not None
    assert queued.attempt == 2
    assert queued.available_at > utc_ms()
    with api_host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.state == "queued"
        assert run.current_stage == "downloading"
        assert run.error_code is None

    assert api_host.runtime.processing.claim_next(worker_id="worker-2") is None

    log_lines = [
        json.loads(line)
        for line in (
            api_host.config.runs_log_dir / f"{run_id}.log"
        ).read_text(encoding="utf-8").splitlines()
    ]
    retry_log = next(line for line in log_lines if line.get("event") == "stage_retry")
    assert retry_log["run_id"] == run_id
    assert retry_log["stage"] == "downloading"
    assert retry_log["attempt"] == 1
    assert retry_log["error_code"] == "download.network"
    assert retry_log["delay_ms"] > 0
    assert retry_log["task_id"] == first.id

    api_host.stack.downloader.fail_code = None
    run = _drain(api_host, run_id, worker_id="worker-2")
    assert run.state == "completed"
    with api_host.runtime.sessions() as session:
        downloading = list(
            session.execute(
                select(RunStep)
                .where(
                    RunStep.run_id == run_id,
                    RunStep.stage == "downloading",
                )
                .order_by(RunStep.attempt)
            ).scalars()
        )
    assert [(task.state, task.attempt) for task in downloading] == [
        ("failed", 1),
        ("completed", 2),
    ]


def test_non_retryable_error_fails_without_a_new_attempt(api_host):
    _, run_id = _create_item(api_host, "retry-permanent")
    api_host.stack.downloader.fail_code = "download.login_required"

    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    task = _latest_task(api_host, run_id)
    api_host.runtime.processing.process(run_id, "worker-1")

    task = _task(api_host, run_id, task.id)
    assert (task.state, task.attempt, task.error_code) == (
        "failed",
        1,
        "download.login_required",
    )
    assert _queued_task(api_host, run_id) is None
    with api_host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert (run.state, run.error_code) == ("failed", "download.login_required")
    assert api_host.runtime.processing.claim_next(worker_id="worker-2") is None


@pytest.mark.ffmpeg
def test_retryable_error_goes_dead_after_max_attempts_and_manual_retry_succeeds(api_host):
    item_id, run_id = _create_item(api_host, "retry-dead")
    api_host.stack.downloader.fail_code = "download.network"
    dead_before = counter_value("trove_stage_dead_total", stage="downloading")
    failures_before = counter_value(
        "trove_stage_failures_total", stage="downloading", code="download.network"
    )

    for attempt in range(1, 4):
        with api_host.runtime.sessions() as session:
            queued = session.execute(
                select(RunStep).where(
                    RunStep.run_id == run_id, RunStep.state == "queued"
                )
            ).scalars().first()
            if queued is not None:
                queued.available_at = utc_ms()
                session.commit()
        assert api_host.runtime.processing.claim_next(worker_id=f"worker-{attempt}") == run_id
        api_host.runtime.processing.process(run_id, f"worker-{attempt}")

    dead = _latest_task(api_host, run_id)
    assert (dead.state, dead.attempt, dead.error_code) == (
        "dead",
        3,
        "download.network",
    )
    with api_host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert (run.state, run.error_code) == ("failed", "run.dead")
    assert counter_value("trove_stage_dead_total", stage="downloading") == dead_before + 1
    assert (
        counter_value(
            "trove_stage_failures_total", stage="downloading", code="download.network"
        )
        == failures_before + 3
    )

    api_host.stack.downloader.fail_code = None
    response = api_host.client.post(f"/api/items/{item_id}/retry")
    assert response.status_code == 200

    queued = _queued_task(api_host, run_id)
    assert queued is not None
    assert queued.attempt == 4
    assert queued.max_attempts == 6

    run = _drain(api_host, run_id, worker_id="worker-retry")
    assert run.state == "completed"


@pytest.mark.ffmpeg
def test_cancelling_a_backoff_waiter_stops_future_retries(api_host):
    _, run_id = _create_item(api_host, "retry-cancel")
    api_host.stack.downloader.fail_code = "download.network"

    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    api_host.runtime.processing.process(run_id, "worker-1")
    assert _queued_task(api_host, run_id) is not None

    api_host.runtime.processing.cancel(run_id)

    queued = _queued_task(api_host, run_id)
    assert queued is None
    with api_host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.state == "cancelled"
        cancelled = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id, RunStep.state == "cancelled"
            )
        ).scalars().all()
    assert len(cancelled) == 1
    assert api_host.runtime.processing.claim_next(worker_id="worker-2") is None


def test_reprocess_forces_an_active_run(api_host):
    item_id, run_id = _create_item(api_host, "reprocess-active")

    run = api_host.runtime.processing.reprocess(item_id, "organizing")

    assert run.id == run_id
    with api_host.runtime.sessions() as session:
        current = session.get(Run, run_id)
        assert current is not None
        assert current.force is True


def test_automatic_retry_keeps_an_explicit_reprocess_forced(api_host):
    bundle = seed_item(api_host, title="Forced retry")
    api_host.stack.organizer.fail_code = "llm.failed"
    run = api_host.runtime.processing.reprocess(bundle.item.id, "organizing")

    assert run.force is True
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run.id
    api_host.runtime.processing.process(run.id, "worker-1")

    with api_host.runtime.sessions() as session:
        current = session.get(Run, run.id)
        assert current is not None
        assert current.state == "queued"
        assert current.force is True
    queued = _queued_task(api_host, run.id)
    assert queued is not None
    assert queued.attempt == 2


@pytest.mark.ffmpeg
def test_automatic_retry_reuses_a_cached_ai_result_after_a_transient_failure(api_host):
    item_id, first_run_id = _create_item(api_host, "retry-cache")
    _drain(api_host, first_run_id)
    organizer_calls = len(api_host.stack.organizer.calls)
    transcript = api_host.runtime.package.read_transcript(item_id)
    assert transcript is not None
    original = api_host.runtime.package.read_transcript(item_id)
    assert original is not None
    transcript.segments[0].text = f"{transcript.segments[0].text} changed"
    api_host.runtime.package.write_transcript(item_id, transcript)
    retry_run_id = _add_failed_organizing_run(api_host, item_id)

    api_host.runtime.processing.retry(item_id)
    api_host.stack.organizer.fail_code = "llm.failed"
    assert (
        api_host.runtime.processing.claim_next(worker_id="worker-fail") == retry_run_id
    )
    api_host.runtime.processing.process(retry_run_id, "worker-fail")
    assert len(api_host.stack.organizer.calls) == organizer_calls + 1

    api_host.runtime.package.write_transcript(item_id, original)
    api_host.stack.organizer.fail_code = None
    run = _drain(api_host, retry_run_id, worker_id="worker-retry")
    assert run.state == "completed"
    assert len(api_host.stack.organizer.calls) == organizer_calls + 1
    payload = api_host.item(item_id)
    assert any("ai cache hit" in line for line in payload["run"]["log_tail"])
    with api_host.runtime.sessions() as session:
        assert len(
            session.execute(
                select(AiResult).where(AiResult.item_id == item_id)
            ).scalars().all()
        ) == 1
