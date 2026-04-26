"""Weekly cron: generate Stripe draft invoices for all partners with a Stripe customer ID.

Runs every Sunday at 9pm AEST (11am UTC) via Railway Cron Jobs:
    python scripts/generate_invoices.py

Dry run (prints what would be created, does not touch Stripe):
    python scripts/generate_invoices.py --dry-run

Manual run for a specific week ending on a given Sunday:
    python scripts/generate_invoices.py --week-ending 2026-04-19
"""

import argparse
import os
import sys
import logging
from datetime import datetime, timedelta, date, timezone

import pytz
import stripe

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Account, Partner, Call, SharedDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_week_range(local_tz, reference_date=None):
    """Return (period_start, period_end) for the most recently completed Mon–Sun week.

    Works correctly whether called on Sunday, Monday, or any other day — always
    returns the same completed week until the next Sunday rolls over.
    """
    if reference_date is None:
        reference_date = datetime.now(local_tz).date()
    # weekday(): Mon=0 … Sun=6. Days since last Sunday = (weekday+1) % 7
    days_since_sunday = (reference_date.weekday() + 1) % 7
    period_end = reference_date - timedelta(days=days_since_sunday)    # most recent Sunday
    period_start = period_end - timedelta(days=6)                       # Monday before that
    return period_start, period_end


def to_utc(local_date, local_tz, end_of_day=False):
    """Convert a local date to a UTC-aware datetime for DB queries."""
    if end_of_day:
        local_dt = local_tz.localize(datetime(local_date.year, local_date.month, local_date.day, 23, 59, 59))
    else:
        local_dt = local_tz.localize(datetime(local_date.year, local_date.month, local_date.day, 0, 0, 0))
    return local_dt.astimezone(pytz.utc)


def get_call_stats(partner, account_id, dt_start_utc, dt_end_utc):
    """Return call stats dict for a partner over the given UTC date range.

    Uses the snapshotted partner_id on each call so that line reassignments
    don't retroactively change which calls count toward each partner.
    """
    calls = Call.query.filter(
        Call.account_id == account_id,
        Call.partner_id == partner.id,
        Call.call_date >= dt_start_utc,
        Call.call_date < dt_end_utc,
    ).all()

    booked = sum(1 for c in calls if c.classification == 'JOB_BOOKED')
    not_booked = sum(1 for c in calls if c.call_outcome == 'answered' and c.classification != 'JOB_BOOKED')
    missed = sum(1 for c in calls if c.call_outcome == 'missed')
    answered = booked + not_booked
    total = answered + missed

    conversion_pct = round(booked / answered * 100) if answered else 0
    missed_pct = round(missed / total * 100) if total else 0

    return dict(calls=calls, booked=booked, not_booked=not_booked, missed=missed,
                answered=answered, total=total, conversion_pct=conversion_pct,
                missed_pct=missed_pct)


def calculate_amount(partner, stats):
    """Return (qty, unit_price_dollars, line_description, amount_dollars) based on pricing model."""
    model = partner.pricing_model or 'standard'

    if model in ('standard', 'per_lead'):
        unit_price = float(partner.cost_per_lead or 0)
        qty = stats['booked']
        description = 'Booked Lead'

    elif model == 'per_call':
        unit_price = float(partner.cost_per_call or 0)
        qty = stats['answered']
        description = 'Answered Call'

    elif model == 'per_qualified_call':
        threshold = partner.qualified_call_seconds or 60
        unit_price = float(partner.cost_per_qualified_call or 0)
        qty = sum(
            1 for c in stats['calls']
            if c.call_outcome == 'answered' and (c.call_duration or 0) >= threshold
        )
        description = f'Qualified Call (>{threshold}s)'

    else:
        unit_price = float(partner.cost_per_lead or 0)
        qty = stats['booked']
        description = 'Booked Lead'

    amount = unit_price * qty

    # Apply weekly minimum if set and amount falls short
    min_fee = float(partner.weekly_minimum_fee or 0)
    if min_fee > 0 and amount < min_fee:
        amount = min_fee

    return qty, unit_price, description, amount


def build_memo(stats, period_start, period_end, dashboard_url):
    """Build the invoice memo/description block."""
    period_label = f"{period_start.strftime('%-d %b')} – {period_end.strftime('%-d %b %Y')}"
    lines = [
        f"Service Period: {period_label}",
        "",
        f"- {stats['booked']} Booked",
        f"- {stats['not_booked']} Not Booked",
        f"- {stats['missed']} Missed",
        f"- {stats['conversion_pct']}% Conversion",
        f"- {stats['missed_pct']}% Missed",
    ]
    if dashboard_url:
        lines += ["", "Call Outcome Dashboard:", dashboard_url]
    return "\n".join(lines)


def draft_already_exists(partner_id, period_start):
    """Check Stripe for an existing draft invoice for this partner + period."""
    try:
        results = stripe.Invoice.search(
            query=(
                f"metadata['partner_id']:'{partner_id}' "
                f"AND metadata['period_start']:'{period_start.isoformat()}'"
            )
        )
        # Filter to only active drafts (search index can return recently-deleted invoices)
        active_drafts = [inv for inv in results.data if inv.status == 'draft']
        return bool(active_drafts)
    except stripe.StripeError as e:
        logger.warning("Stripe search error (will proceed): %s", e)
        return False


def generate_invoice_for_partner(partner, account, period_start, period_end, dry_run):
    """Create a Stripe draft invoice for one partner. Returns True on success."""
    local_tz = pytz.timezone(account.timezone or 'Australia/Adelaide')
    dt_start_utc = to_utc(period_start, local_tz, end_of_day=False)
    dt_end_utc = to_utc(period_end, local_tz, end_of_day=True)

    # Fetch dashboard first — its tracking lines determine what gets billed
    dashboard = SharedDashboard.query.filter_by(
        account_id=account.id,
        partner_id=partner.id,
        active=True,
    ).first()

    stats = get_call_stats(partner, account.id, dt_start_utc, dt_end_utc)
    qty, unit_price, line_desc, amount = calculate_amount(partner, stats)

    dashboard_url = None
    if dashboard:
        dashboard_url = (
            f"https://calloutcome.com/proof/{dashboard.share_token}"
            f"?date_from={period_start.isoformat()}&date_to={period_end.isoformat()}"
        )

    memo = build_memo(stats, period_start, period_end, dashboard_url)
    period_label = f"{period_start.strftime('%-d %b')} – {period_end.strftime('%-d %b %Y')}"

    logger.info(
        "Partner: %s | Period: %s | Booked: %d | Not Booked: %d | Missed: %d | Amount: $%.2f",
        partner.name, period_label, stats['booked'], stats['not_booked'], stats['missed'], amount,
    )

    if dry_run:
        logger.info("[DRY RUN] Would create Stripe draft invoice for %s: $%.2f", partner.name, amount)
        if memo:
            for line in memo.splitlines():
                logger.info("  %s", line)
        return True

    if draft_already_exists(partner.id, period_start):
        logger.info("Draft already exists for %s (%s) — skipping", partner.name, period_label)
        return True

    # Create the draft invoice
    invoice = stripe.Invoice.create(
        customer=partner.stripe_customer_id,
        collection_method='send_invoice',
        days_until_due=7,
        auto_advance=False,
        currency='aud',
        description=memo,
        metadata={
            'partner_id': str(partner.id),
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
        },
    )

    # Add line items (even for $0 we leave the invoice empty — Stripe shows $0.00 due)
    if qty > 0 and unit_price > 0:
        line_total_cents = int(round(unit_price * qty * 100))
        stripe.InvoiceItem.create(
            customer=partner.stripe_customer_id,
            invoice=invoice.id,
            amount=line_total_cents,
            currency='aud',
            description=f'{qty} x {line_desc} @ A${unit_price:.2f}',
        )
        # Weekly minimum top-up
        topup_cents = int(round((amount - unit_price * qty) * 100))
        if topup_cents > 0:
            stripe.InvoiceItem.create(
                customer=partner.stripe_customer_id,
                invoice=invoice.id,
                amount=topup_cents,
                currency='aud',
                description='Weekly minimum fee top-up',
            )

    logger.info("Created draft invoice %s for %s ($%.2f)", invoice.id, partner.name, amount)
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate weekly Stripe draft invoices")
    parser.add_argument('--dry-run', action='store_true',
                        help="Print what would be created without touching Stripe")
    parser.add_argument('--week-ending', metavar='YYYY-MM-DD',
                        help="Override the Sunday end date (default: most recently completed week)")
    args = parser.parse_args()

    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    if not stripe.api_key:
        logger.error("STRIPE_SECRET_KEY not set")
        sys.exit(1)

    override_date = None
    if args.week_ending:
        override_date = date.fromisoformat(args.week_ending)

    app = create_app()
    with app.app_context():
        accounts = Account.query.all()
        for account in accounts:
            local_tz = pytz.timezone(account.timezone or 'Australia/Adelaide')

            if override_date:
                period_end = override_date
                period_start = period_end - timedelta(days=6)
            else:
                period_start, period_end = get_week_range(local_tz)

            partners = Partner.query.filter(
                Partner.account_id == account.id,
                Partner.stripe_customer_id.isnot(None),
            ).all()

            if not partners:
                continue

            logger.info(
                "Account: %s | Week: %s – %s | Partners: %d",
                account.name, period_start, period_end, len(partners),
            )

            for partner in partners:
                try:
                    generate_invoice_for_partner(partner, account, period_start, period_end, args.dry_run)
                except Exception:
                    logger.exception("Error generating invoice for partner %s", partner.name)


if __name__ == '__main__':
    main()
