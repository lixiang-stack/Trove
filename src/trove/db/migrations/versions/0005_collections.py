"""video collections and EPUB URL intake

Revision ID: 0005_collections
Revises: 0004_v1_sync_schema
Create Date: 2026-11-17

Adds the Collection aggregate and the nullable Item membership fields. A
Collection is not consumable itself; its episodes are regular Items and keep
their own Processing Runs, artifacts, and sync sequences.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_collections"
down_revision: str | None = "0004_v1_sync_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_key", sa.String(length=2048), nullable=False, unique=True),
        sa.Column("source_url_raw", sa.Text(), nullable=True),
        sa.Column("source_url_canonical", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=2048), nullable=False),
        sa.Column("author", sa.String(length=1024), nullable=True),
        sa.Column("episode_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_sec", sa.Float(), nullable=True),
        sa.Column("deleted_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_collections_created_at", "collections", ["created_at"])
    op.create_index("ix_collections_updated_at", "collections", ["updated_at"])

    with op.batch_alter_table("items") as batch:
        batch.add_column(sa.Column("collection_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("collection_index", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_items_collection_id",
            "collections",
            ["collection_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_items_collection_id", ["collection_id"], unique=False
        )
        batch.create_index(
            "ix_items_collection_order",
            ["collection_id", "collection_index"],
            unique=False,
        )
        batch.create_unique_constraint(
            "uq_items_collection_index", ["collection_id", "collection_index"]
        )


def downgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.drop_constraint("uq_items_collection_index", type_="unique")
        batch.drop_index("ix_items_collection_order")
        batch.drop_index("ix_items_collection_id")
        batch.drop_constraint("fk_items_collection_id", type_="foreignkey")
        batch.drop_column("collection_index")
        batch.drop_column("collection_id")
    op.drop_index("ix_collections_updated_at", table_name="collections")
    op.drop_index("ix_collections_created_at", table_name="collections")
    op.drop_table("collections")
