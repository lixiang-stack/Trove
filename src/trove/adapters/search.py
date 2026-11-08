from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from trove.db.models import Item
from trove.domain.search import build_match_query, norm_text
from trove.ports import SearchHit


class FtsSearchIndex:
    def index_item(self, session: Session, item_id: str) -> None:
        item = session.get(Item, item_id)
        if item is None:
            return
        self.delete_item(session, item_id)
        documents: list[tuple[str, str, str, str]] = []
        documents.append(("title", item.title, "title", "title"))
        if item.summary:
            documents.append(("summary", item.summary, "summary", "summary"))
        tags = session.execute(
            text(
                "SELECT tags.name FROM tags "
                "JOIN item_tags ON item_tags.tag_id = tags.id "
                "WHERE item_tags.item_id = :item_id"
            ),
            {"item_id": item_id},
        ).scalars()
        for name in tags:
            documents.append(("tag", str(name), "tag", str(name)))
        segments = session.execute(
            text(
                "SELECT seq, start_ms, text FROM transcript_segments "
                "WHERE item_id = :item_id ORDER BY seq"
            ),
            {"item_id": item_id},
        )
        for seq, start_ms, segment_text in segments:
            documents.append(("transcript", str(segment_text), "transcript", f"{seq}:{start_ms}"))
        paragraphs = session.execute(
            text(
                "SELECT chapter_index, paragraph_index, text FROM book_paragraphs "
                "WHERE item_id = :item_id ORDER BY chapter_index, paragraph_index"
            ),
            {"item_id": item_id},
        )
        for chapter_index, paragraph_index, paragraph_text in paragraphs:
            documents.append(
                (
                    "book",
                    str(paragraph_text),
                    "book",
                    f"{chapter_index}:{paragraph_index}",
                )
            )
        rows: list[dict[str, Any]] = []
        for _doc_kind, value, ref_kind, ref in documents:
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

    def delete_item(self, session: Session, item_id: str) -> None:
        session.execute(
            text("DELETE FROM search_fts WHERE item_id = :item_id"), {"item_id": item_id}
        )

    def search(self, session: Session, query: str, *, limit: int = 50) -> list[SearchHit]:
        match, like_terms = build_match_query(query)
        hits: list[SearchHit] = []
        if match:
            rows = session.execute(
                text(
                    "SELECT item_id, doc_kind, ref, text, "
                    "bm25(search_fts, 1.0, 0.0, 0.0, 0.0, 0.0) AS score "
                    "FROM search_fts WHERE search_fts MATCH :match LIMIT :limit"
                ),
                {"match": match, "limit": limit * 20},
            )
            for row in rows:
                hits.append(
                    SearchHit(
                        item_id=str(row.item_id),
                        score=float(row.score),
                        doc_kind=str(row.doc_kind),
                        ref=str(row.ref),
                        text=str(row.text),
                    )
                )
        for term in like_terms:
            rows = session.execute(
                text(
                    "SELECT item_id, doc_kind, ref, text FROM search_fts "
                    "WHERE text LIKE :term LIMIT :limit"
                ),
                {"term": f"%{term}%", "limit": limit * 20},
            )
            for row in rows:
                hits.append(
                    SearchHit(
                        item_id=str(row.item_id),
                        score=0.0,
                        doc_kind=str(row.doc_kind),
                        ref=str(row.ref),
                        text=str(row.text),
                    )
                )
        return _group_hits(hits, limit)


KIND_WEIGHT = {"title": 3.0, "summary": 2.0, "tag": 2.0, "transcript": 1.0, "book": 1.0}


def _group_hits(hits: list[SearchHit], limit: int) -> list[SearchHit]:
    grouped: dict[str, list[SearchHit]] = defaultdict(list)
    for hit in hits:
        weighted = replace(hit, score=hit.score / KIND_WEIGHT.get(hit.doc_kind, 1.0))
        grouped[hit.item_id].append(weighted)
    best: list[SearchHit] = []
    for item_hits in grouped.values():
        item_hits.sort(key=lambda hit: (hit.score, -KIND_WEIGHT.get(hit.doc_kind, 1.0)))
        chosen = item_hits[0]
        evidence = item_hits[:3]
        best.append(replace(chosen, text=evidence[0].text))
    best.sort(key=lambda hit: (hit.score, hit.item_id))
    return best[:limit]
