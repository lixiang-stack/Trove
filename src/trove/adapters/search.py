from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from trove.content_package import ContentPackage
from trove.db.models import Item
from trove.domain.search import build_match_query, norm_text, normalize_text
from trove.ports import SearchHit, SearchResult

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
        if transcript is None:
            segments = session.execute(
                text(
                    "SELECT seq, start_ms, text FROM transcript_segments "
                    "WHERE item_id = :item_id ORDER BY seq"
                ),
                {"item_id": item_id},
            )
            transcript = [
                (str(segment_text), "transcript", f"{seq}:{start_ms}")
                for seq, start_ms, segment_text in segments
            ]
        documents.extend(transcript)
        book = self._package_book(item_id)
        if book is None:
            paragraphs = session.execute(
                text(
                    "SELECT chapter_index, paragraph_index, text FROM book_paragraphs "
                    "WHERE item_id = :item_id ORDER BY chapter_index, paragraph_index"
                ),
                {"item_id": item_id},
            )
            book = [
                (str(paragraph_text), "book", f"{chapter_index}:{paragraph_index}")
                for chapter_index, paragraph_index, paragraph_text in paragraphs
            ]
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
        data = self._read_package_json(item_id, "transcript.json")
        if data is None:
            return None
        documents: list[tuple[str, str, str]] = []
        for segment in data.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text") or "").strip()
            seq = segment.get("seq")
            start_ms = segment.get("start_ms")
            if not text or not isinstance(seq, int) or not isinstance(start_ms, int):
                continue
            documents.append((text, "transcript", f"{seq}:{start_ms}"))
        return documents or None

    def _package_book(self, item_id: str) -> list[tuple[str, str, str]] | None:
        data = self._read_package_json(item_id, "book.json")
        if data is None:
            return None
        documents: list[tuple[str, str, str]] = []
        for chapter in data.get("chapters") or []:
            if not isinstance(chapter, dict):
                continue
            chapter_index = chapter.get("chapter_index")
            if not isinstance(chapter_index, int):
                continue
            for paragraph_index, paragraph in enumerate(chapter.get("paragraphs") or []):
                text = str(paragraph or "").strip()
                if text:
                    documents.append(
                        (text, "book", f"{chapter_index}:{paragraph_index}")
                    )
        return documents or None

    def _read_package_json(self, item_id: str, filename: str) -> dict[str, Any] | None:
        path = self.package.directory(item_id) / filename
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None


def _add_hit(hits: dict[tuple[str, str, str], SearchHit], hit: SearchHit) -> None:
    key = (hit.item_id, hit.doc_kind, hit.ref)
    existing = hits.get(key)
    if existing is None or hit.score > existing.score:
        hits[key] = hit


def _matches_all(value: str, terms: list[str]) -> bool:
    normalized = normalize_text(value)
    return all(term in normalized for term in terms)


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
