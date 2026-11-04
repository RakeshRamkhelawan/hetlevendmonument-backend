"""
SA-6.1: Two-Factor Authentication (TOTP) Model and Service
Implements Time-based One-Time Password (TOTP) for enhanced security.

Dependencies:
- pyotp: For TOTP generation and verification
- qrcode: For QR code generation (optional, for setup)
"""

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, cast
from urllib.parse import quote

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

pyotp: Any = None
PYOTP_AVAILABLE = False
try:
    import pyotp as _pyotp

    pyotp = _pyotp
    PYOTP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    pass

from src.core.database.database import Base

logger = logging.getLogger(__name__)


class _FallbackTOTP:
    """Minimal RFC 6238-compatible TOTP implementation for environments without pyotp."""

    def __init__(self, secret: str, interval: int = 30, digits: int = 6) -> None:
        self.secret = secret
        self.interval = interval
        self.digits = digits

    def _counter(self, for_time: float | None = None) -> int:
        timestamp = for_time if for_time is not None else datetime.now(timezone.utc).timestamp()
        return int(timestamp // self.interval)

    def _generate(self, counter: int) -> str:
        normalized = self.secret.strip().upper()
        padding = "=" * ((8 - len(normalized) % 8) % 8)
        key = base64.b32decode(normalized + padding, casefold=True)
        msg = counter.to_bytes(8, byteorder="big")
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
        otp = binary % (10**self.digits)
        return f"{otp:0{self.digits}d}"

    def now(self) -> str:
        return self._generate(self._counter())

    def verify(self, code: str, valid_window: int = 1) -> bool:
        current_counter = self._counter()
        for offset in range(-valid_window, valid_window + 1):
            if self._generate(current_counter + offset) == code:
                return True
        return False

    def provisioning_uri(self, name: str, issuer_name: str) -> str:
        encoded_name = quote(name)
        encoded_issuer = quote(issuer_name)
        return (
            f"otpauth://totp/{encoded_issuer}:{encoded_name}"
            f"?secret={self.secret}&issuer={encoded_issuer}"
        )


class TwoFactorAuth(Base):  # type: ignore[misc]
    """
    Two-Factor Authentication model for storing TOTP secrets.

    SA-6.1: Database layer for 2FA/TOTP
    """

    __tablename__ = "two_factor_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )

    # Encrypted TOTP secret (should be encrypted at rest in production)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)

    # Whether 2FA is currently enabled for this user
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Backup codes (comma-separated, hashed)
    backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Recovery email (optional)
    recovery_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Failed attempt tracking
    failed_attempts: Mapped[int | None] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TwoFactorAuth(user_id={self.user_id}, enabled={self.is_enabled})>"


class _TOTPLike(Protocol):
    """Protocol for TOTP implementations (pyotp.TOTP or _FallbackTOTP)."""

    def now(self) -> str: ...
    def verify(self, code: str, valid_window: int = 1) -> bool: ...
    def provisioning_uri(self, name: str, issuer_name: str) -> str: ...


class TOTPService:
    """
    SA-6.2: TOTP Service for generating and verifying codes.
    """

    ISSUER_NAME = "SanskritiSetu"
    BACKUP_CODE_COUNT = 10
    BACKUP_CODE_LENGTH = 8
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15

    def __init__(self) -> None:
        if pyotp is None:
            logger.warning("pyotp not installed. 2FA functionality disabled.")

    def generate_secret(self) -> str:
        """Generate a new TOTP secret."""
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp not installed")
        if pyotp is not None:
            return cast(str, pyotp.random_base32())
        return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

    def get_totp(self, secret: str) -> _TOTPLike:
        """Get TOTP instance for a secret."""
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp not installed")
        if pyotp is not None:
            return cast(_TOTPLike, pyotp.TOTP(secret))
        return _FallbackTOTP(secret)

    def verify_code(self, secret: str, code: str, window: int = 1) -> bool:
        """
        Verify a TOTP code.

        Args:
            secret: The user's TOTP secret
            code: The 6-digit code to verify
            window: Number of time windows to check (default 1 = 30 seconds each way)

        Returns:
            True if code is valid, False otherwise
        """
        if not PYOTP_AVAILABLE:
            logger.error("pyotp not installed, cannot verify 2FA")
            return False

        try:
            totp = self.get_totp(secret)
            return bool(totp.verify(code, valid_window=window))
        except Exception as e:
            logger.error(f"Error verifying TOTP code: {e}")
            return False

    def get_provisioning_uri(self, secret: str, email: str) -> str:
        """
        Get the provisioning URI for QR code generation.

        Args:
            secret: The TOTP secret
            email: User's email for identification

        Returns:
            otpauth:// URI string
        """
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp not installed")

        totp = self.get_totp(secret)
        return totp.provisioning_uri(name=email, issuer_name=self.ISSUER_NAME)

    def generate_backup_codes(self) -> list[str]:
        """Generate backup codes for recovery."""
        codes: list[str] = []
        for _ in range(self.BACKUP_CODE_COUNT):
            code = secrets.token_hex(self.BACKUP_CODE_LENGTH // 2).upper()
            # Format as XXXX-XXXX for readability
            formatted = f"{code[:4]}-{code[4:]}"
            codes.append(formatted)
        return codes

    def get_current_code(self, secret: str) -> str:
        """Get current TOTP code (for testing only)."""
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp not installed")
        return self.get_totp(secret).now()


# Singleton instance
totp_service = TOTPService()
