"""
Unit Tests for Pydantic Validators (SC-7.1)

Tests custom validators for common data types.
"""

import pytest
from pydantic import BaseModel, ValidationError

from src.core.schemas.validators import (
    NormalizedEmail,
    PhoneNumber,
    Slug,
    Username,
    normalize_email,
    validate_phone_number,
    validate_slug,
    validate_url,
    validate_username,
)


class TestPhoneNumberValidator:
    """Tests for phone number validation."""

    def test_valid_international_format(self):
        """Test valid international phone number."""
        assert validate_phone_number("+31612345678") == "+31612345678"

    def test_valid_local_format(self):
        """Test valid local phone number."""
        assert validate_phone_number("0612345678") == "0612345678"

    def test_strips_spaces(self):
        """Test spaces are removed."""
        assert validate_phone_number("06 12 34 56 78") == "0612345678"

    def test_strips_dashes(self):
        """Test dashes are removed."""
        assert validate_phone_number("06-12345678") == "0612345678"

    def test_invalid_phone(self):
        """Test invalid phone number raises error."""
        with pytest.raises(ValueError):
            validate_phone_number("invalid")

    def test_too_short(self):
        """Test too short phone number raises error."""
        with pytest.raises(ValueError):
            validate_phone_number("123")


class TestSlugValidator:
    """Tests for URL slug validation."""

    def test_valid_slug(self):
        """Test valid slug."""
        assert validate_slug("my-blog-post") == "my-blog-post"
        assert validate_slug("article123") == "article123"

    def test_invalid_uppercase_strict(self):
        """Test uppercase in strict slug raises error."""
        with pytest.raises(ValueError):
            validate_slug("MySlug", strict=True)

    def test_invalid_underscore_strict(self):
        """Test underscore in strict slug raises error."""
        with pytest.raises(ValueError):
            validate_slug("my_slug", strict=True)


class TestUsernameValidator:
    """Tests for username validation."""

    def test_valid_username(self):
        """Test valid username."""
        assert validate_username("johndoe") == "johndoe"
        assert validate_username("User123") == "user123"  # Normalized to lowercase

    def test_with_underscore(self):
        """Test username with underscore."""
        assert validate_username("john_doe") == "john_doe"

    def test_too_short(self):
        """Test username too short."""
        with pytest.raises(ValueError):
            validate_username("ab")

    def test_starts_with_number(self):
        """Test username starting with number."""
        with pytest.raises(ValueError):
            validate_username("1user")


class TestUrlValidator:
    """Tests for URL validation."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        url = "https://example.com/path"
        assert validate_url(url) == url

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        url = "http://localhost:8100"
        assert validate_url(url) == url

    def test_invalid_url(self):
        """Test invalid URL raises error."""
        with pytest.raises(ValueError):
            validate_url("not-a-url")


class TestEmailNormalization:
    """Tests for email normalization."""

    def test_lowercase(self):
        """Test email is lowercased."""
        assert normalize_email("TEST@Example.COM") == "test@example.com"

    def test_strip_whitespace(self):
        """Test whitespace is stripped."""
        assert normalize_email("  test@example.com  ") == "test@example.com"


class TestPydanticIntegration:
    """Tests for Pydantic model integration."""

    def test_phone_in_model(self):
        """Test PhoneNumber type in Pydantic model."""

        class Contact(BaseModel):
            phone: PhoneNumber

        contact = Contact(phone="06 12 34 56 78")
        assert contact.phone == "0612345678"

    def test_email_normalization_in_model(self):
        """Test NormalizedEmail in Pydantic model."""

        class User(BaseModel):
            email: NormalizedEmail

        user = User(email="  TEST@EXAMPLE.COM  ")
        assert user.email == "test@example.com"
