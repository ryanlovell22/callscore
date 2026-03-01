import os
import uuid
import logging
from datetime import datetime, timezone

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from ..models import db, Call, TrackingLine, Account
from ..twilio_service import submit_media_to_ci
from ..ai_classifier import classify_transcript
from . import bp

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "ogg", "mp4"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if current_user.user_type != "account":
        from flask import abort
        abort(403)
    if request.method == "POST":
        file = request.files.get("audio_file")
        if not file or not file.filename:
            flash("Please select an audio file.", "error")
            return redirect(url_for("upload.index"))

        if not allowed_file(file.filename):
            flash(
                f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
                "error",
            )
            return redirect(url_for("upload.index"))

        account = db.session.get(Account, current_user.id)
        has_twilio = bool(account.twilio_account_sid and account.twilio_service_sid)
        has_openai = bool(current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))

        if not has_twilio and not has_openai:
            flash(
                "Please connect Twilio or CallRail in Settings first.",
                "error",
            )
            return redirect(url_for("settings.index"))

        # Save file temporarily
        ext = file.filename.rsplit(".", 1)[1].lower()
        temp_filename = f"{uuid.uuid4()}.{ext}"
        upload_dir = os.path.join(current_app.instance_path, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        temp_path = os.path.join(upload_dir, temp_filename)
        file.save(temp_path)

        # Create call record
        line_id = request.form.get("tracking_line_id", type=int)
        call = Call(
            account_id=current_user.id,
            tracking_line_id=line_id if line_id else None,
            caller_number="Upload",
            call_date=datetime.now(timezone.utc),
            source="upload",
            status="processing",
        )
        db.session.add(call)
        db.session.commit()

        try:
            if has_twilio:
                # Twilio CI path — serve file via URL for Twilio to fetch
                base_url = request.host_url.rstrip("/")
                media_url = f"{base_url}/upload/serve/{temp_filename}"

                transcript_sid = submit_media_to_ci(
                    account.twilio_account_sid,
                    account.twilio_auth_token_encrypted,
                    account.twilio_service_sid,
                    media_url,
                )

                call.transcript_sid = transcript_sid
                db.session.commit()
            else:
                # OpenAI path — transcribe locally with Whisper + classify with GPT
                from openai import OpenAI
                api_key = current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
                client = OpenAI(api_key=api_key)

                with open(temp_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                    )

                call.transcript = transcript.text

                result = classify_transcript(transcript.text)
                call.classification = result.get("classification")
                call.summary = result.get("summary")
                call.customer_name = result.get("customer_name")
                call.booking_time = result.get("booking_time")
                call.status = "complete"
                db.session.commit()

            flash("File uploaded and submitted for analysis.", "success")
        except Exception as e:
            logger.exception("Failed to process uploaded recording")
            call.status = "failed"
            db.session.commit()
            flash(f"Upload failed: {e}", "error")

        return redirect(url_for("dashboard.index"))

    lines = TrackingLine.query.filter_by(
        account_id=current_user.id, active=True
    ).all()
    return render_template("upload/index.html", lines=lines, active_page="upload")


@bp.route("/serve/<filename>")
def serve_upload(filename):
    """Serve uploaded files temporarily so Twilio CI can fetch them.
    In production, consider using Supabase Storage with signed URLs instead."""
    from flask import send_from_directory

    upload_dir = os.path.join(current_app.instance_path, "uploads")
    return send_from_directory(upload_dir, filename)
