from __future__ import annotations

from fastapi import APIRouter, Query, Request

from trove.errors import ValidationError
from trove.web.deps import runtime
from trove.web.urls import locate_url

router = APIRouter()


@router.get("/search")
def api_search(
    request: Request,
    q: str = "",
    type: str = Query("", alias="type"),
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    app_runtime = runtime(request)
    query = (q or "").strip()
    if not query:
        return {"query": query, "results": [], "count": 0}
    try:
        matching = app_runtime.search.search(
            query,
            item_type=type or None,
            consumption=consumption or None,
            tag=tag or None,
            platform=source or None,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
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
    return {"query": query, "results": results, "count": len(results)}
