"""v1 sync schema

Revision ID: 0004_v1_sync_schema
Revises: 0003_drop_derived_content_tables
Create Date: 2026-11-14

Adds item-level versions, tombstones, content/state sync sequences, device
tokens, field clocks, and idempotency records. Existing Items are backfilled
in a stable created_at/id order.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_v1_sync_schema"
down_revision: str | None = "0003_drop_derived_content_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("content_seq", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("state_seq", sa.Integer(), nullable=False, server_default="0")
        )
    op.create_index("ix_items_content_seq", "items", ["content_seq"])
    op.create_index("ix_items_state_seq", "items", ["state_seq"])

    op.create_table(
        "device_tokens",
        sa.Column("device_id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.Column("session_epoch", sa.Integer(), nullable=False),
    )
    op.create_table(
        "sync_sequence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("epoch", sa.String(length=36), nullable=False),
    )
    op.create_table(
        "sync_field_clocks",
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("field", sa.String(length=32), primary_key=True),
        sa.Column("client_updated_at", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
    )
    op.create_table(
        "sync_mutations",
        sa.Column("device_id", sa.String(length=36), primary_key=True),
        sa.Column("mutation_id", sa.String(length=128), primary_key=True),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_sync_mutations_created_at", "sync_mutations", ["created_at"]
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO sync_sequence (id, value, epoch) VALUES (1, 0, :epoch)"
        ),
        {"epoch": str(uuid.uuid4())},
    )
    item_ids = list(
        connection.execute(
            sa.text("SELECT id FROM items ORDER BY created_at, id")
        ).scalars()
    )
    value = 0
    for item_id in item_ids:
        value += 1
        connection.execute(
            sa.text("UPDATE items SET content_seq = :value WHERE id = :item_id"),
            {"value": value, "item_id": item_id},
        )
        value += 1
        connection.execute(
            sa.text(
                "UPDATE items SET version = 1, state_seq = :value WHERE id = :item_id"
            ),
            {"value": value, "item_id": item_id},
        )
    connection.execute(
        sa.text("UPDATE sync_sequence SET value = :value WHERE id = 1"),
        {"value": value},
    )


def downgrade() -> None:
    op.drop_index("ix_sync_mutations_created_at", table_name="sync_mutations")
    op.drop_table("sync_mutations")
    op.drop_table("sync_field_clocks")
    op.drop_table("sync_sequence")
    op.drop_table("device_tokens")
    op.drop_index("ix_items_state_seq", table_name="items")
    op.drop_index("ix_items_content_seq", table_name="items")
    with op.batch_alter_table("items") as batch:
        batch.drop_column("state_seq")
        batch.drop_column("content_seq")
        batch.drop_column("deleted_at")
        batch.drop_column("version")
