from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from trove.db.models import Item
from trove.domain.search import snippet
from trove.ports import SearchIndex
from trove.services.library import ItemBundle, LibraryService, item_bundle

FILTER_FETCH_MULTIPLIER = 10
MIN_FILTER_FETCH = 200
INDEX_KINDS = ("title", "summary", "tag", "transcript", "book")


@dataclass(slots=True)
class SearchEvidenceView:
    doc_kind: str
    ref: str
    text: str
    snippet: str
    score: float


@dataclass(slots=True)
class SearchResultView:
    bundle: ItemBundle
    score: float
    evidence: list[SearchEvidenceView]


@dataclass(slots=True)
class IndexItemStatus:
    item_id: str
    title: str
    counts: dict[str, int]
    expected: dict[str, int]

    @property
    def missing_kinds(self) -> list[str]:
        return [
            kind
            for kind in INDEX_KINDS
            if self.counts.get(kind, 0) < self.expected.get(kind, 0)
        ]


@dataclass(slots=True)
class IndexStatus:
    items: list[IndexItemStatus]
    total_rows: int
    orphan_rows: int


class SearchService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        search_index: SearchIndex,
        library: LibraryService,
    ) -> None:
        self.sessions = sessions
        self.search_index = search_index
        self.library = library

    def search(
        self,
        query: str,
        *,
        item_type: str | None = None,
        consumption: str | None = None,
        tag: str | None = None,
        platform: str | None = None,
        limit: int = 50,
    ) -> list[SearchResultView]:
        filtered = any((item_type, consumption, tag, platform))
        allowed_ids = (
            self.library.filtered_item_ids(
                item_type=item_type,
                consumption=consumption,
                platform=platform,
                tag=tag,
            )
            if filtered
            else None
        )
        fetch_limit = (
            max(limit * FILTER_FETCH_MULTIPLIER, MIN_FILTER_FETCH) if filtered else limit
        )
        results: list[SearchResultView] = []
        with self.sessions() as session:
            for result in self.search_index.search(query, limit=fetch_limit):
                if allowed_ids is not None and result.item_id not in allowed_ids:
                    continue
                item = session.get(Item, result.item_id)
                if item is None:
                    continue
                evidence = [
                    SearchEvidenceView(
                        doc_kind=hit.doc_kind,
                        ref=hit.ref,
                        text=hit.text,
                        snippet=snippet(hit.text, query),
                        score=hit.score,
                    )
                    for hit in result.evidence
                ]
                results.append(
                    SearchResultView(
                        bundle=item_bundle(session, item),
                        score=result.score,
                        evidence=evidence,
                    )
                )
                if len(results) == limit:
                    break
        return results

    def index_status(self) -> IndexStatus:
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
            transcript_counts = _counts_by_item(
                session,
                "SELECT item_id, count(*) FROM transcript_segments GROUP BY item_id",
            )
            book_counts = _counts_by_item(
                session,
                "SELECT item_id, count(*) FROM book_paragraphs GROUP BY item_id",
            )
        statuses = [
            IndexItemStatus(
                item_id=item.id,
                title=item.title,
                counts=counts.get(item.id, {}),
                expected={
                    "title": 1,
                    "summary": 1 if item.summary else 0,
                    "tag": tag_counts.get(item.id, 0),
                    "transcript": transcript_counts.get(item.id, 0),
                    "book": book_counts.get(item.id, 0),
                },
            )
            for item in items
        ]
        return IndexStatus(items=statuses, total_rows=total_rows, orphan_rows=orphan_rows)


def _counts_by_item(session: Session, statement: str) -> dict[str, int]:
    return {
        str(item_id): int(count) for item_id, count in session.execute(text(statement))
    }
