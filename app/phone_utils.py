import logging

from .models import TrackingLine
from .callrail_service import fetch_callrail_trackers
from .twilio_service import fetch_twilio_phone_numbers

logger = logging.getLogger(__name__)


def get_available_numbers(account, exclude_line_id=None):
    """Fetch phone numbers from connected sources and filter out already-assigned ones.

    Args:
        account: The Account object
        exclude_line_id: If editing a line, keep its number in the list

    Returns:
        List of dicts with number, label, source, and optional callrail fields.
    """
    available = []

    # Twilio numbers
    twilio_connected = bool(
        account.twilio_account_sid and account.twilio_auth_token
    )
    if twilio_connected:
        try:
            twilio_numbers = fetch_twilio_phone_numbers(
                account.twilio_account_sid,
                account.twilio_auth_token,
            )
            for num in twilio_numbers:
                available.append({
                    "number": num["phone_number"],
                    "label": f"{num['phone_number']} — {num['friendly_name']} (Twilio)",
                    "friendly_name": num["friendly_name"],
                    "source": "twilio",
                })
        except Exception:
            logger.exception("Failed to fetch Twilio phone numbers")

    # CallRail numbers
    callrail_connected = bool(
        account.callrail_api_key and account.callrail_account_id
    )
    if callrail_connected:
        try:
            trackers = fetch_callrail_trackers(
                account.callrail_api_key,
                account.callrail_account_id,
            )
            for t in trackers:
                available.append({
                    "number": t["tracking_phone_number"],
                    "label": f"{t['tracking_phone_number']} — {t['name'] or 'Unnamed'} (CallRail)",
                    "friendly_name": t["name"] or "Unnamed",
                    "source": "callrail",
                    "callrail_tracker_id": str(t["id"]),
                    "callrail_tracking_number": t["tracking_phone_number"],
                })
        except Exception:
            logger.exception("Failed to fetch CallRail trackers")

    # Filter out numbers already assigned to other tracking lines
    existing_lines = TrackingLine.query.filter_by(account_id=account.id).all()
    used_numbers = set()
    for line in existing_lines:
        if exclude_line_id and line.id == exclude_line_id:
            continue
        if line.twilio_phone_number:
            used_numbers.add(line.twilio_phone_number)
        if line.callrail_tracking_number:
            used_numbers.add(line.callrail_tracking_number)

    available = [n for n in available if n["number"] not in used_numbers]

    return available
