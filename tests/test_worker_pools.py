from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import select

from trove.cli import main
from trove.clock import utc_ms
from trove.config import Config, ConfigError, load_config
from trove.db.models import RunStep
from trove.domain.items import (
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
)
from trove.worker import WorkerThread, resolve_worker_pools

from .fakes import FakeDownloader, FakeStack, wait_until


def test_pools_map_to_their_stage_sets(tmp_path):
    config = Config(home=tmp_path / "Trove")

    download = resolve_worker_pools(config, pools=["download"])[0]
    asr = resolve_worker_pools(config, pools=["asr"])[0]
    llm = resolve_worker_pools(config, pools=["llm"])[0]
    index = resolve_worker_pools(config, pools=["index"])[0]
    all_pool = resolve_worker_pools(config, pools=["all"])[0]

    assert download.stages == frozenset(
        {STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO, STAGE_EXTRACTING_TEXT}
    )
    assert asr.stages == frozenset({STAGE_TRANSCRIBING})
    assert llm.stages == frozenset({STAGE_ORGANIZING})
    assert index.stages == frozenset({STAGE_INDEXING})
    assert asr.stages < all_pool.stages


def test_pool_concurrency_defaults_and_overrides(tmp_path):
    config = Config(home=tmp_path / "Trove")

    resolved = resolve_worker_pools(config, pools=["download", "asr", "llm"])
    by_name = {pool.name: pool.concurrency for pool in resolved}

    assert by_name == {"download": 3, "asr": 1, "llm": 2}
    assert resolve_worker_pools(config, pools=["asr"], concurrency=4)[0].concurrency == 4


def test_index_pool_is_always_single_writer(tmp_path):
    config = Config(home=tmp_path / "Trove")

    pool = resolve_worker_pools(config, pools=["index"], concurrency=4)[0]

    assert pool.concurrency == 1


def test_stages_flag_builds_a_custom_pool(tmp_path):
    config = Config(home=tmp_path / "Trove")

    pool = resolve_worker_pools(
        config, stages=f"{STAGE_DOWNLOADING},{STAGE_EXTRACTING_AUDIO}"
    )[0]

    assert pool.name == "custom"
    assert pool.stages == frozenset({STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO})
    assert pool.concurrency == 1


def test_unknown_pool_fails_with_a_readable_hint(tmp_path):
    config = Config(home=tmp_path / "Trove")

    with pytest.raises(ConfigError, match="unknown.*all, download, asr, llm, index"):
        resolve_worker_pools(config, pools=["bogus"])


def test_unknown_stage_fails_with_a_readable_hint(tmp_path):
    config = Config(home=tmp_path / "Trove")

    with pytest.raises(ConfigError, match="bogus"):
        resolve_worker_pools(config, stages="downloading,bogus")


def test_worker_pools_and_concurrency_load_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv("TROVE_WORKER_POOLS", "download,asr")
    monkeypatch.setenv("TROVE_ASR_CONCURRENCY", "2")

    config = load_config()

    assert config.worker_pools == ("download", "asr")
    assert config.worker_concurrency["asr"] == 2
    assert config.worker_concurrency["download"] == 3


def test_empty_worker_pools_default_to_all(tmp_path, monkeypatch):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv("TROVE_WORKER_POOLS", "")

    assert load_config().worker_pools == ("all",)


def test_duplicate_worker_pools_are_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv("TROVE_WORKER_POOLS", "download, asr,download")

    assert load_config().worker_pools == ("download", "asr")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TROVE_WORKER_POOLS", "bogus"),
        ("TROVE_WORKER_POOLS", "download,,asr"),
        ("TROVE_ASR_CONCURRENCY", "0"),
        ("TROVE_DOWNLOAD_CONCURRENCY", "-1"),
        ("TROVE_LLM_CONCURRENCY", "two"),
    ],
)
def test_invalid_worker_configuration_fails_at_startup(
    tmp_path, monkeypatch, name, value
):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError, match=name):
        load_config()


def test_worker_cli_rejects_an_unknown_pool(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))

    code = main(["worker", "--pool", "bogus"])

    assert code == 2
    assert "Invalid worker pool" in capsys.readouterr().err


def test_worker_cli_rejects_zero_concurrency(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))

    code = main(["worker", "--pool", "asr", "--concurrency", "0"])

    assert code == 2
    assert "--concurrency" in capsys.readouterr().err


def test_worker_cli_rejects_pool_and_stages_together(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TROVE_HOME", str(tmp_path / "Trove"))

    code = main(["worker", "--pool", "asr", "--stages", "transcribing"])

    assert code == 2
    assert "--pool" in capsys.readouterr().err


def _create_item(host, slug: str) -> tuple[str, str]:
    host.login()
    response = host.client.post(
        "/api/items",
        json={"kind": "url", "url": f"https://www.youtube.com/watch?v={slug}"},
    )
    assert response.status_code == 201, response.text
    item = response.json()["item"]
    return item["id"], item["run"]["id"]


def _stage_state(host, run_id: str, stage: str) -> str | None:
    with host.runtime.sessions() as session:
        task = session.execute(
            select(RunStep)
            .where(RunStep.run_id == run_id, RunStep.stage == stage)
            .order_by(RunStep.id.desc())
        ).scalars().first()
        return task.state if task is not None else None


def test_health_exposes_the_running_worker_pools(api_host):
    pools = resolve_worker_pools(api_host.config, pools=["download", "asr"])
    worker = WorkerThread(api_host.runtime, pools=pools).start()
    try:
        payload = wait_until(
            lambda: _healthy_worker_pools(api_host), timeout=10
        )
        assert payload["worker"]["state"] == "idle"
        assert {
            pool["name"]: (pool["concurrency"], pool["active"])
            for pool in payload["worker"]["pools"]
        } == {"download": (3, 0), "asr": (1, 0)}
    finally:
        worker.stop()


def _healthy_worker_pools(host):
    response = host.client.get("/api/health")
    payload = response.json()
    if payload["worker"]["status"] != "ok" or not payload["worker"].get("pools"):
        return None
    return payload


@pytest.mark.ffmpeg
def test_a_slow_asr_task_does_not_block_the_download_pool(api_host):
    api_host.stack.transcriber.blocked = True
    pools = resolve_worker_pools(
        api_host.config, pools=["download", "asr", "llm", "index"]
    )
    worker = WorkerThread(api_host.runtime, pools=pools).start()
    try:
        first_item, _ = _create_item(api_host, "slow-asr")
        assert api_host.stack.transcriber.started.wait(10)

        second_item, second_run = _create_item(api_host, "download-behind-asr")
        wait_until(
            lambda: _stage_state(api_host, second_run, "downloading") == "completed",
            timeout=10,
        )
        assert not api_host.stack.transcriber.block.is_set()

        api_host.stack.transcriber.blocked = False
        api_host.stack.transcriber.block.set()
        assert api_host.wait_for_item(first_item)["processing_state"] == "completed"
        assert api_host.wait_for_item(second_item)["processing_state"] == "completed"
    finally:
        api_host.stack.transcriber.blocked = False
        api_host.stack.transcriber.block.set()
        worker.stop()


class _CountingDownloader(FakeDownloader):
    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0

    def download(self, source, context):
        with self.lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            assert self.gate.wait(10)
            return super().download(source, context)
        finally:
            with self.lock:
                self.in_flight -= 1


@pytest.mark.ffmpeg
def test_a_pool_never_exceeds_its_configured_concurrency(host_factory):
    stack = FakeStack()
    downloader = _CountingDownloader()
    stack.downloader = downloader
    host = host_factory(stack=stack)
    pools = resolve_worker_pools(host.config, pools=["download"], concurrency=2)
    worker = WorkerThread(host.runtime, pools=pools).start()
    try:
        runs = [_create_item(host, f"concurrency-{index}")[1] for index in range(5)]
        wait_until(lambda: downloader.peak == 2, timeout=10)
        time.sleep(0.2)
        assert downloader.peak == 2

        downloader.gate.set()
        wait_until(
            lambda: all(
                _stage_state(host, run_id, "downloading") == "completed"
                for run_id in runs
            ),
            timeout=15,
        )
        assert downloader.peak == 2
    finally:
        downloader.gate.set()
        worker.stop()


@pytest.mark.ffmpeg
def test_stop_waits_for_the_running_task_and_claims_nothing_new(host_factory):
    stack = FakeStack()
    stack.downloader.blocked = True
    host = host_factory(stack=stack)
    pools = resolve_worker_pools(host.config, pools=["download"])
    worker = WorkerThread(host.runtime, pools=pools).start()
    stop_thread: threading.Thread | None = None
    try:
        _, running_run = _create_item(host, "stopping-worker")
        assert stack.downloader.started.wait(10)

        stop_thread = threading.Thread(target=worker.stop, daemon=True)
        stop_thread.start()
        wait_until(lambda: worker.stop_event.is_set(), timeout=5)

        _, queued_run = _create_item(host, "queued-after-stop")
        time.sleep(0.5)
        assert _stage_state(host, queued_run, "downloading") == "queued"

        stack.downloader.block.set()
        stop_thread.join(timeout=10)
        assert not stop_thread.is_alive()
        assert _stage_state(host, running_run, "downloading") == "completed"

        with host.runtime.sessions() as session:
            queued = session.execute(
                select(RunStep).where(
                    RunStep.run_id == queued_run,
                    RunStep.stage == "downloading",
                )
            ).scalars().one()
            assert queued.state == "queued"
    finally:
        stack.downloader.block.set()
        if stop_thread is not None and stop_thread.is_alive():
            stop_thread.join(timeout=10)


@pytest.mark.ffmpeg
def test_shutdown_timeout_leaves_the_lease_for_the_reaper(host_factory):
    stack = FakeStack()
    stack.downloader.blocked = True
    host = host_factory(stack=stack)
    host.config.worker_shutdown_timeout_seconds = 1
    pools = resolve_worker_pools(host.config, pools=["download"])
    worker = WorkerThread(host.runtime, pools=pools).start()
    try:
        _, run_id = _create_item(host, "shutdown-timeout")
        assert stack.downloader.started.wait(10)

        started = time.monotonic()
        worker.stop(timeout=10)
        assert time.monotonic() - started < 5

        with host.runtime.sessions() as session:
            task = session.execute(
                select(RunStep).where(
                    RunStep.run_id == run_id,
                    RunStep.stage == "downloading",
                    RunStep.state == "running",
                )
            ).scalars().one()
            task.lease_until = 1
            session.commit()

        assert host.runtime.processing.reap_expired(now=utc_ms()) == 1
        with host.runtime.sessions() as session:
            queued = session.execute(
                select(RunStep).where(
                    RunStep.run_id == run_id,
                    RunStep.stage == "downloading",
                    RunStep.state == "queued",
                )
            ).scalars().one()
            assert queued.attempt == 2
    finally:
        stack.downloader.block.set()
