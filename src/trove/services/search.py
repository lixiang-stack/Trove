from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from trove.db.models import Item
from trove.domain.search import snippet
from trove.ports import SearchIndex
from trove.services.library import ItemBundle, LibraryService, item_bundle

FILTER_FETCH_MULTIPLIER = 10
MIN_FILTER_FETCH = 200


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
