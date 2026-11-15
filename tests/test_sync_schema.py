from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from trove.clock import utc_ms
from trove.config import Config
from trove.db.engine import (
    MIGRATIONS_DIR,
    create_engine_for,
    create_session_factory,
    upgrade_database,
)
from trove.db.models import DeviceToken, Item, SyncMutation


def _alembic_config(config: Config) -> AlembicConfig:
    alembic = AlembicConfig()
    alembic.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic.set_main_option("sqlalchemy.url", f"sqlite:///{config.db_path}")
    return alembic


def _database(tmp_path: Path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    engine = create_engine_for(config)
    return config, engine, create_session_factory(engine)


def _mvp_item(item_id: str, created_at: int) -> str:
    return (
        "INSERT INTO items (id, source_key, source_type, platform, title, fetched_at, "
        "consumption_state, audio_position_sec, created_at, updated_at) VALUES "
        f"('{item_id}', 'key-{item_id}', 'local_audio', 'local', 'Item {item_id}', "
        f"{created_at}, 'unstarted', 0, {created_at}, {created_at})"
    )


def test_migration_creates_v1_tables_columns_and_indexes(tmp_path):
    _, engine, _ = _database(tmp_path)
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
        item_columns = {
            row.name for row in connection.execute(text("PRAGMA table_info(items)"))
        }
        indexes = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'index'")
            ).scalars()
        )
    assert {"device_tokens", "sync_sequence", "sync_field_clocks", "sync_mutations"} <= tables
    assert {"version", "deleted_at", "content_seq", "state_seq"} <= item_columns
    assert {"ix_items_content_seq", "ix_items_state_seq"} <= indexes


def test_empty_database_backfills_sequence_row(tmp_path):
    _, engine, _ = _database(tmp_path)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT value, epoch FROM sync_sequence WHERE id = 1")
        ).one()
        items = connection.execute(text("SELECT count(*) FROM items")).scalar()
    assert row.value == 0
    assert row.epoch
    assert items == 0


def test_mvp_database_backfills_version_and_sequences_stably(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    command.upgrade(_alembic_config(config), "0003_drop_derived_content_tables")
    engine = create_engine_for(config)
    with engine.begin() as connection:
        connection.execute(text(_mvp_item("older", 1000)))
        connection.execute(text(_mvp_item("newer", 2000)))
    engine.dispose()

    upgrade_database(config)
    upgrade_database(config)

    engine = create_engine_for(config)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, version, content_seq, state_seq FROM items "
                "ORDER BY content_seq"
            )
        ).all()
        sequence = connection.execute(
            text("SELECT value FROM sync_sequence WHERE id = 1")
        ).scalar()
    assert [row.id for row in rows] == ["older", "newer"]
    assert all(row.version == 1 for row in rows)
    assert all(row.content_seq and row.state_seq for row in rows)
    assert rows[0].content_seq < rows[1].content_seq
    assert rows[0].state_seq < rows[1].state_seq
    assert sequence >= max(row.content_seq for row in rows)
    assert sequence >= max(row.state_seq for row in rows)


def test_migration_failure_rolls_back(tmp_path, monkeypatch):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    command.upgrade(_alembic_config(config), "0003_drop_derived_content_tables")
    engine = create_engine_for(config)
    with engine.begin() as connection:
        connection.execute(text(_mvp_item("rollback", 1000)))
    engine.dispose()

    from alembic import op

    original = op.create_index

    def fail_content_index(name: str, *args, **kwargs):
        if name == "ix_items_content_seq":
            raise RuntimeError("simulated migration failure")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(op, "create_index", fail_content_index)
    with pytest.raises(RuntimeError, match="simulated migration failure"):
        upgrade_database(config)

    engine = create_engine_for(config)
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        columns = {
            row.name for row in connection.execute(text("PRAGMA table_info(items)"))
        }
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
    assert revision == "0003_drop_derived_content_tables"
    assert "version" not in columns
    assert "sync_sequence" not in tables


def test_device_token_and_mutation_unique_constraints(tmp_path):
    _, _, sessions = _database(tmp_path)
    now = utc_ms()
    with sessions() as session:
        session.add(
            DeviceToken(
                device_id="device-1",
                name="Pixel",
                token_hash="hash-1",
                created_at=now,
                last_used_at=now,
                session_epoch=1,
            )
        )
        session.commit()
        session.add(
            DeviceToken(
                device_id="device-2",
                name="Tablet",
                token_hash="hash-1",
                created_at=now,
                last_used_at=now,
                session_epoch=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with sessions() as session:
        session.add(
            SyncMutation(
                device_id="device-1",
                mutation_id="mutation-1",
                response_json="{}",
                created_at=now,
            )
        )
        session.commit()
        session.add(
            SyncMutation(
                device_id="device-1",
                mutation_id="mutation-1",
                response_json="{}",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_new_items_get_sync_sequences(tmp_path):
    _, _, sessions = _database(tmp_path)
    now = utc_ms()

    def item(item_id: str, created_at: int) -> Item:
        return Item(
            id=item_id,
            source_key=f"key-{item_id}",
            source_type="local_audio",
            platform="local",
            title=item_id,
            fetched_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )

    with sessions() as session:
        session.add(item("first", now))
        session.commit()
        first = session.get(Item, "first")
        first_content_seq = first.content_seq
        first_state_seq = first.state_seq

    with sessions() as session:
        session.add(item("second", now + 1))
        session.commit()
        second = session.get(Item, "second")

    assert first.version == 1
    assert first_content_seq > 0
    assert first_state_seq > 0
    assert second.content_seq > first.content_seq
    assert second.state_seq > first.state_seq
