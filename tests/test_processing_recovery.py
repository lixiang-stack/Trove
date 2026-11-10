from __future__ import annotations

import pytest
from sqlalchemy import select

from trove.db.models import Run, RunStep
from trove.worker import WorkerThread


def _add(host, url="https://youtu.be/dQw4w9WgXcQ") -> tuple[str, str]:
    host.login()
    response = host.client.post("/api/items", json={"kind": "url", "url": url})
    assert response.status_code == 201, response.text
    payload = response.json()["item"]
    return payload["id"], payload["run"]["id"]


def _steps(host, item_id: str) -> list[dict]:
    return host.item(item_id)["run"]["steps"]


@pytest.mark.ffmpeg
def test_retry_resumes_from_failed_stage(host):
    host.stack.downloader.fail_code = "download.network"
    item_id, run_id = _add(host, "https://youtu.be/retryfromdownload")
    failed = host.wait_for_item(item_id)
    assert failed["run"]["state"] == "failed"
    host.stack.downloader.fail_code = None
    response = host.client.post(f"/api/items/{item_id}/retry")
    assert response.status_code == 200
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "completed"
    steps = _steps(host, item_id)
    downloading = [step for step in steps if step["stage"] == "downloading"]
    assert [step["state"] for step in downloading] == ["failed", "completed"]
    assert [step["attempt"] for step in downloading] == [1, 2]
    assert len([step for step in steps if step["stage"] == "extracting_audio"]) == 1
    assert len(host.stack.downloader.calls) == 2


@pytest.mark.ffmpeg
def test_retry_does_not_repeat_completed_stages(host):
    host.stack.transcriber.fail_code = "asr.failed"
    item_id, _ = _add(host, "https://youtu.be/retryfromtranscribe")
    failed = host.wait_for_item(item_id)
    assert failed["run"]["current_stage"] == "transcribing"
    audio_path = host.config.library_dir / item_id / "audio.m4a"
    audio_before = audio_path.read_bytes()
    host.stack.transcriber.fail_code = None
    host.client.post(f"/api/items/{item_id}/retry")
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "completed"
    steps = _steps(host, item_id)
    for stage in ("downloading", "extracting_audio"):
        assert len([step for step in steps if step["stage"] == stage]) == 1
        assert [step["state"] for step in steps if step["stage"] == stage] == ["completed"]
    transcribing = [step for step in steps if step["stage"] == "transcribing"]
    assert [step["state"] for step in transcribing] == ["failed", "completed"]
    assert audio_path.read_bytes() == audio_before
    assert len(host.stack.downloader.calls) == 1


def test_cancel_queued_run_worker_never_claims(host, host_factory):
    queued_host = host_factory(start_worker=False, home_name="queued-cancel")
    item_id, run_id = _add(queued_host, "https://youtu.be/cancelqueued")
    response = queued_host.client.post(f"/api/items/{item_id}/cancel")
    assert response.status_code == 200
    assert queued_host.item(item_id)["run"]["state"] == "cancelled"
    assert queued_host.runtime.processing.claim_next() is None
    assert queued_host.stack.downloader.calls == []
    assert queued_host.item(item_id)["run"]["state"] == "cancelled"


@pytest.mark.ffmpeg
def test_cancel_running_stage_stops_and_keeps_audio(host):
    host.stack.transcriber.fail_code = None
    host.stack.transcriber.blocked = True
    item_id, run_id = _add(host, "https://youtu.be/cancelrunning")
    assert host.stack.transcriber.started.wait(5)
    response = host.client.post(f"/api/items/{item_id}/cancel")
    assert response.status_code == 200
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "cancelled"
    assert (host.config.library_dir / item_id / "audio.m4a").is_file()
    assert host.client.get(f"/api/items/{item_id}/audio").status_code == 200
    assert host.item(item_id)["run"]["current_stage"] == "transcribing"


@pytest.mark.ffmpeg
def test_restart_reclaims_running_run_and_resumes(host):
    host.stack.transcriber.fail_code = "asr.failed"
    item_id, run_id = _add(host, "https://youtu.be/restarttest")
    failed = host.wait_for_item(item_id)
    assert failed["run"]["state"] == "failed"
    host.stack.transcriber.fail_code = None
    # Simulate a worker crash inside the transcribing stage: the run is active and
    # has a running attempt that never finished.
    with host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        run.state = "transcribing"
        run.error_code = None
        run.error_message = None
        run.finished_at = None
        run.current_stage = "transcribing"
        session.add(
            RunStep(
                run_id=run_id,
                stage="transcribing",
                state="running",
                attempt=2,
                started_at=1,
            )
        )
        session.commit()
    reclaimed = host.runtime.processing.reclaim_stale_runs()
    assert reclaimed == 1
    with host.runtime.sessions() as session:
        run = session.get(Run, run_id)
        assert run.state == "queued"
        running = session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.stage == "transcribing",
                RunStep.state == "cancelled",
            )
        ).scalars().all()
        assert len(running) == 1
    worker = WorkerThread(host.runtime).start()
    try:
        payload = host.wait_for_item(item_id)
    finally:
        worker.stop()
    assert payload["run"]["state"] == "completed"
    steps = _steps(host, item_id)
    for stage in ("downloading", "extracting_audio"):
        assert [step["state"] for step in steps if step["stage"] == stage] == ["completed"]
    assert len(host.stack.downloader.calls) == 1
    assert host.config.library_dir.joinpath(item_id, "audio.m4a").is_file()


def test_repeated_retry_and_cancel_are_idempotent(api_host):
    api_host.login()
    response = api_host.client.post(
        "/api/items", json={"kind": "url", "url": "https://youtu.be/idempotent"}
    )
    item_id = response.json()["item"]["id"]
    run_id = response.json()["item"]["run"]["id"]
    first = api_host.client.post(f"/api/items/{item_id}/retry")
    second = api_host.client.post(f"/api/items/{item_id}/retry")
    assert first.status_code == second.status_code == 200
    assert first.json()["run"]["id"] == second.json()["run"]["id"] == run_id
    with api_host.runtime.sessions() as session:
        assert len(session.execute(select(Run)).scalars().all()) == 1
    cancelled = api_host.client.post(f"/api/items/{item_id}/cancel")
    cancelled_again = api_host.client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == cancelled_again.status_code == 200
    assert api_host.item(item_id)["run"]["state"] == "cancelled"
    with api_host.runtime.sessions() as session:
        assert len(session.execute(select(Run)).scalars().all()) == 1


@pytest.mark.ffmpeg
def test_failure_reason_is_visible_in_html(host):
    host.stack.transcriber.fail_code = "asr.failed"
    item_id, _ = _add(host, "https://youtu.be/visiblefailure")
    host.wait_for_item(item_id)
    detail = host.client.get(f"/items/{item_id}")
    assert "处理失败" in detail.text
    assert "asr.failed" in detail.text
    listen = host.client.get(f"/items/{item_id}/listen")
    assert "处理失败" in listen.text
