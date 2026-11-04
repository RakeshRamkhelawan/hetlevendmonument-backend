"""
Unit Tests for Password Policy (SA-3.1)

Tests password validation against security policy requirements.
"""

import pytest

from src.core.auth.password_policy import MIN_LENGTH, validate_password, validate_password_detailed


class TestPasswordValidation:
    """Tests for validate_password function."""

    def test_valid_password(self):
        """Test a password that meets all requirements."""
        assert validate_password("StrongPass123!") is True
        assert validate_password("MyP@ssw0rd123") is True
        assert validate_password("AbcDefGhi1!@") is True

    def test_too_short(self):
        """Test password shorter than minimum length."""
        assert validate_password("Short1!") is False
        assert validate_password("Ab1!") is False

    def test_missing_uppercase(self):
        """Test password without uppercase letter."""
        assert validate_password("nouppercase123!") is False

    def test_missing_lowercase(self):
        """Test password without lowercase letter."""
        assert validate_password("NOLOWERCASE123!") is False

    def test_missing_digit(self):
        """Test password without digit."""
        assert validate_password("NoDigitsHere!!") is False

    def test_missing_special(self):
        """Test password without special character."""
        assert validate_password("NoSpecialChar123") is False

    def test_edge_case_exactly_min_length(self):
        """Test password exactly at minimum length."""
        # 12 characters with all requirements
        assert validate_password("ValidPass1!a") is True


class TestPasswordValidationDetailed:
    """Tests for validate_password_detailed function."""

    def test_valid_password_no_errors(self):
        """Test valid password returns no errors."""
        is_valid, errors = validate_password_detailed("StrongPass123!")
        assert is_valid is True
        assert errors == []

    def test_multiple_violations(self):
        """Test password with multiple violations returns all errors."""
        is_valid, errors = validate_password_detailed("short")
        assert is_valid is False
        assert len(errors) >= 4  # Too short, no uppercase, no digit, no special

    def test_single_violation_message(self):
        """Test specific error message for single violation."""
        # Has uppercase, lowercase, digit - just missing special char
        is_valid, errors = validate_password_detailed("ValidPassword123")
        assert is_valid is False
        assert any("special character" in e for e in errors)


class TestPasswordPolicyConstants:
    """Tests for password policy constants."""

    def test_min_length_is_12(self):
        """Verify minimum length requirement is 12."""
        assert MIN_LENGTH == 12
