from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from trove.errors import ValidationError
from trove.web.deps import runtime
from trove.web.schemas import SearchResponse
from trove.web.urls import locate_url

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def api_search(
    request: Request,
    q: str = "",
    type: str = Query("", alias="type"),
    consumption: str = "",
    tag: str = "",
    source: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    app_runtime = runtime(request)
    query = (q or "").strip()
    if not query:
        return {
            "query": query,
            "results": [],
            "count": 0,
            "limit": limit,
            "offset": offset,
        }
    try:
        matching = app_runtime.search.search(
            query,
            item_type=type or None,
            consumption=consumption or None,
            tag=tag or None,
            platform=source or None,
            limit=limit + offset,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    matching = matching[offset:]
    results = [
        {
            "item": app_runtime.library.payload(result.bundle),
            "score": result.score,
            "evidence": [
                {
                    "doc_kind": evidence.doc_kind,
                    "ref": evidence.ref,
                    "text": evidence.text,
                    "snippet": evidence.snippet,
                    "score": evidence.score,
                    "url": locate_url(
                        result.bundle.item.id,
                        result.bundle.item.source_type,
                        evidence.doc_kind,
                        evidence.ref,
                    ),
                }
                for evidence in result.evidence
            ],
        }
        for result in matching
    ]
    return {
        "query": query,
        "results": results,
        "count": len(results),
        "limit": limit,
        "offset": offset,
    }
