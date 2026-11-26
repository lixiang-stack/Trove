from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from trove.composition import Runtime
from trove.config import ConfigError
from trove.db.engine import current_revision, head_revision, verify_fts5
from trove.domain.items import STAGE_INDEXING
from trove.domain.worker_pools import (
    ALL_STAGES,
    INDEX_POOL_CONCURRENCY,
    POOL_NAMES,
    POOL_STAGES,
)
from trove.logging_setup import append_run_log

logger = logging.getLogger("trove.worker")
POLL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class WorkerPool:
    name: str
    stages: frozenset[str]
    concurrency: int


def resolve_worker_pools(
    config,
    *,
    pools: Sequence[str] = (),
    stages: str | None = None,
    concurrency: int | None = None,
) -> list[WorkerPool]:
    if pools and stages is not None:
        raise ConfigError("Use either --pool or --stages, not both")
    if concurrency is not None and concurrency <= 0:
        raise ConfigError("--concurrency must be a positive integer")
    if stages is not None:
        return [_custom_pool(stages, concurrency)]
    names = tuple(dict.fromkeys(pools)) or config.worker_pools
    unknown = [name for name in names if name not in POOL_STAGES]
    if unknown:
        raise ConfigError(
            f"Invalid worker pool: {', '.join(unknown)} is unknown; "
            f"choose from: {', '.join(POOL_NAMES)}"
        )
    resolved: list[WorkerPool] = []
    for name in names:
        value = concurrency if concurrency is not None else config.worker_concurrency[name]
        if value <= 0:
            raise ConfigError("--concurrency must be a positive integer")
        if name == "index":
            value = INDEX_POOL_CONCURRENCY
        resolved.append(WorkerPool(name=name, stages=POOL_STAGES[name], concurrency=value))
    return resolved


def _custom_pool(stages: str, concurrency: int | None) -> WorkerPool:
    names = [item.strip() for item in stages.split(",") if item.strip()]
    if not names:
        raise ConfigError("--stages must list at least one stage")
    unknown = sorted(set(names) - set(ALL_STAGES) - {"all"})
    if unknown:
        raise ConfigError(
            f"Invalid stage: {', '.join(unknown)}; "
            f"choose from: {', '.join(ALL_STAGES)}, all"
        )
    selected = frozenset(ALL_STAGES) if "all" in names else frozenset(names)
    value = concurrency if concurrency is not None else 1
    if value <= 0:
        raise ConfigError("--concurrency must be a positive integer")
    if selected == frozenset({STAGE_INDEXING}):
        value = INDEX_POOL_CONCURRENCY
    return WorkerPool(name="custom", stages=selected, concurrency=value)


def ensure_migrated(runtime: Runtime) -> None:
    current = current_revision(runtime.engine)
    head = head_revision(runtime.config)
    if current != head:
        raise RuntimeError("Database is not migrated; run: uv run trove db upgrade")


def run_worker(
    runtime: Runtime,
    stop_event: threading.Event | None = None,
    *,
    pools: Sequence[WorkerPool] | None = None,
) -> None:
    stop_event = stop_event or threading.Event()
    specs = list(pools) if pools is not None else resolve_worker_pools(runtime.config)
    parent_pid = _parent_pid()
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
    heartbeat = _Heartbeat(runtime, specs)
    heartbeat.refresh()
    workers: list[threading.Thread] = []
    try:
        for spec in specs:
            for index in range(spec.concurrency):
                thread = threading.Thread(
                    target=_pool_loop,
                    args=(runtime, spec, index, stop_event, heartbeat),
                    name=f"trove-{spec.name}-{index}",
                    daemon=True,
                )
                thread.start()
                workers.append(thread)
        interval = min(1.0, max(0.2, float(runtime.config.worker_heartbeat_seconds)))
        while not stop_event.wait(interval):
            if parent_pid is not None and os.getppid() != parent_pid:
                logger.info("serve parent exited; stopping embedded worker")
                stop_event.set()
                break
            heartbeat.refresh()
    finally:
        reaper_stop.set()
        reaper_thread.join(timeout=2)
        deadline = time.monotonic() + runtime.config.worker_shutdown_timeout_seconds
        for thread in workers:
            thread.join(max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                logger.warning(
                    "worker thread did not stop before the shutdown timeout; "
                    "its lease will be recovered by the reaper"
                )
        heartbeat.stop()


def _pool_loop(
    runtime: Runtime,
    pool: WorkerPool,
    index: int,
    stop_event: threading.Event,
    heartbeat: _Heartbeat,
) -> None:
    worker_id = f"worker-{os.getpid()}-{pool.name}-{index}"
    while not stop_event.is_set():
        run_id = runtime.processing.claim_next(worker_id, stages=pool.stages)
        if run_id is None:
            stop_event.wait(POLL_SECONDS)
            continue
        heartbeat.busy(worker_id, pool.name, run_id)
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
            heartbeat.idle(worker_id)


class _Heartbeat:
    def __init__(self, runtime: Runtime, pools: Sequence[WorkerPool]) -> None:
        self.runtime = runtime
        self._lock = threading.Lock()
        self._active: dict[str, tuple[str, str]] = {}
        self._concurrency = {pool.name: pool.concurrency for pool in pools}
        self._closed = False

    def busy(self, worker_id: str, pool_name: str, run_id: str) -> None:
        with self._lock:
            self._active[worker_id] = (pool_name, run_id)
            self._write()

    def idle(self, worker_id: str) -> None:
        with self._lock:
            if self._active.pop(worker_id, None) is not None:
                self._write()

    def refresh(self) -> None:
        with self._lock:
            self._write()

    def stop(self) -> None:
        with self._lock:
            self._closed = True
            self._write(state="stopped")

    def _write(self, *, state: str | None = None) -> None:
        if self._closed and state != "stopped":
            return
        pools = []
        first_run_id = None
        for name, concurrency in self._concurrency.items():
            active = sorted(
                run_id
                for pool_name, run_id in self._active.values()
                if pool_name == name
            )
            if active and first_run_id is None:
                first_run_id = active[0]
            pools.append(
                {
                    "name": name,
                    "concurrency": concurrency,
                    "active": len(active),
                    "run_id": active[0] if active else None,
                }
            )
        resolved_state = state or ("busy" if self._active else "idle")
        write_heartbeat(
            self.runtime,
            state=resolved_state,
            run_id=first_run_id,
            pools=pools,
        )


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
    runtime: Runtime,
    *,
    state: str,
    run_id: str | None = None,
    pools: list[dict[str, Any]] | None = None,
) -> None:
    path = runtime.config.worker_heartbeat_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "state": state,
        "run_id": run_id,
        "updated_at": int(time.time() * 1000),
        "pid": _pid(),
    }
    if pools is not None:
        payload["pools"] = pools
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
    def __init__(
        self, runtime: Runtime, *, pools: Sequence[WorkerPool] | None = None
    ) -> None:
        self.runtime = runtime
        self.pools = pools
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="trove-worker", daemon=True)
        self.error: BaseException | None = None

    def _run(self) -> None:
        try:
            run_worker(self.runtime, self.stop_event, pools=self.pools)
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
