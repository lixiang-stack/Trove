from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from trove import __version__
from trove.db.engine import fts5_available, migration_status
from trove.web.deps import runtime
from trove.worker import heartbeat_is_fresh, read_heartbeat

router = APIRouter()


@router.get("/health")
def health(request: Request):
    app_runtime = runtime(request)
    status: dict[str, Any] = {
        "host": {"status": "ok", "version": __version__, "pid": os.getpid()},
        "database": {"status": "ok"},
        "worker": {"status": "unknown"},
    }
    overall = 200
    try:
        migration = migration_status(app_runtime.engine, app_runtime.config)
        status["database"]["migration"] = migration
        status["database"]["fts5"] = fts5_available(app_runtime.engine)
        if not migration["up_to_date"]:
            status["database"]["status"] = "not_migrated"
            overall = 503
        if not status["database"]["fts5"]:
            status["database"]["status"] = "fts5_missing"
            overall = 503
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        status["database"] = {"status": "error", "error": str(exc)}
        overall = 503
    heartbeat = read_heartbeat(app_runtime.config)
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
