from __future__ import annotations

import shutil
import traceback
import uuid
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.content_package import (
    ArtifactKind,
    ContentPackage,
    SourceDocument,
    sha256_file,
)
from trove.db.models import (
    Artifact,
    Item,
    ItemTag,
    Run,
    RunStep,
    Tag,
)
from trove.domain.books import meaningful_title
from trove.domain.items import (
    ACTIVE_RUN_STATES,
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
    RunState,
    stages_for,
)
from trove.domain.organization import MAX_EXISTING_TAGS
from trove.errors import (
    ConflictError,
    NotFoundError,
    ProcessingCancelled,
    ProcessingError,
    TroveError,
    ValidationError,
)
from trove.logging_setup import append_run_log
from trove.ports import (
    DOWNLOAD_MEDIA_FILENAME,
    AudioExtractor,
    BookExtractor,
    BookResult,
    Downloader,
    Organizer,
    SearchIndex,
    StageContext,
    Transcriber,
)
from trove.services.package_documents import (
    ai_document,
    book_document,
    source_document,
    transcript_document,
)
from trove.services.uploads import UploadStore

INDEX_AFTER_STAGES = frozenset(
    {STAGE_DOWNLOADING, STAGE_TRANSCRIBING, STAGE_EXTRACTING_TEXT, STAGE_ORGANIZING}
)
REPROCESSABLE_STAGES = frozenset({STAGE_ORGANIZING, STAGE_INDEXING})


class ProcessingService:
    def __init__(
        self,
        config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        *,
        downloader: Downloader,
        audio_extractor: AudioExtractor,
        transcriber: Transcriber,
        organizer: Organizer,
        book_extractor: BookExtractor,
        search_index: SearchIndex,
        uploads: UploadStore,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.downloader = downloader
        self.audio_extractor = audio_extractor
        self.transcriber = transcriber
        self.organizer = organizer
        self.book_extractor = book_extractor
        self.search_index = search_index
        self.uploads = uploads

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------
    def create_run(self, item_id: str) -> Run:
        with self.sessions() as session:
            active = session.execute(
                select(Run).where(
                    Run.item_id == item_id,
                    Run.state.in_(tuple(ACTIVE_RUN_STATES)),
                )
            ).scalars().first()
            if active is not None:
                return active
            run = Run(
                id=str(uuid.uuid4()),
                item_id=item_id,
                state=RunState.QUEUED,
                created_at=utc_ms(),
            )
            session.add(run)
            session.commit()
            append_run_log(self.config, run.id, f"run queued for item {item_id}")
            return run

    def claim_next(self) -> str | None:
        with self.sessions() as session:
            candidate = session.execute(
                select(Run).where(Run.state == RunState.QUEUED).order_by(Run.created_at)
            ).scalars().first()
            if candidate is None:
                return None
            item = session.get(Item, candidate.item_id)
            if item is None:
                session.delete(candidate)
                session.commit()
                return None
            stage = self._next_pending_stage(session, candidate, item)
            if stage is None:
                candidate.state = RunState.COMPLETED
                candidate.finished_at = utc_ms()
                session.commit()
                return None
            now = utc_ms()
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(Run)
                    .where(Run.id == candidate.id, Run.state == RunState.QUEUED)
                    .values(
                        state=stage,
                        current_stage=stage,
                        heartbeat_at=now,
                        started_at=func.coalesce(Run.started_at, now),
                    )
                ),
            )
            session.commit()
            if result.rowcount != 1:
                return None
            append_run_log(self.config, candidate.id, f"claimed at stage {stage}")
            return candidate.id

    def process(self, run_id: str) -> None:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            item = session.get(Item, run.item_id)
            if item is None:
                run.state = RunState.FAILED
                run.error_code = "internal.error"
                run.error_message = "Content not found"
                run.finished_at = utc_ms()
                session.commit()
                return
            stages = stages_for(item.source_type)
            source = self.package.read_source(item.id)

        if source is None:
            append_run_log(
                self.config,
                run_id,
                "content package source.json is missing",
                level="error",
            )
            self._fail(
                run_id,
                None,
                "storage.source_missing",
                "Content package is missing source.json",
            )
            return

        work_dir = self.config.cache_dir / "runs" / run_id
        work_dir.mkdir(parents=True, exist_ok=True)
        work_dir.chmod(0o700)
        context = StageContext(
            item_id=item.id,
            run_id=run_id,
            work_dir=work_dir,
            should_cancel=lambda: self._cancel_requested(run_id),
            log=lambda message: append_run_log(self.config, run_id, message),
        )

        for stage in stages:
            if self._stage_completed(run_id, stage):
                continue
            if self._cancel_requested(run_id):
                self._cancel(run_id, stage)
                self._try_index(run_id, context.item_id)
                return
            step = self._start_step(run_id, stage)
            append_run_log(self.config, run_id, f"stage {stage} started (attempt {step.attempt})")
            try:
                with self.sessions() as session:
                    item = session.get(Item, context.item_id)
                    assert item is not None
                    source = self.package.read_source(item.id)
                    if source is None:
                        raise ProcessingError(
                            "storage.source_missing",
                            "Content package is missing source.json",
                        )
                    self._execute_stage(stage, session, item, run_id, source, context)
                    session.commit()
            except ProcessingCancelled:
                self._cancel(run_id, stage)
                self._cleanup_work_dir(work_dir, keep_download=True)
                append_run_log(self.config, run_id, f"stage {stage} cancelled", level="warning")
                self._try_index(run_id, context.item_id)
                return
            except ProcessingError as exc:
                self._fail(run_id, stage, exc.code, exc.message, exc.details)
                self._cleanup_work_dir(work_dir, keep_download=stage != STAGE_DOWNLOADING)
                append_run_log(
                    self.config, run_id, f"stage {stage} failed: {exc.code}", level="error"
                )
                if stage != STAGE_INDEXING:
                    self._try_index(run_id, context.item_id)
                return
            except Exception as exc:  # noqa: BLE001 - boundary for a durable worker
                append_run_log(
                    self.config,
                    run_id,
                    f"stage {stage} crashed: {traceback.format_exc()}",
                    level="error",
                )
                self._fail(run_id, stage, "internal.error", "Internal error", {"error": str(exc)})
                self._cleanup_work_dir(work_dir, keep_download=stage != STAGE_DOWNLOADING)
                if stage != STAGE_INDEXING:
                    self._try_index(run_id, context.item_id)
                return
            self._finish_step(run_id, stage)
            append_run_log(self.config, run_id, f"stage {stage} completed")
            if stage in {STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO, STAGE_TRANSCRIBING}:
                self._cleanup_stage_leftovers(work_dir)
            if stage in INDEX_AFTER_STAGES:
                self._try_index(run_id, context.item_id)

        self._complete(run_id)
        self._cleanup_work_dir(work_dir, keep_download=False)
        append_run_log(self.config, run_id, "run completed")

    # ------------------------------------------------------------------
    # Retry / cancel / reclaim
    # ------------------------------------------------------------------
    def retry(self, item_id: str) -> Run:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise TroveError("Content not found")
            run = self._latest_run(session, item_id)
            if run is None:
                raise ConflictError("No retryable Processing Run")
            if run.state in ACTIVE_RUN_STATES:
                return run
            if run.state not in {RunState.FAILED, RunState.CANCELLED}:
                raise ConflictError("The current Processing Run does not need a retry")
            run.state = RunState.QUEUED
            run.current_stage = None
            run.error_code = None
            run.error_message = None
            run.cancel_requested_at = None
            run.finished_at = None
            session.commit()
            append_run_log(self.config, run.id, "run queued for retry")
            return run

    def reprocess(self, item_id: str, from_stage: str) -> Run:
        if from_stage not in REPROCESSABLE_STAGES:
            raise ValidationError(
                "Only organizing or indexing can be rerun",
                details={"code": "reprocess.invalid_stage"},
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            active = session.execute(
                select(Run).where(
                    Run.item_id == item_id,
                    Run.state.in_(tuple(ACTIVE_RUN_STATES)),
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
            now = utc_ms()
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
                        state="completed",
                        attempt=1,
                        started_at=now,
                        finished_at=now,
                    )
                )
            session.commit()
            append_run_log(self.config, run.id, f"run queued for {from_stage} reprocess")
            return run

    def cancel(self, run_id: str) -> Run:
        now = utc_ms()
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise TroveError("Processing Run not found")
            if run.state in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}:
                return run
            if run.state == RunState.QUEUED:
                result = cast(
                    CursorResult[Any],
                    session.execute(
                        update(Run)
                        .where(Run.id == run_id, Run.state == RunState.QUEUED)
                        .values(state=RunState.CANCELLED, finished_at=now)
                    ),
                )
                session.commit()
                if result.rowcount == 1:
                    append_run_log(
                        self.config, run.id, "cancel requested", level="warning"
                    )
                    session.refresh(run)
                    return run
                run = session.get(Run, run_id)
                if run is None:
                    raise TroveError("Processing Run not found")
                if run.state in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}:
                    return run
            run.cancel_requested_at = now
            session.commit()
            append_run_log(self.config, run.id, "cancel requested", level="warning")
            return run

    def cancel_item(self, item_id: str) -> Run:
        with self.sessions() as session:
            run = self._latest_run(session, item_id)
            if run is None:
                raise TroveError("No Processing Run to cancel")
        return self.cancel(run.id)

    def reclaim_stale_runs(self) -> int:
        reclaimed = 0
        with self.sessions() as session:
            runs = list(
                session.execute(select(Run).where(Run.state.in_(tuple(ACTIVE_RUN_STATES)))).scalars()
            )
            for run in runs:
                if run.state == RunState.QUEUED:
                    continue
                running_steps = list(
                    session.execute(
                        select(RunStep).where(
                            RunStep.run_id == run.id, RunStep.state == "running"
                        )
                    ).scalars()
                )
                for step in running_steps:
                    step.state = "cancelled"
                    step.error_code = "run.reclaimed"
                    step.error_message = "Host restarted; stage requeued"
                    step.finished_at = utc_ms()
                if run.cancel_requested_at is not None:
                    run.state = RunState.CANCELLED
                    run.finished_at = utc_ms()
                else:
                    run.state = RunState.QUEUED
                    run.current_stage = None
                run.heartbeat_at = None
                append_run_log(self.config, run.id, "stale run reclaimed on worker start")
                self._cleanup_work_dir(
                    self.config.cache_dir / "runs" / run.id, keep_download=True
                )
                reclaimed += 1
            session.commit()
        return reclaimed

    def heartbeat(self, run_id: str) -> None:
        with self.sessions() as session:
            session.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(heartbeat_at=utc_ms())
            )
            session.commit()

    def mark_worker_failure(self, run_id: str) -> None:
        with self.sessions() as session:
            session.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    state=RunState.FAILED,
                    error_code="internal.error",
                    error_message="worker exited unexpectedly",
                    finished_at=utc_ms(),
                )
            )
            session.commit()

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------
    def _execute_stage(
        self,
        stage: str,
        session: Session,
        item: Item,
        run_id: str,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        if stage == STAGE_DOWNLOADING:
            self._stage_download(session, item, source, context)
        elif stage == STAGE_EXTRACTING_AUDIO:
            self._stage_extract_audio(session, item, source, context)
        elif stage == STAGE_TRANSCRIBING:
            self._stage_transcribe(session, item, context)
        elif stage == STAGE_EXTRACTING_TEXT:
            self._stage_extract_text(session, item, context)
        elif stage == STAGE_ORGANIZING:
            self._stage_organize(session, item, run_id, context)
        elif stage == STAGE_INDEXING:
            self.search_index.index_item(item.id)
        else:
            raise ProcessingError("internal.error", f"Unknown stage: {stage}")

    def _stage_download(
        self, session: Session, item: Item, source: SourceDocument, context: StageContext
    ) -> None:
        result = self.downloader.download(source, context)
        item.title = result.title or item.title
        item.author = result.author or item.author
        item.published_at = result.published_at or item.published_at
        item.duration_sec = result.duration_sec or item.duration_sec
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        self._sync_source(item, source)
        context.log(f"downloaded media {result.path.name}")

    def _stage_extract_audio(
        self, session: Session, item: Item, source: SourceDocument, context: StageContext
    ) -> None:
        if item.source_type in {"video_url", "podcast_episode"}:
            media_path = context.work_dir / DOWNLOAD_MEDIA_FILENAME
            if not media_path.is_file():
                raise ProcessingError("download.parse", "Downloaded media file not found")
            force_transcode = True
        else:
            if not item.source_path:
                raise ProcessingError("storage.source_missing", "Local source file path is missing")
            media_path = Path(item.source_path)
            if not media_path.is_file():
                raise ProcessingError(
                    "storage.source_missing", "Source file does not exist or is not readable"
                )
            force_transcode = item.source_type == "local_video"
        result = self.audio_extractor.extract(
            media_path,
            context.work_dir,
            force_transcode=force_transcode,
            context=context,
        )
        artifact = self._install_artifact(
            session,
            item,
            kind=ArtifactKind.AUDIO,
            temp_path=result.path,
            extension=result.extension,
            mime=result.mime,
            duration=result.duration_sec,
        )
        item.duration_sec = result.duration_sec or item.duration_sec
        item.updated_at = utc_ms()
        if (
            source.uploaded
            and item.source_path
            and self.uploads.discard_for_path(item.source_path)
        ):
            item.source_path = None
        self._sync_source(item, source)
        if item.source_type in {"video_url", "podcast_episode"}:
            media_path.unlink(missing_ok=True)
        context.log(f"audio artifact {artifact.path} ({artifact.size} bytes)")

    def _stage_transcribe(
        self, session: Session, item: Item, context: StageContext
    ) -> None:
        audio = self._artifact(session, item.id, ArtifactKind.AUDIO)
        if audio is None:
            raise ProcessingError("asr.failed", "Audio is missing; cannot transcribe")
        audio_path = self.package.artifact_path(item.id, audio.path)
        result = self.transcriber.transcribe(audio_path, context)
        path = self.package.write_transcript(item.id, transcript_document(result, item))
        self._record_document(session, item, kind=ArtifactKind.TRANSCRIPT, path=path)
        if result.language:
            item.language = result.language
        item.updated_at = utc_ms()

    def _stage_extract_text(
        self, session: Session, item: Item, context: StageContext
    ) -> None:
        book = self._artifact(session, item.id, ArtifactKind.BOOK)
        if book is None:
            raise ProcessingError("epub.invalid", "EPUB file is missing")
        book_path = self.package.artifact_path(item.id, book.path)
        result = self.book_extractor.extract(book_path, context)
        title = self._book_title(result, item)
        path = self.package.write_book(item.id, book_document(result, title=title))
        self._record_document(session, item, kind=ArtifactKind.BOOK_JSON, path=path)
        previous_cover = self._artifact(session, item.id, ArtifactKind.COVER)
        if result.cover is not None:
            cover_temp = context.work_dir / f"cover{result.cover.extension}"
            cover_temp.write_bytes(result.cover.data)
            self._install_artifact(
                session,
                item,
                kind=ArtifactKind.COVER,
                temp_path=cover_temp,
                extension=result.cover.extension,
                mime=result.cover.mime,
                duration=None,
            )
        elif previous_cover is not None:
            self.package.remove_artifact(item.id, previous_cover.path)
            session.delete(previous_cover)
        item.title = title
        item.author = result.author or item.author
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        source = self.package.read_source(item.id)
        if source is None:
            raise ProcessingError(
                "storage.source_missing", "Content package is missing source.json"
            )
        self._sync_source(item, source)

    def _stage_organize(
        self, session: Session, item: Item, run_id: str, context: StageContext
    ) -> None:
        source_text = self._item_text(item)
        existing_tags = self._tag_vocabulary(session)
        result = self.organizer.organize(
            text=source_text,
            title=item.title,
            existing_tags=existing_tags,
            context=context,
        )
        generated_at = utc_ms()
        path = self.package.write_ai(item.id, ai_document(result, generated_at))
        self._record_document(session, item, kind=ArtifactKind.AI, path=path)
        item.summary = result.summary
        item.updated_at = utc_ms()
        from trove.db.models import AiResult

        session.add(
            AiResult(
                item_id=item.id,
                run_id=run_id,
                summary=result.summary,
                model=result.model,
                prompt_version=result.prompt_version,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                created_at=generated_at,
            )
        )
        self._replace_ai_tags(session, item.id, result.tags)

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

    def _book_title(self, result: BookResult, item: Item) -> str:
        for candidate in (result.title, item.title):
            title = meaningful_title(candidate)
            if title:
                return title
        for chapter in result.chapters:
            title = meaningful_title(chapter.title)
            if title:
                return title
        return "Untitled book"

    def _item_text(self, item: Item) -> str:
        transcript = self.package.read_transcript(item.id)
        if transcript is not None:
            body = "\n".join(segment.text for segment in transcript.segments)
            if body:
                return body
        book = self.package.read_book(item.id)
        if book is not None:
            body = "\n".join(
                paragraph
                for chapter in book.chapters
                for paragraph in chapter.paragraphs
            )
            if body:
                return body
        return ""

    def _tag_vocabulary(self, session: Session) -> list[str]:
        return [
            str(name)
            for name in session.execute(
                select(Tag.name)
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .group_by(Tag.id)
                .order_by(func.count(ItemTag.item_id).desc(), Tag.normalized_name)
                .limit(MAX_EXISTING_TAGS)
            ).scalars()
        ]

    def _replace_ai_tags(self, session: Session, item_id: str, tags: list[str]) -> None:
        from trove.domain.tags import normalize_tag

        attached = {
            row.tag_id: row
            for row in session.execute(select(ItemTag).where(ItemTag.item_id == item_id)).scalars()
        }
        existing_ai = {
            tag_id for tag_id, row in attached.items() if row.source == "ai"
        }
        keep: set[int] = set()
        for raw in tags:
            try:
                display, normalized = normalize_tag(raw)
            except TroveError:
                continue
            tag = session.execute(
                select(Tag).where(Tag.normalized_name == normalized)
            ).scalars().first()
            if tag is None:
                tag = Tag(name=display, normalized_name=normalized)
                session.add(tag)
                session.flush()
            if tag.id not in keep:
                if tag.id not in attached:
                    session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="ai"))
                keep.add(tag.id)
        for tag_id in existing_ai - keep:
            session.delete(attached[tag_id])

    # ------------------------------------------------------------------
    # Artifact helpers
    # ------------------------------------------------------------------
    def _install_artifact(
        self,
        session: Session,
        item: Item,
        *,
        kind: ArtifactKind,
        temp_path: Path,
        extension: str,
        mime: str | None,
        duration: float | None,
    ) -> Artifact:
        previous = self._artifact(session, item.id, kind)
        installed = self.package.install_artifact(
            item.id,
            kind,
            temp_path,
            extension=extension,
            mime=mime,
            replaces=previous.path if previous is not None else None,
        )
        return self._record_artifact(
            session,
            item,
            kind=installed.kind,
            relative=installed.relative_path,
            checksum=installed.sha256,
            size=installed.size,
            mime=installed.mime,
            duration=duration,
        )

    def _record_document(
        self, session: Session, item: Item, *, kind: ArtifactKind, path: Path
    ) -> Artifact:
        return self._record_artifact(
            session,
            item,
            kind=kind,
            relative=path.name,
            checksum=sha256_file(path),
            size=path.stat().st_size,
            mime="application/json",
            duration=None,
        )

    def _record_artifact(
        self,
        session: Session,
        item: Item,
        *,
        kind: ArtifactKind,
        relative: str,
        checksum: str,
        size: int,
        mime: str,
        duration: float | None,
    ) -> Artifact:
        artifact = self._artifact(session, item.id, kind)
        if artifact is None:
            artifact = Artifact(
                item_id=item.id,
                kind=kind,
                path=relative,
                sha256=checksum,
                size=size,
                mime=mime,
                duration_sec=duration,
            )
            session.add(artifact)
        else:
            artifact.path = relative
            artifact.sha256 = checksum
            artifact.size = size
            artifact.mime = mime
            artifact.duration_sec = duration
        session.flush()
        return artifact

    @staticmethod
    def _artifact(session: Session, item_id: str, kind: ArtifactKind) -> Artifact | None:
        return session.execute(
            select(Artifact).where(Artifact.item_id == item_id, Artifact.kind == kind)
        ).scalars().first()

    # ------------------------------------------------------------------
    # Run bookkeeping
    # ------------------------------------------------------------------
    def _next_pending_stage(self, session: Session, run: Run, item: Item) -> str | None:
        completed = set(
            session.execute(
                select(RunStep.stage).where(
                    RunStep.run_id == run.id, RunStep.state == "completed"
                )
            ).scalars()
        )
        for stage in stages_for(item.source_type):
            if stage not in completed:
                return stage
        return None

    def _stage_completed(self, run_id: str, stage: str) -> bool:
        with self.sessions() as session:
            return (
                session.execute(
                    select(RunStep.id).where(
                        RunStep.run_id == run_id,
                        RunStep.stage == stage,
                        RunStep.state == "completed",
                    )
                ).first()
                is not None
            )

    def _start_step(self, run_id: str, stage: str) -> RunStep:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            assert run is not None
            attempt = (
                session.execute(
                    select(RunStep.attempt)
                    .where(RunStep.run_id == run_id, RunStep.stage == stage)
                    .order_by(RunStep.attempt.desc())
                    .limit(1)
                ).scalars().first()
                or 0
            ) + 1
            step = RunStep(
                run_id=run_id,
                stage=stage,
                state="running",
                attempt=attempt,
                started_at=utc_ms(),
            )
            run.state = stage
            run.current_stage = stage
            run.heartbeat_at = utc_ms()
            session.add(step)
            session.commit()
            session.refresh(step)
            return step

    def _finish_step(self, run_id: str, stage: str) -> None:
        with self.sessions() as session:
            step = session.execute(
                select(RunStep)
                .where(RunStep.run_id == run_id, RunStep.stage == stage, RunStep.state == "running")
                .order_by(RunStep.attempt.desc())
                .limit(1)
            ).scalars().first()
            if step is not None:
                step.state = "completed"
                step.finished_at = utc_ms()
            run = session.get(Run, run_id)
            if run is not None:
                run.heartbeat_at = utc_ms()
            session.commit()

    def _fail(
        self,
        run_id: str,
        stage: str | None,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.sessions() as session:
            step = (
                session.execute(
                    select(RunStep)
                    .where(
                        RunStep.run_id == run_id,
                        RunStep.stage == stage,
                        RunStep.state == "running",
                    )
                    .order_by(RunStep.attempt.desc())
                    .limit(1)
                ).scalars().first()
                if stage is not None
                else None
            )
            if step is not None:
                step.state = "failed"
                step.error_code = code
                step.error_message = message
                step.finished_at = utc_ms()
            run = session.get(Run, run_id)
            if run is not None:
                run.state = RunState.FAILED
                run.error_code = code
                run.error_message = message
                run.current_stage = stage
                run.finished_at = utc_ms()
            session.commit()

    def _cancel(self, run_id: str, stage: str) -> None:
        with self.sessions() as session:
            step = session.execute(
                select(RunStep)
                .where(RunStep.run_id == run_id, RunStep.stage == stage, RunStep.state == "running")
                .order_by(RunStep.attempt.desc())
                .limit(1)
            ).scalars().first()
            if step is not None:
                step.state = "cancelled"
                step.error_code = "run.cancelled"
                step.error_message = "Cancelled"
                step.finished_at = utc_ms()
            run = session.get(Run, run_id)
            if run is not None:
                run.state = RunState.CANCELLED
                run.current_stage = stage
                run.finished_at = utc_ms()
            session.commit()

    def _complete(self, run_id: str) -> None:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.state = RunState.COMPLETED
                run.current_stage = None
                run.error_code = None
                run.error_message = None
                run.finished_at = utc_ms()
                run.heartbeat_at = utc_ms()
            session.commit()

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

    def _sync_source(self, item: Item, source: SourceDocument) -> None:
        self.package.write_source(
            item.id, source_document(item, base=source)
        )

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
