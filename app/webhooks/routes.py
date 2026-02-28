import json
import logging
from datetime import datetime, timezone

from flask import request, jsonify, current_app

from ..models import db, Call, Account
from ..twilio_service import fetch_transcript_text, fetch_operator_results
from . import bp

logger = logging.getLogger(__name__)


@bp.route("/twilio-ci", methods=["POST"])
def twilio_ci_callback():
    """Receive webhook from Twilio Conversational Intelligence when
    transcription and operator analysis is complete."""

    data = request.json or request.form.to_dict()
    logger.info("Twilio CI webhook received: %s", json.dumps(data, default=str))

    transcript_sid = data.get("TranscriptSid") or data.get("transcript_sid")
    if not transcript_sid:
        return jsonify({"error": "No TranscriptSid provided"}), 400

    # Find the call record by transcript_sid
    call = Call.query.filter_by(transcript_sid=transcript_sid).first()
    if not call:
        logger.warning("No call found for transcript_sid=%s", transcript_sid)
        return jsonify({"error": "Call not found"}), 404

    account = db.session.get(Account, call.account_id)
    if not account or not account.twilio_account_sid:
        return jsonify({"error": "Account not configured"}), 400

    try:
        # Fetch operator results from Twilio
        operator_results = fetch_operator_results(
            account.twilio_account_sid,
            account.twilio_auth_token_encrypted,
            transcript_sid,
        )

        if operator_results:
            call.classification = operator_results.get("classification")
            call.confidence = operator_results.get("confidence")
            call.summary = operator_results.get("summary")
            call.service_type = operator_results.get("service_type")
            call.urgent = operator_results.get("urgent", False)

        # Fetch full transcript text
        transcript_text = fetch_transcript_text(
            account.twilio_account_sid,
            account.twilio_auth_token_encrypted,
            transcript_sid,
        )
        if transcript_text:
            call.full_transcript = transcript_text

        call.status = "completed"
        call.analysed_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(
            "Call %s analysed: %s", call.id, call.classification
        )
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.exception("Error processing webhook for transcript %s", transcript_sid)
        call.status = "failed"
        db.session.commit()
        return jsonify({"error": str(e)}), 500
