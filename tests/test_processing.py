from __future__ import annotations

import threading
import time

import pytest

from trove.worker import WorkerThread


def _add_url(host, url="https://www.youtube.com/watch?v=dQw4w9WgXcQ") -> str:
    host.login()
    response = host.client.post("/api/items", json={"kind": "url", "url": url})
    assert response.status_code == 201, response.text
    return response.json()["item"]["id"]


@pytest.mark.ffmpeg
def test_fake_stages_advance_in_order(host):
    item_id = _add_url(host)
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "completed"
    steps = payload["run"]["steps"]
    assert [step["stage"] for step in steps] == [
        "downloading",
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ]
    assert all(step["state"] == "completed" for step in steps)
    assert all(step["attempt"] == 1 for step in steps)


def test_stage_failure_is_terminal_and_readable(host):
    host.stack.downloader.fail_code = "download.login_required"
    item_id = _add_url(host)
    payload = host.wait_for_item(item_id)
    run = payload["run"]
    assert run["state"] == "failed"
    assert run["error_code"] == "download.login_required"
    assert "fake download failure" in run["error_message"]
    assert run["current_stage"] == "downloading"
    assert run["steps"][-1]["state"] == "failed"
    assert host.runtime.processing.claim_next() is None
    assert len(host.stack.downloader.calls) == 1
    detail = host.client.get(f"/items/{item_id}")
    assert detail.status_code == 200
    assert "download.login_required" in detail.text
    api = host.client.get(f"/api/runs/{run['id']}").json()
    assert api["run"]["error_code"] == "download.login_required"
    assert api["run"]["log_tail"]


def test_two_workers_claim_only_one_run(api_host):
    api_host.login()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert response.status_code == 201
    barrier = threading.Barrier(2)
    results: list[str | None] = []
    lock = threading.Lock()

    def claim():
        barrier.wait()
        run_id = api_host.runtime.processing.claim_next()
        with lock:
            results.append(run_id)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len([result for result in results if result]) == 1
    assert len([result for result in results if result is None]) == 1


def test_status_polling_stops_after_terminal(api_host):
    api_host.login()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    item_id = response.json()["item"]["id"]
    run = api_host.item(item_id)["run"]
    assert run["state"] == "queued"
    active = api_host.client.get(f"/items/{item_id}/status?context=row")
    assert "hx-trigger" in active.text
    worker = WorkerThread(api_host.runtime).start()
    try:
        api_host.wait_for_item(item_id)
    finally:
        worker.stop()
    terminal = api_host.client.get(f"/items/{item_id}/status?context=row")
    assert "hx-trigger" not in terminal.text


@pytest.mark.ffmpeg
def test_transcript_stays_searchable_when_organizing_fails(host):
    host.stack.organizer.fail_code = "llm.not_configured"
    item_id = _add_url(host)
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "failed"
    assert payload["run"]["current_stage"] == "organizing"

    api = host.client.get("/api/search", params={"q": "记忆"}).json()
    page = host.client.get("/search", params={"q": "记忆"})

    assert api["count"] == 1
    assert api["results"][0]["item"]["id"] == item_id
    assert "Fixture Video" in page.text


@pytest.mark.ffmpeg
def test_artifact_stays_readable_after_later_stage_failure(host):
    host.stack.transcriber.fail_code = "asr.failed"
    item_id = _add_url(host)
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "failed"
    assert payload["run"]["current_stage"] == "transcribing"
    item_dir = host.config.library_dir / item_id
    assert (item_dir / "audio.m4a").is_file()
    assert not (item_dir / "transcript.json").exists()
    audio = host.client.get(f"/api/items/{item_id}/audio")
    assert audio.status_code == 200
    assert audio.headers["etag"]


@pytest.mark.ffmpeg
def test_atomic_artifact_install_does_not_expose_partial_files(host):
    host.stack.transcriber.fail_code = "asr.failed"
    item_id = _add_url(host)
    host.wait_for_item(item_id)
    item_dir = host.config.library_dir / item_id
    leftovers = [path.name for path in item_dir.iterdir() if path.name.endswith((".tmp", ".part"))]
    assert leftovers == []
    # A failed stage leaves only completed artifacts in the content package.
    assert sorted(path.name for path in item_dir.iterdir()) == ["audio.m4a", "source.json"]


def test_cancelled_subprocess_is_terminated(tmp_path):
    import sys
    import threading

    from trove.adapters.process import run_command
    from trove.errors import ProcessingCancelled
    from trove.ports import StageContext

    cancel = threading.Event()
    context = StageContext(
        item_id="item",
        run_id="run",
        work_dir=tmp_path,
        should_cancel=cancel.is_set,
        log=lambda message: None,
    )
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(ProcessingCancelled):
        run_command(
            context,
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=60,
        )
    assert time.monotonic() - started < 5
