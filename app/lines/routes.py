from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..models import db, TrackingLine, Partner, Account
from ..callrail_service import fetch_callrail_trackers
from . import bp


def account_required(f):
    """Block partner users from accessing these routes."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.user_type != "account":
            abort(403)
        return f(*args, **kwargs)
    return decorated


@bp.route("/")
@login_required
@account_required
def index():
    lines = TrackingLine.query.filter_by(account_id=current_user.id).order_by(
        TrackingLine.label
    ).all()

    # Check if CallRail is connected for import button
    account = db.session.get(Account, current_user.id)
    callrail_connected = bool(
        account and account.callrail_api_key_encrypted and account.callrail_account_id
    )

    return render_template(
        "lines/index.html",
        lines=lines,
        callrail_connected=callrail_connected,
        active_page="lines",
    )


@bp.route("/import-callrail", methods=["POST"])
@login_required
@account_required
def import_callrail():
    account = db.session.get(Account, current_user.id)
    if not account or not account.callrail_api_key_encrypted or not account.callrail_account_id:
        flash("Connect CallRail in Settings first.", "error")
        return redirect(url_for("lines.index"))

    try:
        trackers = fetch_callrail_trackers(
            account.callrail_api_key_encrypted,
            account.callrail_account_id,
        )
    except Exception:
        flash("Failed to fetch tracking numbers from CallRail. Please try again.", "error")
        return redirect(url_for("lines.index"))

    imported = 0
    skipped = 0
    for tracker in trackers:
        # Skip if already imported (by tracker ID)
        existing = TrackingLine.query.filter_by(
            account_id=current_user.id,
            callrail_tracker_id=str(tracker["id"]),
        ).first()
        if existing:
            skipped += 1
            continue

        line = TrackingLine(
            account_id=current_user.id,
            callrail_tracker_id=str(tracker["id"]),
            callrail_tracking_number=tracker["tracking_phone_number"],
            label=tracker["name"] or tracker["tracking_phone_number"],
        )
        db.session.add(line)
        imported += 1

    db.session.commit()

    if imported:
        flash(f"Imported {imported} tracking number(s) from CallRail.", "success")
    if skipped:
        flash(f"Skipped {skipped} already imported number(s).", "info")
    if not imported and not skipped:
        flash("No tracking numbers found in your CallRail account.", "info")

    return redirect(url_for("lines.index"))


@bp.route("/add", methods=["GET", "POST"])
@login_required
@account_required
def add():
    partners = Partner.query.filter_by(account_id=current_user.id).order_by(
        Partner.name
    ).all()

    if request.method == "POST":
        partner_id = request.form.get("partner_id", type=int) or None
        line = TrackingLine(
            account_id=current_user.id,
            partner_id=partner_id,
            twilio_phone_number=request.form.get("twilio_phone_number", "").strip(),
            label=request.form.get("label", "").strip(),
            partner_name=request.form.get("partner_name", "").strip(),
            partner_phone=request.form.get("partner_phone", "").strip(),
            cost_per_lead=request.form.get("cost_per_lead", 0) or 0,
        )
        db.session.add(line)
        db.session.commit()
        flash("Tracking line added.", "success")
        return redirect(url_for("lines.index"))

    return render_template("lines/form.html", line=None, partners=partners, active_page="lines")


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

    if request.method == "POST":
        line.twilio_phone_number = request.form.get("twilio_phone_number", "").strip()
        line.label = request.form.get("label", "").strip()
        line.partner_name = request.form.get("partner_name", "").strip()
        line.partner_phone = request.form.get("partner_phone", "").strip()
        line.cost_per_lead = request.form.get("cost_per_lead", 0) or 0
        line.partner_id = request.form.get("partner_id", type=int) or None
        line.active = "active" in request.form
        db.session.commit()
        flash("Tracking line updated.", "success")
        return redirect(url_for("lines.index"))

    return render_template("lines/form.html", line=line, partners=partners, active_page="lines")


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
