"""SQLite FTS5 search adapter.

FTS5 has no SQLAlchemy expression construct, so its raw SQL lives only in
this module. Services call the SearchIndex port and never see the schema.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from trove.content_package import ContentPackage
from trove.db.models import Item
from trove.domain.search import build_match_query, norm_text, normalize_text
from trove.errors import StorageError
from trove.ports import (
    IndexItemStatus,
    IndexStatus,
    SearchHit,
    SearchResult,
)

KIND_WEIGHT = {"title": 3.0, "summary": 2.0, "tag": 2.0, "transcript": 1.0, "book": 1.0}
LIKE_SCORE = 1.0
EVIDENCE_PER_ITEM = 3
FETCH_MULTIPLIER = 30


class FtsSearchIndex:
    def __init__(self, sessions: sessionmaker[Session], package: ContentPackage) -> None:
        self.sessions = sessions
        self.package = package

    def index_item(self, item_id: str) -> None:
        with self.sessions() as session:
            self._index_item(session, item_id)
            session.commit()

    def delete_item(self, item_id: str) -> None:
        with self.sessions() as session:
            session.execute(
                text("DELETE FROM search_fts WHERE item_id = :item_id"), {"item_id": item_id}
            )
            session.commit()

    def rebuild(self) -> int:
        with self.sessions() as session:
            item_ids = list(session.execute(text("SELECT id FROM items ORDER BY id")).scalars())
            session.execute(text("DELETE FROM search_fts"))
            session.commit()
        for item_id in item_ids:
            self.index_item(str(item_id))
        return len(item_ids)

    def status(self) -> IndexStatus:
        with self.sessions() as session:
            items = list(
                session.execute(
                    select(Item).order_by(Item.created_at.desc(), Item.id.desc())
                ).scalars()
            )
            item_ids = {item.id for item in items}
            counts: dict[str, dict[str, int]] = {}
            total_rows = 0
            orphan_rows = 0
            for item_id, doc_kind, count in session.execute(
                text(
                    "SELECT item_id, doc_kind, count(*) FROM search_fts "
                    "GROUP BY item_id, doc_kind"
                )
            ):
                total_rows += int(count)
                if item_id in item_ids:
                    counts.setdefault(str(item_id), {})[str(doc_kind)] = int(count)
                else:
                    orphan_rows += int(count)
            tag_counts = _counts_by_item(
                session, "SELECT item_id, count(*) FROM item_tags GROUP BY item_id"
            )
        statuses = []
        for item in items:
            transcript_expected, book_expected = self._content_counts(item.id)
            statuses.append(
                IndexItemStatus(
                    item_id=item.id,
                    title=item.title,
                    counts=counts.get(item.id, {}),
                    expected={
                        "title": 1,
                        "summary": 1 if item.summary else 0,
                        "tag": tag_counts.get(item.id, 0),
                        "transcript": transcript_expected,
                        "book": book_expected,
                    },
                )
            )
        return IndexStatus(items=statuses, total_rows=total_rows, orphan_rows=orphan_rows)

    def _content_counts(self, item_id: str) -> tuple[int, int]:
        try:
            transcript = self.package.read_transcript(item_id)
            book = self.package.read_book(item_id)
        except StorageError:
            return 0, 0
        return (
            len(transcript.segments) if transcript is not None else 0,
            sum(len(chapter.paragraphs) for chapter in book.chapters)
            if book is not None
            else 0,
        )

    def search(self, query: str, *, limit: int = 50) -> list[SearchResult]:
        match, like_terms = build_match_query(query)
        if match is None and not like_terms:
            return []
        fetch_limit = max(limit * FETCH_MULTIPLIER, 200)
        hits: dict[tuple[str, str, str], SearchHit] = {}
        with self.sessions() as session:
            if match:
                rows = session.execute(
                    text(
                        "SELECT item_id, doc_kind, ref, text, "
                        "(-bm25(search_fts, 1.0, 0.0, 0.0, 0.0, 0.0)) AS score "
                        "FROM search_fts WHERE search_fts MATCH :match "
                        "ORDER BY score DESC LIMIT :limit"
                    ),
                    {"match": match, "limit": fetch_limit},
                )
                for row in rows:
                    if like_terms and not _matches_all(str(row.text), like_terms):
                        continue
                    _add_hit(
                        hits,
                        SearchHit(
                            item_id=str(row.item_id),
                            score=float(row.score),
                            doc_kind=str(row.doc_kind),
                            ref=str(row.ref),
                            text=str(row.text),
                        ),
                    )
            for term in like_terms:
                clause = "text LIKE :term"
                params: dict[str, Any] = {"term": f"%{term}%", "limit": fetch_limit}
                if match:
                    clause = f"search_fts MATCH :match AND {clause}"
                    params["match"] = match
                rows = session.execute(
                    text(
                        "SELECT item_id, doc_kind, ref, text FROM search_fts "
                        f"WHERE {clause} LIMIT :limit"
                    ),
                    params,
                )
                for row in rows:
                    if not _matches_all(str(row.text), like_terms):
                        continue
                    _add_hit(
                        hits,
                        SearchHit(
                            item_id=str(row.item_id),
                            score=LIKE_SCORE,
                            doc_kind=str(row.doc_kind),
                            ref=str(row.ref),
                            text=str(row.text),
                        ),
                    )
        return _group_hits(list(hits.values()), limit)

    def _index_item(self, session: Session, item_id: str) -> None:
        item = session.get(Item, item_id)
        if item is None:
            return
        session.execute(
            text("DELETE FROM search_fts WHERE item_id = :item_id"), {"item_id": item_id}
        )
        documents: list[tuple[str, str, str]] = []
        documents.append((item.title, "title", "title"))
        if item.summary:
            documents.append((item.summary, "summary", "summary"))
        tags = session.execute(
            text(
                "SELECT tags.name FROM tags "
                "JOIN item_tags ON item_tags.tag_id = tags.id "
                "WHERE item_tags.item_id = :item_id"
            ),
            {"item_id": item_id},
        ).scalars()
        for name in tags:
            documents.append((str(name), "tag", str(name)))
        transcript = self._package_transcript(item_id)
        if transcript is not None:
            documents.extend(transcript)
        book = self._package_book(item_id)
        if book is not None:
            documents.extend(book)
        rows: list[dict[str, Any]] = []
        for value, ref_kind, ref in documents:
            tokens = norm_text(value)
            if not tokens:
                continue
            rows.append(
                {
                    "norm_text": tokens,
                    "text": value,
                    "item_id": item_id,
                    "doc_kind": ref_kind,
                    "ref": ref,
                }
            )
        if rows:
            session.execute(
                text(
                    "INSERT INTO search_fts (norm_text, text, item_id, doc_kind, ref) "
                    "VALUES (:norm_text, :text, :item_id, :doc_kind, :ref)"
                ),
                rows,
            )


    def _package_transcript(self, item_id: str) -> list[tuple[str, str, str]] | None:
        try:
            document = self.package.read_transcript(item_id)
        except StorageError:
            return None
        if document is None:
            return None
        documents: list[tuple[str, str, str]] = []
        for segment in document.segments:
            text = segment.text.strip()
            if not text:
                continue
            documents.append((text, "transcript", f"{segment.seq}:{segment.start_ms}"))
        return documents or None

    def _package_book(self, item_id: str) -> list[tuple[str, str, str]] | None:
        try:
            document = self.package.read_book(item_id)
        except StorageError:
            return None
        if document is None:
            return None
        documents: list[tuple[str, str, str]] = []
        for chapter in document.chapters:
            for paragraph_index, paragraph in enumerate(chapter.paragraphs):
                text = paragraph.strip()
                if text:
                    documents.append(
                        (text, "book", f"{chapter.chapter_index}:{paragraph_index}")
                    )
        return documents or None


def _add_hit(hits: dict[tuple[str, str, str], SearchHit], hit: SearchHit) -> None:
    key = (hit.item_id, hit.doc_kind, hit.ref)
    existing = hits.get(key)
    if existing is None or hit.score > existing.score:
        hits[key] = hit


def _matches_all(value: str, terms: list[str]) -> bool:
    normalized = normalize_text(value)
    return all(term in normalized for term in terms)


def _counts_by_item(session: Session, statement: str) -> dict[str, int]:
    return {
        str(item_id): int(count) for item_id, count in session.execute(text(statement))
    }


def _group_hits(hits: list[SearchHit], limit: int) -> list[SearchResult]:
    grouped: dict[str, list[SearchHit]] = defaultdict(list)
    for hit in hits:
        weighted = replace(hit, score=hit.score * KIND_WEIGHT.get(hit.doc_kind, 1.0))
        grouped[hit.item_id].append(weighted)
    results: list[SearchResult] = []
    for item_id, item_hits in grouped.items():
        item_hits.sort(key=lambda hit: (hit.score, hit.ref), reverse=True)
        unique: list[SearchHit] = []
        seen: set[tuple[str, str]] = set()
        for hit in item_hits:
            key = (hit.doc_kind, hit.ref)
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)
            if len(unique) == EVIDENCE_PER_ITEM:
                break
        results.append(SearchResult(item_id=item_id, score=unique[0].score, evidence=unique))
    results.sort(key=lambda result: (-result.score, result.item_id))
    return results[:limit]
