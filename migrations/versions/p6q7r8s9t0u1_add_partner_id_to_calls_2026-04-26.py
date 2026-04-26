"""Add partner_id to calls (snapshot partner attribution at call time)

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa

revision = 'p6q7r8s9t0u1'
down_revision = 'o5p6q7r8s9t0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('calls', sa.Column('partner_id', sa.Integer(), nullable=True))
    op.create_index('ix_call_partner_id', 'calls', ['partner_id'])
    op.create_foreign_key(
        'fk_call_partner_id', 'calls', 'partners', ['partner_id'], ['id'],
        ondelete='SET NULL'
    )
    # Backfill existing calls from current tracking line assignments (best effort)
    op.execute("""
        UPDATE calls
        SET partner_id = tracking_lines.partner_id
        FROM tracking_lines
        WHERE calls.tracking_line_id = tracking_lines.id
          AND tracking_lines.partner_id IS NOT NULL
    """)


def downgrade():
    op.drop_constraint('fk_call_partner_id', 'calls', type_='foreignkey')
    op.drop_index('ix_call_partner_id', table_name='calls')
    op.drop_column('calls', 'partner_id')
