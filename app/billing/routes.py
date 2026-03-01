import logging
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..models import db
from ..stripe_service import create_checkout_session, create_customer_portal_session
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


@bp.route("/")
@login_required
@account_required
def index():
    from flask import current_app
    return render_template(
        "billing/index.html",
        account=current_user,
        stripe_publishable_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY", ""),
        active_page="billing",
    )


@bp.route("/checkout", methods=["POST"])
@login_required
@account_required
def checkout():
    from flask import current_app

    plan = request.form.get("plan", "").strip()
    price_ids = {
        "starter": current_app.config.get("STRIPE_PRICE_STARTER"),
        "pro": current_app.config.get("STRIPE_PRICE_PRO"),
        "agency": current_app.config.get("STRIPE_PRICE_AGENCY"),
    }

    price_id = price_ids.get(plan)
    if not price_id:
        flash("Invalid plan selected.", "error")
        return redirect(url_for("billing.index"))

    try:
        checkout_url = create_checkout_session(
            current_user,
            price_id,
            success_url=url_for("billing.success", _external=True),
            cancel_url=url_for("billing.index", _external=True),
        )
        return redirect(checkout_url)
    except Exception:
        logger.exception("Failed to create checkout session")
        flash("Failed to start checkout. Please try again.", "error")
        return redirect(url_for("billing.index"))


@bp.route("/success")
@login_required
@account_required
def success():
    flash("Payment successful! Your plan has been upgraded.", "success")
    return redirect(url_for("billing.index"))


@bp.route("/portal")
@login_required
@account_required
def portal():
    try:
        portal_url = create_customer_portal_session(
            current_user,
            return_url=url_for("billing.index", _external=True),
        )
        if portal_url:
            return redirect(portal_url)
        flash("No active subscription found.", "error")
    except Exception:
        logger.exception("Failed to create portal session")
        flash("Failed to open billing portal. Please try again.", "error")
    return redirect(url_for("billing.index"))
