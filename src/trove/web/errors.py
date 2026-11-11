from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from trove.errors import RateLimitedError, TroveError
from trove.web.deps import error_page, render
from trove.web.security import wants_json


def install_exception_handlers(app) -> None:
    @app.exception_handler(TroveError)
    async def trove_error_handler(request: Request, exc: TroveError):
        response: Response
        if wants_json(request):
            response = JSONResponse(
                {"code": exc.code, "message": exc.message, "details": exc.details},
                status_code=exc.status_code,
            )
        else:
            response = error_page(request, exc)
        if isinstance(exc, RateLimitedError):
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = {"errors": exc.errors()}
        if not wants_json(request):
            return render(
                request,
                "error.html",
                {
                    "status": 422,
                    "message": "Invalid request parameters",
                    "code": "request.invalid",
                },
                status_code=422,
            )
        return JSONResponse(
            {
                "code": "request.invalid",
                "message": "Invalid request parameters",
                "details": details,
            },
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        if wants_json(request):
            return JSONResponse(
                {"code": f"http.{exc.status_code}", "message": str(exc.detail)},
                status_code=exc.status_code,
            )
        return render(
            request,
            "error.html",
            {
                "status": exc.status_code,
                "message": str(exc.detail),
                "code": f"http.{exc.status_code}",
            },
            status_code=exc.status_code,
        )
