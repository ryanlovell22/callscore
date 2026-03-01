"""Cron job: Poll Twilio for new recordings and submit to Conversational Intelligence.

Run every 5 minutes via Railway Cron Jobs:
    python scripts/poll_twilio.py

One-time backfill (e.g. recover missed calls from last 7 days):
    python scripts/poll_twilio.py --days 7
"""

import argparse
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Account
from app.poll_service import (
    poll_account,
    poll_missed_calls,
    poll_short_answered_calls,
    retry_failed_submissions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Default lookback: 24 hours (covers cron gaps, Railway restarts, etc.)
# The dedup logic prevents double-processing.
DEFAULT_LOOKBACK_HOURS = 24


def main():
    parser = argparse.ArgumentParser(description="Poll Twilio for new calls")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Lookback period in days (for backfill). Default: 24 hours.",
    )
    args = parser.parse_args()

    if args.days:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        logger.info("Backfill mode: looking back %d days", args.days)
    else:
        since = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)

    app = create_app()
    with app.app_context():
        accounts = Account.query.filter(
            Account.twilio_account_sid.isnot(None)
        ).all()

        logger.info("Polling %d accounts for new recordings", len(accounts))

        total_new = 0
        total_missed = 0
        total_short = 0
        total_retried = 0
        for account in accounts:
            try:
                count = poll_account(account, since)
                total_new += count
                if count:
                    logger.info("Account %s: %d new recordings", account.id, count)
            except Exception as e:
                logger.exception("Error polling account %s: %s", account.id, e)

            try:
                missed_count = poll_missed_calls(account, since)
                total_missed += missed_count
                if missed_count:
                    logger.info("Account %s: %d missed calls", account.id, missed_count)
            except Exception as e:
                logger.exception("Error polling missed calls for account %s: %s", account.id, e)

            try:
                short_count = poll_short_answered_calls(account, since)
                total_short += short_count
                if short_count:
                    logger.info("Account %s: %d short answered calls", account.id, short_count)
            except Exception as e:
                logger.exception("Error polling short calls for account %s: %s", account.id, e)

            try:
                retried_count = retry_failed_submissions(account)
                total_retried += retried_count
                if retried_count:
                    logger.info("Account %s: retried %d failed submissions", account.id, retried_count)
            except Exception as e:
                logger.exception("Error retrying failed submissions for account %s: %s", account.id, e)

        logger.info(
            "Done. %d new recordings, %d missed calls, %d short answered calls, %d retried.",
            total_new, total_missed, total_short, total_retried,
        )


if __name__ == "__main__":
    main()
