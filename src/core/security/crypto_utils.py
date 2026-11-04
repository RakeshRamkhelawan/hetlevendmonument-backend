"""
Cryptographic Utilities for OWASP A02: Cryptographic Failures Prevention

Provides centralized, hardened cryptographic functions for:
- JWT token creation and validation with algorithm confusion protection
- Password hashing with bcrypt (configurable rounds)
- Secret key validation and management
- Timing-safe comparisons

Security Features:
- Explicit algorithm whitelist (prevents "none" algorithm attack)
- Minimum key length enforcement
- Password policy validation
- ASCII-only password enforcement (bcrypt compatibility)
- 72-byte password truncation (bcrypt limit)
- Constant-time comparisons where applicable
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, ValidationInfo, field_validator

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS - Security Configuration
# ============================================================================

# Allowed JWT algorithms (CRITICAL: Never include "none")
ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})

# Minimum secret key length for production
MIN_SECRET_KEY_LENGTH = 32
MIN_SECRET_KEY_LENGTH_PRODUCTION = 64

# Password policy constants
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
BCRYPT_MAX_PASSWORD_LENGTH = 72  # bcrypt truncates at 72 bytes

# Default bcrypt rounds (12 for production, 4 for testing)
BCRYPT_ROUNDS_PRODUCTION = 12
BCRYPT_ROUNDS_TESTING = 4

# Weak password patterns
WEAK_PASSWORD_PATTERNS = [
    r"^123456",
    r"^password",
    r"^qwerty",
    r"^admin",
    r"^letmein",
    r"^welcome",
    r"^abc123",
    r"^111111",
]


# ============================================================================
# PASSWORD POLICY
# ============================================================================


class PasswordPolicy(BaseModel):
    """Password policy configuration with validation"""

    min_length: int = Field(default=MIN_PASSWORD_LENGTH, ge=8, le=128)
    max_length: int = Field(default=MAX_PASSWORD_LENGTH, ge=8, le=128)
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = False
    special_characters: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    reject_common_passwords: bool = True

    @field_validator("max_length")
    @classmethod
    def max_length_must_exceed_min(cls, v: int, info: ValidationInfo) -> int:
        """Ensure max_length exceeds min_length"""
        if "min_length" in info.data and v < info.data["min_length"]:
            raise ValueError("max_length must be >= min_length")
        return v


class PasswordValidationResult(BaseModel):
    """Result of password validation"""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    strength_score: int = Field(default=0, ge=0, le=100)


def validate_password(
    password: str, policy: PasswordPolicy | None = None
) -> PasswordValidationResult:
    """
    Validate password against security policy.

    OWASP A02 Protection:
    - Enforces minimum length
    - Checks character requirements
    - Rejects common/weak passwords
    - Validates ASCII-only (bcrypt compatibility)

    Args:
        password: Plain text password to validate
        policy: Optional custom policy (uses default if not provided)

    Returns:
        PasswordValidationResult with validation details
    """
    if policy is None:
        policy = PasswordPolicy()

    errors: list[str] = []
    warnings: list[str] = []
    strength_score = 0

    # Type check
    if not isinstance(password, str):
        return PasswordValidationResult(
            is_valid=False, errors=["Password must be a string"], strength_score=0
        )

    # ASCII-only check (bcrypt compatibility)
    if not password.isascii():
        errors.append("Password must contain only ASCII characters (bcrypt compatibility)")

    # Length checks
    if len(password) < policy.min_length:
        errors.append(f"Password must be at least {policy.min_length} characters")
    elif len(password) >= policy.min_length:
        strength_score += 20

    if len(password) > policy.max_length:
        errors.append(f"Password must not exceed {policy.max_length} characters")

    # Character truncation warning
    if len(password) > BCRYPT_MAX_PASSWORD_LENGTH:
        warnings.append(
            f"Password exceeds {BCRYPT_MAX_PASSWORD_LENGTH} characters and will be truncated by bcrypt"
        )

    # Uppercase check
    if policy.require_uppercase:
        if re.search(r"[A-Z]", password):
            strength_score += 15
        else:
            errors.append("Password must contain at least one uppercase letter")

    # Lowercase check
    if policy.require_lowercase:
        if re.search(r"[a-z]", password):
            strength_score += 15
        else:
            errors.append("Password must contain at least one lowercase letter")

    # Digit check
    if policy.require_digit:
        if re.search(r"\d", password):
            strength_score += 15
        else:
            errors.append("Password must contain at least one digit")

    # Special character check
    if policy.require_special:
        special_pattern = f"[{re.escape(policy.special_characters)}]"
        if re.search(special_pattern, password):
            strength_score += 20
        else:
            errors.append(
                f"Password must contain at least one special character: {policy.special_characters}"
            )
    else:
        # Bonus for optional special characters
        if re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
            strength_score += 15

    # Common password check
    if policy.reject_common_passwords:
        password_lower = password.lower()
        for pattern in WEAK_PASSWORD_PATTERNS:
            if re.match(pattern, password_lower, re.IGNORECASE):
                errors.append("Password matches a common/weak password pattern")
                strength_score = max(0, strength_score - 30)
                break

    # Entropy bonus for length
    if len(password) >= 12:
        strength_score += 10
    if len(password) >= 16:
        strength_score += 5

    # Cap strength score
    strength_score = min(100, max(0, strength_score))

    return PasswordValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        strength_score=strength_score,
    )


# ============================================================================
# PASSWORD HASHING
# ============================================================================


def get_password_context(testing: bool = False) -> CryptContext:
    """
    Get configured password hashing context.

    OWASP A02 Protection:
    - Uses bcrypt with appropriate work factor
    - Lower rounds in testing for performance
    - Production-grade rounds for deployment

    Args:
        testing: If True, use lower rounds for test performance

    Returns:
        Configured CryptContext for password hashing
    """
    rounds = BCRYPT_ROUNDS_TESTING if testing else BCRYPT_ROUNDS_PRODUCTION

    return CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=rounds)


def _prepare_password_for_bcrypt(password: str) -> str:
    """
    Prepare password for bcrypt hashing.

    Performs:
    1. ASCII validation
    2. 72-byte truncation (bcrypt limit)

    Args:
        password: Plain text password

    Returns:
        Prepared password string

    Raises:
        ValueError: If password is None, empty, or contains non-ASCII
        TypeError: If password is not a string
    """
    if password is None:
        raise ValueError("Password cannot be None")

    if not isinstance(password, str):
        raise TypeError(f"Password must be a string, got {type(password).__name__}")

    if not password:
        raise ValueError("Password cannot be empty")

    if not password.isascii():
        raise ValueError("Password must contain only ASCII characters")

    # Truncate to 72 bytes (bcrypt limit)
    # Since password is ASCII-only, len(password) == byte length
    if len(password) > BCRYPT_MAX_PASSWORD_LENGTH:
        return password[:BCRYPT_MAX_PASSWORD_LENGTH]

    return password


def hash_password_sync(password: str, testing: bool = False) -> str:
    """
    Hash password synchronously using bcrypt.

    OWASP A02 Protection:
    - Validates password before hashing
    - Uses appropriate bcrypt rounds
    - Handles truncation safely

    Args:
        password: Plain text password
        testing: If True, use lower rounds for performance

    Returns:
        Bcrypt hash string

    Raises:
        ValueError: If password is invalid
        TypeError: If password is not a string
    """
    prepared = _prepare_password_for_bcrypt(password)
    ctx = get_password_context(testing=testing)
    return str(ctx.hash(prepared))


def verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash synchronously.

    OWASP A02 Protection:
    - Validates inputs before verification
    - Uses constant-time comparison (via passlib)
    - Handles truncation consistently

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise

    Raises:
        ValueError: If inputs are invalid
        TypeError: If inputs are not strings
    """
    prepared = _prepare_password_for_bcrypt(plain_password)

    if hashed_password is None:
        raise ValueError("Hashed password cannot be None")

    if not isinstance(hashed_password, str):
        raise TypeError(f"Hashed password must be a string, got {type(hashed_password).__name__}")

    if not hashed_password:
        raise ValueError("Hashed password cannot be empty")

    # Use testing=False for verification (rounds don't matter for verify)
    ctx = get_password_context(testing=False)

    try:
        return bool(ctx.verify(prepared, hashed_password))
    except Exception as e:
        logger.warning(f"Password verification failed: {e}")
        return False


# ============================================================================
# JWT TOKEN HANDLING
# ============================================================================


class JWTConfig(BaseModel):
    """JWT configuration with security validation"""

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=43200)  # Max 30 days
    issuer: str | None = None
    audience: str | None = None

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        """Ensure algorithm is in whitelist (prevents 'none' attack)"""
        if v not in ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"Algorithm '{v}' not allowed. Allowed: {sorted(ALLOWED_JWT_ALGORITHMS)}"
            )
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate secret key strength"""
        if not v:
            raise ValueError("Secret key cannot be empty")

        if len(v) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"Secret key must be at least {MIN_SECRET_KEY_LENGTH} characters")

        return v


def validate_jwt_algorithm(algorithm: str) -> bool:
    """
    Validate that JWT algorithm is in the allowed whitelist.

    OWASP A02 Protection:
    - Prevents "none" algorithm attack
    - Prevents algorithm confusion attacks
    - Only allows HMAC-SHA algorithms

    Args:
        algorithm: Algorithm string to validate

    Returns:
        True if algorithm is allowed

    Raises:
        ValueError: If algorithm is not allowed
    """
    if algorithm is None:
        raise ValueError("Algorithm cannot be None")

    if not isinstance(algorithm, str):
        raise TypeError(f"Algorithm must be a string, got {type(algorithm).__name__}")

    # Normalize and check
    algo_upper = algorithm.upper().strip()

    # Explicitly reject "none" algorithm
    if algo_upper in ("NONE", ""):
        raise ValueError("Algorithm 'none' is not allowed (security vulnerability)")

    if algo_upper not in ALLOWED_JWT_ALGORITHMS:
        raise ValueError(
            f"Algorithm '{algorithm}' not allowed. Allowed: {sorted(ALLOWED_JWT_ALGORITHMS)}"
        )

    return True


def validate_secret_key(
    secret_key: str, is_production: bool = False, raise_on_weak: bool = True
) -> tuple[bool, list[str]]:
    """
    Validate JWT secret key strength.

    OWASP A02 Protection:
    - Enforces minimum key length
    - Detects development/default keys in production
    - Warns about weak patterns

    Args:
        secret_key: Secret key to validate
        is_production: If True, apply stricter requirements
        raise_on_weak: If True, raise ValueError on weak keys

    Returns: tuple[bool, list[str]] of (is_valid, list of warnings/errors)

    Raises:
        ValueError: If key is weak and raise_on_weak=True
    """
    issues: list[str] = []

    if not secret_key:
        issues.append("Secret key cannot be empty")
        if raise_on_weak:
            raise ValueError("Secret key cannot be empty")
        return False, issues

    # Length check
    min_length = MIN_SECRET_KEY_LENGTH_PRODUCTION if is_production else MIN_SECRET_KEY_LENGTH
    if len(secret_key) < min_length:
        issue = f"Secret key must be at least {min_length} characters"
        issues.append(issue)
        if raise_on_weak:
            raise ValueError(issue)

    # Development key detection in production
    weak_patterns = [
        ("dev-", "Starts with 'dev-' (development key)"),
        ("test-", "Starts with 'test-' (test key)"),
        ("change-in-production", "Contains 'change-in-production'"),
        ("secret", "Contains 'secret' literally"),
        ("password", "Contains 'password' literally"),
    ]

    secret_lower = secret_key.lower()
    for pattern, description in weak_patterns:
        if pattern in secret_lower:
            if is_production:
                issue = f"Production secret key issue: {description}"
                issues.append(issue)
                if raise_on_weak:
                    raise ValueError(issue)
            else:
                issues.append(f"Warning: {description}")

    return len([i for i in issues if not i.startswith("Warning")]) == 0, issues


def create_jwt_token(
    payload: dict[str, object],
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
    default_expire_minutes: int = 30,
) -> str:
    """
    Create JWT token with security hardening.

    OWASP A02 Protection:
    - Validates algorithm against whitelist
    - Validates secret key strength
    - Ensures expiration is always set
    - Uses timezone-aware timestamps

    Args:
        payload: Data to encode in token
        secret_key: Secret key for signing
        algorithm: Signing algorithm (must be in whitelist)
        expires_delta: Optional custom expiration
        default_expire_minutes: Default expiration if not specified

    Returns:
        Encoded JWT token string

    Raises:
        ValueError: If algorithm or secret key is invalid
    """
    # Validate algorithm (prevents "none" attack)
    validate_jwt_algorithm(algorithm)

    # Validate secret key
    validate_secret_key(secret_key, is_production=False, raise_on_weak=False)

    # Prepare payload
    to_encode = payload.copy()

    # Always set expiration (security requirement)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=default_expire_minutes)

    to_encode["exp"] = expire

    # Add issued-at if not present
    if "iat" not in to_encode:
        to_encode["iat"] = datetime.now(timezone.utc)

    # Encode token
    return cast(str, jwt.encode(to_encode, secret_key, algorithm=algorithm))


def verify_jwt_token(
    token: str,
    secret_key: str,
    algorithms: list[str] | None = None,
    verify_exp: bool = True,
    require_exp: bool = True,
) -> dict[str, object] | None:  # TODO(TYPE): replace Any with concrete type
    """
    Verify and decode JWT token with security hardening.

    OWASP A02 Protection:
    - Validates algorithms against whitelist
    - Verifies expiration by default
    - Requires expiration claim by default
    - Handles errors securely (no information leakage)

    Args:
        token: JWT token string to verify
        secret_key: Secret key for verification
        algorithms: list[str] | None = None,  # TODO(TYPE): replace Any with concrete type
        verify_exp: Whether to verify expiration
        require_exp: Whether to require exp claim

    Returns:
        Decoded payload if valid, None if invalid

    Raises:
        ValueError: If algorithms are not in whitelist
    """
    # Default to safe algorithm list
    if algorithms is None:
        algorithms = ["HS256"]

    # Validate all algorithms are in whitelist
    for algo in algorithms:
        validate_jwt_algorithm(algo)

    try:
        options = {
            "verify_exp": verify_exp,
            "require_exp": require_exp,
        }

        payload = jwt.decode(token, secret_key, algorithms=algorithms, options=options)

        return cast(dict[str, object] | None, payload)  # TODO(TYPE): replace Any with concrete type

    except JWTError as e:
        # Log error without exposing details to caller
        logger.warning(f"JWT verification failed: {type(e).__name__}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying JWT: {type(e).__name__}")
        return None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.

    Args:
        length: Number of bytes (output will be longer due to encoding)

    Returns:
        URL-safe base64-encoded random token
    """
    return secrets.token_urlsafe(length)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Perform constant-time string comparison.

    OWASP A02 Protection:
    - Prevents timing attacks
    - Uses HMAC comparison for constant time

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False

    return hmac.compare_digest(a.encode(), b.encode())


def hash_token_for_storage(token: str) -> str:
    """
    Hash a token for secure storage (e.g., refresh tokens).

    Uses SHA-256 for fast, secure hashing of tokens.
    Not suitable for passwords (use bcrypt instead).

    Args:
        token: Token to hash

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================================================
# SECURITY AUDIT HELPERS
# ============================================================================


def audit_crypto_config() -> dict[str, object]:  # TODO(TYPE): replace Any with concrete type
    """
    Audit current cryptographic configuration.

    Returns dictionary with configuration status for security review.
    """
    testing_mode = os.getenv("TESTING") == "1"

    return {
        "allowed_jwt_algorithms": sorted(ALLOWED_JWT_ALGORITHMS),
        "min_secret_key_length": MIN_SECRET_KEY_LENGTH,
        "min_secret_key_length_production": MIN_SECRET_KEY_LENGTH_PRODUCTION,
        "bcrypt_rounds": BCRYPT_ROUNDS_TESTING if testing_mode else BCRYPT_ROUNDS_PRODUCTION,
        "bcrypt_max_password_length": BCRYPT_MAX_PASSWORD_LENGTH,
        "password_min_length": MIN_PASSWORD_LENGTH,
        "password_max_length": MAX_PASSWORD_LENGTH,
        "testing_mode": testing_mode,
    }
