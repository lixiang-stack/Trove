"""carry W3C trace context on stage tasks

Revision ID: 0010_stage_traceparent
Revises: 0009_external_call_cache
Create Date: 2026-11-27

The API records the active ``traceparent`` when it enqueues a stage task; the
worker extracts it before running the stage so one trace covers HTTP, queue,
stage, and adapter spans.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_stage_traceparent"
down_revision: str | None = "0009_external_call_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("run_steps") as batch:
        batch.add_column(sa.Column("traceparent", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("run_steps") as batch:
        batch.drop_column("traceparent")
