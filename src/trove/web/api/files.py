from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from trove.content_package import ArtifactKind
from trove.errors import ArtifactMissingError
from trove.web.deps import runtime

router = APIRouter()

DOWNLOADABLE_KINDS = frozenset(kind.value for kind in ArtifactKind)

_FILE_HEADERS = {
    "ETag": {
        "description": "Quoted SHA-256 of the artifact",
        "schema": {"type": "string"},
    },
    "Accept-Ranges": {"description": "Always `bytes`", "schema": {"type": "string"}},
    "Cache-Control": {"description": "Always `private`", "schema": {"type": "string"}},
    "X-Content-Type-Options": {"description": "Always `nosniff`", "schema": {"type": "string"}},
}


@router.get(
    "/items/{item_id}/files/{kind}",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Content Package artifact",
            "content": {"application/octet-stream": {}},
            "headers": _FILE_HEADERS,
        },
        206: {
            "description": "Partial content for Range requests",
            "content": {"application/octet-stream": {}},
            "headers": {
                **_FILE_HEADERS,
                "Content-Range": {
                    "description": "Inclusive byte range and total size",
                    "schema": {"type": "string"},
                },
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
