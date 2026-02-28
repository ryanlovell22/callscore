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
from app.twilio_service import create_ci_service, create_ci_operator

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
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.bootstrap:
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
