"""Initial tables: guild_settings, users, guild_members

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guild_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_guild_id", sa.String(20), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("onboarding_channel_id", sa.String(20), nullable=True),
        sa.Column("announcement_channel_id", sa.String(20), nullable=True),
        sa.Column("contest_alert_channel_id", sa.String(20), nullable=True),
        sa.Column("alert_role_id", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_guild_id"),
    )
    op.create_index("ix_guild_settings_discord_guild_id", "guild_settings", ["discord_guild_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_user_id", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_user_id"),
    )
    op.create_index("ix_users_discord_user_id", "users", ["discord_user_id"])

    op.create_table(
        "guild_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_settings_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "verified_competitor", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["guild_settings_id"], ["guild_settings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("guild_settings_id", "user_id", name="uq_guild_member"),
    )


def downgrade() -> None:
    op.drop_table("guild_members")
    op.drop_index("ix_users_discord_user_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_guild_settings_discord_guild_id", table_name="guild_settings")
    op.drop_table("guild_settings")
