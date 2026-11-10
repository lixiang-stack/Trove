from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trove.content_package import (
    AiDocument,
    BookChapterDocument,
    BookCoverDocument,
    BookDocument,
    FeedSourceDocument,
    SourceDocument,
    TranscriptDocument,
    TranscriptSegment,
)
from trove.db.models import Item
from trove.domain.items import Platform, SourceType
from trove.ports import BookResult, OrganizationResult, TranscriptResult


def source_document(
    item: Item,
    *,
    base: SourceDocument | None = None,
    extra: Mapping[str, Any] | None = None,
) -> SourceDocument:
    values = dict(extra or {})
    feed = base.feed if base is not None else None
    if "feed" in values:
        feed_value = values.pop("feed")
        if feed_value is not None and not isinstance(feed_value, Mapping):
            raise ValueError("feed must be an object")
        feed = FeedSourceDocument.from_json(feed_value) if feed_value is not None else None
    uploaded = base.uploaded if base is not None else None
    if "uploaded" in values:
        uploaded_value = values.pop("uploaded")
        if not isinstance(uploaded_value, bool):
            raise ValueError("uploaded must be a boolean")
        uploaded = uploaded_value
    document_extra = dict(base.extra) if base is not None else {}
    document_extra.update(values)
    return SourceDocument(
        id=item.id,
        source_key=item.source_key,
        source_type=SourceType(item.source_type),
        platform=Platform(item.platform),
        title=item.title,
        source_url_raw=item.source_url_raw,
        source_url_canonical=item.source_url_canonical,
        source_path=item.source_path,
        author=item.author,
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        language=item.language,
        duration_sec=item.duration_sec,
        uploaded=uploaded,
        feed=feed,
        extra=document_extra,
    )


def transcript_document(result: TranscriptResult, item: Item) -> TranscriptDocument:
    return TranscriptDocument(
        language=result.language or item.language,
        model=result.model,
        segments=[
            TranscriptSegment(
                seq=segment.seq,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
            )
            for segment in result.segments
        ],
    )


def book_document(result: BookResult, *, title: str) -> BookDocument:
    return BookDocument(
        title=title,
        author=result.author,
        language=result.language,
        cover=(
            BookCoverDocument(
                extension=result.cover.extension, mime=result.cover.mime
            )
            if result.cover is not None
            else None
        ),
        chapters=[
            BookChapterDocument(
                chapter_index=chapter.chapter_index,
                title=chapter.title,
                html=chapter.html,
                text=chapter.text,
                paragraphs=list(chapter.paragraphs),
            )
            for chapter in result.chapters
        ]
    )


def ai_document(result: OrganizationResult, generated_at: int) -> AiDocument:
    return AiDocument(
        summary=result.summary,
        tags=list(result.tags),
        model=result.model,
        prompt_version=result.prompt_version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        generated_at=generated_at,
    )
