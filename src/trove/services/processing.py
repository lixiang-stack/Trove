from __future__ import annotations

import json
import shutil
import traceback
import uuid
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage, guess_mime
from trove.db.models import (
    Artifact,
    BookChapter,
    BookParagraph,
    Item,
    ItemTag,
    Run,
    RunStep,
    Tag,
    TranscriptSegment,
)
from trove.domain.items import (
    ACTIVE_RUN_STATES,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
    RunState,
    stages_for,
)
from trove.errors import ConflictError, ProcessingCancelled, ProcessingError, TroveError
from trove.logging_setup import append_run_log
from trove.ports import (
    AudioExtractor,
    BookExtractor,
    Downloader,
    Organizer,
    SearchIndex,
    StageContext,
    Transcriber,
)
from trove.services.library import LibraryService


class ProcessingService:
    def __init__(
        self,
        config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        library: LibraryService,
        *,
        downloader: Downloader,
        audio_extractor: AudioExtractor,
        transcriber: Transcriber,
        organizer: Organizer,
        book_extractor: BookExtractor,
        search_index: SearchIndex,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.library = library
        self.downloader = downloader
        self.audio_extractor = audio_extractor
        self.transcriber = transcriber
        self.organizer = organizer
        self.book_extractor = book_extractor
        self.search_index = search_index

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
                    text(
                        "UPDATE runs SET state = :state, current_stage = :stage, "
                        "heartbeat_at = :now, started_at = COALESCE(started_at, :now) "
                        "WHERE id = :run_id AND state = 'queued'"
                    ),
                    {"state": stage, "stage": stage, "now": now, "run_id": candidate.id},
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
                run.error_message = "内容不存在"
                run.finished_at = utc_ms()
                session.commit()
                return
            stages = stages_for(item.source_type)
            source = self.package.read_source(item.id)

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
                return
            step = self._start_step(run_id, stage)
            append_run_log(self.config, run_id, f"stage {stage} started (attempt {step.attempt})")
            try:
                with self.sessions() as session:
                    item = session.get(Item, context.item_id)
                    assert item is not None
                    source = self.package.read_source(item.id)
                    self._execute_stage(stage, session, item, run_id, source, context)
                    session.commit()
            except ProcessingCancelled:
                self._cancel(run_id, stage)
                self._cleanup_work_dir(work_dir, keep_download=True)
                append_run_log(self.config, run_id, f"stage {stage} cancelled", level="warning")
                return
            except ProcessingError as exc:
                self._fail(run_id, stage, exc.code, exc.message, exc.details)
                self._cleanup_work_dir(work_dir, keep_download=stage != "downloading")
                append_run_log(
                    self.config, run_id, f"stage {stage} failed: {exc.code}", level="error"
                )
                return
            except Exception as exc:  # noqa: BLE001 - boundary for a durable worker
                append_run_log(
                    self.config,
                    run_id,
                    f"stage {stage} crashed: {traceback.format_exc()}",
                    level="error",
                )
                self._fail(run_id, stage, "internal.error", "内部错误", {"error": str(exc)})
                self._cleanup_work_dir(work_dir, keep_download=stage != "downloading")
                return
            self._finish_step(run_id, stage)
            append_run_log(self.config, run_id, f"stage {stage} completed")
            if stage in {"downloading", STAGE_EXTRACTING_AUDIO, STAGE_TRANSCRIBING}:
                self._cleanup_stage_leftovers(work_dir)

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
                raise TroveError("内容不存在")
            run = self._latest_run(session, item_id)
            if run is None:
                raise ConflictError("没有可重试的 Processing Run")
            if run.state in ACTIVE_RUN_STATES:
                return run
            if run.state not in {RunState.FAILED, RunState.CANCELLED}:
                raise ConflictError("当前 Processing Run 不需要重试")
            run.state = RunState.QUEUED
            run.current_stage = None
            run.error_code = None
            run.error_message = None
            run.cancel_requested_at = None
            run.finished_at = None
            session.commit()
            append_run_log(self.config, run.id, "run queued for retry")
            return run

    def cancel(self, run_id: str) -> Run:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise TroveError("Processing Run 不存在")
            if run.state in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}:
                return run
            if run.state == RunState.QUEUED:
                run.state = RunState.CANCELLED
                run.finished_at = utc_ms()
            else:
                run.cancel_requested_at = utc_ms()
            session.commit()
            append_run_log(self.config, run.id, "cancel requested", level="warning")
            return run

    def cancel_item(self, item_id: str) -> Run:
        with self.sessions() as session:
            run = self._latest_run(session, item_id)
            if run is None:
                raise TroveError("没有可取消的 Processing Run")
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
                    step.error_message = "Host 重启，阶段重新排队"
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

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------
    def _execute_stage(
        self,
        stage: str,
        session: Session,
        item: Item,
        run_id: str,
        source: dict[str, Any],
        context: StageContext,
    ) -> None:
        if stage == "downloading":
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
            self.search_index.index_item(session, item.id)
        else:
            raise ProcessingError("internal.error", f"未知阶段: {stage}")

    def _stage_download(
        self, session: Session, item: Item, source: dict[str, Any], context: StageContext
    ) -> None:
        result = self.downloader.download(source, context)
        item.title = result.title or item.title
        item.author = result.author or item.author
        item.published_at = result.published_at or item.published_at
        item.duration_sec = result.duration_sec or item.duration_sec
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        self._sync_source(session, item, source)

    def _stage_extract_audio(
        self, session: Session, item: Item, source: dict[str, Any], context: StageContext
    ) -> None:
        if item.source_type in {"video_url", "podcast_episode"}:
            media_path = _downloaded_media(context.work_dir)
            if media_path is None:
                raise ProcessingError("download.parse", "找不到已下载的媒体文件")
            force_transcode = True
        else:
            if not item.source_path:
                raise ProcessingError("storage.source_missing", "缺少本地源文件路径")
            media_path = Path(item.source_path)
            if not media_path.is_file():
                raise ProcessingError("storage.source_missing", "原始文件不存在或不可读")
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
            kind="audio",
            temp_path=result.path,
            filename=f"audio{result.extension}",
            mime=result.mime,
            duration=result.duration_sec,
        )
        item.duration_sec = result.duration_sec or item.duration_sec
        item.updated_at = utc_ms()
        self._sync_source(session, item, source)
        if item.source_type in {"video_url", "podcast_episode"}:
            media_path.unlink(missing_ok=True)
        if source.get("uploaded") and item.source_path:
            upload_path = Path(item.source_path)
            if upload_path.is_relative_to(self.config.uploads_dir):
                upload_directory = upload_path.parent
                upload_path.unlink(missing_ok=True)
                shutil.rmtree(upload_directory, ignore_errors=True)
        context.log(f"audio artifact {artifact.path} ({artifact.size} bytes)")

    def _stage_transcribe(
        self, session: Session, item: Item, context: StageContext
    ) -> None:
        audio = self._artifact(session, item.id, "audio")
        if audio is None:
            raise ProcessingError("asr.failed", "缺少音频，无法转写")
        audio_path = self.package.artifact_path(item.id, audio.path)
        result = self.transcriber.transcribe(audio_path, context)
        payload = {
            "language": result.language or item.language,
            "segments": [
                {
                    "seq": segment.seq,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text,
                }
                for segment in result.segments
            ],
        }
        temp = context.work_dir / "transcript.json"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._install_artifact(
            session,
            item,
            kind="transcript",
            temp_path=temp,
            filename="transcript.json",
            mime="application/json",
            duration=None,
        )
        session.execute(
            text("DELETE FROM transcript_segments WHERE item_id = :item_id"),
            {"item_id": item.id},
        )
        session.add_all(
            [
                TranscriptSegment(
                    item_id=item.id,
                    seq=segment.seq,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                )
                for segment in result.segments
            ]
        )
        if result.language:
            item.language = result.language
        item.updated_at = utc_ms()

    def _stage_extract_text(
        self, session: Session, item: Item, context: StageContext
    ) -> None:
        book = self._artifact(session, item.id, "book")
        if book is None:
            raise ProcessingError("epub.invalid", "缺少 EPUB 文件")
        book_path = self.package.artifact_path(item.id, book.path)
        result = self.book_extractor.extract(book_path, context)
        payload = {
            "title": result.title,
            "author": result.author,
            "language": result.language,
            "chapters": [
                {
                    "chapter_index": chapter.chapter_index,
                    "title": chapter.title,
                    "html": chapter.html,
                    "text": chapter.text,
                    "paragraphs": chapter.paragraphs,
                }
                for chapter in result.chapters
            ],
        }
        temp = context.work_dir / "book.json"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._install_artifact(
            session,
            item,
            kind="book_json",
            temp_path=temp,
            filename="book.json",
            mime="application/json",
            duration=None,
        )
        session.execute(
            text("DELETE FROM book_chapters WHERE item_id = :item_id"), {"item_id": item.id}
        )
        session.execute(
            text("DELETE FROM book_paragraphs WHERE item_id = :item_id"), {"item_id": item.id}
        )
        for chapter in result.chapters:
            session.add(
                BookChapter(
                    item_id=item.id,
                    chapter_index=chapter.chapter_index,
                    title=chapter.title,
                    html=chapter.html,
                    text=chapter.text,
                )
            )
            session.add_all(
                [
                    BookParagraph(
                        item_id=item.id,
                        chapter_index=chapter.chapter_index,
                        paragraph_index=index,
                        text=paragraph,
                    )
                    for index, paragraph in enumerate(chapter.paragraphs)
                ]
            )
        item.title = result.title or item.title
        item.author = result.author or item.author
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        source = self.package.read_source(item.id)
        self._sync_source(session, item, source)

    def _stage_organize(
        self, session: Session, item: Item, run_id: str, context: StageContext
    ) -> None:
        source_text = self._item_text(session, item)
        existing_tags = list(
            session.execute(
                text(
                    "SELECT tags.name FROM tags JOIN item_tags ON item_tags.tag_id = tags.id "
                    "WHERE item_tags.item_id = :item_id"
                ),
                {"item_id": item.id},
            ).scalars()
        )
        result = self.organizer.organize(
            text=source_text,
            title=item.title,
            existing_tags=[str(tag) for tag in existing_tags],
            context=context,
        )
        payload = {
            "summary": result.summary,
            "tags": result.tags,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }
        temp = context.work_dir / "ai.json"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._install_artifact(
            session,
            item,
            kind="ai",
            temp_path=temp,
            filename="ai.json",
            mime="application/json",
            duration=None,
        )
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
                created_at=utc_ms(),
            )
        )
        self._replace_ai_tags(session, item.id, result.tags)

    def _item_text(self, session: Session, item: Item) -> str:
        rows = session.execute(
            text("SELECT text FROM transcript_segments WHERE item_id = :item_id ORDER BY seq"),
            {"item_id": item.id},
        ).scalars()
        body = "\n".join(str(row) for row in rows)
        if body:
            return body
        rows = session.execute(
            text(
                "SELECT text FROM book_paragraphs WHERE item_id = :item_id "
                "ORDER BY chapter_index, paragraph_index"
            ),
            {"item_id": item.id},
        ).scalars()
        return "\n".join(str(row) for row in rows)

    def _replace_ai_tags(self, session: Session, item_id: str, tags: list[str]) -> None:
        from trove.domain.tags import normalize_tag

        existing = {
            row.tag_id
            for row in session.execute(
                select(ItemTag).where(ItemTag.item_id == item_id, ItemTag.source == "ai")
            ).scalars()
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
                if tag.id not in existing:
                    session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="ai"))
                keep.add(tag.id)
        for tag_id in existing - keep:
            row = session.get(ItemTag, (item_id, tag_id))
            if row is not None and row.source == "ai":
                session.delete(row)

    # ------------------------------------------------------------------
    # Artifact helpers
    # ------------------------------------------------------------------
    def _install_artifact(
        self,
        session: Session,
        item: Item,
        *,
        kind: str,
        temp_path: Path,
        filename: str,
        mime: str | None,
        duration: float | None,
    ) -> Artifact:
        previous = self._artifact(session, item.id, kind)
        destination, checksum, size = self.package.install_temp(item.id, temp_path, filename)
        relative = destination.relative_to(self.package.directory(item.id)).as_posix()
        if previous is None:
            artifact = Artifact(
                item_id=item.id,
                kind=kind,
                path=relative,
                sha256=checksum,
                size=size,
                mime=mime or guess_mime(filename),
                duration_sec=duration,
            )
            session.add(artifact)
        else:
            old_path = previous.path
            artifact = previous
            artifact.path = relative
            artifact.sha256 = checksum
            artifact.size = size
            artifact.mime = mime or guess_mime(filename)
            artifact.duration_sec = duration
            if old_path != relative:
                (self.package.directory(item.id) / old_path).unlink(missing_ok=True)
        session.flush()
        return artifact

    @staticmethod
    def _artifact(session: Session, item_id: str, kind: str) -> Artifact | None:
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
        stage: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.sessions() as session:
            step = session.execute(
                select(RunStep)
                .where(RunStep.run_id == run_id, RunStep.stage == stage, RunStep.state == "running")
                .order_by(RunStep.attempt.desc())
                .limit(1)
            ).scalars().first()
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
                step.error_message = "已取消"
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

    def _sync_source(self, session: Session, item: Item, source: dict[str, Any]) -> None:
        source.update(
            {
                "title": item.title,
                "author": item.author,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at,
                "language": item.language,
                "duration_sec": item.duration_sec,
                "source_path": item.source_path,
                "source_url_raw": item.source_url_raw,
                "source_url_canonical": item.source_url_canonical,
            }
        )
        self.package.write_source(item.id, source)

    @staticmethod
    def _cleanup_work_dir(work_dir: Path, *, keep_download: bool) -> None:
        if not work_dir.exists():
            return
        for path in work_dir.iterdir():
            if keep_download and path.name.startswith("download.") and not path.name.endswith(
                (".tmp", ".part")
            ):
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


def _downloaded_media(work_dir: Path) -> Path | None:
    candidates = [
        path
        for path in work_dir.iterdir()
        if path.is_file()
        and path.name.startswith("download.")
        and not path.name.endswith((".tmp", ".part"))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)
