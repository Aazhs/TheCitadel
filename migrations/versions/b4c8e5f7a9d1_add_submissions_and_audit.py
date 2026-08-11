"""add submissions and audit

Revision ID: b4c8e5f7a9d1
Revises: 297b383d89f4
Create Date: 2026-08-07 23:48:32.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c8e5f7a9d1'
down_revision = '297b383d89f4'
branch_labels = None
depends_on = None


def upgrade():
    # events table changes
    op.add_column('events', sa.Column('submission_deadline_utc', sa.DateTime(timezone=True), nullable=True))
    op.add_column('events', sa.Column('results_require_moderator_approval', sa.Boolean(), server_default='true', nullable=False))

    # event_submissions table
    op.create_table(
        'event_submissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('guild_member_id', sa.Integer(), nullable=False),
        sa.Column('questions_solved', sa.Integer(), nullable=False),
        sa.Column('claimed_rank', sa.Integer(), nullable=True),
        sa.Column('claimed_rating_before', sa.Integer(), nullable=True),
        sa.Column('claimed_rating_after', sa.Integer(), nullable=True),
        sa.Column('claimed_rating_change', sa.Integer(), nullable=True),
        sa.Column('evidence_url', sa.String(length=500), nullable=True),
        sa.Column('reflection', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('verified_by_discord_user_id', sa.String(length=20), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('moderator_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['guild_member_id'], ['guild_members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'guild_member_id', name='uq_event_submission')
    )

    # audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('guild_settings_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('performed_by_discord_user_id', sa.String(length=20), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['guild_settings_id'], ['guild_settings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('event_submissions')
    op.drop_column('events', 'results_require_moderator_approval')
    op.drop_column('events', 'submission_deadline_utc')
