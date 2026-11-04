"""
Fernet-based encryption for OAuth tokens at rest.

Uses MASTER_ENCRYPTION_KEY env var (same pattern as SecretManager).
"""

import base64
import hashlib
import logging
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

_SALT = hashlib.sha256(b"sanskritisetu_calendar_tokens").digest()
_ITERATIONS = 100_000
_PROCESS_FALLBACK_KEY = secrets.token_hex(32)


class TokenEncryptionService:
    """Encrypt / decrypt OAuth tokens using Fernet (symmetric AES-128-CBC).

    The master key is derived from ``MASTER_ENCRYPTION_KEY`` via PBKDF2.
    """

    def __init__(self, master_key: str | None = None) -> None:
        raw_key = master_key or os.getenv("MASTER_ENCRYPTION_KEY")
        if not raw_key:
            logger.warning(
                "MASTER_ENCRYPTION_KEY not set -- using process-local fallback key "
                "(tokens will be unreadable after restart)"
            )
            raw_key = _PROCESS_FALLBACK_KEY
        self._fernet = self._create_fernet(raw_key)

    @staticmethod
    def _create_fernet(master_key: str) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Return a Fernet-encrypted, base64-encoded string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet-encrypted string.

        Raises ``InvalidToken`` if the ciphertext is corrupt or the key
        does not match.
        """
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            logger.error("Failed to decrypt token -- key mismatch or corrupt data")
            raise
