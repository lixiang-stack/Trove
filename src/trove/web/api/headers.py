from __future__ import annotations

FILE_RESPONSE_HEADERS = {
    "ETag": {
        "description": "Quoted SHA-256 of the artifact",
        "schema": {"type": "string"},
    },
    "Accept-Ranges": {"description": "Always `bytes`", "schema": {"type": "string"}},
    "Cache-Control": {"description": "Always `private`", "schema": {"type": "string"}},
    "X-Content-Type-Options": {
        "description": "Always `nosniff`",
        "schema": {"type": "string"},
    },
}

CONTENT_RANGE_HEADER = {
    "description": "Inclusive byte range and total size",
    "schema": {"type": "string"},
}
