"""add scoring and leaderboard tables

Revision ID: c5d8f1a2b3e4
Revises: b4c8e5f7a9d1
Create Date: 2026-08-08 19:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d8f1a2b3e4"
down_revision: str | None = "b4c8e5f7a9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- events table: add points_config JSONB column --
    op.add_column(
        "events",
        sa.Column("points_config", sa.dialects.postgresql.JSONB(), nullable=True),
    )

    # -- event_submissions table: add scoring columns --
    op.add_column(
        "event_submissions",
        sa.Column("points_awarded", sa.Integer(), nullable=True),
    )
    op.add_column(
        "event_submissions",
        sa.Column("score_breakdown", sa.dialects.postgresql.JSONB(), nullable=True),
    )

    # -- event_leaderboard_entries table --
    op.create_table(
        "event_leaderboard_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("guild_member_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False),
        sa.Column("score_breakdown", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["guild_member_id"], ["guild_members.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "guild_member_id", name="uq_event_lb_entry"),
    )
    op.create_index(
        "ix_event_lb_event_rank",
        "event_leaderboard_entries",
        ["event_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_lb_event_rank", table_name="event_leaderboard_entries")
    op.drop_table("event_leaderboard_entries")
    op.drop_column("event_submissions", "score_breakdown")
    op.drop_column("event_submissions", "points_awarded")
    op.drop_column("events", "points_config")
