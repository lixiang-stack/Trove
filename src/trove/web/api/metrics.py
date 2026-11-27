from __future__ import annotations

from fastapi import APIRouter, Request, Response

from trove import metrics
from trove.web.deps import runtime

router = APIRouter()


@router.get(metrics.METRICS_PATH, include_in_schema=False)
def api_metrics(request: Request):
    return Response(
        content=metrics.render_for_runtime(runtime(request)),
        media_type=metrics.CONTENT_TYPE_LATEST,
    )
