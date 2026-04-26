"""Detect and flag duplicate bookings: same caller booking the same partner twice
within a rolling window. Flagged calls are excluded from booking counts and
billing math, so partners aren't charged twice for the same customer.
"""

import re
import logging
from datetime import datetime, timezone, timedelta

from .models import db, Call, TrackingLine

logger = logging.getLogger(__name__)

DUPLICATE_WINDOW_DAYS = 90


def normalise_phone(num):
    """Normalise a phone number for comparison.

    Strips +, spaces, hyphens, parens. Converts AU national format
    (leading 0) to international (61 prefix) so 0402... and +61402...
    collapse to the same key. Returns None if the input doesn't look
    like a real phone number.
    """
    if not num:
        return None
    digits = re.sub(r'\D', '', str(num))
    if not digits or len(digits) < 7:
        return None
    # AU national → international: 04xxxxxxxx → 614xxxxxxxx, 0Nxxxxxxx → 61Nxxxxxxx
    if digits.startswith('0') and len(digits) in (9, 10):
        digits = '61' + digits[1:]
    # 00 international prefix → drop
    elif digits.startswith('00'):
        digits = digits[2:]
    return digits


def mark_if_duplicate_booking(call):
    """Set call.is_duplicate_booking=True if a prior JOB_BOOKED exists from
    the same caller, same partner, within DUPLICATE_WINDOW_DAYS.

    Caller is responsible for committing. Safe to call on any call — only
    acts when classification == JOB_BOOKED, the line has a partner, and
    the caller_number is a real phone number.
    """
    if call.classification != 'JOB_BOOKED':
        call.is_duplicate_booking = False
        return None

    normalised = normalise_phone(call.caller_number)
    if not normalised:
        return None

    line = call.tracking_line or (
        TrackingLine.query.get(call.tracking_line_id) if call.tracking_line_id else None
    )
    if not line or not line.partner_id:
        return None

    reference_date = call.call_date or datetime.now(timezone.utc)
    window_start = reference_date - timedelta(days=DUPLICATE_WINDOW_DAYS)

    q = (
        Call.query
        .filter(
            Call.account_id == call.account_id,
            Call.classification == 'JOB_BOOKED',
            Call.is_duplicate_booking.is_(False),
            Call.partner_id == line.partner_id,
            Call.call_date.isnot(None),
            Call.call_date >= window_start,
            Call.call_date < reference_date,
        )
    )
    if call.id is not None:
        q = q.filter(Call.id != call.id)
    candidates = q.all()

    for prior in candidates:
        if normalise_phone(prior.caller_number) == normalised:
            call.is_duplicate_booking = True
            logger.info(
                "Call %s flagged as duplicate booking of call %s (partner %s, caller %s)",
                call.id, prior.id, line.partner_id, normalised,
            )
            return prior.id

    call.is_duplicate_booking = False
    return None
