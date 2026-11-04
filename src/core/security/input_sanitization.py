"""
Input Sanitization and Injection Prevention Module
==================================================

Provides comprehensive protection against:
- SQL Injection (OWASP A03:2021)
- NoSQL Injection (MongoDB-style operators)
- Command Injection
- Path Traversal
- Header Injection

CRITICAL SECURITY COMPONENT - Used across all API endpoints for input validation.

Design Principles:
- Fail-secure: Invalid inputs are rejected, not sanitized
- Whitelist approach: Only allow known-safe patterns
- Defense in depth: Multiple validation layers
- Type coercion validation: Prevents type confusion attacks

Usage:
    from src.core.security.input_sanitization import (
        validate_string_input,
        validate_integer_id,
        validate_search_query,
        validate_json_data,
        InjectionProtector,
    )

    # Validate user input
    safe_name = validate_string_input(user_input, max_length=100)
    safe_id = validate_integer_id(tenant_id_string)
    safe_query = validate_search_query(search_term)

References:
- OWASP A03:2021 - Injection
- CWE-89: SQL Injection
- CWE-943: NoSQL Injection
- CWE-78: OS Command Injection
"""

import logging
import re
from enum import Enum
from typing import Any, Self, cast
from collections.abc import Iterator, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# SQL INJECTION PATTERNS
# ============================================================================

SQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Comment injection - more specific to avoid false positives
    # -- followed by end of string, space, or alphanumeric (SQL comment style)
    re.compile(r"--\s*$", re.IGNORECASE),  # -- at end of string
    re.compile(r"--\s+[a-zA-Z]", re.IGNORECASE),  # -- followed by text (comment)
    re.compile(r"'--", re.IGNORECASE),  # Quote followed by comment
    re.compile(r"/\*", re.IGNORECASE),
    re.compile(r"\*/"),
    # Union-based injection
    re.compile(r"\bUNION\s+(ALL\s+)?SELECT\b", re.IGNORECASE),
    re.compile(r"\bSELECT\s+.*\bFROM\b", re.IGNORECASE),
    # Boolean-based blind injection
    re.compile(r'\bOR\s+[\'"]?\d+[\'"]?\s*=\s*[\'"]?\d+[\'"]?', re.IGNORECASE),
    re.compile(r'\bAND\s+[\'"]?\d+[\'"]?\s*=\s*[\'"]?\d+[\'"]?', re.IGNORECASE),
    re.compile(r'\bOR\s+[\'"]?[a-zA-Z]+[\'"]?\s*=\s*[\'"]?[a-zA-Z]+[\'"]?', re.IGNORECASE),
    # Time-based blind injection
    re.compile(r"\bSLEEP\s*\(\d+\)", re.IGNORECASE),
    re.compile(r"\bWAITFOR\s+DELAY\b", re.IGNORECASE),
    re.compile(r"\bBENCHMARK\s*\(", re.IGNORECASE),
    re.compile(r"\bPG_SLEEP\s*\(", re.IGNORECASE),
    # Stacked queries
    re.compile(r";\s*DROP\b", re.IGNORECASE),
    re.compile(r";\s*DELETE\b", re.IGNORECASE),
    re.compile(r";\s*UPDATE\b", re.IGNORECASE),
    re.compile(r";\s*INSERT\b", re.IGNORECASE),
    re.compile(r";\s*ALTER\b", re.IGNORECASE),
    re.compile(r";\s*CREATE\b", re.IGNORECASE),
    re.compile(r";\s*TRUNCATE\b", re.IGNORECASE),
    re.compile(r";\s*GRANT\b", re.IGNORECASE),
    re.compile(r";\s*REVOKE\b", re.IGNORECASE),
    # Error-based injection
    re.compile(r"\bEXTRACTVALUE\s*\(", re.IGNORECASE),
    re.compile(r"\bUPDATEXML\s*\(", re.IGNORECASE),
    # Function-based injection
    re.compile(r"\bCONCAT\s*\(", re.IGNORECASE),
    re.compile(r"\bCHAR\s*\(\d+\)", re.IGNORECASE),
    re.compile(r"\bCONVERT\s*\(", re.IGNORECASE),
    re.compile(r"\bHEX\s*\(", re.IGNORECASE),
    re.compile(r"\bUNHEX\s*\(", re.IGNORECASE),
    re.compile(r"\bASCII\s*\(", re.IGNORECASE),
    # Information schema access
    re.compile(r"\bINFORMATION_SCHEMA\b", re.IGNORECASE),
    re.compile(r"\bSYSTEM_USER\b", re.IGNORECASE),
    re.compile(r"\bSESSION_USER\b", re.IGNORECASE),
    re.compile(r"\bCURRENT_USER\b", re.IGNORECASE),
    # Database-specific attacks
    re.compile(r"\bEXEC\s+XP_", re.IGNORECASE),  # SQL Server
    re.compile(r"\bEXEC\s+SP_", re.IGNORECASE),  # SQL Server stored procs
    re.compile(r"@@VERSION", re.IGNORECASE),
    re.compile(r"\bLOAD_FILE\s*\(", re.IGNORECASE),  # MySQL
    re.compile(r"\bINTO\s+OUTFILE\b", re.IGNORECASE),  # MySQL
    re.compile(r"\bINTO\s+DUMPFILE\b", re.IGNORECASE),  # MySQL
]


# ============================================================================
# NOSQL INJECTION PATTERNS (MongoDB-style)
# ============================================================================

NOSQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # MongoDB operators
    re.compile(r"\$where\b", re.IGNORECASE),
    re.compile(r"\$gt\b", re.IGNORECASE),
    re.compile(r"\$lt\b", re.IGNORECASE),
    re.compile(r"\$gte\b", re.IGNORECASE),
    re.compile(r"\$lte\b", re.IGNORECASE),
    re.compile(r"\$ne\b", re.IGNORECASE),
    re.compile(r"\$in\b", re.IGNORECASE),
    re.compile(r"\$nin\b", re.IGNORECASE),
    re.compile(r"\$or\b", re.IGNORECASE),
    re.compile(r"\$and\b", re.IGNORECASE),
    re.compile(r"\$not\b", re.IGNORECASE),
    re.compile(r"\$nor\b", re.IGNORECASE),
    re.compile(r"\$exists\b", re.IGNORECASE),
    re.compile(r"\$type\b", re.IGNORECASE),
    re.compile(r"\$regex\b", re.IGNORECASE),
    re.compile(r"\$expr\b", re.IGNORECASE),
    re.compile(r"\$text\b", re.IGNORECASE),
    re.compile(r"\$mod\b", re.IGNORECASE),
    re.compile(r"\$all\b", re.IGNORECASE),
    re.compile(r"\$elemMatch\b", re.IGNORECASE),
    re.compile(r"\$size\b", re.IGNORECASE),
    # JavaScript injection in MongoDB
    re.compile(r"function\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"this\.[a-zA-Z]", re.IGNORECASE),
    re.compile(r"\bdb\.[a-zA-Z_]+\.", re.IGNORECASE),  # db.collection.method pattern
    re.compile(r"\bdb\.[a-zA-Z_]+\s*\(", re.IGNORECASE),  # db.command() pattern
    # JSON-based injection patterns
    re.compile(r'"\s*:\s*\{"\$', re.IGNORECASE),  # Nested operator objects
]


# ============================================================================
# COMMAND INJECTION PATTERNS
# ============================================================================

COMMAND_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[;&|`$]"),  # Shell metacharacters
    re.compile(r"\$\("),  # Command substitution
    re.compile(r"\|\|"),  # OR operator
    re.compile(r"&&"),  # AND operator
    re.compile(r"\n"),  # Newline injection
    re.compile(r"\r"),  # Carriage return injection
    re.compile(r"%0[ad]", re.IGNORECASE),  # URL-encoded newlines
]


# ============================================================================
# PATH TRAVERSAL PATTERNS
# ============================================================================

PATH_TRAVERSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.\.[\\/]"),  # Directory traversal
    re.compile(r"\.\.%2[fF]"),  # URL-encoded traversal
    re.compile(r"\.\.%5[cC]"),  # URL-encoded backslash traversal
    re.compile(r"%2[eE]%2[eE]"),  # Double URL-encoded dots
    re.compile(r"/etc/passwd", re.IGNORECASE),
    re.compile(r"\\windows\\", re.IGNORECASE),
    re.compile(r"c:\\", re.IGNORECASE),
]


# ============================================================================
# ENUMS AND TYPES
# ============================================================================


class InjectionType(str, Enum):
    """Types of injection attacks detected."""

    SQL = "sql_injection"
    NOSQL = "nosql_injection"
    COMMAND = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    HEADER = "header_injection"
    UNKNOWN = "unknown"


class ValidationResult(BaseModel):
    """Result of input validation."""

    is_valid: bool = Field(..., description="Whether input passed validation")
    sanitized_value: str | None = Field(default=None, description="Sanitized value (if applicable)")
    error_message: str | None = Field(default=None, description="Error description if invalid")
    injection_type: InjectionType | None = Field(
        default=None, description="Type of injection detected"
    )
    matched_pattern: str | None = Field(
        default=None, description="Pattern that matched (for logging)"
    )


# ============================================================================
# CORE VALIDATION CLASS
# ============================================================================


class InjectionProtector:
    """
    Comprehensive injection attack detector and preventer.

    Security Features:
    - Pattern-based detection for SQL, NoSQL, command injection
    - Type coercion validation
    - Length limiting
    - Character whitelisting
    - Audit logging for detected attacks

    Usage:
        protector = InjectionProtector()

        # Check for SQL injection
        result = protector.check_sql_injection(user_input)
        if not result.is_valid:
            raise ValueError(result.error_message)

        # Full validation pipeline
        result = protector.validate_input(user_input, max_length=100)
    """

    def __init__(self, log_detections: bool = True) -> None:
        """
        Initialize the injection protector.

        Args:
            log_detections: Whether to log detected injection attempts
        """
        self.log_detections = log_detections

    def check_sql_injection(self, value: str) -> ValidationResult:
        """
        Check for SQL injection patterns.

        Args:
            value: Input string to check

        Returns:
            ValidationResult with detection details
        """
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value).__name__}",
                injection_type=InjectionType.UNKNOWN,
            )

        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                if self.log_detections:
                    logger.warning(
                        f"SQL injection attempt detected: pattern={pattern.pattern}, "
                        f"value_preview={value[:50]}..."
                    )
                return ValidationResult(
                    is_valid=False,
                    error_message="Potentially malicious SQL pattern detected",
                    injection_type=InjectionType.SQL,
                    matched_pattern=pattern.pattern,
                )

        return ValidationResult(is_valid=True, sanitized_value=value)

    def check_nosql_injection(self, value: str | dict[str, object]) -> ValidationResult:
        """
        Check for NoSQL/MongoDB injection patterns.

        Args:
            value: Input string or dict to check

        Returns:
            ValidationResult with detection details
        """
        # Convert dict to string for pattern matching
        if isinstance(value, dict):
            # Check for operator keys in dict
            def check_dict_keys(d: dict[str, object], path: str = "") -> str | None:
                for key, val in d.items():
                    if key.startswith("$"):
                        return f"NoSQL operator '{key}' at {path or 'root'}"
                    if isinstance(val, dict):
                        result = check_dict_keys(
                            cast(dict[str, object], val), f"{path}.{key}" if path else key
                        )
                        if result:
                            return result
                return None

            operator_found = check_dict_keys(value)
            if operator_found:
                if self.log_detections:
                    logger.warning(f"NoSQL injection attempt: {operator_found}")
                return ValidationResult(
                    is_valid=False,
                    error_message=f"NoSQL operator injection detected: {operator_found}",
                    injection_type=InjectionType.NOSQL,
                )
            return ValidationResult(is_valid=True)

        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string or dict, got {type(value).__name__}",
                injection_type=InjectionType.UNKNOWN,
            )

        for pattern in NOSQL_INJECTION_PATTERNS:
            if pattern.search(value):
                if self.log_detections:
                    logger.warning(
                        f"NoSQL injection attempt detected: pattern={pattern.pattern}, "
                        f"value_preview={value[:50]}..."
                    )
                return ValidationResult(
                    is_valid=False,
                    error_message="Potentially malicious NoSQL pattern detected",
                    injection_type=InjectionType.NOSQL,
                    matched_pattern=pattern.pattern,
                )

        return ValidationResult(is_valid=True, sanitized_value=value)

    def check_command_injection(self, value: str) -> ValidationResult:
        """
        Check for command injection patterns.

        Args:
            value: Input string to check

        Returns:
            ValidationResult with detection details
        """
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value).__name__}",
                injection_type=InjectionType.UNKNOWN,
            )

        for pattern in COMMAND_INJECTION_PATTERNS:
            if pattern.search(value):
                if self.log_detections:
                    logger.warning(f"Command injection attempt detected: pattern={pattern.pattern}")
                return ValidationResult(
                    is_valid=False,
                    error_message="Potentially malicious shell characters detected",
                    injection_type=InjectionType.COMMAND,
                    matched_pattern=pattern.pattern,
                )

        return ValidationResult(is_valid=True, sanitized_value=value)

    def check_path_traversal(self, value: str) -> ValidationResult:
        """
        Check for path traversal patterns.

        Args:
            value: Input string to check

        Returns:
            ValidationResult with detection details
        """
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value).__name__}",
                injection_type=InjectionType.UNKNOWN,
            )

        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(value):
                if self.log_detections:
                    logger.warning(f"Path traversal attempt detected: pattern={pattern.pattern}")
                return ValidationResult(
                    is_valid=False,
                    error_message="Path traversal pattern detected",
                    injection_type=InjectionType.PATH_TRAVERSAL,
                    matched_pattern=pattern.pattern,
                )

        return ValidationResult(is_valid=True, sanitized_value=value)

    def validate_input(
        self,
        value: str,
        max_length: int = 1000,
        allowed_chars: str | None = None,
        check_sql: bool = True,
        check_nosql: bool = True,
        check_command: bool = False,
        check_path: bool = False,
    ) -> ValidationResult:
        """
        Full validation pipeline for user input.

        Args:
            value: Input string to validate
            max_length: Maximum allowed length
            allowed_chars: Regex pattern for allowed characters (optional)
            check_sql: Check for SQL injection
            check_nosql: Check for NoSQL injection
            check_command: Check for command injection
            check_path: Check for path traversal

        Returns:
            ValidationResult with validation outcome
        """
        # Type check
        if not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                error_message=f"Expected string, got {type(value).__name__}",
            )

        # Length check
        if len(value) > max_length:
            return ValidationResult(
                is_valid=False,
                error_message=f"Input exceeds maximum length of {max_length}",
            )

        # Character whitelist check
        if allowed_chars:
            pattern = re.compile(f"^[{allowed_chars}]*$")
            if not pattern.match(value):
                return ValidationResult(
                    is_valid=False, error_message="Input contains disallowed characters"
                )

        # Injection checks
        if check_sql:
            result = self.check_sql_injection(value)
            if not result.is_valid:
                return result

        if check_nosql:
            result = self.check_nosql_injection(value)
            if not result.is_valid:
                return result

        if check_command:
            result = self.check_command_injection(value)
            if not result.is_valid:
                return result

        if check_path:
            result = self.check_path_traversal(value)
            if not result.is_valid:
                return result

        return ValidationResult(is_valid=True, sanitized_value=value)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Global protector instance
_protector = InjectionProtector()


def validate_string_input(
    value: object,
    max_length: int = 1000,
    min_length: int = 0,
    field_name: str = "input",
    strip_whitespace: bool = True,
    allow_empty: bool = False,
) -> str:
    """
    Validate and sanitize a string input.

    Args:
        value: Input value to validate
        max_length: Maximum allowed length
        min_length: Minimum required length
        field_name: Name of the field (for error messages)
        strip_whitespace: Whether to strip leading/trailing whitespace
        allow_empty: Whether to allow empty strings

    Returns:
        Validated and sanitized string

    Raises:
        ValueError: If validation fails
    """
    # Type coercion check
    if value is None:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name}: Cannot be None")

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name}: Expected string, got {type(value).__name__}. "
            "Type coercion attack detected."
        )

    str_value: str = value

    # Strip whitespace
    if strip_whitespace:
        str_value = str_value.strip()

    # Empty check
    if not str_value and not allow_empty:
        raise ValueError(f"{field_name}: Cannot be empty")

    # Length checks
    if len(str_value) < min_length:
        raise ValueError(f"{field_name}: Must be at least {min_length} characters")

    if len(str_value) > max_length:
        raise ValueError(f"{field_name}: Cannot exceed {max_length} characters")

    # Injection check
    result = _protector.validate_input(str_value, max_length=max_length)
    if not result.is_valid:
        raise ValueError(f"{field_name}: {result.error_message}")

    return str_value


def validate_integer_id(
    value: object,
    field_name: str = "id",
    min_value: int = 1,
    max_value: int = 2147483647,  # Max 32-bit signed int
) -> int:
    """
    Validate an integer ID value (e.g., tenant_id, user_id).

    CRITICAL: Prevents SQL injection via type confusion attacks.

    Args:
        value: Input value to validate
        field_name: Name of the field (for error messages)
        min_value: Minimum allowed value (default: 1)
        max_value: Maximum allowed value

    Returns:
        Validated integer

    Raises:
        ValueError: If validation fails
        TypeError: If type conversion fails
    """
    # Already an int
    if isinstance(value, int) and not isinstance(value, bool):
        if min_value <= value <= max_value:
            return value
        raise ValueError(f"{field_name}: Must be between {min_value} and {max_value}")

    # None check
    if value is None:
        raise ValueError(f"{field_name}: Cannot be None")

    # String that looks like SQL injection
    if isinstance(value, str):
        # Check for SQL injection patterns BEFORE conversion
        value_stripped = value.strip()

        # Must be purely numeric (with optional leading sign)
        if not re.match(r"^-?\d+$", value_stripped):
            logger.warning(
                f"Type coercion attack detected on {field_name}: value={value_stripped[:50]}"
            )
            raise ValueError(
                f"{field_name}: Invalid integer format. SQL injection attempt detected."
            )

        try:
            int_value = int(value_stripped)
            if min_value <= int_value <= max_value:
                return int_value
            raise ValueError(f"{field_name}: Must be between {min_value} and {max_value}")
        except ValueError:
            raise ValueError(f"{field_name}: Cannot convert to integer")

    # Unexpected type -- float/list/dict/bool etc. indicate a type confusion attack.
    # Use ValueError so Pydantic wraps it in ValidationError (TypeError escapes the validator).
    raise ValueError(
        f"{field_name}: Expected int or numeric string, got {type(value).__name__}. "
        "This may indicate a type confusion attack."
    )


def validate_search_query(
    value: object,
    max_length: int = 500,
    field_name: str = "search_query",
) -> str:
    """
    Validate a search query string with extra SQL/NoSQL checks.

    Search queries are high-risk because they often end up in LIKE clauses.

    Args:
        value: Search query to validate
        max_length: Maximum length
        field_name: Name of the field

    Returns:
        Validated search query

    Raises:
        ValueError: If validation fails
    """
    # Basic string validation
    validated = validate_string_input(
        value,
        max_length=max_length,
        field_name=field_name,
        allow_empty=True,
    )

    if not validated:
        return validated

    # Extra checks for search-specific patterns
    dangerous_patterns = [
        r"%[0-9a-fA-F]{2}",  # URL encoding (potential evasion)
        r"\\x[0-9a-fA-F]{2}",  # Hex encoding
        r"0x[0-9a-fA-F]+",  # Hex literals
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, validated):
            raise ValueError(f"{field_name}: Contains potentially malicious encoding")

    return validated


def validate_json_data(
    data: object,
    max_depth: int = 10,
    max_keys: int = 100,
    field_name: str = "json_data",
) -> dict[str, object]:
    """
    Validate JSON data for NoSQL injection patterns.

    Args:
        data: dictionary to validate
        max_depth: Maximum nesting depth
        max_keys: Maximum total number of keys
        field_name: Name of the field

    Returns:
        Validated dictionary

    Raises:
        ValueError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValueError(f"{field_name}: Expected dictionary, got {type(data).__name__}")

    dict_data = cast(dict[str, object], data)
    key_count = [0]  # Use list for mutability in nested function

    def check_dict(d: dict[str, object], depth: int = 0) -> None:
        if depth > max_depth:
            raise ValueError(f"{field_name}: JSON nesting exceeds maximum depth of {max_depth}")

        for key, value in d.items():
            key_count[0] += 1
            if key_count[0] > max_keys:
                raise ValueError(f"{field_name}: JSON has too many keys (max: {max_keys})")

            # Check for NoSQL operators
            if isinstance(key, str) and key.startswith("$"):
                raise ValueError(f"{field_name}: NoSQL operator key '{key}' not allowed")

            # Validate string keys
            if isinstance(key, str):
                result = _protector.check_nosql_injection(key)
                if not result.is_valid:
                    raise ValueError(f"{field_name}: {result.error_message} in key")

            # Validate string values
            if isinstance(value, str):
                result = _protector.validate_input(value)
                if not result.is_valid:
                    raise ValueError(f"{field_name}: {result.error_message} in value")

            # Recurse into nested dicts
            if isinstance(value, dict):
                check_dict(cast(dict[str, object], value), depth + 1)

            # Check lists
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        check_dict(cast(dict[str, object], item), depth + 1)
                    elif isinstance(item, str):
                        result = _protector.validate_input(item)
                        if not result.is_valid:
                            raise ValueError(f"{field_name}: {result.error_message} in array")

    check_dict(dict_data)
    return dict_data


def validate_email(
    value: object,
    field_name: str = "email",
) -> str:
    """
    Validate an email address.

    Args:
        value: Email to validate
        field_name: Name of the field

    Returns:
        Validated email

    Raises:
        ValueError: If validation fails
    """
    # Basic string validation
    validated = validate_string_input(
        value,
        max_length=254,  # RFC 5321 max length
        field_name=field_name,
    )

    # Email format check
    email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    if not email_pattern.match(validated):
        raise ValueError(f"{field_name}: Invalid email format")

    return validated.lower()


def validate_uuid(
    value: object,
    field_name: str = "uuid",
) -> str:
    """
    Validate a UUID string.

    Args:
        value: UUID to validate
        field_name: Name of the field

    Returns:
        Validated UUID string (lowercase)

    Raises:
        ValueError: If validation fails
    """
    # Basic string validation
    validated = validate_string_input(
        value,
        max_length=36,
        field_name=field_name,
    )

    # UUID format check
    uuid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )

    if not uuid_pattern.match(validated):
        raise ValueError(f"{field_name}: Invalid UUID format")

    return validated.lower()


def escape_like_pattern(value: str) -> str:
    """
    Escape special characters for SQL LIKE patterns.

    Use this when building LIKE queries with user input.

    Args:
        value: String to escape

    Returns:
        Escaped string safe for LIKE patterns

    Example:
        # Instead of: query.filter(Model.name.like(f"%{user_input}%"))
        # Use:
        safe_pattern = escape_like_pattern(user_input)
        query.filter(Model.name.like(f"%{safe_pattern}%", escape='\\'))
    """
    # Escape backslash first, then other special chars
    value = value.replace("\\", "\\\\")
    value = value.replace("%", "\\%")
    value = value.replace("_", "\\_")
    return value


# ============================================================================
# PYDANTIC VALIDATORS FOR SCHEMAS
# ============================================================================


class SecureStringField(str):
    """
    Custom string type with built-in injection protection.

    Usage in Pydantic models:
        class MySchema(BaseModel):
            name: SecureStringField
    """

    @classmethod
    def __get_validators__(cls) -> Iterator[Callable[..., Self]]:
        yield cls.validate

    @classmethod
    def validate(cls, v: object, info: object = None) -> Self:
        if not isinstance(v, str):
            raise ValueError("String required")

        result = _protector.validate_input(v)
        if not result.is_valid:
            raise ValueError(result.error_message)

        return cls(v)


class SecureIntField(int):
    """
    Custom integer type with built-in validation.

    Usage in Pydantic models:
        class MySchema(BaseModel):
            tenant_id: SecureIntField
    """

    @classmethod
    def __get_validators__(cls) -> Iterator[Callable[..., Self]]:
        yield cls.validate

    @classmethod
    def validate(cls, v: object, info: object = None) -> Self:
        validated = validate_integer_id(v, field_name="field")
        return cls(validated)


# ============================================================================
# SECURITY AUDIT LOGGING
# ============================================================================


def log_injection_attempt(
    injection_type: InjectionType,
    value: str,
    endpoint: str | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Log a detected injection attempt for security auditing.

    Args:
        injection_type: Type of injection detected
        value: The malicious input value
        endpoint: API endpoint where detected
        user_id: ID of the user (if authenticated)
        ip_address: Client IP address
    """
    logger.critical(
        f"INJECTION ATTEMPT DETECTED | "
        f"type={injection_type.value} | "
        f"endpoint={endpoint or 'unknown'} | "
        f"user_id={user_id or 'anonymous'} | "
        f"ip={ip_address or 'unknown'} | "
        f"value_preview={value[:100] if value else 'empty'}..."
    )


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Core classes
    "InjectionProtector",
    "ValidationResult",
    "InjectionType",
    # Validation functions
    "validate_string_input",
    "validate_integer_id",
    "validate_search_query",
    "validate_json_data",
    "validate_email",
    "validate_uuid",
    # Utilities
    "escape_like_pattern",
    "log_injection_attempt",
    # Custom types
    "SecureStringField",
    "SecureIntField",
    # Pattern lists (for testing)
    "SQL_INJECTION_PATTERNS",
    "NOSQL_INJECTION_PATTERNS",
    "COMMAND_INJECTION_PATTERNS",
    "PATH_TRAVERSAL_PATTERNS",
]
