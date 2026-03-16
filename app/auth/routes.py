import json
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user

from ..models import db, Account
from ..email_service import send_email
from ..extensions import limiter
from . import bp


@bp.route("/google")
def google_login():
    from .. import oauth
    if not hasattr(oauth, 'google'):
        flash("Google sign-in is not configured.", "error")
        return redirect(url_for("auth.login"))
    redirect_uri = url_for("auth.google_callback", _external=True, _scheme="https" if request.host != "127.0.0.1:5099" else "http")
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/google/callback")
def google_callback():
    from .. import oauth
    if not hasattr(oauth, 'google'):
        flash("Google sign-in is not configured.", "error")
        return redirect(url_for("auth.login"))

    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash("Google sign-in was cancelled or failed.", "error")
        return redirect(url_for("auth.login"))

    userinfo = token.get('userinfo')
    if not userinfo:
        flash("Could not retrieve your Google account info.", "error")
        return redirect(url_for("auth.login"))

    google_id = userinfo['sub']
    email = userinfo['email'].strip().lower()
    name = userinfo.get('name', email.split('@')[0])

    # 1. Find by google_id (returning Google user)
    account = Account.query.filter_by(google_id=google_id).first()
    if account:
        login_user(account)
        if not account.onboarding_completed:
            return redirect(url_for("onboarding.wizard"))
        return redirect(url_for("dashboard.index"))

    # 2. Find by email (existing email/password user)
    # Block auto-linking to prevent account takeover via email squatting.
    # User must log in with their password first, then link Google manually.
    account = Account.query.filter_by(email=email).first()
    if account:
        flash(
            "An account with that email already exists. "
            "Please log in with your password first.",
            "error",
        )
        return redirect(url_for("auth.login"))

    # 3. New user — create account via Google
    is_admin = email in current_app.config.get("ADMIN_EMAILS", [])
    account = Account(
        name=name,
        email=email,
        google_id=google_id,
        auth_provider="google",
        is_admin=is_admin,
    )

    # Auto-detect timezone from cookie (set by JS on login/signup pages)
    detected_tz = request.cookies.get("tz_detect", "").strip()
    if detected_tz:
        import pytz
        if detected_tz in pytz.all_timezones:
            account.timezone = detected_tz

    # Capture UTM data from session
    utm_data = session.pop('utm_data', None)
    if utm_data:
        account.signup_source = json.dumps(utm_data)

    db.session.add(account)
    db.session.commit()
    login_user(account)
    flash("Account created successfully.", "success")
    return redirect(url_for("onboarding.wizard"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute")
def login():
    if current_user.is_authenticated:
        if hasattr(current_user, 'onboarding_completed') and not current_user.onboarding_completed:
            return redirect(url_for("onboarding.wizard"))
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = Account.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            # Prevent open redirect — only allow relative URLs
            if next_page:
                from urllib.parse import urlparse
                parsed = urlparse(next_page)
                if parsed.netloc or parsed.scheme:
                    next_page = None
            if not next_page and hasattr(user, 'onboarding_completed') and not user.onboarding_completed:
                return redirect(url_for("onboarding.wizard"))
            return redirect(next_page or url_for("dashboard.index"))

        flash("Invalid email or password.", "error")

    return render_template("auth/login.html")


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5/minute")
def signup():
    if current_user.is_authenticated:
        if hasattr(current_user, 'onboarding_completed') and not current_user.onboarding_completed:
            return redirect(url_for("onboarding.wizard"))
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Preserve UTM data across validation errors
        post_utm = session.get('utm_data', {})

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("auth/signup.html", utm_data=post_utm)

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/signup.html", utm_data=post_utm)

        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            flash("Password must contain at least one letter and one number.", "error")
            return render_template("auth/signup.html", utm_data=post_utm)

        if Account.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("auth/signup.html", utm_data=post_utm)

        is_admin = email in current_app.config.get("ADMIN_EMAILS", [])
        account = Account(name=name, email=email, is_admin=is_admin)
        account.set_password(password)

        # Auto-detect timezone from browser
        detected_tz = request.form.get("timezone", "").strip()
        if detected_tz:
            import pytz
            if detected_tz in pytz.all_timezones:
                account.timezone = detected_tz

        # Store acquisition source — try session first, fall back to hidden form fields
        utm_data = session.pop('utm_data', None)
        if not utm_data:
            # Fallback: read from hidden form fields (covers lost session cookies)
            from ..utm_utils import UTM_PARAMS
            form_utm = {p: request.form.get(p, '') for p in UTM_PARAMS if request.form.get(p)}
            if form_utm:
                utm_data = form_utm
        if utm_data:
            account.signup_source = json.dumps(utm_data)

        db.session.add(account)
        db.session.commit()

        login_user(account)
        flash("Account created successfully.", "success")
        return redirect(url_for("onboarding.wizard"))

    # Pass UTM data to template for hidden form fields (fallback if session is lost)
    utm_data = session.get('utm_data', {})
    return render_template("auth/signup.html", utm_data=utm_data)


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3/minute")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        # Always show the same message to prevent email enumeration
        flash("If an account with that email exists, we've sent a password reset link.", "success")

        account = Account.query.filter_by(email=email).first()
        if account:
            # Google-only accounts have no password to reset
            if account.auth_provider == "google" and not account.password_hash:
                send_email(
                    to=account.email,
                    subject="CallOutcome sign-in help",
                    html=f"""
                    <h2>Sign-in Help</h2>
                    <p>Hi {account.name},</p>
                    <p>Your CallOutcome account uses Google sign-in, so there's no password to reset.</p>
                    <p>To log in, visit <a href="https://calloutcome.com/login">calloutcome.com/login</a> and click <strong>"Sign in with Google"</strong>.</p>
                    <p>If you didn't request this, you can safely ignore this email.</p>
                    <p>— CallOutcome</p>
                    """,
                )
            else:
                import hashlib as _hashlib
                token = secrets.token_urlsafe(32)
                # Store hash of token in DB — raw token only sent via email
                token_hash = _hashlib.sha256(token.encode()).hexdigest()
                account.password_reset_token = token_hash
                account.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
                db.session.commit()

                reset_url = url_for("auth.reset_password", token=token, _external=True)
                send_email(
                    to=account.email,
                    subject="Reset your CallOutcome password",
                    html=f"""
                    <h2>Password Reset</h2>
                    <p>Hi {account.name},</p>
                    <p>Click the link below to reset your password. This link expires in 1 hour.</p>
                    <p><a href="{reset_url}" style="display:inline-block;padding:12px 24px;background:#1095c1;color:white;text-decoration:none;border-radius:6px;">Reset Password</a></p>
                    <p>If you didn't request this, you can safely ignore this email.</p>
                    <p>— CallOutcome</p>
                    """,
                )

        return redirect(url_for("auth.forgot_password"))

    return render_template("auth/forgot_password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    import hashlib as _hashlib
    token_hash = _hashlib.sha256(token.encode()).hexdigest()
    account = Account.query.filter_by(password_reset_token=token_hash).first()

    if not account or not account.password_reset_expires:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("auth.forgot_password"))

    if account.password_reset_expires < datetime.now(timezone.utc):
        account.password_reset_token = None
        account.password_reset_expires = None
        db.session.commit()
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", token=token)

        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            flash("Password must contain at least one letter and one number.", "error")
            return render_template("auth/reset_password.html", token=token)

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token)

        account.set_password(password)
        account.password_reset_token = None
        account.password_reset_expires = None
        db.session.commit()

        flash("Password reset successfully. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)
