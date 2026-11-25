"""stage task queue: lease, availability, and dead letters

Revision ID: 0007_stage_tasks
Revises: 0006_idempotency_keys
Create Date: 2026-11-25

Upgrades ``run_steps`` into claimable StageTasks. Each row is one attempt for a
stage; workers claim the queued row, renew its lease, and the reaper requeues
expired rows as new attempts. Existing active Runs are backfilled with a queued
task for their next pending stage so they continue on the new queue.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_stage_tasks"
down_revision: str | None = "0006_idempotency_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_ATTEMPTS = 3

STAGE_ORDER: dict[str, tuple[str, ...]] = {
    "video_url": (
        "downloading",
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ),
    "podcast_episode": (
        "downloading",
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ),
    "local_audio": (
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ),
    "local_video": (
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ),
    "epub": ("extracting_text", "organizing", "indexing"),
    "epub_url": ("downloading", "extracting_text", "organizing", "indexing"),
}


def upgrade() -> None:
    with op.batch_alter_table("run_steps") as batch:
        batch.add_column(
            sa.Column(
                "max_attempts",
                sa.Integer(),
                nullable=False,
                server_default=str(MAX_ATTEMPTS),
            )
        )
        batch.add_column(
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("available_at", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("lease_until", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("worker_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_run_steps_claim", "run_steps", ["state", "available_at", "priority"]
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE run_steps SET state = 'failed', "
            "error_code = COALESCE(error_code, 'run.reclaimed'), "
            "error_message = COALESCE(error_message, "
            "'Host stopped before the stage finished') "
            "WHERE state = 'running' AND run_id IN "
            "(SELECT id FROM runs WHERE state = 'failed')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE run_steps SET state = 'cancelled', "
            "error_code = COALESCE(error_code, 'run.cancelled'), "
            "error_message = COALESCE(error_message, 'Cancelled') "
            "WHERE state = 'running' AND run_id IN "
            "(SELECT id FROM runs WHERE state = 'cancelled')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE run_steps SET state = 'queued', lease_until = NULL, "
            "worker_id = NULL, available_at = 0 "
            "WHERE state = 'running' AND run_id IN "
            "(SELECT id FROM runs WHERE state NOT IN "
            "('completed', 'failed', 'cancelled'))"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE runs SET state = 'queued' "
            "WHERE state NOT IN ('queued', 'completed', 'failed', 'cancelled')"
        )
    )

    now = int(time.time() * 1000)
    active_runs = bind.execute(
        sa.text(
            "SELECT runs.id AS run_id, items.source_type AS source_type "
            "FROM runs JOIN items ON items.id = runs.item_id "
            "WHERE runs.state = 'queued'"
        )
    ).mappings()
    for row in active_runs:
        run_id = row["run_id"]
        pending = bind.execute(
            sa.text(
                "SELECT 1 FROM run_steps "
                "WHERE run_id = :run_id AND state IN ('queued', 'running') LIMIT 1"
            ),
            {"run_id": run_id},
        ).first()
        if pending is not None:
            continue
        completed = {
            stage
            for (stage,) in bind.execute(
                sa.text(
                    "SELECT stage FROM run_steps "
                    "WHERE run_id = :run_id AND state = 'completed'"
                ),
                {"run_id": run_id},
            )
        }
        stages = STAGE_ORDER.get(str(row["source_type"]), ())
        if not stages:
            bind.execute(
                sa.text(
                    "UPDATE runs SET state = 'failed', error_code = 'internal.error', "
                    "error_message = 'Unsupported content type', "
                    "finished_at = COALESCE(finished_at, :now) WHERE id = :run_id"
                ),
                {"now": now, "run_id": run_id},
            )
            continue
        next_stage = next((stage for stage in stages if stage not in completed), None)
        if next_stage is None:
            bind.execute(
                sa.text(
                    "UPDATE runs SET state = 'completed', "
                    "finished_at = COALESCE(finished_at, :now) WHERE id = :run_id"
                ),
                {"now": now, "run_id": run_id},
            )
            continue
        latest_attempt = bind.execute(
            sa.text(
                "SELECT MAX(attempt) FROM run_steps "
                "WHERE run_id = :run_id AND stage = :stage"
            ),
            {"run_id": run_id, "stage": next_stage},
        ).scalar()
        bind.execute(
            sa.text(
                "INSERT INTO run_steps "
                "(run_id, stage, state, attempt, max_attempts, priority, "
                "available_at, started_at) "
                "VALUES (:run_id, :stage, 'queued', :attempt, :max_attempts, 0, 0, NULL)"
            ),
            {
                "run_id": run_id,
                "stage": next_stage,
                "attempt": int(latest_attempt or 0) + 1,
                "max_attempts": MAX_ATTEMPTS,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE run_steps SET state = 'failed' WHERE state = 'dead'"))
    bind.execute(sa.text("UPDATE run_steps SET state = 'running' WHERE state = 'queued'"))
    bind.execute(
        sa.text(
            "UPDATE runs SET state = COALESCE(current_stage, 'queued') "
            "WHERE state = 'queued'"
        )
    )
    op.drop_index("ix_run_steps_claim", table_name="run_steps")
    with op.batch_alter_table("run_steps") as batch:
        batch.drop_column("worker_id")
        batch.drop_column("lease_until")
        batch.drop_column("available_at")
        batch.drop_column("priority")
        batch.drop_column("max_attempts")
