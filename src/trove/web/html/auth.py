from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from trove.errors import RateLimitedError
from trove.services.auth import SESSION_COOKIE
from trove.web.deps import render, runtime
from trove.web.security import safe_next, set_session_cookie

router = APIRouter()


@router.get("/", include_in_schema=False)
def root(request: Request):
    if request.state.authenticated:
        return RedirectResponse("/library", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/login", include_in_schema=False)
def login_page(request: Request, next: str = "/library"):
    if request.state.authenticated:
        return RedirectResponse(safe_next(next), status_code=303)
    app_runtime = runtime(request)
    return render(
        request,
        "login.html",
        {
            "password_configured": app_runtime.config.password_configured(),
            "next_path": safe_next(next),
            "error": None,
            "active_nav": None,
        },
    )


@router.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/library",
):
    app_runtime = runtime(request)
    client = request.client.host if request.client else "unknown"
    try:
        token = app_runtime.auth.login(password, client)
    except RateLimitedError as exc:
        response = render(
            request,
            "login.html",
            {
                "password_configured": app_runtime.config.password_configured(),
                "next_path": safe_next(next),
                "error": exc.message,
                "active_nav": None,
            },
            status_code=429,
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response
    if token is None:
        return render(
            request,
            "login.html",
            {
                "password_configured": app_runtime.config.password_configured(),
                "next_path": safe_next(next),
                "error": "Incorrect password",
                "active_nav": None,
            },
            status_code=401,
        )
    redirect = RedirectResponse(safe_next(next), status_code=303)
    set_session_cookie(request, redirect, token)
    return redirect


@router.post("/logout", include_in_schema=False)
def logout_submit(request: Request):
    runtime(request).auth.logout()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
