from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    source_url_raw: Mapped[str | None] = mapped_column(Text)
    source_url_canonical: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(2048), nullable=False)
    author: Mapped[str | None] = mapped_column(String(1024))
    published_at: Mapped[str | None] = mapped_column(String(128))
    fetched_at: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    duration_sec: Mapped[float | None] = mapped_column()
    summary: Mapped[str | None] = mapped_column(Text)
    consumption_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unstarted", server_default="unstarted"
    )
    audio_position_sec: Mapped[float] = mapped_column(
        nullable=False, default=0.0, server_default="0"
    )
    book_locator: Mapped[str | None] = mapped_column(Text)
    last_consumed_at: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)

    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )
    runs: Mapped[list[Run]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list[ItemTag]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_items_created_at", "created_at"),
        Index("ix_items_updated_at", "updated_at"),
        Index("ix_items_last_consumed_at", "last_consumed_at"),
        Index("ix_items_consumption_state", "consumption_state"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    current_stage: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested_at: Mapped[int | None] = mapped_column(Integer)
    heartbeat_at: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)

    item: Mapped[Item] = relationship(back_populates="runs")
    steps: Mapped[list[RunStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_runs_state", "state"),
        Index("ix_runs_created_at", "created_at"),
        Index(
            "uq_runs_active_item",
            "item_id",
            unique=True,
            sqlite_where=text("state NOT IN ('completed', 'failed', 'cancelled')"),
        ),
    )


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)

    run: Mapped[Run] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("run_id", "stage", "attempt", name="uq_run_steps_attempt"),
        Index("ix_run_steps_run_stage", "run_id", "stage"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column()

    item: Mapped[Item] = relationship(back_populates="artifacts")

    __table_args__ = (UniqueConstraint("item_id", "kind", name="uq_artifacts_item_kind"),)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    __table_args__ = (Index("ix_tags_normalized", "normalized_name"),)


class ItemTag(Base):
    __tablename__ = "item_tags"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="ai")

    item: Mapped[Item] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship()

    __table_args__ = (Index("ix_item_tags_tag", "tag_id"),)


class AiResult(Base):
    __tablename__ = "ai_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_ai_results_item_created", "item_id", "created_at"),)
