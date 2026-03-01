from datetime import datetime, timedelta, timezone
from decimal import Decimal

import requests as http_requests
from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user

from ..models import db, Call, TrackingLine, Account
from . import bp


@bp.route("/")
@login_required
def index():
    # Filters
    line_id = request.args.get("line", type=int)
    classification = request.args.get("classification")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    # Partners see only their assigned lines; accounts see everything
    if current_user.user_type == "partner":
        account_id = current_user.account_id
        partner_line_ids = [l.id for l in current_user.tracking_lines]
        query = Call.query.filter(
            Call.account_id == account_id,
            Call.tracking_line_id.in_(partner_line_ids)
        )
    else:
        account_id = current_user.id
        query = Call.query.filter_by(account_id=account_id)

    # Apply user filters to the base query
    if line_id:
        query = query.filter_by(tracking_line_id=line_id)
    if classification and classification in ("JOB_BOOKED", "NOT_BOOKED"):
        query = query.filter_by(classification=classification)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Call.call_date >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Call.call_date < dt_to)
        except ValueError:
            pass

    # Missed calls count (respects same filters)
    missed = query.filter(Call.call_outcome == "missed").count()

    # Answered calls only for the table (excludes missed)
    calls = query.filter(Call.call_outcome != "missed").order_by(Call.call_date.desc()).all()

    if current_user.user_type == "partner":
        lines = [l for l in current_user.tracking_lines if l.active]
    else:
        lines = TrackingLine.query.filter_by(
            account_id=current_user.id, active=True
        ).all()

    # Stats
    total = len(calls)
    booked = sum(1 for c in calls if c.classification == "JOB_BOOKED")
    not_booked = sum(1 for c in calls if c.classification == "NOT_BOOKED")
    pending = sum(1 for c in calls if c.status in ("pending", "processing"))
    rate = round(booked / total * 100, 1) if total > 0 else 0

    # Calculate total lead value from booked calls
    total_value = Decimal("0")
    for c in calls:
        if c.classification == "JOB_BOOKED" and c.tracking_line:
            total_value += c.tracking_line.cost_per_lead or Decimal("0")

    return render_template(
        "dashboard/index.html",
        calls=calls,
        lines=lines,
        stats={
            "total": total,
            "booked": booked,
            "not_booked": not_booked,
            "pending": pending,
            "rate": rate,
            "total_value": total_value,
            "missed": missed,
        },
        filters={
            "line": line_id,
            "classification": classification,
            "date_from": date_from or "",
            "date_to": date_to or "",
        },
    )


@bp.route("/calls/<int:call_id>")
@login_required
def call_detail(call_id):
    if current_user.user_type == "partner":
        partner_line_ids = [l.id for l in current_user.tracking_lines]
        call = Call.query.filter(
            Call.id == call_id,
            Call.account_id == current_user.account_id,
            Call.tracking_line_id.in_(partner_line_ids)
        ).first_or_404()
    else:
        call = Call.query.filter_by(
            id=call_id, account_id=current_user.id
        ).first_or_404()
    return render_template("dashboard/call_detail.html", call=call)


@bp.route("/calls/<int:call_id>/override", methods=["POST"])
@login_required
def override_classification(call_id):
    # Partners cannot override classifications
    if current_user.user_type == "partner":
        flash("You don't have permission to do that.", "error")
        return redirect(url_for("dashboard.index"))

    call = Call.query.filter_by(
        id=call_id, account_id=current_user.id
    ).first_or_404()

    new_classification = request.form.get("classification")
    if new_classification in ("JOB_BOOKED", "NOT_BOOKED"):
        call.classification = new_classification
        db.session.commit()
        flash("Classification updated.", "success")

    return redirect(url_for("dashboard.call_detail", call_id=call.id))


@bp.route("/calls/<int:call_id>/recording")
@login_required
def call_recording(call_id):
    """Proxy the Twilio recording so users don't need Twilio credentials."""
    if current_user.user_type == "partner":
        partner_line_ids = [l.id for l in current_user.tracking_lines]
        call = Call.query.filter(
            Call.id == call_id,
            Call.account_id == current_user.account_id,
            Call.tracking_line_id.in_(partner_line_ids)
        ).first_or_404()
        account = db.session.get(Account, current_user.account_id)
    else:
        call = Call.query.filter_by(
            id=call_id, account_id=current_user.id
        ).first_or_404()
        account = db.session.get(Account, current_user.id)

    if not call.recording_url or not account:
        return "Recording not available", 404

    resp = http_requests.get(
        f"{call.recording_url}.mp3",
        auth=(account.twilio_account_sid, account.twilio_auth_token_encrypted),
        stream=True,
        timeout=30,
    )

    if resp.status_code != 200:
        return "Recording not available", 404

    return Response(
        resp.iter_content(chunk_size=8192),
        content_type="audio/mpeg",
        headers={"Content-Disposition": "inline"},
    )
