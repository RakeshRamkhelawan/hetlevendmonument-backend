"""
Unit tests for TOTPService (two_factor_auth.py).

Covers: generate_secret, get_totp, verify_code, get_provisioning_uri,
generate_backup_codes, get_current_code.
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from src.core.auth.two_factor_auth import TOTPService, PYOTP_AVAILABLE

requires_pyotp = pytest.mark.skipif(not PYOTP_AVAILABLE, reason="pyotp not installed")


@pytest.fixture
def totp_service():
    return TOTPService()


class TestTOTPServiceGenerateSecret:
    """Tests for generate_secret()."""

    @requires_pyotp
    def test_generates_base32_string(self, totp_service):
        secret = totp_service.generate_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0
        # Base32 characters only
        assert re.match(r"^[A-Z2-7]+=*$", secret)

    @requires_pyotp
    def test_generates_unique_secrets(self, totp_service):
        secrets = {totp_service.generate_secret() for _ in range(50)}
        assert len(secrets) == 50

    def test_raises_when_pyotp_unavailable(self, totp_service):
        with patch("src.core.auth.two_factor_auth.PYOTP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyotp not installed"):
                totp_service.generate_secret()


class TestTOTPServiceGetTotp:
    """Tests for get_totp()."""

    @requires_pyotp
    def test_returns_totp_instance(self, totp_service):
        secret = totp_service.generate_secret()
        totp = totp_service.get_totp(secret)
        assert totp is not None
        assert hasattr(totp, "verify")
        assert hasattr(totp, "now")

    def test_raises_when_pyotp_unavailable(self, totp_service):
        with patch("src.core.auth.two_factor_auth.PYOTP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyotp not installed"):
                totp_service.get_totp("ABCDEFGH")


class TestTOTPServiceVerifyCode:
    """Tests for verify_code()."""

    @requires_pyotp
    def test_valid_code_returns_true(self, totp_service):
        secret = totp_service.generate_secret()
        current_code = totp_service.get_current_code(secret)
        assert totp_service.verify_code(secret, current_code) is True

    @requires_pyotp
    def test_invalid_code_returns_false(self, totp_service):
        secret = totp_service.generate_secret()
        assert totp_service.verify_code(secret, "000000") is False

    @requires_pyotp
    def test_wrong_secret_returns_false(self, totp_service):
        secret1 = totp_service.generate_secret()
        secret2 = totp_service.generate_secret()
        code = totp_service.get_current_code(secret1)
        assert totp_service.verify_code(secret2, code) is False

    @requires_pyotp
    def test_window_parameter_accepted(self, totp_service):
        secret = totp_service.generate_secret()
        code = totp_service.get_current_code(secret)
        # Window of 2 allows more time drift
        assert totp_service.verify_code(secret, code, window=2) is True

    def test_returns_false_when_pyotp_unavailable(self, totp_service):
        with patch("src.core.auth.two_factor_auth.PYOTP_AVAILABLE", False):
            assert totp_service.verify_code("secret", "123456") is False

    @requires_pyotp
    def test_returns_false_on_exception(self, totp_service):
        # Invalid secret that causes an exception
        assert totp_service.verify_code("", "123456") is False


class TestTOTPServiceProvisioningUri:
    """Tests for get_provisioning_uri()."""

    @requires_pyotp
    def test_returns_otpauth_uri(self, totp_service):
        secret = totp_service.generate_secret()
        uri = totp_service.get_provisioning_uri(secret, "user@example.com")
        assert uri.startswith("otpauth://totp/")

    @requires_pyotp
    def test_contains_issuer(self, totp_service):
        secret = totp_service.generate_secret()
        uri = totp_service.get_provisioning_uri(secret, "user@example.com")
        assert "SanskritiSetu" in uri

    @requires_pyotp
    def test_contains_email(self, totp_service):
        secret = totp_service.generate_secret()
        uri = totp_service.get_provisioning_uri(secret, "test@domain.com")
        assert "test%40domain.com" in uri or "test@domain.com" in uri

    def test_raises_when_pyotp_unavailable(self, totp_service):
        with patch("src.core.auth.two_factor_auth.PYOTP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyotp not installed"):
                totp_service.get_provisioning_uri("secret", "email@test.com")


class TestTOTPServiceBackupCodes:
    """Tests for generate_backup_codes()."""

    def test_generates_correct_count(self, totp_service):
        codes = totp_service.generate_backup_codes()
        assert len(codes) == TOTPService.BACKUP_CODE_COUNT  # 10

    def test_codes_are_formatted(self, totp_service):
        codes = totp_service.generate_backup_codes()
        for code in codes:
            # Format: XXXX-XXXX
            assert re.match(r"^[A-F0-9]{4}-[A-F0-9]{4}$", code), f"Bad format: {code}"    

    def test_codes_are_unique(self, totp_service):
        codes = totp_service.generate_backup_codes()
        assert len(set(codes)) == len(codes)

    def test_codes_are_different_each_call(self, totp_service):
        codes1 = set(totp_service.generate_backup_codes())
        codes2 = set(totp_service.generate_backup_codes())
        # Extremely unlikely all 10 codes match
        assert codes1 != codes2


class TestTOTPServiceGetCurrentCode:
    """Tests for get_current_code()."""

    @requires_pyotp
    def test_returns_6_digit_string(self, totp_service):
        secret = totp_service.generate_secret()
        code = totp_service.get_current_code(secret)
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()

    def test_raises_when_pyotp_unavailable(self, totp_service):
        with patch("src.core.auth.two_factor_auth.PYOTP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyotp not installed"):
                totp_service.get_current_code("ABCDEF")
