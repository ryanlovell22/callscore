"""Add retry_count, unique constraints, and indexes

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-03-01 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    # Add retry_count column
    op.add_column('calls',
        sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0')
    )

    # Add unique constraints (NULLs are excluded in PostgreSQL, so uploads
    # and missed calls with NULL SIDs are unaffected)
    op.create_unique_constraint(
        'uq_call_account_call_sid', 'calls',
        ['account_id', 'twilio_call_sid']
    )
    op.create_unique_constraint(
        'uq_call_account_recording_sid', 'calls',
        ['account_id', 'twilio_recording_sid']
    )

    # Add composite indexes for common queries
    op.create_index(
        'ix_call_account_date', 'calls',
        ['account_id', 'call_date']
    )
    op.create_index(
        'ix_call_account_line', 'calls',
        ['account_id', 'tracking_line_id']
    )


def downgrade():
    op.drop_index('ix_call_account_line', table_name='calls')
    op.drop_index('ix_call_account_date', table_name='calls')
    op.drop_constraint('uq_call_account_recording_sid', 'calls', type_='unique')
    op.drop_constraint('uq_call_account_call_sid', 'calls', type_='unique')
    op.drop_column('calls', 'retry_count')
