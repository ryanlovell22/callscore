"""Add missed calls and booking details columns to calls

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('calls',
        sa.Column('call_outcome', sa.String(length=20), nullable=False, server_default='answered')
    )
    op.add_column('calls',
        sa.Column('customer_name', sa.String(length=255), nullable=True)
    )
    op.add_column('calls',
        sa.Column('customer_address', sa.Text(), nullable=True)
    )
    op.add_column('calls',
        sa.Column('booking_time', sa.String(length=255), nullable=True)
    )


def downgrade():
    op.drop_column('calls', 'booking_time')
    op.drop_column('calls', 'customer_address')
    op.drop_column('calls', 'customer_name')
    op.drop_column('calls', 'call_outcome')
