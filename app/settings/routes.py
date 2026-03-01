import logging
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..models import db
from ..twilio_service import (
    validate_twilio_credentials,
    create_ci_service,
    create_ci_operator,
)
from . import bp

logger = logging.getLogger(__name__)


def account_required(f):
    """Block partner users from accessing these routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.user_type != "account":
            abort(403)
        return f(*args, **kwargs)
    return decorated


@bp.route("/", methods=["GET", "POST"])
@login_required
@account_required
def index():
    account = current_user

    if request.method == "POST":
        sid = request.form.get("twilio_account_sid", "").strip()
        token_input = request.form.get("twilio_auth_token", "").strip()

        # If token field is blank or matches the masked placeholder, keep existing
        if not token_input or token_input.startswith("••••"):
            token = account.twilio_auth_token_encrypted
        else:
            token = token_input

        if not sid or not token:
            flash("Both Account SID and Auth Token are required.", "error")
            return redirect(url_for("settings.index"))

        # Validate credentials against Twilio API
        if not validate_twilio_credentials(sid, token):
            flash(
                "Invalid Twilio credentials. Please check your Account SID "
                "and Auth Token and try again.",
                "error",
            )
            return redirect(url_for("settings.index"))

        # Save credentials
        account.twilio_account_sid = sid
        account.twilio_auth_token_encrypted = token

        if not account.twilio_service_sid:
            # First-time setup — provision CI service + operator
            try:
                webhook_url = url_for(
                    "webhooks.twilio_ci_callback", _external=True
                )
                service_sid = create_ci_service(sid, token, webhook_url)
                account.twilio_service_sid = service_sid
                create_ci_operator(sid, token, service_sid)
                db.session.commit()
                flash(
                    "Twilio connected and call analysis enabled.", "success"
                )
            except Exception:
                db.session.rollback()
                logger.exception("Failed to provision Twilio CI")
                flash(
                    "Credentials are valid but CI setup failed. "
                    "Please try again or contact support.",
                    "error",
                )
                return redirect(url_for("settings.index"))
        else:
            # Just updating credentials
            db.session.commit()
            flash("Twilio credentials updated.", "success")

        return redirect(url_for("settings.index"))

    # GET — prepare display values
    masked_token = ""
    if account.twilio_auth_token_encrypted:
        masked_token = "••••" + account.twilio_auth_token_encrypted[-4:]

    connected = bool(account.twilio_service_sid)
    webhook_url = ""
    if connected:
        webhook_url = url_for("webhooks.twilio_ci_callback", _external=True)

    return render_template(
        "settings/index.html",
        account_sid=account.twilio_account_sid or "",
        masked_token=masked_token,
        connected=connected,
        webhook_url=webhook_url,
    )
