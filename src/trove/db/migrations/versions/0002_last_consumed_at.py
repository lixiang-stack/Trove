"""add last consumed timestamp

Revision ID: 0002_last_consumed_at
Revises: 0001_initial
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_last_consumed_at"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("items", sa.Column("last_consumed_at", sa.Integer()))
    op.create_index("ix_items_last_consumed_at", "items", ["last_consumed_at"])
    op.execute(
        """
        UPDATE items
        SET last_consumed_at = updated_at
        WHERE audio_position_sec > 0
           OR book_locator IS NOT NULL
           OR consumption_state != 'unstarted'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_items_last_consumed_at", table_name="items")
    op.drop_column("items", "last_consumed_at")
