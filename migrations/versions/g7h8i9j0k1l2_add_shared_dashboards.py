"""Add shared dashboards table.

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
"""
from alembic import op
import sqlalchemy as sa

revision = "g7h8i9j0k1l2"
down_revision = "f6g7h8i9j0k1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_dashboards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("tracking_line_id", sa.Integer(), sa.ForeignKey("tracking_lines.id"), nullable=True),
        sa.Column("partner_id", sa.Integer(), sa.ForeignKey("partners.id"), nullable=True),
        sa.Column("share_token", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("show_recordings", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("show_transcripts", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("shared_dashboards")
