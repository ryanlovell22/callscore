"""Add Stripe billing fields.

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
"""
from alembic import op
import sqlalchemy as sa

revision = "f6g7h8i9j0k1"
down_revision = "e5f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("accounts", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column("accounts", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
    op.add_column("accounts", sa.Column("stripe_plan", sa.String(20), server_default="free", nullable=True))
    op.add_column("accounts", sa.Column("plan_calls_limit", sa.Integer(), server_default="10", nullable=True))
    op.add_column("accounts", sa.Column("plan_calls_used", sa.Integer(), server_default="0", nullable=True))
    op.add_column("accounts", sa.Column("plan_period_start", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("plan_period_end", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("subscription_status", sa.String(20), server_default="active", nullable=True))


def downgrade():
    op.drop_column("accounts", "subscription_status")
    op.drop_column("accounts", "plan_period_end")
    op.drop_column("accounts", "plan_period_start")
    op.drop_column("accounts", "plan_calls_used")
    op.drop_column("accounts", "plan_calls_limit")
    op.drop_column("accounts", "stripe_plan")
    op.drop_column("accounts", "stripe_subscription_id")
    op.drop_column("accounts", "stripe_customer_id")
