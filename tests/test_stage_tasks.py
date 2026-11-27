from __future__ import annotations

import threading

from sqlalchemy import select

from trove.clock import utc_ms
from trove.db.models import Run, RunStep
from trove.metrics import counter_value

from .conftest import seed_item


def _create_item(api_host, slug: str) -> tuple[str, str]:
    api_host.login()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": f"https://www.youtube.com/watch?v={slug}"},
    )
    assert response.status_code == 201, response.text
    item = response.json()["item"]
    assert item["run"] is not None
    return item["id"], item["run"]["id"]


def _task(api_host, run_id: str, *, state: str | None = None) -> RunStep:
    with api_host.runtime.sessions() as session:
        query = select(RunStep).where(RunStep.run_id == run_id)
        if state is not None:
            query = query.where(RunStep.state == state)
        return session.execute(query.order_by(RunStep.id.desc())).scalars().one()


def _run(api_host, run_id: str) -> Run:
    with api_host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        return run


def test_concurrent_claims_take_different_tasks(api_host):
    _, first_run = _create_item(api_host, "claim-one")
    _, second_run = _create_item(api_host, "claim-two")
    barrier = threading.Barrier(4)
    results: list[str | None] = []
    lock = threading.Lock()

    def claim(worker_id: str) -> None:
        barrier.wait()
        run_id = api_host.runtime.processing.claim_next(worker_id=worker_id)
        with lock:
            results.append(run_id)

    threads = [
        threading.Thread(target=claim, args=(f"worker-{index}",))
        for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(result for result in results if result) == sorted(
        [first_run, second_run]
    )
    assert len([result for result in results if result is None]) == 2
    with api_host.runtime.sessions() as session:
        running = list(
            session.execute(
                select(RunStep).where(RunStep.state == "running")
            ).scalars()
        )
    assert {task.run_id for task in running} == {first_run, second_run}
    assert len({task.worker_id for task in running}) == 2


def test_enqueued_stage_keeps_traceparent(api_host, monkeypatch):
    traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    monkeypatch.setattr(
        "trove.services.run_coordinator.telemetry.current_traceparent",
        lambda: traceparent,
    )

    _, run_id = _create_item(api_host, "trace-parent")

    assert _task(api_host, run_id, state="queued").traceparent == traceparent


def test_claim_honors_available_at(api_host):
    _, run_id = _create_item(api_host, "not-yet-available")
    task = _task(api_host, run_id, state="queued")
    with api_host.runtime.sessions() as session:
        session.get(RunStep, task.id).available_at = utc_ms() + 60_000
        session.commit()

    assert api_host.runtime.processing.claim_next(worker_id="worker-1") is None

    with api_host.runtime.sessions() as session:
        session.get(RunStep, task.id).available_at = utc_ms() - 1
        session.commit()
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id


def test_dependency_blocks_the_next_stage(api_host):
    _, run_id = _create_item(api_host, "dependency")
    with api_host.runtime.sessions() as session:
        session.add(
            RunStep(
                run_id=run_id,
                stage="extracting_audio",
                state="queued",
                attempt=1,
                available_at=0,
            )
        )
        session.commit()

    assert (
        api_host.runtime.processing.claim_next(
            worker_id="worker-1", stages={"extracting_audio"}
        )
        is None
    )

    with api_host.runtime.sessions() as session:
        downloading = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id, RunStep.stage == "downloading"
            )
        ).scalars().one()
        downloading.state = "completed"
        session.commit()

    assert (
        api_host.runtime.processing.claim_next(
            worker_id="worker-1", stages={"extracting_audio"}
        )
        == run_id
    )


def test_expired_lease_is_requeued_as_a_new_attempt(api_host):
    _, run_id = _create_item(api_host, "lease-expired")
    retries_before = counter_value("trove_stage_retries_total", stage="downloading")
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    expired = _task(api_host, run_id, state="running")
    with api_host.runtime.sessions() as session:
        session.get(RunStep, expired.id).lease_until = 1
        session.commit()

    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1
    assert counter_value("trove_stage_retries_total", stage="downloading") == retries_before + 1

    with api_host.runtime.sessions() as session:
        old = session.get(RunStep, expired.id)
        assert old is not None
        assert old.state == "failed"
        assert old.error_code == "run.lease_expired"
        assert old.worker_id is None
        assert old.lease_until is None
        queued = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.stage == "downloading",
                RunStep.state == "queued",
            )
        ).scalars().one()
        assert queued.attempt == 2
        assert queued.available_at > utc_ms()
        queued.available_at = utc_ms() - 1
        session.commit()
        run = session.get(Run, run_id)
        assert run is not None
        assert run.state == "queued"

    assert api_host.runtime.processing.claim_next(worker_id="worker-2") == run_id
    with api_host.runtime.sessions() as session:
        running = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.state == "running",
            )
        ).scalars().one()
        assert running.attempt == 2
        assert running.worker_id == "worker-2"


def test_expired_lease_goes_dead_after_max_attempts(api_host):
    _, run_id = _create_item(api_host, "lease-dead")
    dead_before = counter_value("trove_stage_dead_total", stage="downloading")
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    task = _task(api_host, run_id, state="running")
    with api_host.runtime.sessions() as session:
        row = session.get(RunStep, task.id)
        row.attempt = row.max_attempts
        row.lease_until = 1
        session.commit()

    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1
    assert counter_value("trove_stage_dead_total", stage="downloading") == dead_before + 1

    with api_host.runtime.sessions() as session:
        dead = session.get(RunStep, task.id)
        assert dead is not None
        assert dead.state == "dead"
        assert dead.worker_id is None
        run = session.get(Run, run_id)
        assert run is not None
        assert run.state == "failed"
        assert run.error_code == "run.dead"
    assert api_host.runtime.processing.claim_next(worker_id="worker-2") is None


def test_one_attempt_stage_recovers_once_from_a_crashed_lease(api_host):
    bundle = seed_item(api_host, title="ASR crash")
    run_id = "run-asr-crash"
    with api_host.runtime.sessions() as session:
        session.add(
            Run(
                id=run_id,
                item_id=bundle.item.id,
                state="queued",
                current_stage="transcribing",
                created_at=utc_ms(),
            )
        )
        session.add(
            RunStep(
                run_id=run_id,
                stage="transcribing",
                state="running",
                attempt=1,
                max_attempts=1,
                worker_id="crashed-worker",
                lease_until=1,
            )
        )
        session.commit()

    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1
    with api_host.runtime.sessions() as session:
        queued = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.state == "queued",
            )
        ).scalars().one()
        assert queued.attempt == 2
        queued.state = "running"
        queued.worker_id = "crashed-worker-2"
        queued.lease_until = 1
        session.commit()

    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1
    with api_host.runtime.sessions() as session:
        dead = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.state == "dead",
            )
        ).scalars().one()
        assert dead.attempt == 2
        run = session.get(Run, run_id)
        assert run is not None
        assert (run.state, run.error_code) == ("failed", "run.dead")


def test_worker_that_lost_its_lease_cannot_complete_the_stage(api_host):
    _, run_id = _create_item(api_host, "lease-fence")
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    task = _task(api_host, run_id, state="running")
    with api_host.runtime.sessions() as session:
        session.get(RunStep, task.id).lease_until = 1
        session.commit()

    api_host.stack.downloader.blocked = True
    errors: list[BaseException] = []

    def work() -> None:
        try:
            api_host.runtime.processing.process(run_id, "worker-1")
        except BaseException as exc:  # noqa: BLE001 - surfaced to the assertion
            errors.append(exc)

    thread = threading.Thread(target=work)
    thread.start()
    assert api_host.stack.downloader.started.wait(5)
    api_host.stack.downloader.block.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    with api_host.runtime.sessions() as session:
        expired = session.get(RunStep, task.id)
        assert expired is not None
        assert expired.state == "running"
        next_stage = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id, RunStep.stage == "extracting_audio"
            )
        ).scalars().first()
        assert next_stage is None
        run = session.get(Run, run_id)
        assert run is not None
        assert run.state == "queued"

    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1
    with api_host.runtime.sessions() as session:
        expired = session.get(RunStep, task.id)
        assert expired is not None
        assert expired.state == "failed"
        queued = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.stage == "downloading",
                RunStep.state == "queued",
            )
        ).scalars().one()
        assert queued.attempt == 2


def test_manual_retry_requeues_a_dead_task(api_host):
    item_id, run_id = _create_item(api_host, "dead-retry")
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    task = _task(api_host, run_id, state="running")
    with api_host.runtime.sessions() as session:
        row = session.get(RunStep, task.id)
        row.attempt = row.max_attempts
        row.lease_until = 1
        session.commit()
    assert api_host.runtime.processing.reap_expired(now=utc_ms()) == 1

    response = api_host.client.post(f"/api/items/{item_id}/retry")
    assert response.status_code == 200

    queued = _task(api_host, run_id, state="queued")
    assert queued.attempt == 4
    assert api_host.runtime.processing.claim_next(worker_id="worker-2") == run_id


def test_recovery_enqueues_the_next_stage_for_an_active_run(api_host):
    _, run_id = _create_item(api_host, "recover-active")
    with api_host.runtime.sessions() as session:
        for task in session.execute(
            select(RunStep).where(RunStep.run_id == run_id)
        ).scalars():
            session.delete(task)
        session.commit()

    assert api_host.runtime.processing.recover_active_runs() == 1

    with api_host.runtime.sessions() as session:
        task = session.execute(
            select(RunStep).where(RunStep.run_id == run_id)
        ).scalars().one()
        assert (task.stage, task.state, task.attempt) == ("downloading", "queued", 1)
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id


def test_heartbeat_renews_the_running_task_lease(api_host):
    _, run_id = _create_item(api_host, "heartbeat")
    assert api_host.runtime.processing.claim_next(worker_id="worker-1") == run_id
    task = _task(api_host, run_id, state="running")
    with api_host.runtime.sessions() as session:
        session.get(RunStep, task.id).lease_until = 1
        session.commit()

    api_host.runtime.processing.heartbeat(run_id, worker_id="worker-1")

    renewed = _task(api_host, run_id, state="running")
    assert renewed.lease_until is not None
    assert renewed.lease_until > 1
