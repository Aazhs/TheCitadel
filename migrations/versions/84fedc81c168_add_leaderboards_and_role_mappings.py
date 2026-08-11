"""Add leaderboards and role mappings

Revision ID: 84fedc81c168
Revises: c5d8f1a2b3e4
Create Date: 2026-08-08 20:36:25.826936

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op



# revision identifiers, used by Alembic.
revision: str = '84fedc81c168'
down_revision: Union[str, None] = 'c5d8f1a2b3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create role_mappings table
    op.create_table(
        'role_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_settings_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('min_value', sa.Integer(), nullable=True),
        sa.Column('role_id', sa.String(length=20), nullable=False),
        sa.Column('role_name_cache', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['guild_settings_id'], ['guild_settings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 2. Add columns to guild_members
    op.add_column('guild_members', sa.Column('arena_points_all_time', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('arena_points_current_cycle', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('events_participated', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('verified_results_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('problems_solved_total', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('current_streak', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('longest_streak', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('cp_star_rating', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guild_members', sa.Column('dsa_star_rating', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('guild_members', 'dsa_star_rating')
    op.drop_column('guild_members', 'cp_star_rating')
    op.drop_column('guild_members', 'longest_streak')
    op.drop_column('guild_members', 'current_streak')
    op.drop_column('guild_members', 'problems_solved_total')
    op.drop_column('guild_members', 'verified_results_count')
    op.drop_column('guild_members', 'events_participated')
    op.drop_column('guild_members', 'arena_points_current_cycle')
    op.drop_column('guild_members', 'arena_points_all_time')
    op.drop_table('role_mappings')
