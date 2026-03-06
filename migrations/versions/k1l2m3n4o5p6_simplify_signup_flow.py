"""Simplify signup flow: partner email nullable, add partner cost_per_lead

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Make partners.email nullable and drop unique constraint
    op.alter_column(
        "partners",
        "email",
        existing_type=sa.String(255),
        nullable=True,
    )
    op.drop_constraint("partners_email_key", "partners", type_="unique")

    # 2. Add partners.cost_per_lead
    op.add_column(
        "partners",
        sa.Column("cost_per_lead", sa.Numeric(10, 2), server_default="0", nullable=False),
    )

    # 3. Migrate existing tracking_lines.cost_per_lead to partners
    # For each partner, take the max cost_per_lead from their assigned lines
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE partners p
        SET cost_per_lead = sub.max_cpl
        FROM (
            SELECT partner_id, MAX(cost_per_lead) AS max_cpl
            FROM tracking_lines
            WHERE partner_id IS NOT NULL AND cost_per_lead > 0
            GROUP BY partner_id
        ) sub
        WHERE p.id = sub.partner_id
    """))


def downgrade():
    op.drop_column("partners", "cost_per_lead")

    op.create_unique_constraint("partners_email_key", "partners", ["email"])
    op.alter_column(
        "partners",
        "email",
        existing_type=sa.String(255),
        nullable=False,
    )
