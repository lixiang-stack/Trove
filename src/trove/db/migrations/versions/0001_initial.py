"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_key", sa.String(length=2048), nullable=False, unique=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("source_url_raw", sa.Text()),
        sa.Column("source_url_canonical", sa.Text()),
        sa.Column("source_path", sa.Text()),
        sa.Column("title", sa.String(length=2048), nullable=False),
        sa.Column("author", sa.String(length=1024)),
        sa.Column("published_at", sa.String(length=128)),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=32)),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "consumption_state",
            sa.String(length=16),
            nullable=False,
            server_default="unstarted",
        ),
        sa.Column("audio_position_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("book_locator", sa.Text()),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_items_created_at", "items", ["created_at"])
    op.create_index("ix_items_updated_at", "items", ["updated_at"])
    op.create_index("ix_items_consumption_state", "items", ["consumption_state"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("current_stage", sa.String(length=32)),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("cancel_requested_at", sa.Integer()),
        sa.Column("heartbeat_at", sa.Integer()),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Integer()),
        sa.Column("finished_at", sa.Integer()),
    )
    op.create_index("ix_runs_item_id", "runs", ["item_id"])
    op.create_index("ix_runs_state", "runs", ["state"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    op.create_index(
        "uq_runs_active_item",
        "runs",
        ["item_id"],
        unique=True,
        sqlite_where=sa.text("state NOT IN ('completed', 'failed', 'cancelled')"),
    )

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.Integer()),
        sa.Column("finished_at", sa.Integer()),
        sa.UniqueConstraint("run_id", "stage", "attempt", name="uq_run_steps_attempt"),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_run_steps_run_stage", "run_steps", ["run_id", "stage"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("duration_sec", sa.Float()),
        sa.UniqueConstraint("item_id", "kind", name="uq_artifacts_item_kind"),
    )
    op.create_index("ix_artifacts_item_id", "artifacts", ["item_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("item_id", "seq", name="uq_transcript_item_seq"),
    )
    op.create_index("ix_transcript_segments_item_id", "transcript_segments", ["item_id"])

    op.create_table(
        "book_chapters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("item_id", "chapter_index", name="uq_book_chapters_item_index"),
    )
    op.create_index("ix_book_chapters_item_id", "book_chapters", ["item_id"])

    op.create_table(
        "book_paragraphs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "item_id", "chapter_index", "paragraph_index", name="uq_book_paragraphs_item_ref"
        ),
    )
    op.create_index("ix_book_paragraphs_item_id", "book_paragraphs", ["item_id"])
    op.create_index(
        "ix_book_paragraphs_item_chapter", "book_paragraphs", ["item_id", "chapter_index"]
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False, unique=True),
    )
    op.create_index("ix_tags_normalized", "tags", ["normalized_name"])

    op.create_table(
        "item_tags",
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source", sa.String(length=8), nullable=False, server_default="ai"),
    )
    op.create_index("ix_item_tags_tag", "item_tags", ["tag_id"])

    op.create_table(
        "ai_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
        ),
        sa.Column("summary", sa.Text()),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_ai_results_item_id", "ai_results", ["item_id"])
    op.create_index("ix_ai_results_item_created", "ai_results", ["item_id", "created_at"])

    op.execute(
        """
        CREATE VIRTUAL TABLE search_fts USING fts5(
            norm_text,
            text UNINDEXED,
            item_id UNINDEXED,
            doc_kind UNINDEXED,
            ref UNINDEXED,
            tokenize = 'porter unicode61'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE search_fts")
    op.drop_table("ai_results")
    op.drop_table("item_tags")
    op.drop_table("tags")
    op.drop_table("book_paragraphs")
    op.drop_table("book_chapters")
    op.drop_table("transcript_segments")
    op.drop_table("artifacts")
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("items")
