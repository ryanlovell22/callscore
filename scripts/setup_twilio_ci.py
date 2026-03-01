"""One-time setup: Create Twilio Conversational Intelligence service and operator.

Usage:
    python scripts/setup_twilio_ci.py --account-id 1

Or to set up using env vars (for initial bootstrap):
    python scripts/setup_twilio_ci.py --bootstrap
"""

import argparse
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Account
from app.twilio_service import create_ci_service, create_ci_operator, update_ci_operator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_for_account(account):
    """Create CI service and operator for an account."""
    logger.info("Setting up CI for account %s (%s)", account.id, account.email)

    if account.twilio_service_sid:
        logger.info("Account already has service_sid: %s", account.twilio_service_sid)
        return

    # Create the Intelligence Service
    service_sid = create_ci_service(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
    )
    logger.info("Created CI service: %s", service_sid)

    # Create the custom operator
    operator_sid = create_ci_operator(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
        service_sid,
    )
    logger.info("Created operator: %s", operator_sid)

    # Save to account
    account.twilio_service_sid = service_sid
    db.session.commit()
    logger.info("Saved service_sid to account %s", account.id)


def update_operator_config(account, operator_sid):
    """Update an existing operator with the expanded prompt and schema."""
    logger.info(
        "Updating operator %s for account %s", operator_sid, account.id
    )

    config = {
        "prompt": (
            "You are analysing a phone conversation between a customer calling "
            "a trades business in Australia. Your job is to determine whether "
            "the customer booked a job during this call, and extract key booking "
            "details.\n\n"
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
            "- Whether the customer mentioned urgency (same day, emergency)\n"
            "- The customer's name if mentioned\n"
            "- The customer's address if mentioned\n"
            "- The booking time if mentioned (e.g. 'Tuesday 2pm', 'next Monday "
            "morning', 'tomorrow arvo') — keep it as the exact wording used"
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
                "customer_name": {"type": "string"},
                "customer_address": {"type": "string"},
                "booking_time": {"type": "string"},
            },
            "required": ["classification", "summary"],
        },
    }

    result = update_ci_operator(
        account.twilio_account_sid,
        account.twilio_auth_token_encrypted,
        operator_sid,
        config,
    )
    logger.info("Operator %s updated successfully", operator_sid)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Set up Twilio Conversational Intelligence"
    )
    parser.add_argument("--account-id", type=int, help="Account ID to set up")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Bootstrap using environment variables",
    )
    parser.add_argument(
        "--update-operator",
        type=str,
        metavar="OPERATOR_SID",
        help="Update an existing operator's config (requires --account-id)",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.update_operator:
            if not args.account_id:
                logger.error("--update-operator requires --account-id")
                sys.exit(1)
            account = db.session.get(Account, args.account_id)
            if not account:
                logger.error("Account %d not found", args.account_id)
                sys.exit(1)
            update_operator_config(account, args.update_operator)

        elif args.bootstrap:
            sid = os.environ.get("TWILIO_ACCOUNT_SID")
            token = os.environ.get("TWILIO_AUTH_TOKEN")
            if not sid or not token:
                logger.error("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set")
                sys.exit(1)

            # Find or create the account
            account = Account.query.filter_by(twilio_account_sid=sid).first()
            if not account:
                logger.error(
                    "No account found with twilio_account_sid=%s. "
                    "Sign up first, then add your Twilio credentials.",
                    sid,
                )
                sys.exit(1)

            setup_for_account(account)

        elif args.account_id:
            account = db.session.get(Account, args.account_id)
            if not account:
                logger.error("Account %d not found", args.account_id)
                sys.exit(1)
            setup_for_account(account)

        else:
            parser.print_help()


if __name__ == "__main__":
    main()
