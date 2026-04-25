"""Add is_duplicate_booking flag to calls

Revision ID: n4o5p6q7r8s9
Revises: 65aeb167c12b
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'n4o5p6q7r8s9'
down_revision = '65aeb167c12b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'calls',
        sa.Column('is_duplicate_booking', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        'ix_call_duplicate_booking', 'calls', ['is_duplicate_booking']
    )


def downgrade():
    op.drop_index('ix_call_duplicate_booking', table_name='calls')
    op.drop_column('calls', 'is_duplicate_booking')
