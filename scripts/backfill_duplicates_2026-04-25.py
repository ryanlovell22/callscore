"""Backfill is_duplicate_booking on existing JOB_BOOKED calls.

Walks every JOB_BOOKED call in chronological order. For each one, if a prior
non-duplicate JOB_BOOKED exists from the same normalised caller, same partner,
within DUPLICATE_WINDOW_DAYS, marks it as a duplicate.

Safe to re-run: clears all flags first, then recomputes.

Usage:
    python scripts/backfill_duplicates_2026-04-25.py
    python scripts/backfill_duplicates_2026-04-25.py --account 12      # one account only
    python scripts/backfill_duplicates_2026-04-25.py --dry-run         # report only, no writes
"""

import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Call, TrackingLine
from app.duplicate_detection import normalise_phone, DUPLICATE_WINDOW_DAYS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', type=int, help='Limit to one account_id')
    parser.add_argument('--dry-run', action='store_true', help='Report only, no DB writes')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        q = (
            db.session.query(Call, TrackingLine.partner_id)
            .outerjoin(TrackingLine, Call.tracking_line_id == TrackingLine.id)
            .filter(Call.classification == 'JOB_BOOKED')
            .filter(Call.call_date.isnot(None))
            .order_by(Call.call_date.asc())
        )
        if args.account:
            q = q.filter(Call.account_id == args.account)

        rows = q.all()
        print(f"Loaded {len(rows)} JOB_BOOKED calls")

        # Reset flags first (in scope)
        if not args.dry_run:
            ids = [c.id for c, _ in rows]
            if ids:
                Call.query.filter(Call.id.in_(ids)).update(
                    {Call.is_duplicate_booking: False}, synchronize_session=False
                )
                db.session.commit()
                print(f"Cleared is_duplicate_booking on {len(ids)} calls")

        # last_booking[(account_id, partner_id, normalised_phone)] = call_date
        last_booking = {}
        marked = 0
        from datetime import timedelta

        for call, partner_id in rows:
            normalised = normalise_phone(call.caller_number)
            if not normalised or partner_id is None:
                continue

            key = (call.account_id, partner_id, normalised)
            prior_date = last_booking.get(key)
            if prior_date is not None and (call.call_date - prior_date) <= timedelta(days=DUPLICATE_WINDOW_DAYS):
                # Duplicate: do not update last_booking (keep the original anchor)
                if not args.dry_run:
                    call.is_duplicate_booking = True
                marked += 1
                print(
                    f"  Call {call.id} ({call.call_date}) flagged — "
                    f"caller {normalised}, partner {partner_id}, "
                    f"prior booking {prior_date}"
                )
            else:
                last_booking[key] = call.call_date

        if not args.dry_run:
            db.session.commit()

        print(f"\nDone. Marked {marked} duplicate bookings ({'dry run' if args.dry_run else 'committed'}).")


if __name__ == '__main__':
    main()
