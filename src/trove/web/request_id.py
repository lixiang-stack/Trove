"""Attach a request id to every HTTP response and to request state."""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import Headers, MutableHeaders

HEADER_NAME = "X-Request-ID"
MAX_LENGTH = 128
_VALID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    if value is not None and _VALID.fullmatch(value):
        return value
    return uuid.uuid4().hex


class RequestIDMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = normalize_request_id(Headers(scope=scope).get("x-request-id"))
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
