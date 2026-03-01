"""Add timezone column to accounts

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-01 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts',
        sa.Column('timezone', sa.String(length=50), server_default='Australia/Adelaide', nullable=True)
    )


def downgrade():
    op.drop_column('accounts', 'timezone')
