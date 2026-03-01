from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..models import db, TrackingLine, Partner
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
    return render_template("lines/index.html", lines=lines, active_page="lines")


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
