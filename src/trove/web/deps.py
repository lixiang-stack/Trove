from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from trove.composition import Runtime
from trove.domain.items import CONSUMPTION_LABELS, PLATFORM_LABELS, SOURCE_TYPE_LABELS
from trove.errors import TroveError
from trove.logging_setup import tail_run_log
from trove.web.templating import templates


def runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def render(
    request: Request,
    name: str,
    context: dict[str, Any],
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def run_logs(runtime: Runtime, bundle) -> dict[str, list[str]]:
    if bundle.run is None:
        return {}
    return {bundle.run.id: tail_run_log(runtime.config, bundle.run.id)}


def error_page(request: Request, error: TroveError) -> HTMLResponse:
    return render(
        request,
        "error.html",
        {
            "status": error.status_code,
            "message": error.message,
            "code": getattr(error, "code", None),
        },
        status_code=error.status_code,
    )


def url_builder(path: str, base: dict[str, str]):
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


def filter_groups(
    build,
    selected: dict[str, str],
    dimensions: list[tuple[str, str, list[tuple[str, str]]]],
) -> list[dict[str, Any]]:
    groups = []
    for key, label, choices in dimensions:
        options = [
            {"label": "All", "href": build(**{key: ""}), "active": not selected.get(key)}
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


def export_ids(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [item_id for value in values for item_id in value.split(",") if item_id]


def export_response(runtime: Runtime, values: list[str] | None) -> FileResponse:
    path, filename = runtime.export.create(export_ids(values))
    return FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_remove_file, path),
    )


def _remove_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def search_dimensions(runtime: Runtime) -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [
        ("type", "Type", list(SOURCE_TYPE_LABELS.items())),
        ("consumption", "Status", list(CONSUMPTION_LABELS.items())),
        ("tag", "Tag", [(name, name) for name, _ in runtime.library.tag_counts()]),
        ("source", "Source", list(PLATFORM_LABELS.items())),
    ]


def add_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {"active_nav": "add", "error": None}
    context.update(extra)
    return context
