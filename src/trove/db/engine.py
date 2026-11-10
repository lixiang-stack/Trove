from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from trove.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def create_engine_for(config: Config) -> Engine:
    engine = create_engine(
        f"sqlite:///{config.db_path}",
        connect_args={"check_same_thread": False, "timeout": 15},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _alembic_config(config: Config) -> AlembicConfig:
    alembic = AlembicConfig()
    alembic.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic.set_main_option("sqlalchemy.url", f"sqlite:///{config.db_path}")
    return alembic


def upgrade_database(config: Config) -> None:
    config.ensure_layout()
    command.upgrade(_alembic_config(config), "head")
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{config.db_path}{suffix}")
        if path.exists():
            path.chmod(0o600)


def head_revision(config: Config) -> str | None:
    script = ScriptDirectory.from_config(_alembic_config(config))
    return script.get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        exists = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        ).first()
        if not exists:
            return None
        row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
        return str(row[0]) if row else None


def migration_status(engine: Engine, config: Config) -> dict[str, object]:
    current = current_revision(engine)
    head = head_revision(config)
    return {
        "current": current,
        "head": head,
        "up_to_date": current is not None and current == head,
    }


def verify_fts5(engine: Engine) -> None:
    """Fail fast with an actionable message when SQLite lacks FTS5."""
    table = f"fts5_check_{uuid.uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f"CREATE VIRTUAL TABLE {table} USING fts5(content)"))
            connection.execute(text(f"DROP TABLE {table}"))
    except Exception as exc:  # sqlite3.OperationalError or SQLAlchemy wrapper
        raise RuntimeError(
            "This SQLite build lacks FTS5. Reinstall the Python 3.12 managed by uv"
            " (uv python install 3.12), or install SQLite with FTS5."
        ) from exc


def fts5_available(engine: Engine) -> bool:
    try:
        verify_fts5(engine)
        return True
    except RuntimeError:
        return False
