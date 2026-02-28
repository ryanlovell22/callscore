from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Account(UserMixin, db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    twilio_account_sid = db.Column(db.String(255))
    twilio_auth_token_encrypted = db.Column(db.Text)
    twilio_service_sid = db.Column(db.String(255))
    webhook_secret = db.Column(db.String(255))
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )

    tracking_lines = db.relationship("TrackingLine", backref="account", lazy=True)
    calls = db.relationship("Call", backref="account", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class TrackingLine(db.Model):
    __tablename__ = "tracking_lines"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    twilio_phone_number = db.Column(db.String(20))
    label = db.Column(db.String(255))
    partner_name = db.Column(db.String(255))
    partner_phone = db.Column(db.String(20))
    cost_per_lead = db.Column(db.Numeric(10, 2), default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )

    calls = db.relationship("Call", backref="tracking_line", lazy=True)


class Call(db.Model):
    __tablename__ = "calls"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    tracking_line_id = db.Column(
        db.Integer, db.ForeignKey("tracking_lines.id"), nullable=True
    )
    twilio_call_sid = db.Column(db.String(255))
    twilio_recording_sid = db.Column(db.String(255))
    caller_number = db.Column(db.String(20))
    call_duration = db.Column(db.Integer)
    call_date = db.Column(db.DateTime)
    recording_url = db.Column(db.Text)
    source = db.Column(db.String(20), default="twilio")

    # Analysis results
    transcript_sid = db.Column(db.String(255))
    status = db.Column(db.String(20), default="pending")
    classification = db.Column(db.String(20))
    confidence = db.Column(db.Numeric(3, 2))
    summary = db.Column(db.Text)
    service_type = db.Column(db.String(100))
    urgent = db.Column(db.Boolean)
    full_transcript = db.Column(db.Text)
    analysed_at = db.Column(db.DateTime)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    tracking_line_id = db.Column(
        db.Integer, db.ForeignKey("tracking_lines.id"), nullable=True
    )
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    total_calls = db.Column(db.Integer)
    booked_calls = db.Column(db.Integer)
    amount = db.Column(db.Numeric(10, 2))
    status = db.Column(db.String(20), default="draft")
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
