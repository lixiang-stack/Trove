from __future__ import annotations

import logging
import time
from urllib.parse import quote, urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from trove.domain.sync import HOST_WEB_DEVICE
from trove.services.auth import SESSION_COOKIE, SESSION_MAX_AGE, is_secure_request
from trove.worker import heartbeat_is_fresh, read_heartbeat

logger = logging.getLogger("trove.request")

PUBLIC_PREFIXES = ("/static/",)
PUBLIC_PATHS = {
    "/login",
    "/api/health",
    "/api/auth/login",
    "/api/auth/device-token",
    "/api/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/manifest.webmanifest",
    "/sw.js",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "media-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)
DOCS_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)


def is_docs_path(path: str) -> bool:
    return path in {"/docs", "/redoc", "/docs/oauth2-redirect"}


def is_api(path: str) -> bool:
    return path.startswith("/api/")


def wants_json(request: Request) -> bool:
    return is_api(request.url.path)


def unauthorized(request: Request) -> Response:
    if wants_json(request):
        return JSONResponse(
            {"code": "auth.required", "message": "Sign in required"}, status_code=401
        )
    target = request.url.path
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def csrf_denied(request: Request) -> Response:
    if wants_json(request):
        return JSONResponse(
            {"code": "auth.csrf", "message": "Cross-site request rejected"}, status_code=403
        )
    return PlainTextResponse("Cross-site request rejected", status_code=403)


def check_csrf(request: Request) -> Response | None:
    if request.method not in UNSAFE_METHODS:
        return None
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site == "cross-site":
        return csrf_denied(request)
    origin = request.headers.get("origin")
    if origin:
        if origin == "null":
            return csrf_denied(request)
        origin_netloc = urlsplit(origin).netloc.lower()
        host = (request.headers.get("host") or "").lower()
        if not origin_netloc or origin_netloc != host:
            return csrf_denied(request)
    return None


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_secure_request(
            request.url.scheme,
            request.headers.get("x-forwarded-proto"),
            request.app.state.runtime.config,
        ),
        path="/",
    )


def safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/library"
    return value


def bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _authenticate(request: Request) -> tuple[bool, str | None]:
    runtime = request.app.state.runtime
    token = bearer_token(request)
    if token is not None:
        device_id, error = runtime.devices.verify(token)
        request.state.device_id = device_id
        request.state.auth_method = "bearer" if error is None else None
        return error is None, error
    request.state.auth_method = None
    if runtime.auth.verify_token(request.cookies.get(SESSION_COOKIE)):
        request.state.device_id = HOST_WEB_DEVICE
        request.state.auth_method = "cookie"
        return True, None
    request.state.device_id = None
    return False, None


def install_middleware(app) -> None:
    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        started = time.monotonic()
        runtime = app.state.runtime
        request.state.authenticated, auth_error = _authenticate(request)
        uses_bearer = bearer_token(request) is not None

        if not uses_bearer:
            csrf_response = check_csrf(request)
            if csrf_response is not None:
                return csrf_response

        path = request.url.path
        public = path in PUBLIC_PATHS or any(
            path.startswith(prefix) for prefix in PUBLIC_PREFIXES
        )
        if path == "/" or path == "":
            public = True
        if not request.state.authenticated and not public:
            if auth_error is not None:
                message = (
                    "Device authorization has been revoked"
                    if auth_error == "auth.device_revoked"
                    else "Device token is invalid"
                )
                return JSONResponse(
                    {"code": auth_error, "message": message}, status_code=401
                )
            return unauthorized(request)
        if request.state.authenticated and path == "/login" and request.method == "GET":
            return RedirectResponse("/library", status_code=303)

        if not path.startswith("/static/"):
            heartbeat = read_heartbeat(runtime.config)
            request.state.worker_offline = (
                not heartbeat_is_fresh(heartbeat)
                or bool(heartbeat and heartbeat.get("state") == "stopped")
            )

        response = await call_next(request)
        policy = DOCS_SECURITY_POLICY if is_docs_path(path) else CONTENT_SECURITY_POLICY
        response.headers.setdefault("Content-Security-Policy", policy)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers.setdefault("Cache-Control", "no-store")
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        if not path.startswith("/static/"):
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else "unknown",
                },
            )
        return response
