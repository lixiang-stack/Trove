"""explicit reprocess flag on processing runs

Revision ID: 0008_run_force
Revises: 0007_stage_tasks
Create Date: 2026-11-25

An explicit reprocess marks the Run as forced so all of its attempts bypass the
external-call cache. Normal runs, manual retries, and worker recovery keep the
flag off and can reuse completed LLM/ASR results.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_run_force"
down_revision: str | None = "0007_stage_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(
            sa.Column("force", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("force")
