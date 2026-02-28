from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..models import db, TrackingLine
from . import bp


@bp.route("/")
@login_required
def index():
    lines = TrackingLine.query.filter_by(account_id=current_user.id).order_by(
        TrackingLine.label
    ).all()
    return render_template("lines/index.html", lines=lines)


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        line = TrackingLine(
            account_id=current_user.id,
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

    return render_template("lines/form.html", line=None)


@bp.route("/<int:line_id>/edit", methods=["GET", "POST"])
@login_required
def edit(line_id):
    line = TrackingLine.query.filter_by(
        id=line_id, account_id=current_user.id
    ).first_or_404()

    if request.method == "POST":
        line.twilio_phone_number = request.form.get("twilio_phone_number", "").strip()
        line.label = request.form.get("label", "").strip()
        line.partner_name = request.form.get("partner_name", "").strip()
        line.partner_phone = request.form.get("partner_phone", "").strip()
        line.cost_per_lead = request.form.get("cost_per_lead", 0) or 0
        line.active = "active" in request.form
        db.session.commit()
        flash("Tracking line updated.", "success")
        return redirect(url_for("lines.index"))

    return render_template("lines/form.html", line=line)


@bp.route("/<int:line_id>/delete", methods=["POST"])
@login_required
def delete(line_id):
    line = TrackingLine.query.filter_by(
        id=line_id, account_id=current_user.id
    ).first_or_404()
    db.session.delete(line)
    db.session.commit()
    flash("Tracking line deleted.", "success")
    return redirect(url_for("lines.index"))
