"""Twilio API helper functions for CallScore."""

import json
import logging

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
TWILIO_CI_BASE = "https://intelligence.twilio.com/v2"


def get_auth(account_sid, auth_token):
    return HTTPBasicAuth(account_sid, auth_token)


# --- Recording Fetch ---


def fetch_recordings(account_sid, auth_token, date_after=None):
    """Fetch call recordings from Twilio.

    Args:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        date_after: Only fetch recordings created after this datetime

    Returns:
        List of recording dicts from Twilio API
    """
    url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Recordings.json"
    params = {"PageSize": 100}
    if date_after:
        params["DateCreated>"] = date_after.strftime("%Y-%m-%dT%H:%M:%SZ")

    auth = get_auth(account_sid, auth_token)
    all_recordings = []

    while url:
        resp = requests.get(url, params=params, auth=auth, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_recordings.extend(data.get("recordings", []))

        # Pagination
        next_page = data.get("next_page_uri")
        if next_page:
            url = f"https://api.twilio.com{next_page}"
            params = {}  # next_page_uri includes params
        else:
            url = None

    return all_recordings


def get_call_details(account_sid, auth_token, call_sid):
    """Get details about a specific call."""
    url = f"{TWILIO_API_BASE}/Accounts/{account_sid}/Calls/{call_sid}.json"
    resp = requests.get(url, auth=get_auth(account_sid, auth_token), timeout=30)
    resp.raise_for_status()
    return resp.json()


# --- Conversational Intelligence ---


def create_ci_service(account_sid, auth_token, webhook_url=None):
    """Create a Conversational Intelligence service.

    Returns:
        service_sid (str)
    """
    url = f"{TWILIO_CI_BASE}/Services"
    auth = get_auth(account_sid, auth_token)

    data = {
        "UniqueName": "callscore",
        "FriendlyName": "CallScore Job Classifier",
        "AutoTranscribe": "false",
        "LanguageCode": "en-AU",
    }
    if webhook_url:
        data["WebhookUrl"] = webhook_url
        data["WebhookHttpMethod"] = "POST"

    resp = requests.post(url, auth=auth, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["sid"]


def create_ci_operator(account_sid, auth_token, service_sid):
    """Create the 'Job Booked?' custom operator and attach it to the service.

    Returns:
        operator_sid (str)
    """
    auth = get_auth(account_sid, auth_token)

    # Create custom operator (Twilio CI uses form-encoded, not JSON body)
    operator_url = f"{TWILIO_CI_BASE}/Operators/Custom"
    config = json.dumps({
        "prompt": (
            "You are analysing a phone conversation between a customer calling "
            "a trades business in Australia. Your job is to determine whether "
            "the customer booked a job during this call.\n\n"
            "Classify the call as one of:\n\n"
            "JOB_BOOKED - The customer and business agreed on a time or "
            "arrangement for work to be done. This includes: scheduling an "
            "appointment, accepting a quote, agreeing someone will come out, "
            "providing or agreeing to text their address, or any clear "
            "commitment to proceed.\n\n"
            "NOT_BOOKED - No job was booked. This includes: general enquiries "
            "without commitment, voicemails, wrong numbers, price shopping "
            "without booking, spam/robocalls, or calls where the customer "
            "said they would think about it.\n\n"
            "Also extract:\n"
            "- A brief one-sentence summary of the call\n"
            "- The service type discussed (e.g. lockout, rekey, tow, painting)\n"
            "- Whether the customer mentioned urgency (same day, emergency)"
        ),
        "json_result_schema": {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["JOB_BOOKED", "NOT_BOOKED"],
                },
                "confidence": {"type": "number"},
                "summary": {"type": "string"},
                "service_type": {"type": "string"},
                "urgent": {"type": "boolean"},
            },
            "required": ["classification", "summary"],
        },
    })

    resp = requests.post(
        operator_url,
        auth=auth,
        data={
            "FriendlyName": "Job Booked Classifier",
            "OperatorType": "GenerativeJSON",
            "Config": config,
        },
        timeout=30,
    )
    resp.raise_for_status()
    operator_sid = resp.json()["sid"]

    # Attach operator to service
    attach_url = (
        f"{TWILIO_CI_BASE}/Services/{service_sid}/Operators/{operator_sid}"
    )
    resp = requests.post(attach_url, auth=auth, data={}, timeout=30)
    resp.raise_for_status()

    return operator_sid


def submit_recording_to_ci(account_sid, auth_token, service_sid, recording_url):
    """Submit a Twilio recording to Conversational Intelligence for analysis.

    Args:
        recording_url: URL of the Twilio recording

    Returns:
        transcript_sid (str)
    """
    url = f"{TWILIO_CI_BASE}/Transcripts"
    auth = get_auth(account_sid, auth_token)

    channel = json.dumps({
        "media_properties": {
            "source_sid": recording_url.split("/")[-1]
            if "Recordings/" in recording_url
            else None,
            "media_url": recording_url,
        }
    })

    resp = requests.post(
        url,
        auth=auth,
        data={"ServiceSid": service_sid, "Channel": channel},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["sid"]


def submit_media_to_ci(account_sid, auth_token, service_sid, media_url):
    """Submit an external media URL to Conversational Intelligence.

    Returns:
        transcript_sid (str)
    """
    url = f"{TWILIO_CI_BASE}/Transcripts"
    auth = get_auth(account_sid, auth_token)

    channel = json.dumps({
        "media_properties": {"media_url": media_url}
    })

    resp = requests.post(
        url,
        auth=auth,
        data={"ServiceSid": service_sid, "Channel": channel},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["sid"]


def fetch_operator_results(account_sid, auth_token, transcript_sid):
    """Fetch operator results for a completed transcript.

    Returns:
        dict with classification, confidence, summary, service_type, urgent
    """
    url = f"{TWILIO_CI_BASE}/Transcripts/{transcript_sid}/OperatorResults"
    auth = get_auth(account_sid, auth_token)

    resp = requests.get(url, auth=auth, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("operator_results", [])
    if not results:
        return None

    # Get the first (and likely only) operator result
    result = results[0]

    # GenerativeJSON operators return results in json_results,
    # while other types use extract_results
    extracted = result.get("json_results") or result.get("extract_results") or {}

    if isinstance(extracted, str):
        try:
            extracted = json.loads(extracted)
        except json.JSONDecodeError:
            extracted = {}

    return {
        "classification": extracted.get("classification"),
        "confidence": extracted.get("confidence"),
        "summary": extracted.get("summary"),
        "service_type": extracted.get("service_type"),
        "urgent": extracted.get("urgent", False),
    }


def fetch_transcript_text(account_sid, auth_token, transcript_sid):
    """Fetch the full transcript text.

    Returns:
        str: Full transcript text with speaker labels
    """
    url = f"{TWILIO_CI_BASE}/Transcripts/{transcript_sid}/Sentences"
    auth = get_auth(account_sid, auth_token)

    resp = requests.get(url, auth=auth, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    sentences = data.get("sentences", [])
    lines = []
    for s in sentences:
        speaker = s.get("media_channel", {}).get("role", "Unknown")
        text = s.get("transcript", "")
        lines.append(f"{speaker}: {text}")

    return "\n".join(lines)
