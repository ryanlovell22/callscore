import csv
import io
import logging
from datetime import datetime, timedelta, timezone

import pytz
import requests as http_requests
from flask import render_template, request, redirect, url_for, session, abort, Response
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash

from ..models import db, Call, SharedDashboard, Account, Partner, TrackingLine
from ..extensions import limiter
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

    # Build call query scoped to the shared link's tracking lines
    query = Call.query.filter_by(account_id=dashboard.account_id)
    line_ids = [l.id for l in dashboard.tracking_lines]
    if line_ids:
        query = query.filter(Call.tracking_line_id.in_(line_ids))
    else:
        query = query.filter(False)

    # Timezone setup
    try:
        account = db.session.get(Account, dashboard.account_id)
        tz_name = account.timezone if account else 'Australia/Adelaide'
        local_tz = pytz.timezone(tz_name)
    except Exception:
        local_tz = pytz.timezone('Australia/Adelaide')

    now_local = datetime.now(timezone.utc).astimezone(local_tz)
    today_local = now_local.date()

    # Date filtering: query params override dashboard config
    period = request.args.get("period")
    qs_date_from = request.args.get("date_from")
    qs_date_to = request.args.get("date_to")
    active_period = None

    if period == "this_week":
        # Monday of current week to today
        active_period = "this_week"
        start_date = today_local - timedelta(days=today_local.weekday())  # Monday
        end_date = today_local + timedelta(days=1)
        window_days = -1
    elif period == "last_week":
        # Previous Monday to Sunday
        active_period = "last_week"
        this_monday = today_local - timedelta(days=today_local.weekday())
        start_date = this_monday - timedelta(days=7)
        end_date = this_monday
        window_days = -1
    elif qs_date_from and qs_date_to:
        # Custom date range from query string
        active_period = "custom"
        try:
            start_date = datetime.strptime(qs_date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(qs_date_to, "%Y-%m-%d").date() + timedelta(days=1)
            window_days = -1
        except ValueError:
            start_date = today_local - timedelta(days=30)
            end_date = today_local + timedelta(days=1)
            window_days = 30
    elif dashboard.date_from and dashboard.date_to:
        # Fixed date range from dashboard config
        start_date = dashboard.date_from
        end_date = dashboard.date_to + timedelta(days=1)
        window_days = -1
    else:
        # Rolling window: 0 = all-time, positive = rolling, NULL defaults to 30
        window_days = dashboard.date_window_days
        if window_days is None:
            window_days = 30
        if window_days > 0:
            start_date = today_local - timedelta(days=window_days)
            end_date = today_local + timedelta(days=1)
        else:
            start_date = None
            end_date = None

    # Apply date filters to query
    if window_days != 0 or (start_date and end_date):
        if start_date and end_date:
            dt_from = local_tz.localize(datetime(start_date.year, start_date.month, start_date.day))
            dt_from_utc = dt_from.astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(Call.call_date >= dt_from_utc)

            dt_to = local_tz.localize(datetime(end_date.year, end_date.month, end_date.day))
            dt_to_utc = dt_to.astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(Call.call_date < dt_to_utc)

    # Classification filter
    classification = request.args.get("classification")
    active_classification = None
    if classification in ("JOB_BOOKED", "NOT_BOOKED"):
        active_classification = classification

    # Stats (computed before classification filter so totals reflect all calls)
    total = query.count()
    booked = query.filter(Call.classification == "JOB_BOOKED").count()
    not_booked = query.filter(Call.classification == "NOT_BOOKED").count()
    missed = query.filter(
        or_(
            Call.call_outcome.in_(["missed", "voicemail"]),
            Call.classification == "VOICEMAIL",
        )
    ).count()
    answered = booked + not_booked
    rate = round(booked / answered * 100, 1) if answered > 0 else 0

    # Lead value: per-booking + per-call + per-voicemail + per-qualified-call + weekly minimums
    booking_value = db.session.query(
        func.coalesce(func.sum(Partner.cost_per_lead), 0)
    ).join(TrackingLine, TrackingLine.partner_id == Partner.id
    ).join(Call, Call.tracking_line_id == TrackingLine.id).filter(
        Call.id.in_(query.filter(Call.classification == "JOB_BOOKED").with_entities(Call.id))
    ).scalar()

    call_value = db.session.query(
        func.coalesce(func.sum(Partner.cost_per_call), 0)
    ).join(TrackingLine, TrackingLine.partner_id == Partner.id
    ).join(Call, Call.tracking_line_id == TrackingLine.id).filter(
        Call.id.in_(query.filter(
            Call.call_outcome == "answered",
            Call.status == "completed",
        ).with_entities(Call.id))
    ).scalar()

    voicemail_value = db.session.query(
        func.coalesce(func.sum(Partner.cost_per_voicemail), 0)
    ).join(TrackingLine, TrackingLine.partner_id == Partner.id
    ).join(Call, Call.tracking_line_id == TrackingLine.id).filter(
        Call.id.in_(query.filter(Call.classification == "VOICEMAIL").with_entities(Call.id))
    ).scalar()

    qualified_value = db.session.query(
        func.coalesce(func.sum(Partner.cost_per_qualified_call), 0)
    ).join(TrackingLine, TrackingLine.partner_id == Partner.id
    ).join(Call, Call.tracking_line_id == TrackingLine.id).filter(
        Call.id.in_(query.filter(
            Call.call_outcome == "answered",
            Call.status == "completed",
        ).with_entities(Call.id)),
        Call.call_duration >= Partner.qualified_call_seconds,
    ).scalar()

    # Weekly minimum fees
    from decimal import Decimal
    weekly_min_value = Decimal(0)
    partners_with_min = Partner.query.filter(
        Partner.account_id == dashboard.account_id,
        Partner.weekly_minimum_fee > 0,
    ).all()
    for p in partners_with_min:
        partner_calls = query.join(
            TrackingLine, Call.tracking_line_id == TrackingLine.id
        ).filter(TrackingLine.partner_id == p.id)
        week_count = db.session.query(
            func.count(func.distinct(func.date_trunc('week', Call.call_date)))
        ).filter(
            Call.id.in_(partner_calls.with_entities(Call.id))
        ).scalar() or 0
        if week_count > 0:
            weekly_min_value += p.weekly_minimum_fee * week_count

    total_value = float(booking_value + call_value + voicemail_value + qualified_value + weekly_min_value)

    # Apply classification filter to table query
    table_query = query
    if active_classification:
        table_query = table_query.filter(Call.classification == active_classification)

    # Pagination
    page = request.args.get("page", 1, type=int)
    pagination = table_query.order_by(Call.call_date.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    calls = pagination.items

    # Build a human-readable window label
    if active_period == "this_week":
        window_label = f"This week ({start_date.strftime('%d %b')} — {today_local.strftime('%d %b %Y')})"
    elif active_period == "last_week":
        last_sun = end_date - timedelta(days=1)
        window_label = f"Last week ({start_date.strftime('%d %b')} — {last_sun.strftime('%d %b %Y')})"
    elif active_period == "custom":
        actual_end = end_date - timedelta(days=1)
        window_label = f"{start_date.strftime('%d %b %Y')} — {actual_end.strftime('%d %b %Y')}"
    elif window_days == -1:
        window_label = f"{dashboard.date_from.strftime('%d %b %Y')} — {dashboard.date_to.strftime('%d %b %Y')}"
    elif window_days == 0:
        window_label = "All time (realtime)"
    elif window_days <= 7:
        window_label = "Last 7 days"
    elif window_days <= 14:
        window_label = "Last 14 days"
    elif window_days <= 30:
        window_label = "Last 30 days"
    elif window_days <= 60:
        window_label = "Last 60 days"
    elif window_days <= 90:
        window_label = "Last 90 days"
    else:
        window_label = f"Last {window_days} days"

    # Build filter dict for pagination/export links
    filters = {}
    if period:
        filters["period"] = period
    if qs_date_from:
        filters["date_from"] = qs_date_from
    if qs_date_to:
        filters["date_to"] = qs_date_to
    if active_classification:
        filters["classification"] = active_classification

    return render_template(
        "shared/dashboard.html",
        dashboard=dashboard,
        calls=calls,
        pagination=pagination,
        stats={
            "total": total, "booked": booked, "not_booked": not_booked,
            "missed": missed, "rate": rate, "total_value": total_value,
            "booking_value": float(booking_value), "call_value": float(call_value),
            "voicemail_value": float(voicemail_value), "qualified_value": float(qualified_value),
            "weekly_min_value": float(weekly_min_value),
        },
        window_label=window_label,
        share_token=share_token,
        local_tz=local_tz,
        active_period=active_period,
        active_classification=active_classification,
        filters=filters,
        qs_date_from=qs_date_from or "",
        qs_date_to=qs_date_to or "",
    )


@bp.route("/proof/<share_token>/export")
def public_dashboard_export(share_token):
    """CSV export for shared proof dashboard."""
    dashboard = SharedDashboard.query.filter_by(
        share_token=share_token, active=True
    ).first_or_404()

    # Password protection check
    if dashboard.password_hash:
        session_key = f"proof_auth_{share_token}"
        if not session.get(session_key):
            return redirect(url_for("shared.public_dashboard", share_token=share_token))

    # Build call query scoped to the shared link's tracking lines
    query = Call.query.filter_by(account_id=dashboard.account_id)
    line_ids = [l.id for l in dashboard.tracking_lines]
    if line_ids:
        query = query.filter(Call.tracking_line_id.in_(line_ids))
    else:
        query = query.filter(False)

    # Timezone setup
    try:
        account = db.session.get(Account, dashboard.account_id)
        tz_name = account.timezone if account else 'Australia/Adelaide'
        local_tz = pytz.timezone(tz_name)
    except Exception:
        local_tz = pytz.timezone('Australia/Adelaide')

    now_local = datetime.now(timezone.utc).astimezone(local_tz)
    today_local = now_local.date()

    # Date filtering (same logic as main route)
    period = request.args.get("period")
    qs_date_from = request.args.get("date_from")
    qs_date_to = request.args.get("date_to")

    start_date = None
    end_date = None
    window_days = 0

    if period == "this_week":
        start_date = today_local - timedelta(days=today_local.weekday())
        end_date = today_local + timedelta(days=1)
        window_days = -1
    elif period == "last_week":
        this_monday = today_local - timedelta(days=today_local.weekday())
        start_date = this_monday - timedelta(days=7)
        end_date = this_monday
        window_days = -1
    elif qs_date_from and qs_date_to:
        try:
            start_date = datetime.strptime(qs_date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(qs_date_to, "%Y-%m-%d").date() + timedelta(days=1)
            window_days = -1
        except ValueError:
            start_date = today_local - timedelta(days=30)
            end_date = today_local + timedelta(days=1)
            window_days = 30
    elif dashboard.date_from and dashboard.date_to:
        start_date = dashboard.date_from
        end_date = dashboard.date_to + timedelta(days=1)
        window_days = -1
    else:
        window_days = dashboard.date_window_days
        if window_days is None:
            window_days = 30
        if window_days > 0:
            start_date = today_local - timedelta(days=window_days)
            end_date = today_local + timedelta(days=1)

    if window_days != 0 or (start_date and end_date):
        if start_date and end_date:
            dt_from = local_tz.localize(datetime(start_date.year, start_date.month, start_date.day))
            dt_from_utc = dt_from.astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(Call.call_date >= dt_from_utc)
            dt_to = local_tz.localize(datetime(end_date.year, end_date.month, end_date.day))
            dt_to_utc = dt_to.astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(Call.call_date < dt_to_utc)

    # Classification filter
    classification = request.args.get("classification")
    if classification in ("JOB_BOOKED", "NOT_BOOKED"):
        query = query.filter(Call.classification == classification)

    calls = query.order_by(Call.call_date.desc()).all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Line", "Caller", "Customer", "Duration", "Classification", "Booking Time", "Summary"])

    for call in calls:
        # Convert date to local timezone
        if call.call_date:
            utc_dt = call.call_date.replace(tzinfo=timezone.utc)
            local_dt = utc_dt.astimezone(local_tz)
            date_str = local_dt.strftime("%-d %b %Y %-I:%M %p")
        else:
            date_str = ""

        duration = f"{call.call_duration // 60}:{call.call_duration % 60:02d}" if call.call_duration else ""

        if call.call_outcome == "missed":
            cls = "Missed"
        elif call.classification == "JOB_BOOKED":
            cls = "Booked"
        elif call.classification == "NOT_BOOKED":
            cls = "Not Booked"
        elif call.classification == "VOICEMAIL":
            cls = "Voicemail"
        else:
            cls = call.status or ""

        writer.writerow([
            date_str,
            call.tracking_line.label if call.tracking_line else "",
            call.caller_number or "",
            call.customer_name or "",
            duration,
            cls,
            call.booking_time or "",
            call.summary or "",
        ])

    csv_data = '\ufeff' + output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=calloutcome_export.csv"},
    )


@bp.route("/proof/<share_token>/auth", methods=["POST"])
@limiter.limit("5/minute")
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
    shared_line_ids = [l.id for l in dashboard.tracking_lines]
    if call.tracking_line_id not in shared_line_ids:
        abort(404)

    # Timezone for display
    try:
        account = db.session.get(Account, dashboard.account_id)
        tz_name = account.timezone if account else 'Australia/Adelaide'
        local_tz = pytz.timezone(tz_name)
    except Exception:
        local_tz = pytz.timezone('Australia/Adelaide')

    return render_template(
        "shared/call_detail.html",
        dashboard=dashboard,
        call=call,
        share_token=share_token,
        local_tz=local_tz,
    )


@bp.route("/proof/<share_token>/calls/<int:call_id>/recording")
@limiter.limit("30/minute")
def public_call_recording(share_token, call_id):
    """Proxy recording audio for shared proof links."""
    dashboard = SharedDashboard.query.filter_by(
        share_token=share_token, active=True
    ).first_or_404()

    # Password check
    if dashboard.password_hash:
        if not session.get(f"proof_auth_{share_token}"):
            abort(403)

    if not dashboard.show_recordings:
        abort(404)

    call = Call.query.filter_by(
        id=call_id, account_id=dashboard.account_id
    ).first_or_404()

    # Verify call belongs to dashboard scope
    shared_line_ids = [l.id for l in dashboard.tracking_lines]
    if call.tracking_line_id not in shared_line_ids:
        abort(404)

    if not call.recording_url:
        return "Recording not available", 404

    account = db.session.get(Account, dashboard.account_id)
    if not account:
        return "Recording not available", 404

    # Twilio recordings need auth; CallRail CDN URLs are pre-signed
    is_twilio = "twilio.com" in call.recording_url
    if is_twilio:
        resp = http_requests.get(
            f"{call.recording_url}.mp3",
            auth=(account.twilio_account_sid, account.twilio_auth_token),
            stream=True,
            timeout=30,
        )
    else:
        resp = http_requests.get(
            call.recording_url,
            stream=True,
            timeout=30,
        )

    if resp.status_code != 200:
        return "Recording not available", 404

    content_type = resp.headers.get("Content-Type", "audio/mpeg")

    return Response(
        resp.iter_content(chunk_size=8192),
        content_type=content_type,
        headers={"Content-Disposition": "inline"},
    )
