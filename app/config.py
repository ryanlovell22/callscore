import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///calloutcome.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PREFERRED_URL_SCHEME = "https"

    # Fix Supabase/Railway postgres:// vs postgresql:// issue
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    # Twilio (bootstrap credentials — per-account creds stored in DB)
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

    # Supabase Storage (for manual uploads)
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    # Resend (transactional email)
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Stripe
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
    STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER")
    STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO")
    STRIPE_PRICE_AGENCY = os.environ.get("STRIPE_PRICE_AGENCY")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Admin emails (auto-flagged as is_admin on signup)
    ADMIN_EMAILS = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "lovell.ryan22@gmail.com").split(",")
        if e.strip()
    ]

    # Session cookie security
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") != "development"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours

    # Fernet encryption key for Twilio/CallRail credentials
    FERNET_KEY = os.environ.get("FERNET_KEY")

    # CallRail webhook shared secret
    CALLRAIL_WEBHOOK_SECRET = os.environ.get("CALLRAIL_WEBHOOK_SECRET")

    # Resend webhook signing secret
    RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET")

    # Max upload size: 50MB
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
