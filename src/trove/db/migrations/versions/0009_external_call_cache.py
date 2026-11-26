"""external call cache keys for AI results

Revision ID: 0009_external_call_cache
Revises: 0008_run_force
Create Date: 2026-11-25

``input_sha256`` is written with each AI result for history and future queries;
the organization cache itself reads ``ai.json`` from the content package. Legacy
rows keep NULL and are treated as cache misses.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_external_call_cache"
down_revision: str | None = "0008_run_force"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_results") as batch:
        batch.add_column(sa.Column("input_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_results") as batch:
        batch.drop_column("input_sha256")
