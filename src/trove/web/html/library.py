from __future__ import annotations

from fastapi import APIRouter, Request

from trove.web.deps import (
    filter_groups,
    render,
    runtime,
    search_dimensions,
    url_builder,
)

router = APIRouter()


@router.get("/library", include_in_schema=False)
def library_page(
    request: Request,
    sort: str = "recent_added",
    state: str = "",
    type: str = "",
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    app_runtime = runtime(request)
    if sort not in {"recent_added", "recent_consumed"}:
        sort = "recent_added"
    states = {value for value in state.split(",") if value}
    inbox = bool(states & {"processing", "failed"})
    items = app_runtime.library.list_items(
        sort=sort,
        states=states or None,
        item_type=type or None,
        consumption=consumption or None,
        platform=source or None,
        tag=tag or None,
    )
    selected = {
        "type": type,
        "consumption": consumption,
        "tag": tag,
        "source": source,
    }
    build = url_builder(
        "/library",
        {"sort": sort, "state": state, **selected},
    )
    return render(
        request,
        "library.html",
        {
            "items": items,
            "sort": sort,
            "inbox": inbox,
            "filter_groups": filter_groups(
                build, selected, search_dimensions(app_runtime)
            ),
            "make_url": build,
            "has_filters": any(selected.values()),
            "active_nav": "library",
        },
    )


@router.get("/search", include_in_schema=False)
def search_page(
    request: Request,
    q: str = "",
    type: str = "",
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    app_runtime = runtime(request)
    query = (q or "").strip()
    results = []
    error: str | None = None
    if query:
        try:
            results = app_runtime.search.search(
                query,
                item_type=type or None,
                consumption=consumption or None,
                tag=tag or None,
                platform=source or None,
            )
        except ValueError as exc:
            error = str(exc)
    selected = {
        "type": type,
        "consumption": consumption,
        "tag": tag,
        "source": source,
    }
    build = url_builder("/search", {"q": query, **selected})
    return render(
        request,
        "search.html",
        {
            "query": query,
            "results": results,
            "search_error": error,
            "filter_groups": filter_groups(
                build, selected, search_dimensions(app_runtime)
            ),
            "make_url": build,
            "clear_url": build(type="", consumption="", tag="", source=""),
            "has_filters": any(selected.values()),
            "active_nav": "search",
        },
    )
