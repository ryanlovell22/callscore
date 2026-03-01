"""Add CallRail integration fields.

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6g7h8i9j0"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade():
    # Account: CallRail fields
    op.add_column("accounts", sa.Column("callrail_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("callrail_account_id", sa.String(50), nullable=True))
    op.add_column("accounts", sa.Column("call_source", sa.String(20), server_default="twilio", nullable=True))

    # Call: CallRail call ID
    op.add_column("calls", sa.Column("callrail_call_id", sa.String(50), nullable=True))
    op.create_unique_constraint("uq_call_account_callrail_id", "calls", ["account_id", "callrail_call_id"])

    # TrackingLine: CallRail tracker fields
    op.add_column("tracking_lines", sa.Column("callrail_tracker_id", sa.String(50), nullable=True))
    op.add_column("tracking_lines", sa.Column("callrail_tracking_number", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("tracking_lines", "callrail_tracking_number")
    op.drop_column("tracking_lines", "callrail_tracker_id")
    op.drop_constraint("uq_call_account_callrail_id", "calls", type_="unique")
    op.drop_column("calls", "callrail_call_id")
    op.drop_column("accounts", "call_source")
    op.drop_column("accounts", "callrail_account_id")
    op.drop_column("accounts", "callrail_api_key_encrypted")
