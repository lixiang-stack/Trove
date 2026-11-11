from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from trove.services.auth import SESSION_COOKIE
from trove.web.deps import runtime
from trove.web.schemas import LoginRequest
from trove.web.security import set_session_cookie

router = APIRouter()


@router.post("/auth/login")
def api_login(request: Request, payload: LoginRequest):
    app_runtime = runtime(request)
    client = request.client.host if request.client else "unknown"
    token = app_runtime.auth.login(payload.password, client)
    if token is None:
        return JSONResponse(
            {"code": "auth.invalid", "message": "Incorrect password"}, status_code=401
        )
    response = JSONResponse({"ok": True})
    set_session_cookie(request, response, token)
    return response


@router.post("/auth/logout")
def api_logout(request: Request):
    runtime(request).auth.logout()
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
