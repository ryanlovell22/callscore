"""Shared dashboard multi-line selection via junction table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create junction table
    op.create_table(
        "shared_dashboard_lines",
        sa.Column("shared_dashboard_id", sa.Integer(), sa.ForeignKey("shared_dashboards.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tracking_line_id", sa.Integer(), sa.ForeignKey("tracking_lines.id", ondelete="CASCADE"), primary_key=True),
    )

    # 2. Migrate existing data into the junction table
    conn = op.get_bind()

    # Rows that had a specific tracking_line_id → copy directly
    conn.execute(sa.text("""
        INSERT INTO shared_dashboard_lines (shared_dashboard_id, tracking_line_id)
        SELECT id, tracking_line_id
        FROM shared_dashboards
        WHERE tracking_line_id IS NOT NULL
    """))

    # Rows with partner_id but no tracking_line_id → expand to all active partner lines
    conn.execute(sa.text("""
        INSERT INTO shared_dashboard_lines (shared_dashboard_id, tracking_line_id)
        SELECT sd.id, tl.id
        FROM shared_dashboards sd
        JOIN tracking_lines tl
            ON tl.partner_id = sd.partner_id
            AND tl.account_id = sd.account_id
            AND tl.active = true
        WHERE sd.tracking_line_id IS NULL
            AND sd.partner_id IS NOT NULL
    """))

    # 3. Delete orphan rows where partner_id IS NULL (no real use case)
    conn.execute(sa.text("""
        DELETE FROM shared_dashboards WHERE partner_id IS NULL
    """))

    # 4. Drop old tracking_line_id column
    op.drop_column("shared_dashboards", "tracking_line_id")

    # 5. Make partner_id NOT NULL
    op.alter_column(
        "shared_dashboards",
        "partner_id",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade():
    # Make partner_id nullable again
    op.alter_column(
        "shared_dashboards",
        "partner_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Re-add tracking_line_id column
    op.add_column(
        "shared_dashboards",
        sa.Column("tracking_line_id", sa.Integer(), sa.ForeignKey("tracking_lines.id"), nullable=True),
    )

    # Best-effort: if a shared dashboard has exactly one line, set it
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE shared_dashboards sd
        SET tracking_line_id = sdl.tracking_line_id
        FROM shared_dashboard_lines sdl
        WHERE sdl.shared_dashboard_id = sd.id
            AND (SELECT COUNT(*) FROM shared_dashboard_lines WHERE shared_dashboard_id = sd.id) = 1
    """))

    op.drop_table("shared_dashboard_lines")
