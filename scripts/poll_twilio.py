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
from app.models import db, Account, Call, TrackingLine
from app.twilio_service import fetch_recordings, fetch_calls, get_call_details, submit_recording_to_ci

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Default lookback: 24 hours (covers cron gaps, Railway restarts, etc.)
# The dedup logic prevents double-processing.
DEFAULT_LOOKBACK_HOURS = 24

# Minimum recording duration to process (seconds).
# Below this threshold, calls are likely accidental dials or instant hangups.
MIN_RECORDING_SECONDS = 3


def poll_account(account, since):
    """Fetch new recordings for an account and submit them to CI."""
    if not account.twilio_account_sid or not account.twilio_auth_token_encrypted:
        logger.info("Account %s: No Twilio credentials, skipping", account.id)
        return 0

    if not account.twilio_service_sid:
        logger.info("Account %s: No CI service configured, skipping", account.id)
        return 0

    logger.info(
        "Account %s: Fetching recordings since %s", account.id, since.isoformat()
    )

    recordings = fetch_recordings(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
        date_after=since,
    )

    new_count = 0
    for rec in recordings:
        recording_sid = rec.get("sid")

        # Skip if already in database
        existing = Call.query.filter_by(
            account_id=account.id, twilio_recording_sid=recording_sid
        ).first()
        if existing:
            continue

        call_sid = rec.get("call_sid")
        duration = int(rec.get("duration", 0))

        # Skip very short recordings (likely accidental dials)
        if duration < MIN_RECORDING_SECONDS:
            continue

        # Get call details to find the phone numbers
        try:
            call_details = get_call_details(
                account.twilio_account_sid,
                account.twilio_auth_token_encrypted,
                call_sid,
            )
        except Exception as e:
            logger.warning("Failed to get call details for %s: %s", call_sid, e)
            continue

        to_number = call_details.get("to", "")
        from_number = call_details.get("from", "")

        # Match to a tracking line
        tracking_line = TrackingLine.query.filter_by(
            account_id=account.id, twilio_phone_number=to_number, active=True
        ).first()

        recording_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{account.twilio_account_sid}/Recordings/{recording_sid}"
        )

        # Parse the date
        date_str = rec.get("date_created")
        call_date = None
        if date_str:
            try:
                call_date = datetime.strptime(
                    date_str, "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                call_date = datetime.now(timezone.utc)

        # Create call record
        call = Call(
            account_id=account.id,
            tracking_line_id=tracking_line.id if tracking_line else None,
            twilio_call_sid=call_sid,
            twilio_recording_sid=recording_sid,
            caller_number=from_number,
            call_duration=duration,
            call_date=call_date,
            recording_url=recording_url,
            source="twilio",
            status="processing",
            call_outcome="answered",
        )
        db.session.add(call)
        db.session.flush()  # Get the call ID

        # Submit to Conversational Intelligence
        try:
            transcript_sid = submit_recording_to_ci(
                account.twilio_account_sid,
                account.twilio_auth_token_encrypted,
                account.twilio_service_sid,
                recording_url,
            )
            call.transcript_sid = transcript_sid
            logger.info(
                "Submitted recording %s → transcript %s",
                recording_sid,
                transcript_sid,
            )
        except Exception as e:
            logger.error(
                "Failed to submit recording %s to CI: %s", recording_sid, e
            )
            call.status = "failed"

        new_count += 1

    db.session.commit()
    return new_count


def poll_missed_calls(account, since):
    """Fetch missed calls (no-answer, busy, canceled) and create records."""
    if not account.twilio_account_sid or not account.twilio_auth_token_encrypted:
        return 0

    logger.info(
        "Account %s: Fetching missed calls since %s", account.id, since.isoformat()
    )

    missed_calls = fetch_calls(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
        status_list=["no-answer", "busy", "canceled"],
        date_after=since,
    )

    new_count = 0
    for twilio_call in missed_calls:
        call_sid = twilio_call.get("sid")

        # Dedup on twilio_call_sid
        existing = Call.query.filter_by(
            account_id=account.id, twilio_call_sid=call_sid
        ).first()
        if existing:
            continue

        to_number = twilio_call.get("to", "")
        from_number = twilio_call.get("from", "")
        duration = int(twilio_call.get("duration") or 0)

        # Match to a tracking line
        tracking_line = TrackingLine.query.filter_by(
            account_id=account.id, twilio_phone_number=to_number, active=True
        ).first()

        # Parse the date
        date_str = twilio_call.get("date_created")
        call_date = None
        if date_str:
            try:
                call_date = datetime.strptime(
                    date_str, "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                call_date = datetime.now(timezone.utc)

        call = Call(
            account_id=account.id,
            tracking_line_id=tracking_line.id if tracking_line else None,
            twilio_call_sid=call_sid,
            caller_number=from_number,
            call_duration=duration,
            call_date=call_date,
            source="twilio",
            call_outcome="missed",
            status="completed",
        )
        db.session.add(call)
        new_count += 1

    db.session.commit()
    return new_count


def poll_short_answered_calls(account, since):
    """Fetch completed calls that have no recording in our DB.

    Catches very short answered calls where Twilio didn't create a recording.
    These fall through both poll_account (no recording) and poll_missed_calls
    (status is 'completed', not 'no-answer').

    Note: Twilio creates separate call legs for forwarded calls (parent +
    child), each with a different call SID. The recording is on the child
    leg, but the Calls API returns the parent. So we dedup by caller number
    + time window, not just call SID.
    """
    if not account.twilio_account_sid or not account.twilio_auth_token_encrypted:
        return 0

    logger.info(
        "Account %s: Fetching short answered calls since %s",
        account.id, since.isoformat(),
    )

    completed_calls = fetch_calls(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
        status_list=["completed"],
        date_after=since,
    )

    new_count = 0
    for twilio_call in completed_calls:
        call_sid = twilio_call.get("sid")
        duration = int(twilio_call.get("duration") or 0)

        # Only interested in short calls — longer ones already come in via
        # recordings in poll_account(). Using a generous threshold to avoid
        # missing edge cases where recording duration differs from call duration.
        if duration > 15:
            continue

        # Dedup on twilio_call_sid
        existing = Call.query.filter_by(
            account_id=account.id, twilio_call_sid=call_sid
        ).first()
        if existing:
            continue

        from_number = twilio_call.get("from", "")
        to_number = twilio_call.get("to", "")

        # Parse the date
        date_str = twilio_call.get("date_created")
        call_date = None
        if date_str:
            try:
                call_date = datetime.strptime(
                    date_str, "%a, %d %b %Y %H:%M:%S %z"
                )
            except ValueError:
                call_date = datetime.now(timezone.utc)

        # Dedup by caller + time window. Forwarded calls create two legs
        # with different SIDs but same caller and near-identical timestamps.
        if call_date:
            window = timedelta(minutes=3)
            near_dup = Call.query.filter(
                Call.account_id == account.id,
                Call.caller_number == from_number,
                Call.call_date.between(call_date - window, call_date + window),
            ).first()
            if near_dup:
                continue

        # Match to a tracking line
        tracking_line = TrackingLine.query.filter_by(
            account_id=account.id, twilio_phone_number=to_number, active=True
        ).first()

        call = Call(
            account_id=account.id,
            tracking_line_id=tracking_line.id if tracking_line else None,
            twilio_call_sid=call_sid,
            caller_number=from_number,
            call_duration=duration,
            call_date=call_date,
            source="twilio",
            call_outcome="answered",
            status="completed",
            classification="NOT_BOOKED",
            summary="Very short call — no recording available.",
        )
        db.session.add(call)
        new_count += 1

    db.session.commit()
    return new_count


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

        logger.info(
            "Done. %d new recordings, %d missed calls, %d short answered calls.",
            total_new, total_missed, total_short,
        )


if __name__ == "__main__":
    main()
