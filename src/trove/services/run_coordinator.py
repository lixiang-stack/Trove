from __future__ import annotations

import shutil
import traceback
import uuid
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.config import Config
from trove.content_package import ContentPackage, SourceDocument
from trove.db.models import Item, Run, RunStep
from trove.domain.items import (
    DEFAULT_MAX_ATTEMPTS,
    REPROCESSABLE_STAGES,
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
    TERMINAL_RUN_STATES,
    RunState,
    StageTaskState,
    next_stage,
    prior_stages,
    stages_for,
)
from trove.errors import (
    ConflictError,
    NotFoundError,
    ProcessingCancelled,
    ProcessingError,
    TroveError,
    ValidationError,
)
from trove.logging_setup import append_run_log
from trove.ports import DOWNLOAD_MEDIA_FILENAME, SearchIndex, StageContext
from trove.services.stages.base import StageHandler

INDEX_AFTER_STAGES = frozenset(
    {STAGE_DOWNLOADING, STAGE_TRANSCRIBING, STAGE_EXTRACTING_TEXT, STAGE_ORGANIZING}
)
class RunCoordinator:
    def __init__(
        self,
        config: Config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        search_index: SearchIndex,
        stages: dict[str, StageHandler],
        *,
        clock: Callable[[], int] = utc_ms,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.search_index = search_index
        self.stages = stages
        self.clock = clock

    @property
    def lease_ms(self) -> int:
        return max(1, self.config.worker_lease_seconds) * 1000

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------
    def create_run(self, item_id: str) -> Run:
        with self.sessions() as session:
            active = session.execute(
                select(Run).where(
                    Run.item_id == item_id,
                    Run.state.not_in(tuple(TERMINAL_RUN_STATES)),
                )
            ).scalars().first()
            if active is not None:
                return active
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            now = self.clock()
            run = Run(
                id=str(uuid.uuid4()),
                item_id=item_id,
                state=RunState.QUEUED,
                created_at=now,
            )
            session.add(run)
            session.flush()
            self._enqueue_task(
                session,
                run.id,
                stages_for(item.source_type)[0],
                now=now,
                attempt=1,
            )
            session.commit()
            append_run_log(self.config, run.id, f"run queued for item {item_id}")
            return run

    def claim_next(
        self,
        worker_id: str,
        *,
        stages: Collection[str] | None = None,
    ) -> str | None:
        now = self.clock()
        with self.sessions() as session:
            query = (
                select(RunStep, Run, Item)
                .join(Run, Run.id == RunStep.run_id)
                .join(Item, Item.id == Run.item_id)
                .where(
                    RunStep.state == StageTaskState.QUEUED,
                    RunStep.available_at <= now,
                    Run.state == RunState.QUEUED,
                    Run.cancel_requested_at.is_(None),
                )
                .order_by(RunStep.priority.desc(), RunStep.id)
            )
            if stages is not None:
                query = query.where(RunStep.stage.in_(tuple(stages)))
            candidates = session.execute(query).all()
            for task, run, item in candidates:
                if not self._dependencies_completed(
                    session, run.id, item.source_type, task.stage
                ):
                    continue
                if not self._claim_task(session, task, worker_id, now):
                    continue
                session.commit()
                append_run_log(
                    self.config,
                    run.id,
                    f"stage {task.stage} claimed by {worker_id} (attempt {task.attempt})",
                )
                return run.id
        return None

    def process(self, run_id: str, worker_id: str) -> None:
        task_id: int | None = None
        stage: str | None = None
        attempt = 1
        item_id: str | None = None

        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None or run.state in TERMINAL_RUN_STATES:
                return
            task = self._running_task(session, run_id, worker_id)
            if task is None:
                if run.cancel_requested_at is not None:
                    return
                task = self._claim_next_task_for_run(
                    session, run, worker_id, self.clock()
                )
                if task is None:
                    self._complete_if_all_done(session, run)
                    session.commit()
                    return
                session.commit()
            task_id = task.id
            stage = task.stage
            attempt = task.attempt
            item = session.get(Item, run.item_id)
            if item is None:
                self._fail_run(
                    run_id,
                    task_id,
                    stage,
                    "internal.error",
                    "Content not found",
                    worker_id=worker_id,
                    clear_current_stage=True,
                )
                return
            item_id = item.id

        source = self.package.read_source(item_id)
        if source is None:
            append_run_log(
                self.config,
                run_id,
                "content package source.json is missing",
                level="error",
            )
            self._fail_run(
                run_id,
                task_id,
                stage,
                "storage.source_missing",
                "Content package is missing source.json",
                worker_id=worker_id,
                clear_current_stage=True,
            )
            return

        work_dir = self.config.cache_dir / "runs" / run_id
        work_dir.mkdir(parents=True, exist_ok=True)
        work_dir.chmod(0o700)
        context = StageContext(
            item_id=item_id,
            run_id=run_id,
            work_dir=work_dir,
            should_cancel=lambda: self._cancel_requested(run_id),
            log=lambda message: append_run_log(self.config, run_id, message),
        )

        if self._cancel_requested(run_id):
            self._cancel_running_task(run_id, task_id, stage)
            self._cleanup_work_dir(work_dir, keep_download=True)
            append_run_log(self.config, run_id, f"stage {stage} cancelled", level="warning")
            self._try_index(run_id, item_id)
            return

        assert item_id is not None
        append_run_log(
            self.config,
            run_id,
            f"stage {stage} started (attempt {attempt})",
        )
        if not self._execute_task(
            run_id, task_id, stage, item_id, worker_id, context, work_dir
        ):
            return
        append_run_log(self.config, run_id, f"stage {stage} completed")
        if stage in {STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO, STAGE_TRANSCRIBING}:
            self._cleanup_stage_leftovers(work_dir)
        if stage in INDEX_AFTER_STAGES:
            self._try_index(run_id, item_id)
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is not None and run.state == RunState.COMPLETED:
                self._cleanup_work_dir(work_dir, keep_download=False)
                append_run_log(self.config, run_id, "run completed")

    # ------------------------------------------------------------------
    # Retry / cancel / lease recovery
    # ------------------------------------------------------------------
    def retry(self, item_id: str) -> Run:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise TroveError("Content not found")
            run = self._latest_run(session, item_id)
            if run is None:
                raise ConflictError("No retryable Processing Run")
            if run.state not in TERMINAL_RUN_STATES:
                return run
            if run.state not in {RunState.FAILED, RunState.CANCELLED}:
                raise ConflictError("The current Processing Run does not need a retry")
            now = self.clock()
            stage = self._next_pending_stage(session, run.id, item.source_type)
            run.state = RunState.QUEUED
            run.current_stage = stage
            run.error_code = None
            run.error_message = None
            run.cancel_requested_at = None
            run.finished_at = None
            if stage is None:
                run.state = RunState.COMPLETED
                run.current_stage = None
                run.finished_at = now
                session.commit()
                return run
            self._enqueue_retry_task(session, run.id, stage, now)
            session.commit()
            append_run_log(self.config, run.id, f"run queued to retry stage {stage}")
            return run

    def reprocess(self, item_id: str, from_stage: str) -> Run:
        if from_stage not in REPROCESSABLE_STAGES:
            raise ValidationError(
                "Only transcribing, organizing, or indexing can be rerun",
                details={"code": "reprocess.invalid_stage"},
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            active = session.execute(
                select(Run).where(
                    Run.item_id == item_id,
                    Run.state.not_in(tuple(TERMINAL_RUN_STATES)),
                )
            ).scalars().first()
            if active is not None:
                return active
            stages = stages_for(item.source_type)
            if from_stage not in stages:
                raise ValidationError(
                    "Stage does not apply to this content type",
                    details={"code": "reprocess.invalid_stage"},
                )
            now = self.clock()
            run = Run(
                id=str(uuid.uuid4()),
                item_id=item_id,
                state=RunState.QUEUED,
                created_at=now,
            )
            session.add(run)
            session.flush()
            for stage in stages:
                if stage == from_stage:
                    break
                session.add(
                    RunStep(
                        run_id=run.id,
                        stage=stage,
                        state=StageTaskState.COMPLETED,
                        attempt=1,
                        max_attempts=DEFAULT_MAX_ATTEMPTS,
                        started_at=now,
                        finished_at=now,
                    )
                )
            self._enqueue_task(session, run.id, from_stage, now=now, attempt=1)
            session.commit()
            append_run_log(self.config, run.id, f"run queued for {from_stage} reprocess")
            return run

    def cancel(self, run_id: str) -> Run:
        now = self.clock()
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise TroveError("Processing Run not found")
            if run.state in TERMINAL_RUN_STATES:
                return run
            running = self._running_task(session, run_id)
            if running is not None:
                self._request_cancel(session, run, now)
                return run
            session.execute(
                update(RunStep)
                .where(RunStep.run_id == run_id, RunStep.state == StageTaskState.QUEUED)
                .values(
                    state=StageTaskState.CANCELLED,
                    error_code="run.cancelled",
                    error_message="Cancelled",
                    finished_at=now,
                    lease_until=None,
                    worker_id=None,
                )
            )
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(Run)
                    .where(
                        Run.id == run_id,
                        Run.state.not_in(tuple(TERMINAL_RUN_STATES)),
                    )
                    .values(state=RunState.CANCELLED, finished_at=now)
                ),
            )
            if result.rowcount == 1:
                session.commit()
                session.refresh(run)
                append_run_log(self.config, run.id, "cancel requested", level="warning")
                return run
            session.rollback()
            run = session.get(Run, run_id)
            if run is None:
                raise TroveError("Processing Run not found")
            if run.state in TERMINAL_RUN_STATES:
                return run
            self._request_cancel(session, run, now)
            return run

    def _request_cancel(self, session: Session, run: Run, now: int) -> None:
        if run.cancel_requested_at is None:
            run.cancel_requested_at = now
            session.commit()
            append_run_log(self.config, run.id, "cancel requested", level="warning")

    def cancel_item(self, item_id: str) -> Run:
        with self.sessions() as session:
            run = self._latest_run(session, item_id)
            if run is None:
                raise TroveError("No Processing Run to cancel")
        return self.cancel(run.id)

    def reap_expired(self, now: int | None = None) -> int:
        now = self.clock() if now is None else now
        reaped = 0
        with self.sessions() as session:
            expired = list(
                session.execute(
                    select(RunStep).where(
                        RunStep.state == StageTaskState.RUNNING,
                        RunStep.lease_until.is_not(None),
                        RunStep.lease_until <= now,
                    )
                ).scalars()
            )
            for task in expired:
                run = session.get(Run, task.run_id)
                if run is None:
                    continue
                if run.state in TERMINAL_RUN_STATES:
                    if self._update_expired_task(
                        session,
                        task,
                        now,
                        state=StageTaskState.CANCELLED,
                        error_code="run.reclaimed",
                        error_message="Run already finished",
                    ):
                        reaped += 1
                    continue
                if run.cancel_requested_at is not None:
                    if not self._update_expired_task(
                        session,
                        task,
                        now,
                        state=StageTaskState.CANCELLED,
                        error_code="run.cancelled",
                        error_message="Cancelled",
                    ):
                        continue
                    self._cancel_run_row(session, run, task.stage, now)
                    reaped += 1
                    append_run_log(
                        self.config, run.id, f"stage {task.stage} cancelled while reaping"
                    )
                    continue
                if task.attempt >= task.max_attempts:
                    if not self._update_expired_task(
                        session,
                        task,
                        now,
                        state=StageTaskState.DEAD,
                        error_code="run.dead",
                        error_message=(
                            f"Stage {task.stage} exceeded {task.max_attempts} attempts"
                        ),
                    ):
                        continue
                    session.execute(
                        update(Run)
                        .where(Run.id == run.id, Run.state == RunState.QUEUED)
                        .values(
                            state=RunState.FAILED,
                            error_code="run.dead",
                            error_message=(
                                f"Stage {task.stage} exceeded "
                                f"{task.max_attempts} attempts"
                            ),
                            current_stage=task.stage,
                            finished_at=now,
                        )
                    )
                    reaped += 1
                    append_run_log(
                        self.config,
                        run.id,
                        f"stage {task.stage} attempt {task.attempt} dead after lease expiry",
                        level="error",
                    )
                    continue
                if not self._update_expired_task(
                    session,
                    task,
                    now,
                    state=StageTaskState.FAILED,
                    error_code="run.lease_expired",
                    error_message=f"Worker lease expired after attempt {task.attempt}",
                ):
                    continue
                session.add(
                    RunStep(
                        run_id=task.run_id,
                        stage=task.stage,
                        state=StageTaskState.QUEUED,
                        attempt=task.attempt + 1,
                        max_attempts=task.max_attempts,
                        priority=task.priority,
                        available_at=now,
                    )
                )
                session.execute(
                    update(Run)
                    .where(
                        Run.id == run.id,
                        Run.state.not_in(tuple(TERMINAL_RUN_STATES)),
                        Run.cancel_requested_at.is_(None),
                    )
                    .values(
                        state=RunState.QUEUED,
                        current_stage=task.stage,
                        heartbeat_at=None,
                    )
                )
                reaped += 1
                append_run_log(
                    self.config,
                    run.id,
                    f"stage {task.stage} attempt {task.attempt} lease expired; "
                    f"requeued attempt {task.attempt + 1}",
                    level="warning",
                )
            session.commit()
        return reaped

    @staticmethod
    def _update_expired_task(
        session: Session, task: RunStep, now: int, **values: Any
    ) -> bool:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(RunStep)
                .where(
                    RunStep.id == task.id,
                    RunStep.state == StageTaskState.RUNNING,
                    RunStep.lease_until <= now,
                )
                .values(
                    finished_at=now,
                    lease_until=None,
                    worker_id=None,
                    **values,
                )
            ),
        )
        return result.rowcount == 1

    def recover_active_runs(self) -> int:
        repaired = 0
        with self.sessions() as session:
            runs = list(
                session.execute(
                    select(Run).where(Run.state == RunState.QUEUED)
                ).scalars()
            )
            for run in runs:
                item = session.get(Item, run.item_id)
                if item is None:
                    run.state = RunState.FAILED
                    run.error_code = "internal.error"
                    run.error_message = "Content not found"
                    run.finished_at = self.clock()
                    repaired += 1
                    continue
                tasks = list(
                    session.execute(
                        select(RunStep).where(RunStep.run_id == run.id)
                    ).scalars()
                )
                if run.cancel_requested_at is not None:
                    for task in tasks:
                        if task.state in {StageTaskState.QUEUED, StageTaskState.RUNNING}:
                            task.state = StageTaskState.CANCELLED
                            task.error_code = "run.cancelled"
                            task.error_message = "Cancelled"
                            task.finished_at = self.clock()
                            task.lease_until = None
                            task.worker_id = None
                    self._cancel_run_row(session, run, run.current_stage, self.clock())
                    repaired += 1
                    continue
                stages = stages_for(item.source_type)
                completed = {
                    task.stage for task in tasks if task.state == StageTaskState.COMPLETED
                }
                pending = next((stage for stage in stages if stage not in completed), None)
                if pending is None:
                    run.state = RunState.COMPLETED
                    run.current_stage = None
                    run.finished_at = self.clock()
                    repaired += 1
                    continue
                if any(
                    task.state in {StageTaskState.QUEUED, StageTaskState.RUNNING}
                    for task in tasks
                ):
                    continue
                latest = max(
                    (task for task in tasks if task.stage == pending),
                    key=lambda task: task.attempt,
                    default=None,
                )
                if latest is not None and latest.state == StageTaskState.DEAD:
                    run.state = RunState.FAILED
                    run.error_code = "run.dead"
                    run.error_message = latest.error_message
                    run.current_stage = pending
                    run.finished_at = self.clock()
                    repaired += 1
                    continue
                self._enqueue_task(
                    session,
                    run.id,
                    pending,
                    now=self.clock(),
                    attempt=(latest.attempt + 1) if latest is not None else 1,
                )
                run.current_stage = pending
                repaired += 1
                append_run_log(self.config, run.id, f"stage {pending} re-enqueued by recovery")
            session.commit()
        return repaired

    def heartbeat(self, run_id: str, worker_id: str) -> None:
        now = self.clock()
        with self.sessions() as session:
            session.execute(
                update(Run).where(Run.id == run_id).values(heartbeat_at=now)
            )
            session.execute(
                update(RunStep)
                .where(
                    RunStep.run_id == run_id,
                    RunStep.state == StageTaskState.RUNNING,
                    RunStep.worker_id == worker_id,
                )
                .values(lease_until=now + self.lease_ms)
            )
            session.commit()

    def mark_worker_failure(self, run_id: str, worker_id: str) -> None:
        now = self.clock()
        with self.sessions() as session:
            task = session.execute(
                select(RunStep).where(
                    RunStep.run_id == run_id,
                    RunStep.state == StageTaskState.RUNNING,
                    RunStep.worker_id == worker_id,
                )
            ).scalars().first()
            if task is None:
                return
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(RunStep)
                    .where(
                        RunStep.id == task.id,
                        RunStep.state == StageTaskState.RUNNING,
                        RunStep.worker_id == worker_id,
                    )
                    .values(
                        state=StageTaskState.FAILED,
                        error_code="internal.error",
                        error_message="worker exited unexpectedly",
                        finished_at=now,
                        lease_until=None,
                        worker_id=None,
                    )
                ),
            )
            if result.rowcount != 1:
                session.rollback()
                return
            session.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    state=RunState.FAILED,
                    error_code="internal.error",
                    error_message="worker exited unexpectedly",
                    current_stage=task.stage,
                    finished_at=now,
                )
            )
            session.commit()

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------
    def _execute_task(
        self,
        run_id: str,
        task_id: int,
        stage: str,
        item_id: str,
        worker_id: str,
        context: StageContext,
        work_dir: Path,
    ) -> bool:
        try:
            with self.sessions() as session:
                task = session.get(RunStep, task_id)
                if task is None or task.state != StageTaskState.RUNNING:
                    return False
                if task.worker_id != worker_id:
                    return False
                item = session.get(Item, item_id)
                if item is None:
                    raise ProcessingError("internal.error", "Content not found")
                source = self.package.read_source(item.id)
                if source is None:
                    raise ProcessingError(
                        "storage.source_missing",
                        "Content package is missing source.json",
                    )
                self._execute_stage(stage, session, item, source, context)
                if not self._finish_task(
                    session, item, task, now=self.clock(), worker_id=worker_id
                ):
                    session.rollback()
                    append_run_log(
                        self.config,
                        run_id,
                        f"stage {stage} lost its lease before completion; retry queued",
                        level="warning",
                    )
                    return False
                session.commit()
                return True
        except ProcessingCancelled:
            self._cancel_running_task(run_id, task_id, stage)
            self._cleanup_work_dir(work_dir, keep_download=True)
            append_run_log(self.config, run_id, f"stage {stage} cancelled", level="warning")
            self._try_index(run_id, item_id)
            return False
        except ProcessingError as exc:
            self._fail_run(
                run_id,
                task_id,
                stage,
                exc.code,
                exc.message,
                worker_id=worker_id,
                details=exc.details,
            )
            self._cleanup_work_dir(work_dir, keep_download=stage != STAGE_DOWNLOADING)
            append_run_log(
                self.config, run_id, f"stage {stage} failed: {exc.code}", level="error"
            )
            self._try_index(run_id, item_id)
            return False
        except Exception as exc:  # noqa: BLE001 - boundary for a durable worker
            append_run_log(
                self.config,
                run_id,
                f"stage {stage} crashed: {traceback.format_exc()}",
                level="error",
            )
            self._fail_run(
                run_id,
                task_id,
                stage,
                "internal.error",
                "Internal error",
                worker_id=worker_id,
                details={"error": str(exc)},
            )
            self._cleanup_work_dir(work_dir, keep_download=stage != STAGE_DOWNLOADING)
            self._try_index(run_id, item_id)
            return False

    def _execute_stage(
        self,
        stage: str,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        try:
            handler = self.stages[stage]
        except KeyError as exc:
            raise ProcessingError("internal.error", f"Unknown stage: {stage}") from exc
        handler.execute(session, item, source, context)

    def _try_index(self, run_id: str, item_id: str) -> None:
        try:
            self.search_index.index_item(item_id)
        except Exception:  # noqa: BLE001 - retrieval must not change the run outcome
            append_run_log(
                self.config,
                run_id,
                f"search index refresh failed: {traceback.format_exc()}",
                level="warning",
            )

    # ------------------------------------------------------------------
    # Task bookkeeping
    # ------------------------------------------------------------------
    def _enqueue_task(
        self,
        session: Session,
        run_id: str,
        stage: str,
        *,
        now: int,
        attempt: int,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> RunStep:
        task = RunStep(
            run_id=run_id,
            stage=stage,
            state=StageTaskState.QUEUED,
            attempt=attempt,
            max_attempts=max_attempts,
            available_at=now,
        )
        session.add(task)
        return task

    def _enqueue_retry_task(
        self, session: Session, run_id: str, stage: str, now: int
    ) -> RunStep:
        latest = session.execute(
            select(RunStep)
            .where(RunStep.run_id == run_id, RunStep.stage == stage)
            .order_by(RunStep.attempt.desc())
            .limit(1)
        ).scalars().first()
        if latest is not None and latest.state == StageTaskState.QUEUED:
            latest.available_at = now
            return latest
        attempt = (latest.attempt + 1) if latest is not None else 1
        return self._enqueue_task(
            session,
            run_id,
            stage,
            now=now,
            attempt=attempt,
            max_attempts=latest.max_attempts if latest is not None else DEFAULT_MAX_ATTEMPTS,
        )

    def _claim_next_task_for_run(
        self, session: Session, run: Run, worker_id: str, now: int
    ) -> RunStep | None:
        item = session.get(Item, run.item_id)
        if item is None:
            return None
        candidates = list(
            session.execute(
                select(RunStep)
                .where(
                    RunStep.run_id == run.id,
                    RunStep.state == StageTaskState.QUEUED,
                    RunStep.available_at <= now,
                )
                .order_by(RunStep.priority.desc(), RunStep.id)
            ).scalars()
        )
        for task in candidates:
            if not self._dependencies_completed(
                session, run.id, item.source_type, task.stage
            ):
                continue
            if self._claim_task(session, task, worker_id, now):
                return task
        return None

    def _claim_task(
        self, session: Session, task: RunStep, worker_id: str, now: int
    ) -> bool:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(RunStep)
                .where(
                    RunStep.id == task.id,
                    RunStep.state == StageTaskState.QUEUED,
                    RunStep.available_at <= now,
                )
                .values(
                    state=StageTaskState.RUNNING,
                    worker_id=worker_id,
                    lease_until=now + self.lease_ms,
                    started_at=func.coalesce(RunStep.started_at, now),
                )
            ),
        )
        if result.rowcount != 1:
            return False
        run_result = cast(
            CursorResult[Any],
            session.execute(
                update(Run)
                .where(
                    Run.id == task.run_id,
                    Run.state == RunState.QUEUED,
                    Run.cancel_requested_at.is_(None),
                )
                .values(
                    current_stage=task.stage,
                    heartbeat_at=now,
                    started_at=func.coalesce(Run.started_at, now),
                )
            ),
        )
        if run_result.rowcount != 1:
            session.rollback()
            return False
        return True

    def _finish_task(
        self,
        session: Session,
        item: Item,
        task: RunStep,
        *,
        now: int,
        worker_id: str,
    ) -> bool:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(RunStep)
                .where(
                    RunStep.id == task.id,
                    RunStep.state == StageTaskState.RUNNING,
                    RunStep.worker_id == worker_id,
                    RunStep.lease_until > now,
                )
                .values(
                    state=StageTaskState.COMPLETED,
                    finished_at=now,
                    lease_until=None,
                    worker_id=None,
                )
            ),
        )
        if result.rowcount != 1:
            return False
        run = session.get(Run, task.run_id)
        if run is None or run.state in TERMINAL_RUN_STATES:
            return True
        run.heartbeat_at = now
        if run.cancel_requested_at is not None:
            run.state = RunState.CANCELLED
            run.current_stage = task.stage
            run.finished_at = now
            return True
        following = next_stage(item.source_type, task.stage)
        if following is None:
            run.state = RunState.COMPLETED
            run.current_stage = None
            run.error_code = None
            run.error_message = None
            run.finished_at = now
            return True
        run.state = RunState.QUEUED
        run.current_stage = following
        self._enqueue_task(
            session,
            run.id,
            following,
            now=now,
            attempt=self._next_attempt(session, run.id, following),
        )
        return True

    def _cancel_running_task(self, run_id: str, task_id: int, stage: str) -> None:
        now = self.clock()
        with self.sessions() as session:
            task = session.get(RunStep, task_id)
            run = session.get(Run, run_id)
            if task is not None and task.state == StageTaskState.RUNNING:
                self._mark_task_cancelled(session, task, now)
            session.execute(
                update(RunStep)
                .where(
                    RunStep.run_id == run_id,
                    RunStep.state == StageTaskState.QUEUED,
                )
                .values(
                    state=StageTaskState.CANCELLED,
                    error_code="run.cancelled",
                    error_message="Cancelled",
                    finished_at=now,
                    lease_until=None,
                    worker_id=None,
                )
            )
            if run is not None and run.state not in TERMINAL_RUN_STATES:
                self._cancel_run_row(session, run, stage, now)
            session.commit()

    def _cancel_run_row(
        self, session: Session, run: Run, stage: str | None, now: int
    ) -> None:
        run.state = RunState.CANCELLED
        if stage is not None:
            run.current_stage = stage
        run.finished_at = now

    @staticmethod
    def _mark_task_cancelled(session: Session, task: RunStep, now: int) -> None:
        task.state = StageTaskState.CANCELLED
        task.error_code = "run.cancelled"
        task.error_message = "Cancelled"
        task.finished_at = now
        task.lease_until = None
        task.worker_id = None

    def _fail_run(
        self,
        run_id: str,
        task_id: int | None,
        stage: str | None,
        code: str,
        message: str,
        *,
        worker_id: str,
        details: dict[str, Any] | None = None,
        clear_current_stage: bool = False,
    ) -> None:
        now = self.clock()
        with self.sessions() as session:
            if task_id is not None:
                result = cast(
                    CursorResult[Any],
                    session.execute(
                        update(RunStep)
                        .where(
                            RunStep.id == task_id,
                            RunStep.state == StageTaskState.RUNNING,
                            RunStep.worker_id == worker_id,
                            RunStep.lease_until > now,
                        )
                        .values(
                            state=StageTaskState.FAILED,
                            error_code=code,
                            error_message=message,
                            finished_at=now,
                            lease_until=None,
                            worker_id=None,
                        )
                    ),
                )
                if result.rowcount != 1:
                    session.rollback()
                    append_run_log(
                        self.config,
                        run_id,
                        "stage lost its lease before failure was recorded; retry queued",
                        level="warning",
                    )
                    return
            run = session.get(Run, run_id)
            if run is not None and run.state not in TERMINAL_RUN_STATES:
                run.state = RunState.FAILED
                run.error_code = code
                run.error_message = message
                run.current_stage = None if clear_current_stage else stage
                run.finished_at = now
            session.commit()
        if details is not None:
            append_run_log(
                self.config,
                run_id,
                f"run failed with {code}: {details}",
                level="error",
            )

    def _complete_if_all_done(self, session: Session, run: Run) -> None:
        item = session.get(Item, run.item_id)
        if item is None:
            return
        completed = self._completed_stages(session, run.id)
        if all(stage in completed for stage in stages_for(item.source_type)):
            run.state = RunState.COMPLETED
            run.current_stage = None
            run.finished_at = self.clock()

    @staticmethod
    def _completed_stages(session: Session, run_id: str) -> set[str]:
        return set(
            session.execute(
                select(RunStep.stage).where(
                    RunStep.run_id == run_id,
                    RunStep.state == StageTaskState.COMPLETED,
                )
            ).scalars()
        )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    @staticmethod
    def _dependencies_completed(
        session: Session, run_id: str, source_type: str, stage: str
    ) -> bool:
        required = prior_stages(source_type, stage)
        if required is None:
            return False
        if not required:
            return True
        completed = set(
            session.execute(
                select(RunStep.stage).where(
                    RunStep.run_id == run_id,
                    RunStep.state == StageTaskState.COMPLETED,
                    RunStep.stage.in_(required),
                )
            ).scalars()
        )
        return completed == set(required)

    @staticmethod
    def _next_attempt(session: Session, run_id: str, stage: str) -> int:
        latest = session.execute(
            select(RunStep.attempt)
            .where(RunStep.run_id == run_id, RunStep.stage == stage)
            .order_by(RunStep.attempt.desc())
            .limit(1)
        ).scalars().first()
        return int(latest or 0) + 1

    def _next_pending_stage(
        self, session: Session, run_id: str, source_type: str
    ) -> str | None:
        completed = self._completed_stages(session, run_id)
        for stage in stages_for(source_type):
            if stage not in completed:
                return stage
        return None

    @staticmethod
    def _running_task(
        session: Session, run_id: str, worker_id: str | None = None
    ) -> RunStep | None:
        query = select(RunStep).where(
            RunStep.run_id == run_id, RunStep.state == StageTaskState.RUNNING
        )
        if worker_id is not None:
            query = query.where(RunStep.worker_id == worker_id)
        return session.execute(
            query.order_by(RunStep.id.desc()).limit(1)
        ).scalars().first()

    def _cancel_requested(self, run_id: str) -> bool:
        with self.sessions() as session:
            value = session.execute(
                select(Run.cancel_requested_at).where(Run.id == run_id)
            ).scalars().first()
            return value is not None

    def _latest_run(self, session: Session, item_id: str) -> Run | None:
        return session.execute(
            select(Run)
            .where(Run.item_id == item_id)
            .order_by(Run.created_at.desc(), Run.id.desc())
        ).scalars().first()

    @staticmethod
    def _cleanup_work_dir(work_dir: Path, *, keep_download: bool) -> None:
        if not work_dir.exists():
            return
        for path in work_dir.iterdir():
            if keep_download and path.name == DOWNLOAD_MEDIA_FILENAME:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    @staticmethod
    def _cleanup_stage_leftovers(work_dir: Path) -> None:
        if not work_dir.exists():
            return
        for path in work_dir.iterdir():
            if path.name.endswith((".tmp", ".part")):
                path.unlink(missing_ok=True)
