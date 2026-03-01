import logging

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..models import db, TrackingLine, Partner, Account
from ..callrail_service import fetch_callrail_trackers
from ..twilio_service import fetch_twilio_phone_numbers
from . import bp

logger = logging.getLogger(__name__)


def account_required(f):
    """Block partner users from accessing these routes."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.user_type != "account":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _get_available_numbers(account, exclude_line_id=None):
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
        account.twilio_account_sid and account.twilio_auth_token_encrypted
    )
    if twilio_connected:
        try:
            twilio_numbers = fetch_twilio_phone_numbers(
                account.twilio_account_sid,
                account.twilio_auth_token_encrypted,
            )
            for num in twilio_numbers:
                available.append({
                    "number": num["phone_number"],
                    "label": f"{num['phone_number']} — {num['friendly_name']} (Twilio)",
                    "source": "twilio",
                })
        except Exception:
            logger.exception("Failed to fetch Twilio phone numbers")

    # CallRail numbers
    callrail_connected = bool(
        account.callrail_api_key_encrypted and account.callrail_account_id
    )
    if callrail_connected:
        try:
            trackers = fetch_callrail_trackers(
                account.callrail_api_key_encrypted,
                account.callrail_account_id,
            )
            for t in trackers:
                available.append({
                    "number": t["tracking_phone_number"],
                    "label": f"{t['tracking_phone_number']} — {t['name'] or 'Unnamed'} (CallRail)",
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


@bp.route("/")
@login_required
@account_required
def index():
    lines = TrackingLine.query.filter_by(account_id=current_user.id).order_by(
        TrackingLine.label
    ).all()

    return render_template(
        "lines/index.html",
        lines=lines,
        active_page="lines",
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
@account_required
def add():
    partners = Partner.query.filter_by(account_id=current_user.id).order_by(
        Partner.name
    ).all()
    account = db.session.get(Account, current_user.id)

    if request.method == "POST":
        selected_number = request.form.get("twilio_phone_number", "").strip()

        # Look up CallRail metadata if this is a CallRail number
        callrail_tracker_id = request.form.get("callrail_tracker_id", "").strip() or None
        callrail_tracking_number = request.form.get("callrail_tracking_number", "").strip() or None

        partner_id = request.form.get("partner_id", type=int) or None
        line = TrackingLine(
            account_id=current_user.id,
            partner_id=partner_id,
            twilio_phone_number=selected_number,
            callrail_tracker_id=callrail_tracker_id,
            callrail_tracking_number=callrail_tracking_number,
            label=request.form.get("label", "").strip(),
            partner_name=request.form.get("partner_name", "").strip(),
            partner_phone=request.form.get("partner_phone", "").strip(),
            cost_per_lead=request.form.get("cost_per_lead", 0) or 0,
        )
        db.session.add(line)
        db.session.commit()
        flash("Tracking line added.", "success")
        return redirect(url_for("lines.index"))

    available_numbers = _get_available_numbers(account) if account else []

    return render_template(
        "lines/form.html",
        line=None,
        partners=partners,
        available_numbers=available_numbers,
        active_page="lines",
    )


@bp.route("/<int:line_id>/edit", methods=["GET", "POST"])
@login_required
@account_required
def edit(line_id):
    line = TrackingLine.query.filter_by(
        id=line_id, account_id=current_user.id
    ).first_or_404()
    partners = Partner.query.filter_by(account_id=current_user.id).order_by(
        Partner.name
    ).all()
    account = db.session.get(Account, current_user.id)

    if request.method == "POST":
        selected_number = request.form.get("twilio_phone_number", "").strip()

        line.twilio_phone_number = selected_number
        line.callrail_tracker_id = request.form.get("callrail_tracker_id", "").strip() or None
        line.callrail_tracking_number = request.form.get("callrail_tracking_number", "").strip() or None
        line.label = request.form.get("label", "").strip()
        line.partner_name = request.form.get("partner_name", "").strip()
        line.partner_phone = request.form.get("partner_phone", "").strip()
        line.cost_per_lead = request.form.get("cost_per_lead", 0) or 0
        line.partner_id = request.form.get("partner_id", type=int) or None
        line.active = "active" in request.form
        db.session.commit()
        flash("Tracking line updated.", "success")
        return redirect(url_for("lines.index"))

    available_numbers = _get_available_numbers(account, exclude_line_id=line.id) if account else []

    return render_template(
        "lines/form.html",
        line=line,
        partners=partners,
        available_numbers=available_numbers,
        active_page="lines",
    )


@bp.route("/<int:line_id>/delete", methods=["POST"])
@login_required
@account_required
def delete(line_id):
    line = TrackingLine.query.filter_by(
        id=line_id, account_id=current_user.id
    ).first_or_404()
    db.session.delete(line)
    db.session.commit()
    flash("Tracking line deleted.", "success")
    return redirect(url_for("lines.index"))
