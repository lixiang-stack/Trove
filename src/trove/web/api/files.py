from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from trove.content_package import ArtifactKind
from trove.errors import ArtifactMissingError
from trove.web.api.headers import CONTENT_RANGE_HEADER, FILE_RESPONSE_HEADERS
from trove.web.deps import runtime

router = APIRouter()

DOWNLOADABLE_KINDS = frozenset(kind.value for kind in ArtifactKind)


@router.get(
    "/items/{item_id}/files/{kind}",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Content Package artifact",
            "content": {"application/octet-stream": {}},
            "headers": FILE_RESPONSE_HEADERS,
        },
        206: {
            "description": "Partial content for Range requests",
            "content": {"application/octet-stream": {}},
            "headers": {
                **FILE_RESPONSE_HEADERS,
                "Content-Range": CONTENT_RANGE_HEADER,
            },
        },
        416: {"description": "Requested range is not satisfiable"},
    },
)
def api_download_file(request: Request, item_id: str, kind: str):
    app_runtime = runtime(request)
    bundle = app_runtime.library.get(item_id)
    artifact = (
        next(
            (row for row in bundle.artifacts if row.kind == kind),
            None,
        )
        if kind in DOWNLOADABLE_KINDS
        else None
    )
    if artifact is None:
        raise ArtifactMissingError("File artifact is missing")
    try:
        path = app_runtime.package.artifact_path(item_id, artifact.path)
    except FileNotFoundError as exc:
        raise ArtifactMissingError("File artifact is missing") from exc
    if not path.is_file():
        raise ArtifactMissingError("File artifact is missing")
    return FileResponse(
        path,
        media_type=artifact.mime,
        headers={
            "ETag": f'"{artifact.sha256}"',
            "Accept-Ranges": "bytes",
            "Cache-Control": "private",
            "X-Content-Type-Options": "nosniff",
        },
    )
