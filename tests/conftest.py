from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import httpx
import pytest
import uvicorn

from trove.app import create_app
from trove.config import Config
from trove.db.engine import upgrade_database
from trove.services.library import ItemBundle
from trove.worker import WorkerThread

from .fakes import FakeStack, wait_until

PASSWORD = "test-password"
TERMINAL_STATES = {"completed", "failed", "cancelled"}


@dataclass
class Host:
    runtime: object
    app: object
    server: uvicorn.Server
    thread: threading.Thread
    client: httpx.Client
    config: Config
    stack: FakeStack
    worker: WorkerThread | None

    @property
    def base_url(self) -> str:
        return str(self.client.base_url).rstrip("/")

    def login(self, password: str = PASSWORD) -> httpx.Response:
        response = self.client.post("/login", data={"password": password})
        assert response.status_code == 303, response.text
        return response

    def logout(self) -> httpx.Response:
        return self.client.post("/logout")

    def item(self, item_id: str) -> dict:
        response = self.client.get(f"/api/items/{item_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def run(self, item_id: str) -> dict | None:
        return self.item(item_id).get("run")

    def wait_for_item(self, item_id: str, *, timeout: float = 15.0) -> dict:
        def done():
            payload = self.item(item_id)
            run = payload.get("run")
            if run is None:
                return payload if payload["status_category"] == "ready" else None
            return payload if run["state"] in TERMINAL_STATES else None

        return wait_until(done, timeout=timeout)

    def wait_for_run_state(self, item_id: str, state: str, *, timeout: float = 10.0) -> dict:
        def matched():
            payload = self.item(item_id)
            run = payload.get("run")
            if run and run.get("state") == state:
                return run
            return None

        return wait_until(matched, timeout=timeout)

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.client.close()
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv("TROVE_HOME", raising=False)
    monkeypatch.setenv("TROVE_LOG_CONSOLE", "0")
    yield


@pytest.fixture
def fake_stack() -> FakeStack:
    return FakeStack()


@pytest.fixture
def host_factory(tmp_path, fake_stack):
    hosts: list[Host] = []

    def make(
        *,
        start_worker: bool = False,
        stack: FakeStack | None = None,
        password: str = PASSWORD,
        home_name: str = "home",
    ) -> Host:
        stack = stack or fake_stack
        config = Config(home=tmp_path / home_name)
        config.ensure_layout()
        config.set_password(password)
        upgrade_database(config)
        app = create_app(config, stack.ports())
        runtime = app.state.runtime
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                log_level="warning",
                access_log=False,
            )
        )
        thread = threading.Thread(target=server.run, name="trove-test-api", daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("API server failed to start")
            if time.monotonic() > deadline:
                raise TimeoutError("API server did not start")
            time.sleep(0.01)
        sockets = server.servers[0].sockets
        port = sockets[0].getsockname()[1]
        client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            follow_redirects=False,
            timeout=20,
        )
        worker = WorkerThread(runtime).start() if start_worker else None
        host = Host(
            runtime=runtime,
            app=app,
            server=server,
            thread=thread,
            client=client,
            config=config,
            stack=stack,
            worker=worker,
        )
        hosts.append(host)
        return host

    yield make
    for host in hosts:
        try:
            host.stop()
        except Exception:  # noqa: BLE001 - teardown must continue
            logging.getLogger("trove.tests").exception("failed to stop host")


@pytest.fixture
def host(host_factory) -> Host:
    return host_factory(start_worker=True)


@pytest.fixture
def api_host(host_factory) -> Host:
    return host_factory(start_worker=False)


def seed_item(
    host: Host,
    *,
    title: str = "Seeded Item",
    author: str = "Seed Author",
    source_key: str | None = None,
    source_type: str = "local_audio",
    platform: str = "local",
    source_url_raw: str | None = None,
    source_url_canonical: str | None = None,
    source_path: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    consumption_state: str = "unstarted",
    position: float = 0.0,
    duration: float = 2.0,
    with_audio: bool = True,
    audio_fixture: str = "short.m4a",
    run_state: str | None = "completed",
) -> ItemBundle:
    import shutil

    from trove.clock import utc_ms
    from trove.content_package import sha256_file
    from trove.db.models import Artifact, Run, RunStep

    from .fakes import FIXTURES

    bundle, _ = host.runtime.library.create_item(
        source_key=source_key or f"seed:{title}",
        source_type=source_type,
        platform=platform,
        title=title,
        author=author,
        source_url_raw=source_url_raw,
        source_url_canonical=source_url_canonical,
        source_path=source_path,
    )
    item_id = bundle.item.id
    if with_audio:
        destination = host.config.library_dir / item_id / "audio.m4a"
        shutil.copyfile(FIXTURES / audio_fixture, destination)
        with host.runtime.sessions() as session:
            session.add(
                Artifact(
                    item_id=item_id,
                    kind="audio",
                    path="audio.m4a",
                    sha256=sha256_file(destination),
                    size=destination.stat().st_size,
                    mime="audio/mp4",
                    duration_sec=duration,
                )
            )
            session.commit()
    with host.runtime.sessions() as session:
        from trove.db.models import Item

        item = session.get(Item, item_id)
        item.consumption_state = consumption_state
        item.audio_position_sec = position
        item.duration_sec = duration if with_audio else None
        item.summary = summary
        item.updated_at = utc_ms()
        if run_state:
            run = Run(
                id=f"run-{item_id[:8]}",
                item_id=item_id,
                state=run_state,
                created_at=utc_ms(),
                started_at=utc_ms(),
                finished_at=utc_ms() if run_state in TERMINAL_STATES else None,
                error_code="download.network" if run_state == "failed" else None,
                error_message="Network error; download failed" if run_state == "failed" else None,
            )
            session.add(run)
            if run_state in TERMINAL_STATES:
                session.add(
                    RunStep(
                        run_id=run.id,
                        stage="indexing",
                        state="completed",
                        attempt=1,
                        started_at=utc_ms(),
                        finished_at=utc_ms(),
                    )
                )
        session.commit()
    if tags:
        from trove.db.models import ItemTag, Tag
        from trove.domain.tags import normalize_tag

        with host.runtime.sessions() as session:
            for raw in tags:
                display, normalized = normalize_tag(raw)
                tag = session.query(Tag).filter_by(normalized_name=normalized).first()
                if tag is None:
                    tag = Tag(name=display, normalized_name=normalized)
                    session.add(tag)
                    session.flush()
                session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="user"))
            session.commit()
    return host.runtime.library.get(item_id)
