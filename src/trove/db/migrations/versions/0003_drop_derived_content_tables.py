"""drop derived content tables

Revision ID: 0003_drop_derived_content_tables
Revises: 0002_last_consumed_at
Create Date: 2026-11-10

The content package is the source of truth for transcript and book content.
These tables only mirrored package documents; they are no longer read.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_drop_derived_content_tables"
down_revision: str | None = "0002_last_consumed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("book_paragraphs")
    op.drop_table("book_chapters")
    op.drop_table("transcript_segments")


def downgrade() -> None:
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
