from __future__ import annotations

from fastapi.responses import FileResponse

from trove.composition import Runtime
from trove.errors import NotFoundError


def audio_response(runtime: Runtime, item_id: str) -> FileResponse:
    artifact = runtime.playback.audio_artifact(item_id)
    path = runtime.playback.audio_path(item_id)
    headers = {
        "ETag": f'"{artifact.sha256}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "private",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path, media_type=artifact.mime, headers=headers)


def cover_response(runtime: Runtime, item_id: str) -> FileResponse:
    bundle = runtime.library.get(item_id)
    artifact = bundle.cover_artifact
    if artifact is None:
        raise NotFoundError("Cover not found")
    path = runtime.package.artifact_path(item_id, artifact.path)
    if not path.is_file():
        raise NotFoundError("Cover not found")
    headers = {
        "ETag": f'"{artifact.sha256}"',
        "Cache-Control": "private",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path, media_type=artifact.mime, headers=headers)
