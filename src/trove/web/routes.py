from __future__ import annotations

import logging
import os
import time
from typing import Annotated, Any
from urllib.parse import quote, urlencode, urlsplit

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from trove import __version__
from trove.db.engine import fts5_available, migration_status
from trove.db.models import Item, Run
from trove.domain.items import CONSUMPTION_LABELS, PLATFORM_LABELS, SOURCE_TYPE_LABELS
from trove.errors import (
    NotFoundError,
    RateLimitedError,
    TroveError,
    ValidationError,
)
from trove.logging_setup import tail_run_log
from trove.services.auth import SESSION_COOKIE, SESSION_MAX_AGE, is_secure_request
from trove.services.library import item_bundle
from trove.web.templating import templates
from trove.web.urls import locate_url
from trove.worker import heartbeat_is_fresh, read_heartbeat

logger = logging.getLogger("trove.request")

PUBLIC_PREFIXES = ("/static/",)
PUBLIC_PATHS = {
    "/login",
    "/api/health",
    "/api/auth/login",
    "/api/openapi.json",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class LoginRequest(BaseModel):
    password: str


class ItemCreateRequest(BaseModel):
    kind: str
    url: str | None = None
    path: str | None = None
    upload_id: str | None = None
    feed_url: str | None = None
    episode_guid: str | None = None
    enclosure_url: str | None = None


class ItemPatchRequest(BaseModel):
    title: str | None = None
    author: str | None = None


class ProgressRequest(BaseModel):
    position_sec: float = Field(ge=0)
    consumption_state: str | None = None


class FeedPreviewRequest(BaseModel):
    url: str


def _is_api(path: str) -> bool:
    return path.startswith("/api/")


def _wants_json(request: Request) -> bool:
    return _is_api(request.url.path)


def _unauthorized(request: Request) -> Response:
    if _wants_json(request):
        return JSONResponse(
            {"code": "auth.required", "message": "请先登录"}, status_code=401
        )
    target = request.url.path
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def _csrf_denied(request: Request) -> Response:
    if _wants_json(request):
        return JSONResponse(
            {"code": "auth.csrf", "message": "跨站请求被拒绝"}, status_code=403
        )
    return PlainTextResponse("跨站请求被拒绝", status_code=403)


def _check_csrf(request: Request) -> Response | None:
    if request.method not in UNSAFE_METHODS:
        return None
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site == "cross-site":
        return _csrf_denied(request)
    origin = request.headers.get("origin")
    if origin:
        if origin == "null":
            return _csrf_denied(request)
        origin_netloc = urlsplit(origin).netloc.lower()
        host = (request.headers.get("host") or "").lower()
        if not origin_netloc or origin_netloc != host:
            return _csrf_denied(request)
    return None


def _render(request: Request, name: str, context: dict[str, Any], status_code: int = 200):
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def _run_logs(runtime, bundle) -> dict[str, list[str]]:
    if bundle.run is None:
        return {}
    return {bundle.run.id: tail_run_log(runtime.config, bundle.run.id)}


def _error_page(request: Request, error: TroveError) -> HTMLResponse:
    return _render(
        request,
        "error.html",
        {
            "status": error.status_code,
            "message": error.message,
            "code": getattr(error, "code", None),
        },
        status_code=error.status_code,
    )


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
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


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/library"
    return value


def _url_builder(path: str, base: dict[str, str]):
    def build(**overrides: str) -> str:
        params = {key: value for key, value in base.items() if value}
        for key, value in overrides.items():
            if value:
                params[key] = value
            else:
                params.pop(key, None)
        query = urlencode(params)
        return f"{path}?{query}" if query else path

    return build


def _filter_groups(
    build,
    selected: dict[str, str],
    dimensions: list[tuple[str, str, list[tuple[str, str]]]],
) -> list[dict[str, Any]]:
    groups = []
    for key, label, choices in dimensions:
        options = [
            {"label": "全部", "href": build(**{key: ""}), "active": not selected.get(key)}
        ]
        options.extend(
            {
                "label": choice_label,
                "href": build(**{key: value}),
                "active": selected.get(key) == value,
            }
            for value, choice_label in choices
        )
        groups.append({"key": key, "label": label, "options": options})
    return groups


def _search_dimensions(runtime) -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [
        ("type", "类型", list(SOURCE_TYPE_LABELS.items())),
        ("consumption", "状态", list(CONSUMPTION_LABELS.items())),
        ("tag", "Tag", [(name, name) for name, _ in runtime.library.tag_counts()]),
        ("source", "来源", list(PLATFORM_LABELS.items())),
    ]


# ----------------------------------------------------------------------
# HTML routes
# ----------------------------------------------------------------------
html_router = APIRouter()


@html_router.get("/", include_in_schema=False)
def root(request: Request):
    if request.state.authenticated:
        return RedirectResponse("/library", status_code=303)
    return RedirectResponse("/login", status_code=303)


@html_router.get("/login", include_in_schema=False)
def login_page(request: Request, next: str = "/library"):
    if request.state.authenticated:
        return RedirectResponse(_safe_next(next), status_code=303)
    runtime = request.app.state.runtime
    return _render(
        request,
        "login.html",
        {
            "password_configured": runtime.config.password_configured(),
            "next_path": _safe_next(next),
            "error": None,
            "active_nav": None,
        },
    )


@html_router.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/library",
):
    runtime = request.app.state.runtime
    client = request.client.host if request.client else "unknown"
    try:
        token = runtime.auth.login(password, client)
    except RateLimitedError as exc:
        response = _render(
            request,
            "login.html",
            {
                "password_configured": runtime.config.password_configured(),
                "next_path": _safe_next(next),
                "error": exc.message,
                "active_nav": None,
            },
            status_code=429,
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response
    if token is None:
        return _render(
            request,
            "login.html",
            {
                "password_configured": runtime.config.password_configured(),
                "next_path": _safe_next(next),
                "error": "密码错误",
                "active_nav": None,
            },
            status_code=401,
        )
    response = RedirectResponse(_safe_next(next), status_code=303)
    _set_session_cookie(request, response, token)
    return response


@html_router.post("/logout", include_in_schema=False)
def logout_submit(request: Request):
    request.app.state.runtime.auth.logout()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@html_router.get("/library", include_in_schema=False)
def library_page(
    request: Request,
    sort: str = "recent_added",
    state: str = "",
    type: str = "",
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    runtime = request.app.state.runtime
    if sort not in {"recent_added", "recent_consumed"}:
        sort = "recent_added"
    states = {value for value in state.split(",") if value}
    inbox = bool(states & {"processing", "failed"})
    items = runtime.library.list_items(
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
    build = _url_builder(
        "/library",
        {"sort": sort, "state": state, **selected},
    )
    return _render(
        request,
        "library.html",
        {
            "items": items,
            "sort": sort,
            "inbox": inbox,
            "filter_groups": _filter_groups(
                build, selected, _search_dimensions(runtime)
            ),
            "make_url": build,
            "has_filters": any(selected.values()),
            "active_nav": "library",
        },
    )


@html_router.get("/items/{item_id}", include_in_schema=False)
def item_detail(request: Request, item_id: str):
    runtime = request.app.state.runtime
    bundle = runtime.library.get(item_id)
    return _render(
        request,
        "item_detail.html",
        {
            "bundle": bundle,
            "run_logs": _run_logs(runtime, bundle),
            "active_nav": "library",
        },
    )


@html_router.get("/items/{item_id}/read", include_in_schema=False)
def item_read(request: Request, item_id: str):
    runtime = request.app.state.runtime
    bundle = runtime.library.get(item_id)
    return _render(
        request,
        "read.html",
        {
            "bundle": bundle,
            "chapters": runtime.reading.chapters(item_id),
            "active_nav": "library",
        },
    )


@html_router.get("/items/{item_id}/listen", include_in_schema=False)
def item_listen(request: Request, item_id: str, replace: int | None = None):
    runtime = request.app.state.runtime
    bundle = runtime.library.get(item_id)
    transcript = runtime.playback.transcript(item_id)
    return _render(
        request,
        "listen.html",
        {
            "bundle": bundle,
            "transcript": transcript,
            "replace_count": replace,
            "run_logs": _run_logs(runtime, bundle),
            "active_nav": "library",
        },
    )


@html_router.post("/items/{item_id}/transcript/replace", include_in_schema=False)
def replace_transcript(
    request: Request,
    item_id: str,
    old: Annotated[str, Form()] = "",
    new: Annotated[str, Form()] = "",
):
    runtime = request.app.state.runtime
    count, first_seq = runtime.playback.replace_transcript_text(
        item_id, old=old, new=new
    )
    target = f"/items/{item_id}/listen?replace={count}"
    if first_seq is not None:
        target += f"#segment-{first_seq}"
    return RedirectResponse(target, status_code=303)


@html_router.get("/items/{item_id}/status", include_in_schema=False)
def item_status(request: Request, item_id: str, context: str = "row"):
    runtime = request.app.state.runtime
    bundle = runtime.library.get(item_id)
    if context in {"panel", "detail", "listen"}:
        return _render(
            request,
            "status.html",
            {
                "bundle": bundle,
                "context": "panel",
                "run_logs": _run_logs(runtime, bundle),
            },
        )
    return _render(
        request,
        "status.html",
        {"bundle": bundle, "context": "row"},
    )


@html_router.post("/items/{item_id}/edit", include_in_schema=False)
def edit_item(
    request: Request,
    item_id: str,
    title: Annotated[str, Form()] = "",
    author: Annotated[str, Form()] = "",
):
    runtime = request.app.state.runtime
    runtime.library.update_metadata(item_id, title=title, author=author)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@html_router.post("/items/{item_id}/delete", include_in_schema=False)
def delete_item(request: Request, item_id: str):
    runtime = request.app.state.runtime
    runtime.library.delete(item_id)
    return RedirectResponse("/library", status_code=303)


@html_router.post("/items/{item_id}/state", include_in_schema=False)
def set_item_state(request: Request, item_id: str, state: Annotated[str, Form()]):
    runtime = request.app.state.runtime
    runtime.playback.set_consumption_state(item_id, state)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@html_router.post("/items/{item_id}/retry", include_in_schema=False)
def retry_item(request: Request, item_id: str):
    runtime = request.app.state.runtime
    runtime.processing.retry(item_id)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@html_router.post("/items/{item_id}/cancel", include_in_schema=False)
def cancel_item(request: Request, item_id: str):
    runtime = request.app.state.runtime
    runtime.processing.cancel_item(item_id)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


def _add_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {"active_nav": "add", "error": None}
    context.update(extra)
    return context


@html_router.get("/add", include_in_schema=False)
def add_page(request: Request):
    return _render(request, "add.html", _add_context())


@html_router.post("/add/url", include_in_schema=False)
def add_url(request: Request, url: Annotated[str, Form()]):
    runtime = request.app.state.runtime
    try:
        bundle, _ = runtime.intake.add_video_url(url)
    except TroveError as exc:
        return _render(
            request,
            "add.html",
            _add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@html_router.post("/add/path", include_in_schema=False)
def add_path(request: Request, path: Annotated[str, Form()]):
    runtime = request.app.state.runtime
    try:
        bundle, _ = runtime.intake.add_host_path(path)
    except TroveError as exc:
        return _render(
            request,
            "add.html",
            _add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@html_router.post("/add/upload", include_in_schema=False)
async def add_upload(request: Request, file: Annotated[UploadFile, File()]):
    runtime = request.app.state.runtime
    try:
        record = runtime.uploads.save_stream(
            file.file, file.filename or "upload", content_type=file.content_type
        )
        bundle, _ = runtime.intake.add_upload(record.upload_id)
    except TroveError as exc:
        return _render(
            request,
            "add.html",
            _add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@html_router.post("/add/feed/preview", include_in_schema=False)
def preview_feed(request: Request, feed_url: Annotated[str, Form()]):
    runtime = request.app.state.runtime
    try:
        feed = runtime.intake.preview_feed(feed_url)
    except TroveError as exc:
        if request.headers.get("HX-Request") == "true":
            return _render(
                request,
                "feed_preview.html",
                {"feed": None, "feed_error": exc.message, "feed_url": feed_url},
            )
        return _render(
            request,
            "add.html",
            _add_context(error=exc.message),
            status_code=exc.status_code,
        )
    if request.headers.get("HX-Request") == "true":
        return _render(
            request,
            "feed_preview.html",
            {"feed": feed, "feed_url": feed_url, "feed_error": None},
        )
    return _render(
        request,
        "add.html",
        _add_context(feed=feed, feed_url=feed_url),
    )


@html_router.post("/add/podcast", include_in_schema=False)
def add_podcast(
    request: Request,
    feed_url: Annotated[str, Form()],
    episode_guid: Annotated[str, Form()] = "",
    enclosure_url: Annotated[str, Form()] = "",
):
    runtime = request.app.state.runtime
    try:
        bundle, _ = runtime.intake.add_podcast_episode(
            feed_url, episode_guid or None, enclosure_url or None
        )
    except TroveError as exc:
        return _render(
            request,
            "add.html",
            _add_context(error=exc.message),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/items/{bundle.item.id}", status_code=303)


@html_router.get("/search", include_in_schema=False)
def search_page(
    request: Request,
    q: str = "",
    type: str = "",
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    runtime = request.app.state.runtime
    query = (q or "").strip()
    results = []
    error: str | None = None
    if query:
        try:
            results = runtime.search.search(
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
    build = _url_builder("/search", {"q": query, **selected})
    return _render(
        request,
        "search.html",
        {
            "query": query,
            "results": results,
            "search_error": error,
            "filter_groups": _filter_groups(
                build, selected, _search_dimensions(runtime)
            ),
            "make_url": build,
            "clear_url": build(type="", consumption="", tag="", source=""),
            "has_filters": any(selected.values()),
            "active_nav": "search",
        },
    )


# ----------------------------------------------------------------------
# JSON API
# ----------------------------------------------------------------------
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health(request: Request):
    runtime = request.app.state.runtime
    status: dict[str, Any] = {
        "host": {"status": "ok", "version": __version__, "pid": os.getpid()},
        "database": {"status": "ok"},
        "worker": {"status": "unknown"},
    }
    overall = 200
    try:
        migration = migration_status(runtime.engine, runtime.config)
        status["database"]["migration"] = migration
        status["database"]["fts5"] = fts5_available(runtime.engine)
        if not migration["up_to_date"]:
            status["database"]["status"] = "not_migrated"
            overall = 503
        if not status["database"]["fts5"]:
            status["database"]["status"] = "fts5_missing"
            overall = 503
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        status["database"] = {"status": "error", "error": str(exc)}
        overall = 503
    heartbeat = read_heartbeat(runtime.config)
    if heartbeat is None:
        status["worker"] = {"status": "unknown"}
    elif heartbeat_is_fresh(heartbeat):
        status["worker"] = {
            "status": "ok",
            "state": heartbeat.get("state"),
            "run_id": heartbeat.get("run_id"),
            "updated_at": heartbeat.get("updated_at"),
        }
    else:
        status["worker"] = {
            "status": "stale",
            "state": heartbeat.get("state"),
            "updated_at": heartbeat.get("updated_at"),
        }
    return JSONResponse(status, status_code=overall)


@api_router.post("/auth/login")
def api_login(request: Request, payload: LoginRequest):
    runtime = request.app.state.runtime
    client = request.client.host if request.client else "unknown"
    token = runtime.auth.login(payload.password, client)
    if token is None:
        return JSONResponse(
            {"code": "auth.invalid", "message": "密码错误"}, status_code=401
        )
    response = JSONResponse({"ok": True})
    _set_session_cookie(request, response, token)
    return response


@api_router.post("/auth/logout")
def api_logout(request: Request):
    request.app.state.runtime.auth.logout()
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@api_router.get("/items")
def api_list_items(
    request: Request,
    sort: str = "recent_added",
    state: str = "",
    type: str = Query("", alias="type"),
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    runtime = request.app.state.runtime
    if sort not in {"recent_added", "recent_consumed"}:
        sort = "recent_added"
    states = {value for value in state.split(",") if value}
    bundles = runtime.library.list_items(
        sort=sort,
        states=states or None,
        item_type=type or None,
        consumption=consumption or None,
        platform=source or None,
        tag=tag or None,
    )
    return {
        "items": [runtime.library.payload(bundle) for bundle in bundles],
        "count": len(bundles),
    }


@api_router.post("/items")
def api_create_item(request: Request, payload: ItemCreateRequest):
    runtime = request.app.state.runtime
    if payload.kind == "url":
        if not payload.url:
            raise ValidationError("缺少 url")
        bundle, duplicated = runtime.intake.add_video_url(payload.url)
    elif payload.kind == "path":
        if not payload.path:
            raise ValidationError("缺少 path")
        bundle, duplicated = runtime.intake.add_host_path(payload.path)
    elif payload.kind == "upload":
        if not payload.upload_id:
            raise ValidationError("缺少 upload_id")
        bundle, duplicated = runtime.intake.add_upload(payload.upload_id)
    elif payload.kind == "podcast":
        if not payload.feed_url or not (payload.episode_guid or payload.enclosure_url):
            raise ValidationError("缺少 feed_url 或单集标识")
        bundle, duplicated = runtime.intake.add_podcast_episode(
            payload.feed_url, payload.episode_guid, payload.enclosure_url
        )
    else:
        raise ValidationError("kind 必须是 url、path、upload 或 podcast")
    return JSONResponse(
        {"item": runtime.library.payload(bundle), "deduplicated": duplicated},
        status_code=200 if duplicated else 201,
    )


@api_router.get("/items/{item_id}")
def api_get_item(request: Request, item_id: str):
    runtime = request.app.state.runtime
    bundle = runtime.library.get(item_id)
    return runtime.library.payload(bundle)


@api_router.patch("/items/{item_id}")
def api_patch_item(request: Request, item_id: str, payload: ItemPatchRequest):
    runtime = request.app.state.runtime
    fields = payload.model_fields_set
    bundle = runtime.library.update_metadata(
        item_id,
        title=payload.title if "title" in fields else None,
        author=payload.author if "author" in fields else None,
    )
    return runtime.library.payload(bundle)


@api_router.delete("/items/{item_id}", status_code=204)
def api_delete_item(request: Request, item_id: str):
    request.app.state.runtime.library.delete(item_id)
    return Response(status_code=204)


@api_router.get("/items/{item_id}/audio")
def api_audio(request: Request, item_id: str):
    runtime = request.app.state.runtime
    artifact = runtime.playback.audio_artifact(item_id)
    path = runtime.playback.audio_path(item_id)
    headers = {
        "ETag": f'"{artifact.sha256}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "private",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path, media_type=artifact.mime, headers=headers)


@api_router.get("/items/{item_id}/transcript")
def api_transcript(request: Request, item_id: str):
    runtime = request.app.state.runtime
    return {
        "item_id": item_id,
        "segments": runtime.playback.transcript(item_id),
    }


@api_router.put("/items/{item_id}/progress")
def api_progress(request: Request, item_id: str, payload: ProgressRequest):
    runtime = request.app.state.runtime
    bundle = runtime.playback.update_progress(
        item_id,
        position_sec=payload.position_sec,
        consumption_state=payload.consumption_state,
    )
    return {"ok": True, "item": runtime.library.payload(bundle)}


@api_router.post("/items/{item_id}/retry")
def api_retry(request: Request, item_id: str):
    runtime = request.app.state.runtime
    runtime.processing.retry(item_id)
    bundle = runtime.library.get(item_id)
    return runtime.library.payload(bundle)


@api_router.post("/items/{item_id}/cancel")
def api_cancel_item(request: Request, item_id: str):
    runtime = request.app.state.runtime
    runtime.processing.cancel_item(item_id)
    bundle = runtime.library.get(item_id)
    return runtime.library.payload(bundle)


@api_router.get("/runs/{run_id}")
def api_run(request: Request, run_id: str):
    runtime = request.app.state.runtime
    with runtime.sessions() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise NotFoundError("Processing Run 不存在")
        item = session.get(Item, run.item_id)
        if item is None:
            raise NotFoundError("内容不存在")
        bundle = item_bundle(session, item)
        payload = runtime.library.run_payload(bundle)
    return {
        "run": payload,
        "item": {"id": item.id, "title": item.title},
    }


@api_router.post("/runs/{run_id}/cancel")
def api_cancel_run(request: Request, run_id: str):
    runtime = request.app.state.runtime
    with runtime.sessions() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise NotFoundError("Processing Run 不存在")
        item_id = run.item_id
    runtime.processing.cancel(run_id)
    bundle = runtime.library.get(item_id)
    return runtime.library.payload(bundle)


@api_router.get("/search")
def api_search(
    request: Request,
    q: str = "",
    type: str = Query("", alias="type"),
    consumption: str = "",
    tag: str = "",
    source: str = "",
):
    runtime = request.app.state.runtime
    query = (q or "").strip()
    if not query:
        return {"query": query, "results": [], "count": 0}
    try:
        matching = runtime.search.search(
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
            "item": runtime.library.payload(result.bundle),
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


@api_router.post("/uploads")
async def api_upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str | None, Form()] = None,
):
    runtime = request.app.state.runtime
    record = runtime.uploads.save_stream(
        file.file,
        file.filename or "upload",
        kind=kind,
        content_type=file.content_type,
    )
    return {
        "upload_id": record.upload_id,
        "filename": record.filename,
        "sha256": record.sha256,
        "size": record.size,
        "kind": record.kind,
    }


@api_router.post("/feeds/preview")
def api_feed_preview(request: Request, payload: FeedPreviewRequest):
    runtime = request.app.state.runtime
    feed = runtime.intake.preview_feed(payload.url)
    return {
        "title": feed.title,
        "author": feed.author,
        "link": feed.link,
        "episodes": [
            {
                "guid": episode.guid,
                "title": episode.title,
                "author": episode.author,
                "published_at": episode.published_at,
                "duration_sec": episode.duration_sec,
                "enclosure_url": episode.enclosure_url,
                "enclosure_type": episode.enclosure_type,
                "enclosure_size": episode.enclosure_size,
            }
            for episode in feed.episodes
        ],
    }


# ----------------------------------------------------------------------
# Exception handlers and middleware installation
# ----------------------------------------------------------------------
def install_middleware(app) -> None:
    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        started = time.monotonic()
        runtime = app.state.runtime
        token = request.cookies.get(SESSION_COOKIE)
        request.state.authenticated = runtime.auth.verify_token(token)

        csrf_response = _check_csrf(request)
        if csrf_response is not None:
            return csrf_response

        path = request.url.path
        public = path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
        if path == "/" or path == "":
            public = True
        if not request.state.authenticated and not public:
            return _unauthorized(request)
        if request.state.authenticated and path == "/login" and request.method == "GET":
            return RedirectResponse("/library", status_code=303)

        if not path.startswith("/static/"):
            heartbeat = read_heartbeat(runtime.config)
            request.state.worker_offline = (
                not heartbeat_is_fresh(heartbeat)
                or bool(heartbeat and heartbeat.get("state") == "stopped")
            )

        response = await call_next(request)
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


def install_exception_handlers(app) -> None:
    @app.exception_handler(TroveError)
    async def trove_error_handler(request: Request, exc: TroveError):
        response: Response
        if _wants_json(request):
            response = JSONResponse(
                {"code": exc.code, "message": exc.message, "details": exc.details},
                status_code=exc.status_code,
            )
        else:
            response = _error_page(request, exc)
        if isinstance(exc, RateLimitedError):
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = {"errors": exc.errors()}
        if not _wants_json(request):
            return _render(
                request,
                "error.html",
                {"status": 422, "message": "请求参数无效", "code": "request.invalid"},
                status_code=422,
            )
        return JSONResponse(
            {"code": "request.invalid", "message": "请求参数无效", "details": details},
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        if _wants_json(request):
            return JSONResponse(
                {"code": f"http.{exc.status_code}", "message": str(exc.detail)},
                status_code=exc.status_code,
            )
        return _render(
            request,
            "error.html",
            {
                "status": exc.status_code,
                "message": str(exc.detail),
                "code": f"http.{exc.status_code}",
            },
            status_code=exc.status_code,
        )
