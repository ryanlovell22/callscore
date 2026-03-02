"""Add booking_date column to calls table

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-03-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('calls', sa.Column('booking_date', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('calls', 'booking_date')
