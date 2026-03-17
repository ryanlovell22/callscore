import os
import time
import uuid
import logging
import threading
from datetime import datetime, timezone

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from ..models import db, Account, Call, TrackingLine
from ..ai_classifier import classify_transcript
from . import bp

logger = logging.getLogger(__name__)


def _parse_booking_date(value):
    """Parse an ISO 8601 booking_date string into a datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "ogg", "mp4"}

# Magic byte signatures for audio file validation
AUDIO_MAGIC_BYTES = {
    "wav": [b"RIFF"],          # RIFF header
    "mp3": [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3"],  # MPEG sync word or ID3 tag
    "m4a": [b"\x00\x00\x00"],  # ftyp box (variable size prefix)
    "mp4": [b"\x00\x00\x00"],  # ftyp box
    "ogg": [b"OggS"],          # Ogg container
}

# Per-file size limit (25MB)
MAX_FILE_SIZE = 25 * 1024 * 1024


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_audio_magic(file_obj, ext):
    """Check if the first bytes match expected audio magic bytes for the extension."""
    signatures = AUDIO_MAGIC_BYTES.get(ext, [])
    if not signatures:
        return True  # No signatures to check
    pos = file_obj.tell()
    header = file_obj.read(12)
    file_obj.seek(pos)  # Reset position
    if not header:
        return False
    for sig in signatures:
        if header[:len(sig)] == sig:
            return True
    # Special case for m4a/mp4: check for 'ftyp' at offset 4
    if ext in ("m4a", "mp4") and len(header) >= 8 and header[4:8] == b"ftyp":
        return True
    return False


BATCH_SIZE = 10


def _process_uploads(file_tasks, account_id, app):
    """Background thread: transcribe + classify each uploaded file via OpenAI.

    Processes in batches of BATCH_SIZE with a brief pause between batches.
    file_tasks is a list of dicts: {"call_id": int, "temp_path": str, "temp_filename": str}
    """
    with app.app_context():
        from openai import OpenAI
        api_key = app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        for i, task in enumerate(file_tasks):
            if i > 0 and i % BATCH_SIZE == 0:
                logger.info("Batch pause: processed %d/%d uploads", i, len(file_tasks))
                time.sleep(2)
            call = db.session.get(Call, task["call_id"])
            if not call:
                continue

            try:
                with open(task["temp_path"], "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                    )

                call.full_transcript = transcript.text

                tracking_line = call.tracking_line
                biz_name = (tracking_line.label or tracking_line.partner_name) if tracking_line else None
                tradie = None
                if tracking_line:
                    tradie = (tracking_line.partner.name if tracking_line.partner else None) or tracking_line.partner_name
                result = classify_transcript(transcript.text, business_name=biz_name, call_date=call.call_date, tradie_name=tradie)
                call.classification = result.get("classification")
                call.confidence = result.get("confidence")
                call.summary = result.get("summary")
                call.service_type = result.get("service_type")
                call.urgent = result.get("urgent", False)
                call.customer_name = result.get("customer_name")
                call.customer_address = result.get("customer_address")
                call.booking_time = result.get("booking_time")
                call.booking_date = _parse_booking_date(result.get("booking_date"))
                call.analysed_at = datetime.now(timezone.utc)
                call.status = "completed"

                if call.classification == "VOICEMAIL":
                    call.call_outcome = "voicemail"

                # Increment plan usage
                account = db.session.get(Account, account_id)
                if account:
                    if account.plan_calls_used is None:
                        account.plan_calls_used = 0
                    account.plan_calls_used += 1

                db.session.commit()

            except Exception as e:
                logger.exception("Failed to process uploaded file (call_id=%s)", task["call_id"])
                call.status = "failed"
                db.session.commit()


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if current_user.user_type != "account":
        from flask import abort
        abort(403)
    if request.method == "POST":
        files = request.files.getlist("audio_files")
        if not files or not any(f.filename for f in files):
            flash("Please select at least one audio file.", "error")
            return redirect(url_for("upload.index"))

        has_openai = bool(current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))

        if not has_openai:
            flash(
                "OpenAI API key not configured. Please contact support.",
                "error",
            )
            return redirect(url_for("settings.index"))

        # Check plan limits
        account = current_user
        remaining = None
        if not account.is_admin and account.plan_calls_limit is not None:
            used = account.plan_calls_used or 0
            remaining = max(0, account.plan_calls_limit - used)
            if remaining == 0:
                flash("You've reached your call limit. Upgrade your plan to process more calls.", "error")
                return redirect(url_for("billing.index"))

        upload_dir = os.path.join(current_app.instance_path, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        line_id = request.form.get("tracking_line_id", type=int)

        file_tasks = []
        skipped = 0
        limit_capped = 0

        for file in files:
            if not file or not file.filename:
                continue

            if not allowed_file(file.filename):
                skipped += 1
                continue

            # Per-file size check (25MB)
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset
            if file_size > MAX_FILE_SIZE:
                skipped += 1
                continue

            # Validate audio magic bytes
            ext = file.filename.rsplit(".", 1)[1].lower()
            if not validate_audio_magic(file, ext):
                skipped += 1
                continue

            # Check if we've hit the plan limit
            if remaining is not None and len(file_tasks) >= remaining:
                limit_capped += 1
                continue

            # Save file
            temp_filename = f"{uuid.uuid4()}.{ext}"
            temp_path = os.path.join(upload_dir, temp_filename)
            file.save(temp_path)

            # Create call record
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

            file_tasks.append({
                "call_id": call.id,
                "temp_path": temp_path,
                "temp_filename": temp_filename,
            })

        if not file_tasks:
            if limit_capped:
                flash("You've reached your call limit. Upgrade your plan to process more calls.", "error")
                return redirect(url_for("billing.index"))
            flash(
                f"No valid files to process. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}",
                "error",
            )
            return redirect(url_for("upload.index"))

        # Spawn background thread for processing
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_process_uploads,
            args=(file_tasks, current_user.id, app),
            daemon=True,
        )
        thread.start()

        count = len(file_tasks)
        msg = f"{count} file{'s' if count != 1 else ''} uploaded — processing in background."
        if skipped:
            msg += f" {skipped} file{'s' if skipped != 1 else ''} skipped (unsupported format)."
        if limit_capped:
            msg += f" {limit_capped} file{'s' if limit_capped != 1 else ''} skipped (plan limit reached)."
        flash(msg, "success")

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
