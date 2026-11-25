from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from trove.composition import Runtime
from trove.db.engine import current_revision, head_revision, verify_fts5
from trove.logging_setup import append_run_log

logger = logging.getLogger("trove.worker")
POLL_SECONDS = 0.5


def ensure_migrated(runtime: Runtime) -> None:
    current = current_revision(runtime.engine)
    head = head_revision(runtime.config)
    if current != head:
        raise RuntimeError("Database is not migrated; run: uv run trove db upgrade")


def run_worker(runtime: Runtime, stop_event: threading.Event | None = None) -> None:
    stop_event = stop_event or threading.Event()
    parent_pid = _parent_pid()
    worker_id = f"worker-{os.getpid()}-{threading.get_ident()}"
    ensure_migrated(runtime)
    verify_fts5(runtime.engine)
    _reap_once(runtime)
    reaper_stop = threading.Event()
    reaper_thread = threading.Thread(
        target=_reaper_loop,
        args=(runtime, reaper_stop),
        name="trove-reaper",
        daemon=True,
    )
    reaper_thread.start()
    write_heartbeat(runtime, state="idle")
    try:
        while not stop_event.is_set():
            if parent_pid is not None and os.getppid() != parent_pid:
                logger.info("serve parent exited; stopping embedded worker")
                break
            run_id = runtime.processing.claim_next(worker_id)
            if run_id is None:
                write_heartbeat(runtime, state="idle")
                stop_event.wait(POLL_SECONDS)
                continue
            write_heartbeat(runtime, state="busy", run_id=run_id)
            heartbeat_stop = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(runtime, run_id, worker_id, heartbeat_stop),
                name=f"trove-heartbeat-{run_id}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                runtime.processing.process(run_id, worker_id)
            except Exception:  # noqa: BLE001 - the worker must survive one bad run
                logger.exception(
                    "worker failed while processing run", extra={"run_id": run_id}
                )
                append_run_log(
                    runtime.config, run_id, "worker crashed while processing", level="error"
                )
                try:
                    runtime.processing.mark_worker_failure(run_id, worker_id)
                except Exception:  # noqa: BLE001 - the worker must survive one bad run
                    logger.debug("failed to mark run failed", exc_info=True)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2)
            write_heartbeat(runtime, state="idle")
    finally:
        reaper_stop.set()
        reaper_thread.join(timeout=2)
    write_heartbeat(runtime, state="stopped")


def _reap_once(runtime: Runtime) -> None:
    reaped = runtime.processing.reap_expired()
    recovered = runtime.processing.recover_active_runs()
    if reaped or recovered:
        logger.info(
            "recovered stage tasks",
            extra={"reaped": reaped, "recovered": recovered},
        )


def _reaper_loop(runtime: Runtime, stop_event: threading.Event) -> None:
    interval = max(1, runtime.config.worker_reaper_interval_seconds)
    while not stop_event.wait(interval):
        try:
            _reap_once(runtime)
        except Exception:  # noqa: BLE001 - the reaper must not kill the worker
            logger.exception("stage task reaper failed")


def _heartbeat_loop(
    runtime: Runtime, run_id: str, worker_id: str, stop_event: threading.Event
) -> None:
    while not stop_event.wait(runtime.config.worker_heartbeat_seconds):
        try:
            runtime.processing.heartbeat(run_id, worker_id)
        except Exception:  # noqa: BLE001 - heartbeat must not kill the worker
            logger.debug("heartbeat update failed", exc_info=True)


def write_heartbeat(
    runtime: Runtime, *, state: str, run_id: str | None = None
) -> None:
    path = runtime.config.worker_heartbeat_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "run_id": run_id,
        "updated_at": int(time.time() * 1000),
        "pid": _pid(),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def read_heartbeat(config) -> dict[str, Any] | None:
    path = config.worker_heartbeat_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parent_pid() -> int | None:
    value = os.environ.get("TROVE_PARENT_PID")
    if not value or not value.isdigit():
        return None
    return int(value)


def _pid() -> int:
    return os.getpid()


class WorkerThread:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="trove-worker", daemon=True)
        self.error: BaseException | None = None

    def _run(self) -> None:
        try:
            run_worker(self.runtime, self.stop_event)
        except BaseException as exc:  # noqa: BLE001 - surfaced to tests
            self.error = exc

    def start(self) -> WorkerThread:
        self.thread.start()
        return self

    def stop(self, timeout: float = 10.0) -> None:
        self.stop_event.set()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise TimeoutError("worker did not stop before timeout")


def heartbeat_is_fresh(payload: dict[str, Any] | None, *, max_age_ms: int = 15000) -> bool:
    if not payload:
        return False
    updated = payload.get("updated_at")
    if not isinstance(updated, int):
        return False
    return int(time.time() * 1000) - updated <= max_age_ms
