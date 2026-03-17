# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What It Is

CallOutcome is a SaaS app for rank-and-rent / lead gen businesses. It pulls call recordings from Twilio (or CallRail), transcribes them with OpenAI Whisper, classifies whether a job was booked using GPT-4o-mini, and displays results on a dashboard. Live at https://calloutcome.com.

## Development Commands

```bash
# Run locally (port 5099)
export $(cat ~/.claude/credentials.env | grep -v '^#' | xargs)
cd /Users/ryanlovell/Desktop/Vibe\ Coding\ Ideas/calloutcome
./venv/bin/flask run --port 5099

# Database migrations
./venv/bin/flask db migrate -m "description"
./venv/bin/flask db upgrade

# Cron job (poll Twilio for new calls)
./venv/bin/python scripts/poll_twilio.py          # normal (24hr lookback)
./venv/bin/python scripts/poll_twilio.py --days 7  # backfill
```

**Python 3.9** — use `method='pbkdf2:sha256'` for password hashing.

## Tech Stack

- **Framework:** Flask + Jinja2 (server-rendered)
- **Database:** PostgreSQL on Supabase (via SQLAlchemy + Flask-Migrate)
- **Auth:** Flask-Login (session-based, `account:ID` / `partner:ID` prefixed IDs)
- **Security:** Flask-WTF (CSRF), Fernet encryption (credentials at rest via `app/encryption.py`), webhook signature verification (Twilio/CallRail/Resend), session cookie hardening, security headers
- **AI:** OpenAI Whisper (transcription) + GPT-4o-mini (classification) — ~$0.03-0.04/call
- **Billing:** Stripe Checkout + Customer Portal
- **Email:** Resend (transactional send from `noreply@calloutcome.com` + inbound forwarding `*@calloutcome.com` → `admin@lovelldigitalproperties.com`)
- **CSS:** Pico CSS (classless, CDN, dark mode)
- **Deploy:** Railway (web via gunicorn + cron-poll service)

## Architecture

### Call Processing Pipeline

1. **Ingestion** — Cron (`scripts/poll_twilio.py`) runs every 5 min on Railway, calls `app/poll_service.py` which handles: answered calls with recordings, missed calls, short answered calls, and retries of failed submissions
2. **Transcription** — `app/ai_classifier.py:transcribe_recording()` downloads audio and sends to Whisper
3. **Classification** — `app/ai_classifier.py:classify_transcript()` sends transcript to GPT-4o-mini with structured JSON output. Returns: classification (JOB_BOOKED/NOT_BOOKED/VOICEMAIL), confidence, summary, service_type, urgency, customer details, booking date
4. **Manual upload** — Users can upload audio files via `/upload`, processed through same AI pipeline
5. **CallRail** — Alternative to Twilio; uses CallRail API for call ingestion (`app/callrail_service.py`)
6. **Inbound email** — Resend webhook at `/webhooks/resend-inbound` receives `email.received` events, fetches full content, and forwards to admin@lovelldigitalproperties.com

### Multi-Tenancy

- `account_id` FK on all data tables (Call, TrackingLine, Invoice, SharedDashboard)
- Two user types: **Account** (full access) and **Partner** (view-only, filtered to their tracking lines)
- Flask-Login distinguishes via prefixed IDs (`account:1`, `partner:1`)
- `@account_required` decorator in `app/decorators.py` blocks partner access to admin routes

### Blueprints

The app factory (`app/__init__.py:create_app()`) registers 11 blueprints: auth, dashboard, lines, webhooks, upload, partners, settings, landing, billing, onboarding, blog, shared. Routes live in `app/<blueprint>/routes.py`.

### Key Models (`app/models.py`)

- **Account** — tenant, Twilio/CallRail credentials (Fernet-encrypted via properties `twilio_auth_token`/`callrail_api_key`), Stripe billing fields, usage tracking
- **Partner** — view-only user with flexible pricing (per-lead, per-call, per-voicemail, weekly minimum)
- **TrackingLine** — phone number (Twilio or CallRail) linked to account + optional partner
- **Call** — recording metadata, transcript, AI classification, booking details. Deduped via unique constraints on `(account_id, twilio_call_sid)`, `(account_id, twilio_recording_sid)`, `(account_id, callrail_call_id)`
- **SharedDashboard** — token-based public dashboard for partners (configurable visibility, date windows)

### Billing

Stripe Checkout + Customer Portal. Tiers: Free (50 calls), Starter ($29/100), Pro ($79/500), Agency ($149/1500). Usage tracked via `plan_calls_used` / `plan_calls_limit` on Account. Calls at limit get `status="limit_reached"`.

## Environment Variables

All credentials in `~/.claude/credentials.env`. Key vars: `DATABASE_URL`, `SECRET_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `OPENAI_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STARTER/PRO/AGENCY`, `RESEND_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `FERNET_KEY`, `CALLRAIL_WEBHOOK_SECRET`, `RESEND_WEBHOOK_SECRET`.

## Deploy

Railway project with two services:
- **web** — `railway.toml` runs migrations then gunicorn (timeout 120s, healthcheck at `/health`)
- **cron-poll** — runs `scripts/poll_twilio.py` every 5 minutes

Custom domain: calloutcome.com (DNS on Hostinger, ALIAS/CNAME records to Railway).
