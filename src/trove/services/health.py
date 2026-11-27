from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from trove.config import Config
from trove.db.engine import fts5_available, migration_status


def database_health(engine: Engine, config: Config) -> dict[str, Any]:
    migration = migration_status(engine, config)
    fts5 = fts5_available(engine)
    status = "ok"
    if not migration["up_to_date"]:
        status = "not_migrated"
    if not fts5:
        status = "fts5_missing"
    return {"status": status, "migration": migration, "fts5": fts5}
