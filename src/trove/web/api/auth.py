from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from trove.services.auth import SESSION_COOKIE
from trove.web.deps import runtime
from trove.web.schemas import (
    DeviceTokenRequest,
    DeviceTokenResponse,
    LoginRequest,
    OkResponse,
)
from trove.web.security import set_session_cookie

router = APIRouter()


@router.post(
    "/auth/device-token", response_model=DeviceTokenResponse, status_code=201
)
def api_device_token(request: Request, payload: DeviceTokenRequest):
    app_runtime = runtime(request)
    client = request.client.host if request.client else "unknown"
    issued = app_runtime.devices.issue(
        password=payload.password, name=payload.name, client=client
    )
    if issued is None:
        return JSONResponse(
            {
                "code": "auth.invalid",
                "message": "Incorrect password",
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=401,
        )
    return JSONResponse(
        {
            "device_id": issued.device_id,
            "name": issued.name,
            "token": issued.token,
            "created_at": issued.created_at,
        },
        status_code=201,
    )


@router.post("/auth/login", response_model=OkResponse)
def api_login(request: Request, payload: LoginRequest):
    app_runtime = runtime(request)
    client = request.client.host if request.client else "unknown"
    token = app_runtime.auth.login(payload.password, client)
    if token is None:
        return JSONResponse(
            {
                "code": "auth.invalid",
                "message": "Incorrect password",
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=401,
        )
    response = JSONResponse({"ok": True})
    set_session_cookie(request, response, token)
    return response


@router.post("/auth/logout", response_model=OkResponse)
def api_logout(request: Request):
    runtime(request).auth.logout()
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
