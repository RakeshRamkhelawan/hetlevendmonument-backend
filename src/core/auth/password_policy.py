"""
Password Policy Enforcement

Enforces strong password requirements during registration.

Part of SA-3.1 implementation.

Edge Cases:
- None/empty passwords: Raises ValueError
- Non-string types: Raises TypeError
- Unicode passwords: NOT allowed (ASCII-only for bcrypt compatibility)
- Very long passwords (>72 chars): Allowed, but bcrypt truncates internally
"""

import re
from typing import Any

# Password policy configuration
MIN_LENGTH = 12
MAX_LENGTH = 128  # Prevent DoS with very long passwords
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True
SPECIAL_CHARS = r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]"


def _validate_input(password: str) -> str:
    """
    Validate password input type and basic constraints.

    Args:
        password: Value to validate

    Returns:
        Validated password string

    Raises:
        TypeError: If password is not a string
        ValueError: If password is None or empty
    """
    if password is None:
        raise ValueError("Password cannot be None")

    if not isinstance(password, str):
        raise TypeError(f"Password must be a string, got {type(password).__name__}")

    if not password:
        raise ValueError("Password cannot be empty")

    if len(password) > MAX_LENGTH:
        raise ValueError(f"Password cannot exceed {MAX_LENGTH} characters")

    return password


def validate_password(password: str) -> bool:
    """
    Validate password against security policy.

    Requirements:
    - Minimum 12 characters
    - Maximum 128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - ASCII characters only (for bcrypt compatibility)

    Args:
        password: Plain text password to validate

    Returns:
        True if password meets all requirements, False otherwise

    Raises:
        TypeError: If password is not a string
        ValueError: If password is None or empty
    """
    password = _validate_input(password)

    if len(password) < MIN_LENGTH:
        return False
    if not password.isascii():
        return False
    if REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False
    if REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False
    if REQUIRE_DIGIT and not re.search(r"\d", password):
        return False
    if REQUIRE_SPECIAL and not re.search(SPECIAL_CHARS, password):
        return False
    return True


def validate_password_detailed(password: str) -> tuple[bool, list[str]]:
    """
    Validate password with detailed error messages.

    Args:
        password: Plain text password to validate

    Returns: Tuple[Any, ...] of (is_valid, list_of_errors)  # TODO(TYPE): replace Any with concrete type

    Raises:
        TypeError: If password is not a string
        ValueError: If password is None or empty
    """
    password = _validate_input(password)
    errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters")
    if not password.isascii():
        errors.append("Password must contain only ASCII characters")
    if REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if REQUIRE_DIGIT and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")
    if REQUIRE_SPECIAL and not re.search(SPECIAL_CHARS, password):
        errors.append("Password must contain at least one special character (!@#$%^&*)")

    return (len(errors) == 0, errors)
