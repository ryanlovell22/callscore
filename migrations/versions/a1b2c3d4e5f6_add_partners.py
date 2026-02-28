"""Add partners table and partner_id to tracking_lines

Revision ID: a1b2c3d4e5f6
Revises: 16d9006fd983
Create Date: 2026-02-28 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '16d9006fd983'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('partners',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.add_column('tracking_lines',
        sa.Column('partner_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_tracking_lines_partner_id',
        'tracking_lines', 'partners',
        ['partner_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_tracking_lines_partner_id', 'tracking_lines', type_='foreignkey')
    op.drop_column('tracking_lines', 'partner_id')
    op.drop_table('partners')
