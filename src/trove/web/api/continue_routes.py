from __future__ import annotations

from fastapi import APIRouter, Request

from trove.web.deps import continue_entries, runtime
from trove.web.schemas import ContinueResponse

router = APIRouter()


@router.get("/continue", response_model=ContinueResponse)
def api_continue(request: Request):
    app_runtime = runtime(request)
    return {
        "entries": [
            {
                "item": app_runtime.library.payload(entry["bundle"]),
                "kind": entry["kind"],
                "progress": entry["progress"],
                "url": entry["url"],
            }
            for entry in continue_entries(app_runtime)
        ]
    }
