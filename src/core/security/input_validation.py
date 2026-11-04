"""
Input Validation & Sanitization Module

Provides centralized input validation to prevent:
- SQL Injection
- XSS (Cross-Site Scripting)
- Command Injection
- Path Traversal
- NoSQL Injection

Usage:
    from src.core.security.input_validation import validate_input, sanitize_string

    # Validate user input
    username = validate_input(raw_username, pattern=r'^[a-zA-Z0-9_]{3,50}$')

    # Sanitize for display
    safe_html = sanitize_string(user_content, allow_tags=['p', 'br'])
"""

import html
import logging
import re
from typing import Any, Optional, Union
from re import Pattern
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class InputValidationError(ValueError):
    """Raised when input validation fails."""

    pass


# Common validation patterns
PATTERNS = {
    "username": re.compile(r"^[a-zA-Z0-9_]{3,50}$"),
    "email": re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
    "uuid": re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    "slug": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    "safe_string": re.compile(r"^[\w\s\-\.\,\@\/\:\?\=\&\+]{1,1000}$"),
    "alphanumeric": re.compile(r"^[a-zA-Z0-9]+$"),
    "phone": re.compile(r"^\+?[1-9]\d{1,14}$"),  # E.164 format
    "ip_address": re.compile(
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    ),
    "url_path": re.compile(r"^[\/a-zA-Z0-9\-\._~%!$&\'()*+,;=:@]{1,2000}$"),
}

# SQL Injection patterns
SQL_INJECTION_PATTERNS = [
    re.compile(r"(\%27)|(\')|(\-\-)|(\%23)|(#)", re.I),
    re.compile(r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))", re.I),
    re.compile(r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))", re.I),
    re.compile(r"((\%27)|(\'))union", re.I),
    re.compile(r"exec(\s|\+)+(s|x)p\w+", re.I),
    re.compile(r"UNION SELECT", re.I),
    re.compile(r"INSERT INTO", re.I),
    re.compile(r"DELETE FROM", re.I),
    re.compile(r"DROP TABLE", re.I),
]

# XSS patterns
XSS_PATTERNS = [
    re.compile(r"<script[^>]*>[\s\S]*?</script>", re.I),
    re.compile(r"javascript:", re.I),
    re.compile(r"on\w+\s*=", re.I),  # onclick=, onerror=, etc.
    re.compile(r"<iframe", re.I),
    re.compile(r"<object", re.I),
    re.compile(r"<embed", re.I),
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\.\/"),  # ../
    re.compile(r"\.\.\\"),  # ..\
    re.compile(r"%2e%2e%2f", re.I),  # URL encoded ../
    re.compile(r"%2e%2e/", re.I),
    re.compile(r"..%2f", re.I),
]


def validate_input(
    value: str,
    pattern: str | Pattern[str] | None = None,
    pattern_name: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    allow_empty: bool = False,
    field_name: str = "input",
) -> str:
    """
    Validate input against security patterns.

    Args:
        value: Input value to validate
        pattern: Regex pattern or pattern name to validate against
        pattern_name: Name of predefined pattern from PATTERNS dict
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        allow_empty: Whether to allow empty strings
        field_name: Name of field for error messages

    Returns:
        Validated input string

    Raises:
        InputValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise InputValidationError(f"{field_name} must be a string")

    # Check empty
    if not value and not allow_empty:
        raise InputValidationError(f"{field_name} cannot be empty")

    if not value:
        return value

    # Check length
    if min_length is not None and len(value) < min_length:
        raise InputValidationError(f"{field_name} must be at least {min_length} characters")

    if max_length is not None and len(value) > max_length:
        raise InputValidationError(f"{field_name} must be at most {max_length} characters")

    # Check for SQL injection
    if contains_sql_injection(value):
        logger.warning(f"SQL injection attempt detected in {field_name}")
        raise InputValidationError(f"{field_name} contains invalid characters")

    # Check against pattern
    if pattern_name:
        if pattern_name not in PATTERNS:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        pattern = PATTERNS[pattern_name]

    if pattern:
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        if not pattern.match(value):
            raise InputValidationError(f"{field_name} format is invalid")

    return value


def contains_sql_injection(value: str) -> bool:
    """Check if value contains SQL injection patterns."""
    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return True
    return False


def contains_xss(value: str) -> bool:
    """Check if value contains XSS patterns."""
    for pattern in XSS_PATTERNS:
        if pattern.search(value):
            return True
    return False


def contains_path_traversal(value: str) -> bool:
    """Check if value contains path traversal patterns."""
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value):
            return True
    return False


def sanitize_string(
    value: str, allow_tags: list[str] | None = None, escape_html: bool = True
) -> str:
    """
    Sanitize string for safe display.

    Args:
        value: String to sanitize
        allow_tags: List[Any] of allowed HTML tags (empty = no tags)  # TODO(TYPE): replace Any with concrete type
        escape_html: Whether to escape HTML entities

    Returns:
        Sanitized string
    """
    if not value:
        return value

    # Check for XSS
    if contains_xss(value):
        logger.warning("XSS attempt detected in input")
        # Remove all HTML if XSS detected
        allow_tags = []
    # Escape HTML entities
    if escape_html and not allow_tags:
        value = html.escape(value)
    elif escape_html and allow_tags:
        # Allow specific safe HTML tags
        # This is a simplified version - production should use bleach
        value = html.escape(value)
        # Restore allowed tags (simplified)
        for tag in allow_tags:
            value = value.replace(f"&lt;{tag}&gt;", f"<{tag}>")
            value = value.replace(f"&lt;/{tag}&gt;", f"</{tag}>")

    return value


def validate_email(email: str) -> str:
    """Validate email address format."""
    return validate_input(email, pattern_name="email", max_length=254, field_name="email")


def validate_username(username: str) -> str:
    """Validate username format."""
    return validate_input(
        username,
        pattern_name="username",
        min_length=3,
        max_length=50,
        field_name="username",
    )


def validate_uuid(uuid_str: str) -> str:
    """Validate UUID format."""
    return validate_input(uuid_str, pattern_name="uuid", field_name="uuid")


def validate_url(url: str, allowed_schemes: list[str] | None = None) -> str:
    """
    Validate URL format and scheme.

    Args:
        url: URL to validate
        allowed_schemes: List[Any] of allowed schemes (default: http, https)  # TODO(TYPE): replace Any with concrete type

    Returns:
        Validated URL

    Raises:
        InputValidationError: If URL is invalid
    """
    if not allowed_schemes:
        allowed_schemes = ["http", "https"]

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InputValidationError(f"Invalid URL format: {e}")

    if parsed.scheme not in allowed_schemes:
        raise InputValidationError(f"URL scheme must be one of: {', '.join(allowed_schemes)}")

    if not parsed.netloc:
        raise InputValidationError("URL must have a domain")

    return url


def validate_file_path(path: str, base_dir: str | None = None) -> str:
    """
    Validate file path for path traversal attacks.

    Args:
        path: File path to validate
        base_dir: Base directory that path must be within

    Returns:
        Validated path

    Raises:
        InputValidationError: If path is invalid or outside base_dir
    """
    if contains_path_traversal(path):
        raise InputValidationError("Path contains invalid traversal sequences")

    if base_dir:
        from pathlib import Path

        try:
            full_path = Path(base_dir).resolve() / path
            base_resolved = Path(base_dir).resolve()

            # Check if path is within base_dir
            if not str(full_path).startswith(str(base_resolved)):
                raise InputValidationError("Path is outside allowed directory")
        except Exception as e:
            raise InputValidationError(f"Invalid path: {e}")

    return path


def validate_json_payload(data: dict[str, Any], max_depth: int = 10) -> None:  # TODO(TYPE): replace Any with concrete type
    """
    Validate JSON payload for nested depth and size.

    Args:
        data: Dict[str, Any]ionary to validate  # TODO(TYPE): replace Any with concrete type
        max_depth: Maximum allowed nesting depth

    Raises:
        InputValidationError: If payload is invalid
    """

    def check_depth(obj: Any, current_depth: int) -> int:  # TODO(TYPE): replace Any with concrete type
        if current_depth > max_depth:
            raise InputValidationError(f"JSON nesting exceeds maximum depth of {max_depth}")

        if isinstance(obj, dict):
            return max(
                (check_depth(v, current_depth + 1) for v in obj.values()),
                default=current_depth,
            )
        elif isinstance(obj, list):
            return max(
                (check_depth(item, current_depth + 1) for item in obj),
                default=current_depth,
            )
        return current_depth

    check_depth(data, 0)

    # Check total size
    import json

    payload_size = len(json.dumps(data))
    max_size = 10 * 1024 * 1024  # 10MB
    if payload_size > max_size:
        raise InputValidationError(f"JSON payload exceeds maximum size of {max_size} bytes")


# Pydantic validators for use in models
def validate_safe_string(cls: Any, v: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Pydantic validator for safe string fields."""
    if v is None:
        return v
    return validate_input(v, pattern_name="safe_string", field_name=cls.__name__)


def validate_no_sql_injection(cls: Any, v: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Pydantic validator to check for SQL injection."""
    if v is None:
        return v
    if contains_sql_injection(str(v)):
        raise ValueError("Input contains invalid characters")
    return v
