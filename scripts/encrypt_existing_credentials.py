"""One-time migration script: encrypt existing plaintext credentials in the database.

Run once after deploying the encryption code and setting FERNET_KEY:
    python scripts/encrypt_existing_credentials.py

Idempotent — safe to run multiple times. Skips values that are already
Fernet-encrypted (start with 'gAAAAA').
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.claude/credentials.env"))

from app import create_app
from app.models import db, Account
from app.encryption import encrypt_value

app = create_app()

with app.app_context():
    accounts = Account.query.all()
    updated = 0

    for account in accounts:
        changed = False

        # Encrypt Twilio auth token
        if account.twilio_auth_token_encrypted:
            if not account.twilio_auth_token_encrypted.startswith("gAAAAA"):
                print(f"  Account {account.id}: encrypting twilio_auth_token")
                account.twilio_auth_token_encrypted = encrypt_value(
                    account.twilio_auth_token_encrypted
                )
                changed = True
            else:
                print(f"  Account {account.id}: twilio_auth_token already encrypted")

        # Encrypt CallRail API key
        if account.callrail_api_key_encrypted:
            if not account.callrail_api_key_encrypted.startswith("gAAAAA"):
                print(f"  Account {account.id}: encrypting callrail_api_key")
                account.callrail_api_key_encrypted = encrypt_value(
                    account.callrail_api_key_encrypted
                )
                changed = True
            else:
                print(f"  Account {account.id}: callrail_api_key already encrypted")

        if changed:
            updated += 1

    if updated > 0:
        db.session.commit()
        print(f"\nDone — encrypted credentials for {updated} account(s).")
    else:
        print("\nNo plaintext credentials found. Nothing to do.")
