import logging
from datetime import datetime, timedelta, timezone

from flask import render_template, request, redirect, url_for, session, abort
from werkzeug.security import check_password_hash

from ..models import db, Call, SharedDashboard, TrackingLine
from . import bp

logger = logging.getLogger(__name__)


@bp.route("/proof/<share_token>")
def public_dashboard(share_token):
    """Public proof dashboard — no login required."""
    dashboard = SharedDashboard.query.filter_by(
        share_token=share_token, active=True
    ).first_or_404()

    # Password protection check
    if dashboard.password_hash:
        session_key = f"proof_auth_{share_token}"
        if not session.get(session_key):
            return render_template("shared/password.html", share_token=share_token)

    # Build call query based on dashboard scope
    query = Call.query.filter_by(account_id=dashboard.account_id)

    if dashboard.tracking_line_id:
        query = query.filter_by(tracking_line_id=dashboard.tracking_line_id)
    elif dashboard.partner_id:
        # Get all lines assigned to this partner
        partner_lines = TrackingLine.query.filter_by(
            account_id=dashboard.account_id,
            partner_id=dashboard.partner_id,
            active=True,
        ).all()
        line_ids = [l.id for l in partner_lines]
        if line_ids:
            query = query.filter(Call.tracking_line_id.in_(line_ids))
        else:
            query = query.filter(False)  # No lines, no calls

    # Date filters
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    # Default to last 30 days
    today = datetime.now(timezone.utc).date()
    if not date_from:
        date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = today.strftime("%Y-%m-%d")

    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        query = query.filter(Call.call_date >= dt_from)
    except ValueError:
        pass
    try:
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Call.call_date < dt_to)
    except ValueError:
        pass

    # Exclude missed calls from main stats
    stats_query = query.filter(Call.call_outcome != "missed")
    total = stats_query.count()
    booked = stats_query.filter(Call.classification == "JOB_BOOKED").count()
    rate = round(booked / total * 100, 1) if total > 0 else 0

    calls = stats_query.order_by(Call.call_date.desc()).all()

    return render_template(
        "shared/dashboard.html",
        dashboard=dashboard,
        calls=calls,
        stats={"total": total, "booked": booked, "rate": rate},
        date_from=date_from,
        date_to=date_to,
        share_token=share_token,
    )


@bp.route("/proof/<share_token>/auth", methods=["POST"])
def public_dashboard_auth(share_token):
    """Authenticate for a password-protected proof dashboard."""
    dashboard = SharedDashboard.query.filter_by(
        share_token=share_token, active=True
    ).first_or_404()

    password = request.form.get("password", "")
    if dashboard.password_hash and check_password_hash(dashboard.password_hash, password):
        session[f"proof_auth_{share_token}"] = True
        return redirect(url_for("shared.public_dashboard", share_token=share_token))

    return render_template(
        "shared/password.html",
        share_token=share_token,
        error="Incorrect password.",
    )


@bp.route("/proof/<share_token>/calls/<int:call_id>")
def public_call_detail(share_token, call_id):
    """Public call detail page."""
    dashboard = SharedDashboard.query.filter_by(
        share_token=share_token, active=True
    ).first_or_404()

    # Password check
    if dashboard.password_hash:
        if not session.get(f"proof_auth_{share_token}"):
            return redirect(url_for("shared.public_dashboard", share_token=share_token))

    call = Call.query.filter_by(
        id=call_id, account_id=dashboard.account_id
    ).first_or_404()

    # Verify call belongs to dashboard scope
    if dashboard.tracking_line_id and call.tracking_line_id != dashboard.tracking_line_id:
        abort(404)
    if dashboard.partner_id:
        partner_line_ids = [
            l.id for l in TrackingLine.query.filter_by(
                account_id=dashboard.account_id,
                partner_id=dashboard.partner_id,
            ).all()
        ]
        if call.tracking_line_id not in partner_line_ids:
            abort(404)

    return render_template(
        "shared/call_detail.html",
        dashboard=dashboard,
        call=call,
        share_token=share_token,
    )
