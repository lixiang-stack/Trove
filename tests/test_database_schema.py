from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, OperationalError

from trove.clock import utc_ms
from trove.config import Config
from trove.db.engine import create_engine_for, create_session_factory, upgrade_database, verify_fts5
from trove.db.models import (
    Artifact,
    Item,
    ItemTag,
    Run,
    RunStep,
    Tag,
)


def _item(source_key: str = "key-1", *, item_id: str = "item-1", source_path: str | None = None):
    now = utc_ms()
    return Item(
        id=item_id,
        source_key=source_key,
        source_type="local_audio",
        platform="local",
        title="Test Item",
        source_path=source_path,
        fetched_at=now,
        created_at=now,
        updated_at=now,
    )


def _database(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    engine = create_engine_for(config)
    return config, engine, create_session_factory(engine)


def test_migration_creates_tables_and_indexes(tmp_path):
    _, engine, _ = _database(tmp_path)
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
        indexes = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'index'")
            ).scalars()
        )
    assert {
        "items",
        "runs",
        "run_steps",
        "artifacts",
        "tags",
        "item_tags",
        "ai_results",
        "search_fts",
    } <= tables
    assert {
        "transcript_segments",
        "book_chapters",
        "book_paragraphs",
    }.isdisjoint(tables)
    assert "uq_runs_active_item" in indexes
    with engine.connect() as connection:
        schema_sql = " ".join(
            connection.execute(
                text("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
            ).scalars()
        )
    for constraint in (
        "uq_run_steps_attempt",
        "uq_artifacts_item_kind",
    ):
        assert constraint in schema_sql


def test_unique_constraints(tmp_path):
    _, _, sessions = _database(tmp_path)
    with sessions() as session:
        session.add(_item())
        session.commit()
        session.add(_item(source_key="key-1", item_id="item-2"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with sessions() as session:
        session.add(
            Artifact(
                item_id="item-1", kind="audio", path="a.m4a", sha256="x", size=1, mime="audio/mp4"
            )
        )
        session.commit()
        session.add(
            Artifact(
                item_id="item-1", kind="audio", path="b.m4a", sha256="y", size=1, mime="audio/mp4"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with sessions() as session:
        session.add(Tag(name="Memory", normalized_name="memory"))
        session.commit()
        session.add(Tag(name="memory", normalized_name="memory"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with sessions() as session:
        tag = session.query(Tag).filter_by(normalized_name="memory").one()
        session.add(ItemTag(item_id="item-1", tag_id=tag.id, source="ai"))
        session.commit()
        session.add(ItemTag(item_id="item-1", tag_id=tag.id, source="user"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_fts_table_can_be_written_and_deleted(tmp_path):
    _, engine, sessions = _database(tmp_path)
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO search_fts (norm_text, text, item_id, doc_kind, ref) "
                "VALUES (:norm, :text, :item, 'title', 'title')"
            ),
            {"norm": "人工 工智 智能", "text": "人工智能", "item": "item-1"},
        )
        session.commit()
        row = session.execute(
            text("SELECT item_id FROM search_fts WHERE search_fts MATCH '\"人工 工智 智能\"'")
        ).first()
        assert row.item_id == "item-1"
        session.execute(text("DELETE FROM search_fts WHERE item_id = 'item-1'"))
        session.commit()
        assert session.execute(text("SELECT count(*) FROM search_fts")).scalar() == 0


def test_fts5_missing_fails_with_actionable_message(tmp_path, monkeypatch):
    _, engine, _ = _database(tmp_path)
    original = Connection.execute

    def fake_execute(self, statement, *args, **kwargs):
        if "fts5" in str(statement).lower():
            raise OperationalError(
                "CREATE VIRTUAL TABLE",
                {},
                sqlite3.OperationalError("no such module: fts5"),
            )
        return original(self, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", fake_execute)
    with pytest.raises(RuntimeError, match="FTS5"):
        verify_fts5(engine)


def test_delete_cascades_and_keeps_original_file(tmp_path):
    config, _, sessions = _database(tmp_path)
    original = tmp_path / "original.mp3"
    original.write_bytes(b"original")
    with sessions() as session:
        session.add(_item(source_path=str(original)))
        session.add(
            Artifact(
                item_id="item-1",
                kind="audio",
                path="audio.mp3",
                sha256="x",
                size=1,
                mime="audio/mpeg",
            )
        )
        session.add(Run(id="run-1", item_id="item-1", state="completed", created_at=utc_ms()))
        session.add(RunStep(run_id="run-1", stage="indexing", state="completed", attempt=1))
        session.commit()
        session.delete(session.get(Item, "item-1"))
        session.commit()
        assert session.execute(text("SELECT count(*) FROM artifacts")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM runs")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM run_steps")).scalar() == 0
    assert original.exists()
