"""Fernet encryption for sensitive credentials stored in the database."""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    """Lazily initialise and cache the Fernet instance."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("FERNET_KEY")
        if not key:
            raise RuntimeError("FERNET_KEY environment variable is not set")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(plaintext):
    """Encrypt a plaintext string. Returns a Fernet token string."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext):
    """Decrypt a Fernet token string back to plaintext.

    If the value doesn't look like a Fernet token (legacy plaintext),
    returns it as-is for backwards compatibility during migration.
    """
    if not ciphertext:
        return ciphertext
    # Fernet tokens always start with 'gAAAAA'
    if not ciphertext.startswith("gAAAAA"):
        return ciphertext  # Legacy plaintext — not yet encrypted
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as e:
        logger.error("Failed to decrypt value: %s", e)
        raise
