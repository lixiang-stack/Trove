from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from trove.config import Config
from trove.db.sequences import install_sync_tracking

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BACKUP_DIRNAME = "backups"
BACKUP_KEEP = 5
logger = logging.getLogger("trove.db")


class DatabaseUpgradeError(RuntimeError):
    def __init__(
        self, message: str, *, backup_path: Path | None = None
    ) -> None:
        super().__init__(message)
        self.backup_path = backup_path


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
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    install_sync_tracking(sessions)
    return sessions


def _alembic_config(config: Config) -> AlembicConfig:
    alembic = AlembicConfig()
    alembic.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic.set_main_option("sqlalchemy.url", f"sqlite:///{config.db_path}")
    return alembic


def upgrade_database(config: Config) -> Path | None:
    config.ensure_layout()
    backup = None
    if config.db_path.exists() and config.db_path.stat().st_size > 0:
        engine = create_engine_for(config)
        try:
            current = current_revision(engine)
        finally:
            engine.dispose()
        if current != head_revision(config):
            try:
                backup = backup_database(config, revision=current)
            except Exception as exc:
                raise DatabaseUpgradeError(
                    f"Database backup failed; upgrade aborted: {exc}"
                ) from exc
    try:
        command.upgrade(_alembic_config(config), "head")
    except Exception as exc:
        raise DatabaseUpgradeError(
            f"Database upgrade failed: {exc}", backup_path=backup
        ) from exc
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{config.db_path}{suffix}")
        if path.exists():
            path.chmod(0o600)
    return backup


def backup_database(config: Config, *, revision: str | None) -> Path:
    backup_dir = config.home / BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    label = revision or "unversioned"
    destination = backup_dir / f"trove-{label}-{stamp}.db"
    suffix = 1
    while destination.exists():
        destination = backup_dir / f"trove-{label}-{stamp}-{suffix}.db"
        suffix += 1
    source_connection = sqlite3.connect(config.db_path)
    target_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    destination.chmod(0o600)
    _prune_backups(backup_dir)
    return destination


def _prune_backups(backup_dir: Path) -> None:
    backups = sorted(
        backup_dir.glob("trove-*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = [str(stale) for stale in backups[BACKUP_KEEP:]]
    for stale in backups[BACKUP_KEEP:]:
        stale.unlink(missing_ok=True)
    if removed:
        logger.info(
            "pruned old database backups: %s", ", ".join(removed)
        )


def head_revision(config: Config) -> str | None:
    script = ScriptDirectory.from_config(_alembic_config(config))
    return script.get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        if "alembic_version" not in inspect(connection).get_table_names():
            return None
        return MigrationContext.configure(connection).get_current_revision()


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
            quoted = connection.dialect.identifier_preparer.quote(table)
            # Probe in SQLite's connection-local TEMP schema. Creating and
            # dropping a virtual table in the main schema changes its schema
            # cookie and can race with an FTS query on another connection.
            connection.execute(
                text(f"CREATE VIRTUAL TABLE temp.{quoted} USING fts5(content)")
            )
            connection.execute(text(f"DROP TABLE temp.{quoted}"))
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
