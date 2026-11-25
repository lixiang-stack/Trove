from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.config import Config
from trove.content_package import (
    ArtifactKind,
    ContentPackage,
    SourceDocument,
)
from trove.db.engine import create_engine_for
from trove.db.models import AiResult, Artifact, Base, Item, ItemTag, Run, Tag
from trove.domain.items import Platform, SourceType
from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import (
    AudioResult,
    BookChapterData,
    BookCoverData,
    BookResult,
    DownloadResult,
    OrganizationResult,
    StageContext,
    TranscriptResult,
    TranscriptSegmentData,
)
from trove.services.artifacts import ArtifactStore
from trove.services.stages.audio import AudioStage
from trove.services.stages.download import DownloadStage
from trove.services.stages.extract_text import ExtractTextStage
from trove.services.stages.index import IndexStage
from trove.services.stages.organize import OrganizeStage
from trove.services.stages.transcribe import TranscribeStage


@dataclass
class StageEnv:
    sessions: sessionmaker[Session]
    package: ContentPackage
    tmp_path: Path


def _env(tmp_path: Path) -> StageEnv:
    config = Config(home=tmp_path / "home")
    config.ensure_layout()
    engine: Engine = create_engine_for(config)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return StageEnv(sessions=sessions, package=ContentPackage(config), tmp_path=tmp_path)


@pytest.fixture
def env(tmp_path) -> StageEnv:
    return _env(tmp_path)


def _add_item(
    env: StageEnv,
    *,
    source_type: SourceType = SourceType.LOCAL_AUDIO,
    title: str = "Staged Item",
    source_path: str | None = None,
) -> tuple[str, str]:
    item_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = utc_ms()
    with env.sessions() as session:
        session.add(
            Item(
                id=item_id,
                source_key=f"stage-{item_id}",
                source_type=str(source_type),
                platform=str(Platform.LOCAL),
                title=title,
                source_path=source_path,
                fetched_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(Run(id=run_id, item_id=item_id, state="queued", created_at=now))
        session.commit()
    return item_id, run_id


def _source(item: Item) -> SourceDocument:
    return SourceDocument(
        id=item.id,
        source_key=item.source_key,
        source_type=SourceType(item.source_type),
        platform=Platform(item.platform),
        title=item.title,
        source_path=item.source_path,
    )


def _context(env: StageEnv, item: Item, run_id: str, *, cancel: bool = False) -> StageContext:
    work_dir = env.tmp_path / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return StageContext(
        item_id=item.id,
        run_id=run_id,
        work_dir=work_dir,
        should_cancel=lambda: cancel,
        log=lambda message: None,
    )


def _execute(
    env: StageEnv,
    stage,
    item_id: str,
    run_id: str,
    *,
    cancel: bool = False,
) -> None:
    with env.sessions() as session:
        item = session.get(Item, item_id)
        assert item is not None
        source = _source(item)
        env.package.write_source(item.id, source)
        stage.execute(session, item, source, _context(env, item, run_id, cancel=cancel))
        session.commit()


def _install_audio(env: StageEnv, item_id: str) -> None:
    with env.sessions() as session:
        item = session.get(Item, item_id)
        assert item is not None
        temp = env.tmp_path / "audio.tmp"
        temp.write_bytes(b"fake audio")
        ArtifactStore(env.package).install(
            session,
            item,
            kind=ArtifactKind.AUDIO,
            temp_path=temp,
            extension=".m4a",
            mime="audio/mp4",
            duration=2.0,
        )
        session.commit()


def _install_book(env: StageEnv, item_id: str) -> None:
    with env.sessions() as session:
        item = session.get(Item, item_id)
        assert item is not None
        temp = env.tmp_path / "book.tmp"
        temp.write_bytes(b"fake epub")
        ArtifactStore(env.package).install(
            session,
            item,
            kind=ArtifactKind.BOOK,
            temp_path=temp,
            extension=None,
            mime="application/epub+zip",
            duration=None,
        )
        session.commit()


def _item(env: StageEnv, item_id: str) -> Item:
    with env.sessions() as session:
        item = session.get(Item, item_id)
        assert item is not None
        return item


class StubDownloader:
    def __init__(
        self, *, filename: str = "download.media", fail_code: str | None = None
    ) -> None:
        self.filename = filename
        self.fail_code = fail_code

    def download(self, source: SourceDocument, context: StageContext) -> DownloadResult:
        context.check_cancelled()
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake download failure")
        path = context.work_dir / self.filename
        path.write_bytes(b"downloaded")
        return DownloadResult(
            path=path,
            title="Downloaded Title",
            author="Downloaded Author",
            published_at="2026-11-01T00:00:00+00:00",
            duration_sec=2.0,
            language="en",
        )


class StubAudioExtractor:
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.fail_code = fail_code

    def probe(self, source: Path, *, kind: str) -> None:
        return None

    def extract(
        self,
        source: Path,
        destination: Path,
        *,
        force_transcode: bool,
        context: StageContext,
    ) -> AudioResult:
        context.check_cancelled()
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake audio failure")
        path = destination / "audio.m4a"
        path.write_bytes(b"extracted audio")
        return AudioResult(path=path, duration_sec=2.0, mime="audio/mp4", extension=".m4a")


class StubUploads:
    def discard_for_path(self, path: str | Path | None) -> bool:
        return False


class StubTranscriber:
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.fail_code = fail_code

    def transcribe(self, audio_path: Path, context: StageContext) -> TranscriptResult:
        context.check_cancelled()
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake transcription failure")
        return TranscriptResult(
            segments=[
                TranscriptSegmentData(seq=1, start_ms=0, end_ms=1000, text="记忆"),
                TranscriptSegmentData(seq=2, start_ms=1000, end_ms=2000, text="智能体"),
            ],
            language="zh",
            model="fake-model",
        )


class StubBookExtractor:
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.fail_code = fail_code

    def validate(self, book_path: Path) -> None:
        return None

    def extract(self, book_path: Path, context: StageContext) -> BookResult:
        context.check_cancelled()
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake book failure")
        return BookResult(
            title="Fixture Book",
            author="Fixture Author",
            language="en",
            chapters=[
                BookChapterData(
                    chapter_index=1,
                    title="Chapter One",
                    html="<p>Hello</p>",
                    text="Hello",
                    paragraphs=["Hello"],
                )
            ],
            cover=BookCoverData(data=b"cover", extension=".jpg", mime="image/jpeg"),
        )


class StubOrganizer:
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.fail_code = fail_code

    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
        collection_title: str | None = None,
        collection_index: int | None = None,
        reuse_existing_tags: bool = False,
    ) -> OrganizationResult:
        context.check_cancelled()
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake organization failure")
        return OrganizationResult(
            summary="A summary",
            tags=["memory", "agents"],
            model="fake-model",
            prompt_version="test-1",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.001,
        )


class StubSearchIndex:
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_code = fail_code

    def index_item(self, item_id: str) -> None:
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake index failure")
        self.calls.append(item_id)

    def delete_item(self, item_id: str) -> None:
        raise NotImplementedError

    def search(self, query: str, *, limit: int = 50):
        raise NotImplementedError

    def rebuild(self) -> int:
        raise NotImplementedError

    def status(self):
        raise NotImplementedError


def test_all_stages_can_be_instantiated_with_fake_ports(env: StageEnv) -> None:
    artifacts = ArtifactStore(env.package)
    stages = [
        DownloadStage(env.package, artifacts, StubDownloader(), StubBookExtractor()),
        AudioStage(env.package, artifacts, StubAudioExtractor(), StubUploads()),
        TranscribeStage(env.package, artifacts, StubTranscriber()),
        ExtractTextStage(env.package, artifacts, StubBookExtractor()),
        OrganizeStage(env.package, artifacts, StubOrganizer()),
        IndexStage(StubSearchIndex()),
    ]
    assert len(stages) == 6


def test_download_stage_updates_item_and_source(env: StageEnv) -> None:
    item_id, run_id = _add_item(env, source_type=SourceType.VIDEO_URL, title="Original")
    stage = DownloadStage(
        env.package, ArtifactStore(env.package), StubDownloader(), StubBookExtractor()
    )
    _execute(env, stage, item_id, run_id)

    item = _item(env, item_id)
    assert item.title == "Downloaded Title"
    assert item.author == "Downloaded Author"
    assert item.duration_sec == 2.0
    assert item.language == "en"
    source = env.package.read_source(item_id)
    assert source is not None
    assert source.title == "Downloaded Title"


def test_download_stage_installs_epub_artifact(env: StageEnv) -> None:
    item_id, run_id = _add_item(env, source_type=SourceType.EPUB_URL, title="Book")
    stage = DownloadStage(
        env.package,
        ArtifactStore(env.package),
        StubDownloader(filename="source.epub"),
        StubBookExtractor(),
    )
    _execute(env, stage, item_id, run_id)

    with env.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(
                Artifact.item_id == item_id, Artifact.kind == ArtifactKind.BOOK
            )
        ).scalars().one()
        assert artifact.path == "book.epub"
        assert env.package.artifact_path(item_id, artifact.path).is_file()


def test_audio_stage_installs_audio_artifact(env: StageEnv) -> None:
    source_path = env.tmp_path / "source.wav"
    source_path.write_bytes(b"wav")
    item_id, run_id = _add_item(env, source_path=str(source_path))
    stage = AudioStage(
        env.package, ArtifactStore(env.package), StubAudioExtractor(), StubUploads()
    )
    _execute(env, stage, item_id, run_id)

    item = _item(env, item_id)
    assert item.duration_sec == 2.0
    with env.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(
                Artifact.item_id == item_id, Artifact.kind == ArtifactKind.AUDIO
            )
        ).scalars().one()
        assert artifact.path == "audio.m4a"
        assert artifact.duration_sec == 2.0
    assert (env.tmp_path / "home" / "library" / item_id / "audio.m4a").is_file()


def test_transcribe_stage_writes_transcript(env: StageEnv) -> None:
    item_id, run_id = _add_item(env)
    _install_audio(env, item_id)
    stage = TranscribeStage(env.package, ArtifactStore(env.package), StubTranscriber())
    _execute(env, stage, item_id, run_id)

    item = _item(env, item_id)
    assert item.language == "zh"
    transcript = env.package.read_transcript(item_id)
    assert transcript is not None
    assert [segment.text for segment in transcript.segments] == ["记忆", "智能体"]
    with env.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(
                Artifact.item_id == item_id, Artifact.kind == ArtifactKind.TRANSCRIPT
            )
        ).scalars().one()
        assert artifact.path == "transcript.json"


def test_extract_text_stage_writes_book_json_and_cover(env: StageEnv) -> None:
    item_id, run_id = _add_item(env, source_type=SourceType.EPUB, title="Original")
    _install_book(env, item_id)
    stage = ExtractTextStage(env.package, ArtifactStore(env.package), StubBookExtractor())
    _execute(env, stage, item_id, run_id)

    item = _item(env, item_id)
    assert item.title == "Fixture Book"
    assert item.author == "Fixture Author"
    book = env.package.read_book(item_id)
    assert book is not None
    assert book.title == "Fixture Book"
    assert book.chapters[0].paragraphs == ["Hello"]
    with env.sessions() as session:
        kinds = set(
            session.execute(
                select(Artifact.kind).where(Artifact.item_id == item_id)
            ).scalars()
        )
        assert kinds == {ArtifactKind.BOOK, ArtifactKind.BOOK_JSON, ArtifactKind.COVER}


def test_organize_stage_writes_ai_result_and_tags(env: StageEnv) -> None:
    item_id, run_id = _add_item(env)
    stage = OrganizeStage(env.package, ArtifactStore(env.package), StubOrganizer())
    _execute(env, stage, item_id, run_id)

    item = _item(env, item_id)
    assert item.summary == "A summary"
    ai = env.package.read_ai(item_id)
    assert ai is not None
    assert ai.summary == "A summary"
    assert ai.tags == ["memory", "agents"]
    with env.sessions() as session:
        result = session.execute(
            select(AiResult).where(AiResult.item_id == item_id)
        ).scalars().one()
        assert result.run_id == run_id
        assert result.model == "fake-model"
        tags = set(
            session.execute(
                select(Tag.normalized_name)
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .where(ItemTag.item_id == item_id)
            ).scalars()
        )
        assert tags == {"memory", "agent"}


def test_index_stage_refreshes_search_index(env: StageEnv) -> None:
    item_id, run_id = _add_item(env)
    index = StubSearchIndex()
    _execute(env, IndexStage(index), item_id, run_id)
    assert index.calls == [item_id]


@pytest.mark.parametrize(
    "stage_name", ["download", "audio", "transcribe", "extract_text", "organize"]
)
def test_stage_errors_propagate(env: StageEnv, stage_name: str) -> None:
    item_id, run_id = _add_item(env)
    artifacts = ArtifactStore(env.package)
    if stage_name == "download":
        stage = DownloadStage(
            env.package,
            artifacts,
            StubDownloader(fail_code="download.network"),
            StubBookExtractor(),
        )
    elif stage_name == "audio":
        source_path = env.tmp_path / "source.wav"
        source_path.write_bytes(b"wav")
        item_id, run_id = _add_item(env, source_path=str(source_path))
        stage = AudioStage(
            env.package, artifacts, StubAudioExtractor(fail_code="ffmpeg.failed"), StubUploads()
        )
    elif stage_name == "transcribe":
        _install_audio(env, item_id)
        stage = TranscribeStage(
            env.package, artifacts, StubTranscriber(fail_code="asr.failed")
        )
    elif stage_name == "extract_text":
        _install_book(env, item_id)
        stage = ExtractTextStage(
            env.package, artifacts, StubBookExtractor(fail_code="epub.invalid")
        )
    else:
        stage = OrganizeStage(
            env.package, artifacts, StubOrganizer(fail_code="llm.not_configured")
        )

    with pytest.raises(ProcessingError):
        _execute(env, stage, item_id, run_id)


def test_index_error_propagates(env: StageEnv) -> None:
    item_id, run_id = _add_item(env)
    with pytest.raises(ProcessingError):
        _execute(
            env,
            IndexStage(StubSearchIndex(fail_code="search.unavailable")),
            item_id,
            run_id,
        )


@pytest.mark.parametrize(
    "stage_name", ["download", "audio", "transcribe", "extract_text", "organize"]
)
def test_stage_cancellation_propagates(env: StageEnv, stage_name: str) -> None:
    item_id, run_id = _add_item(env)
    artifacts = ArtifactStore(env.package)
    if stage_name == "download":
        stage = DownloadStage(env.package, artifacts, StubDownloader(), StubBookExtractor())
    elif stage_name == "audio":
        source_path = env.tmp_path / "source.wav"
        source_path.write_bytes(b"wav")
        item_id, run_id = _add_item(env, source_path=str(source_path))
        stage = AudioStage(env.package, artifacts, StubAudioExtractor(), StubUploads())
    elif stage_name == "transcribe":
        _install_audio(env, item_id)
        stage = TranscribeStage(env.package, artifacts, StubTranscriber())
    elif stage_name == "extract_text":
        _install_book(env, item_id)
        stage = ExtractTextStage(env.package, artifacts, StubBookExtractor())
    else:
        stage = OrganizeStage(env.package, artifacts, StubOrganizer())

    with pytest.raises(ProcessingCancelled):
        _execute(env, stage, item_id, run_id, cancel=True)
