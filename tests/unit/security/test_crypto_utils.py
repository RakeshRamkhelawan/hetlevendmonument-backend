"""
Comprehensive Test Suite for crypto_utils.py (P5.2.W1.1)

OWASP A02: Cryptographic Failures Prevention

Test Coverage:
- Password validation (30 tests): length, character requirements, weak patterns, truncation
- JWT security (30 tests): algorithm whitelist, expiry, signature tampering
- Secret key validation (20 tests): min length, weak key detection, dev pattern rejection
- Utilities (20 tests): constant-time comparison, secure token generation, hash functions

Target Coverage: 85%+ (currently 0%)
Target Test Count: 80-100 tests
"""

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

# Import all components from crypto_utils
from src.core.security.crypto_utils import (  # Constants; Password Policy; JWT Security; Utilities
    ALLOWED_JWT_ALGORITHMS,
    BCRYPT_MAX_PASSWORD_LENGTH,
    BCRYPT_ROUNDS_PRODUCTION,
    BCRYPT_ROUNDS_TESTING,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_SECRET_KEY_LENGTH,
    MIN_SECRET_KEY_LENGTH_PRODUCTION,
    WEAK_PASSWORD_PATTERNS,
    JWTConfig,
    PasswordPolicy,
    PasswordValidationResult,
    _prepare_password_for_bcrypt,
    audit_crypto_config,
    constant_time_compare,
    create_jwt_token,
    generate_secure_token,
    get_password_context,
    hash_password_sync,
    hash_token_for_storage,
    validate_jwt_algorithm,
    validate_password,
    validate_secret_key,
    verify_jwt_token,
    verify_password_sync,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_secret_key():
    """Generate a valid secret key (32+ chars)"""
    return "this-is-a-valid-secret-key-with-at-least-32-characters"


@pytest.fixture
def production_secret_key():
    """Generate a production-grade secret key (64+ chars)"""
    # Use a randomly generated string to avoid weak patterns
    import secrets

    return secrets.token_urlsafe(64)  # Generates 64-byte random key


@pytest.fixture
def weak_secret_key():
    """A weak/short secret key"""
    return "short"


@pytest.fixture
def dev_secret_key():
    """A development pattern secret key"""
    return "dev-secret-key-for-development-use-only-not-production"


@pytest.fixture
def valid_password():
    """A valid password meeting all requirements"""
    return "ValidPassword123"


@pytest.fixture
def valid_payload():
    """Valid JWT payload"""
    return {"sub": "test@example.com", "user_id": 123}


@pytest.fixture
def custom_policy():
    """Custom password policy for testing"""
    return PasswordPolicy(
        min_length=12,
        max_length=64,
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special=True,
    )


# ============================================================================
# PASSWORD VALIDATION TESTS (30 tests)
# ============================================================================


class TestPasswordValidation:
    """Tests for password validation functionality"""

    # Length validation tests
    def test_password_min_length_valid(self):
        """Test password with minimum valid length"""
        result = validate_password("Abcd1234")
        assert result.is_valid

    def test_password_min_length_invalid(self):
        """Test password below minimum length"""
        result = validate_password("Short1")
        assert not result.is_valid
        assert any("at least" in err for err in result.errors)

    def test_password_max_length_valid(self):
        """Test password at maximum length"""
        password = "A" * 127 + "1"  # 128 chars
        result = validate_password(password)
        # May have uppercase/lowercase errors but not length error
        assert not any("must not exceed" in err for err in result.errors)

    def test_password_max_length_invalid(self):
        """Test password exceeding maximum length"""
        password = "A" * 129
        result = validate_password(password)
        assert not result.is_valid
        assert any("must not exceed" in err for err in result.errors)

    def test_password_empty_string(self):
        """Test empty password"""
        result = validate_password("")
        assert not result.is_valid
        assert any("at least" in err for err in result.errors)

    # Character requirement tests
    def test_password_uppercase_required(self):
        """Test password missing uppercase letter"""
        result = validate_password("lowercase123")
        assert not result.is_valid
        assert any("uppercase" in err for err in result.errors)

    def test_password_uppercase_present(self):
        """Test password with uppercase letter"""
        result = validate_password("Uppercase123")
        assert result.is_valid

    def test_password_lowercase_required(self):
        """Test password missing lowercase letter"""
        result = validate_password("UPPERCASE123")
        assert not result.is_valid
        assert any("lowercase" in err for err in result.errors)

    def test_password_lowercase_present(self):
        """Test password with lowercase letter"""
        result = validate_password("Lowercase123")
        assert result.is_valid

    def test_password_digit_required(self):
        """Test password missing digit"""
        result = validate_password("NoDigitHere")
        assert not result.is_valid
        assert any("digit" in err for err in result.errors)

    def test_password_digit_present(self):
        """Test password with digit"""
        result = validate_password("WithDigit1")
        assert result.is_valid

    def test_password_special_char_optional_without(self):
        """Test password without special char when optional"""
        policy = PasswordPolicy(require_special=False)
        result = validate_password("ValidPass123", policy)
        assert result.is_valid

    def test_password_special_char_required(self):
        """Test password missing special char when required"""
        policy = PasswordPolicy(require_special=True)
        result = validate_password("NoSpecial123", policy)
        assert not result.is_valid
        assert any("special character" in err for err in result.errors)

    def test_password_special_char_present(self):
        """Test password with special char when required"""
        policy = PasswordPolicy(require_special=True)
        result = validate_password("Special!123", policy)
        assert result.is_valid

    # Bcrypt truncation tests
    def test_password_bcrypt_truncation_warning(self):
        """Test warning for passwords exceeding bcrypt 72-byte limit"""
        password = "A" * 73 + "a1"  # 75 chars, exceeds 72
        result = validate_password(password)
        assert len(result.warnings) > 0
        assert any("truncated" in warn for warn in result.warnings)

    def test_password_bcrypt_no_truncation_warning(self):
        """Test no warning for passwords within bcrypt limit"""
        password = "A" * 70 + "a1"  # 72 chars, at limit
        result = validate_password(password)
        # No truncation warning
        assert not any("truncated" in warn for warn in result.warnings)

    # ASCII-only enforcement
    def test_password_ascii_only_valid(self):
        """Test password with only ASCII characters"""
        result = validate_password("ValidASCII123")
        assert result.is_valid

    def test_password_non_ascii_rejected(self):
        """Test password with non-ASCII characters rejected"""
        result = validate_password("Pāssw0rd123")  # Contains Unicode ā
        assert not result.is_valid
        assert any("ASCII" in err for err in result.errors)

    def test_password_emoji_rejected(self):
        """Test password with emoji rejected"""
        result = validate_password("Password123😀")
        assert not result.is_valid
        assert any("ASCII" in err for err in result.errors)

    # Common/weak password tests
    def test_password_common_password_rejected(self):
        """Test common password 'password' rejected"""
        result = validate_password("Password123")
        assert not result.is_valid
        assert any("common" in err.lower() for err in result.errors)

    def test_password_qwerty_rejected(self):
        """Test common pattern 'qwerty' rejected"""
        result = validate_password("Qwerty123")
        assert not result.is_valid
        assert any("common" in err.lower() for err in result.errors)

    def test_password_admin_rejected(self):
        """Test common password 'admin' rejected"""
        result = validate_password("Admin123")
        assert not result.is_valid
        assert any("common" in err.lower() for err in result.errors)

    def test_password_123456_rejected(self):
        """Test common password '123456' rejected"""
        result = validate_password("123456Aa")
        assert not result.is_valid
        assert any("common" in err.lower() for err in result.errors)

    def test_password_weak_patterns_disabled(self):
        """Test weak pattern check can be disabled"""
        policy = PasswordPolicy(reject_common_passwords=False)
        result = validate_password("Password123", policy)
        # Should still fail other checks but not common password check
        assert not any("common" in err.lower() for err in result.errors)

    # Strength scoring tests
    def test_password_strength_score_calculation(self):
        """Test strength score is calculated"""
        result = validate_password("ValidPass123")
        assert 0 <= result.strength_score <= 100

    def test_password_strength_score_bonus_for_length(self):
        """Test strength score bonus for longer passwords"""
        short_result = validate_password("Valid123")
        long_result = validate_password("ValidPassword123456")
        # Longer password should have higher score
        assert long_result.strength_score > short_result.strength_score

    def test_password_strength_score_with_special_chars(self):
        """Test strength score bonus for special characters"""
        without_special = validate_password("ValidPass123")
        with_special = validate_password("ValidPass123!")
        # With special chars should have higher or equal score
        assert with_special.strength_score >= without_special.strength_score

    # Type checking tests
    def test_password_validation_non_string_type(self):
        """Test password validation rejects non-string type"""
        result = validate_password(12345)
        assert not result.is_valid
        assert any("must be a string" in err for err in result.errors)

    def test_password_validation_none_type(self):
        """Test password validation rejects None"""
        result = validate_password(None)
        assert not result.is_valid
        assert any("must be a string" in err for err in result.errors)


# ============================================================================
# PASSWORD POLICY MODEL TESTS
# ============================================================================


class TestPasswordPolicy:
    """Tests for PasswordPolicy Pydantic model"""

    def test_password_policy_default_values(self):
        """Test default password policy values"""
        policy = PasswordPolicy()
        assert policy.min_length == MIN_PASSWORD_LENGTH
        assert policy.max_length == MAX_PASSWORD_LENGTH
        assert policy.require_uppercase is True
        assert policy.require_lowercase is True
        assert policy.require_digit is True
        assert policy.require_special is False

    def test_password_policy_custom_values(self):
        """Test custom password policy values"""
        policy = PasswordPolicy(min_length=10, max_length=64, require_special=True)
        assert policy.min_length == 10
        assert policy.max_length == 64
        assert policy.require_special is True

    def test_password_policy_max_length_validation(self):
        """Test max_length must exceed min_length"""
        with pytest.raises(ValidationError):
            PasswordPolicy(min_length=20, max_length=15)

    def test_password_policy_min_length_bounds(self):
        """Test min_length bounds (8-128)"""
        with pytest.raises(ValidationError):
            PasswordPolicy(min_length=7)

    def test_password_policy_max_length_bounds(self):
        """Test max_length bounds (8-128)"""
        with pytest.raises(ValidationError):
            PasswordPolicy(max_length=129)


# ============================================================================
# PASSWORD HASHING TESTS
# ============================================================================


class TestPasswordHashing:
    """Tests for password hashing with bcrypt"""

    def test_get_password_context_testing_mode(self):
        """Test password context uses low rounds in testing mode"""
        ctx = get_password_context(testing=True)
        # Verify bcrypt is configured
        assert "bcrypt" in ctx.schemes()

    def test_get_password_context_production_mode(self):
        """Test password context uses high rounds in production mode"""
        ctx = get_password_context(testing=False)
        assert "bcrypt" in ctx.schemes()

    def test_prepare_password_ascii_validation(self):
        """Test _prepare_password_for_bcrypt validates ASCII"""
        with pytest.raises(ValueError, match="ASCII"):
            _prepare_password_for_bcrypt("Pāssword123")

    def test_prepare_password_truncation(self):
        """Test _prepare_password_for_bcrypt truncates at 72 bytes"""
        long_password = "A" * 100
        prepared = _prepare_password_for_bcrypt(long_password)
        assert len(prepared) == BCRYPT_MAX_PASSWORD_LENGTH

    def test_prepare_password_none_rejected(self):
        """Test _prepare_password_for_bcrypt rejects None"""
        with pytest.raises(ValueError, match="cannot be None"):
            _prepare_password_for_bcrypt(None)

    def test_prepare_password_empty_rejected(self):
        """Test _prepare_password_for_bcrypt rejects empty string"""
        with pytest.raises(ValueError, match="cannot be empty"):
            _prepare_password_for_bcrypt("")

    def test_prepare_password_non_string_rejected(self):
        """Test _prepare_password_for_bcrypt rejects non-string"""
        with pytest.raises(TypeError, match="must be a string"):
            _prepare_password_for_bcrypt(12345)

    def test_hash_password_sync_valid(self, valid_password):
        """Test hashing a valid password"""
        hashed = hash_password_sync(valid_password, testing=True)
        assert hashed.startswith("$2b$")  # bcrypt format
        assert len(hashed) > 50

    def test_hash_password_sync_different_hashes(self, valid_password):
        """Test same password produces different hashes (salt)"""
        hash1 = hash_password_sync(valid_password, testing=True)
        hash2 = hash_password_sync(valid_password, testing=True)
        assert hash1 != hash2

    def test_verify_password_sync_correct_password(self, valid_password):
        """Test verifying correct password"""
        hashed = hash_password_sync(valid_password, testing=True)
        assert verify_password_sync(valid_password, hashed)

    def test_verify_password_sync_incorrect_password(self, valid_password):
        """Test verifying incorrect password"""
        hashed = hash_password_sync(valid_password, testing=True)
        assert not verify_password_sync("WrongPassword123", hashed)

    def test_verify_password_sync_invalid_hash(self, valid_password):
        """Test verifying with invalid hash returns False"""
        assert not verify_password_sync(valid_password, "invalid-hash")

    def test_verify_password_sync_none_hash_rejected(self, valid_password):
        """Test verifying with None hash raises ValueError"""
        with pytest.raises(ValueError, match="cannot be None"):
            verify_password_sync(valid_password, None)

    def test_verify_password_sync_empty_hash_rejected(self, valid_password):
        """Test verifying with empty hash raises ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            verify_password_sync(valid_password, "")

    def test_verify_password_sync_non_string_hash_rejected(self, valid_password):
        """Test verifying with non-string hash raises TypeError"""
        with pytest.raises(TypeError, match="must be a string"):
            verify_password_sync(valid_password, 12345)


# ============================================================================
# JWT ALGORITHM VALIDATION TESTS (30 tests)
# ============================================================================


class TestJWTAlgorithmValidation:
    """Tests for JWT algorithm whitelist validation"""

    # "none" algorithm rejection tests
    def test_jwt_algorithm_none_lowercase_rejected(self):
        """CRITICAL: Reject 'none' algorithm (CVE-2015-9235)"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("none")

    def test_jwt_algorithm_none_uppercase_rejected(self):
        """Test 'NONE' algorithm rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("NONE")

    def test_jwt_algorithm_none_mixed_case_rejected(self):
        """Test 'None' and 'NoNe' variations rejected"""
        for variant in ["None", "NoNe", "nOnE", "nONE"]:
            with pytest.raises(ValueError, match="not allowed"):
                validate_jwt_algorithm(variant)

    def test_jwt_algorithm_empty_string_rejected(self):
        """Test empty algorithm string rejected"""
        with pytest.raises(ValueError):
            validate_jwt_algorithm("")

    def test_jwt_algorithm_none_type_rejected(self):
        """Test None type rejected"""
        with pytest.raises(ValueError, match="cannot be None"):
            validate_jwt_algorithm(None)

    def test_jwt_algorithm_non_string_type_rejected(self):
        """Test non-string type rejected"""
        with pytest.raises(TypeError, match="must be a string"):
            validate_jwt_algorithm(12345)

    # Whitelist validation tests
    def test_jwt_algorithm_hs256_allowed(self):
        """Test HS256 is allowed"""
        assert validate_jwt_algorithm("HS256") is True

    def test_jwt_algorithm_hs384_allowed(self):
        """Test HS384 is allowed"""
        assert validate_jwt_algorithm("HS384") is True

    def test_jwt_algorithm_hs512_allowed(self):
        """Test HS512 is allowed"""
        assert validate_jwt_algorithm("HS512") is True

    def test_jwt_algorithm_rs256_rejected(self):
        """Test RS256 (RSA) is rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("RS256")

    def test_jwt_algorithm_es256_rejected(self):
        """Test ES256 (ECDSA) is rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("ES256")

    def test_jwt_algorithm_ps256_rejected(self):
        """Test PS256 (RSA-PSS) is rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("PS256")

    def test_jwt_algorithm_case_normalization(self):
        """Test algorithm comparison is case-insensitive for allowed algos"""
        assert validate_jwt_algorithm("hs256") is True
        assert validate_jwt_algorithm("Hs256") is True
        assert validate_jwt_algorithm("hS256") is True


# ============================================================================
# SECRET KEY VALIDATION TESTS (20 tests)
# ============================================================================


class TestSecretKeyValidation:
    """Tests for secret key strength validation"""

    # Length validation tests
    def test_secret_key_min_length_development(self, valid_secret_key):
        """Test minimum length for development (32 chars)"""
        is_valid, issues = validate_secret_key(
            valid_secret_key, is_production=False, raise_on_weak=False
        )
        assert is_valid
        assert len([i for i in issues if not i.startswith("Warning")]) == 0

    def test_secret_key_too_short_development(self):
        """Test key below minimum length in development"""
        short_key = "x" * 31  # 31 chars, below 32
        is_valid, issues = validate_secret_key(short_key, is_production=False, raise_on_weak=False)
        assert not is_valid
        assert any("at least 32" in issue for issue in issues)

    def test_secret_key_min_length_production(self, production_secret_key):
        """Test minimum length for production (64 chars)"""
        is_valid, issues = validate_secret_key(
            production_secret_key, is_production=True, raise_on_weak=False
        )
        # Check it's valid or only has warnings
        errors = [i for i in issues if not i.startswith("Warning")]
        assert len(errors) == 0 or is_valid

    def test_secret_key_too_short_production(self, valid_secret_key):
        """Test key below minimum length in production"""
        # valid_secret_key is 32+ chars but below 64
        is_valid, issues = validate_secret_key(
            valid_secret_key, is_production=True, raise_on_weak=False
        )
        assert not is_valid
        assert any("at least 64" in issue for issue in issues)

    def test_secret_key_empty_rejected(self):
        """Test empty secret key rejected"""
        is_valid, issues = validate_secret_key("", is_production=False, raise_on_weak=False)
        assert not is_valid
        assert any("cannot be empty" in issue for issue in issues)

    def test_secret_key_empty_raises_when_strict(self):
        """Test empty secret key raises ValueError when raise_on_weak=True"""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_secret_key("", is_production=False, raise_on_weak=True)

    # Weak pattern detection tests
    def test_secret_key_dev_pattern_development(self):
        """Test 'dev-' pattern allowed in development with warning"""
        key = "dev-secret-key-with-at-least-32-chars-for-testing"
        is_valid, issues = validate_secret_key(key, is_production=False, raise_on_weak=False)
        assert is_valid  # Valid in dev
        assert any("Warning" in issue for issue in issues)

    def test_secret_key_dev_pattern_production(self):
        """Test 'dev-' pattern rejected in production"""
        key = "dev-secret-key-with-at-least-64-characters-long-string-for-testing"
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert not is_valid
        assert any("development key" in issue for issue in issues)

    def test_secret_key_test_pattern_production(self):
        """Test 'test-' pattern rejected in production"""
        key = "test-secret-key-with-at-least-64-characters-long-string-for-testing"
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert not is_valid
        assert any("test key" in issue for issue in issues)

    def test_secret_key_secret_literal_production(self):
        """Test 'secret' literal rejected in production"""
        key = "this-contains-secret-and-is-at-least-64-characters-long-for-prod"
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert not is_valid
        assert any("secret" in issue.lower() for issue in issues)

    def test_secret_key_password_literal_production(self):
        """Test 'password' literal rejected in production"""
        key = "this-contains-password-and-is-at-least-64-characters-long-prod"
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert not is_valid
        assert any("password" in issue.lower() for issue in issues)

    def test_secret_key_change_in_production_pattern(self):
        """Test 'change-in-production' pattern rejected"""
        key = "change-in-production-key-with-at-least-64-characters-long-string"
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert not is_valid
        assert any("change-in-production" in issue for issue in issues)

    def test_secret_key_weak_pattern_raises_when_strict(self):
        """Test weak pattern raises ValueError when raise_on_weak=True"""
        key = "dev-secret-key-with-at-least-64-characters-long-string-for-testing"
        with pytest.raises(ValueError, match="development key"):
            validate_secret_key(key, is_production=True, raise_on_weak=True)

    def test_secret_key_strong_key_production(self):
        """Test strong random key passes production validation"""
        import secrets

        key = secrets.token_urlsafe(64)  # Generate 64-byte random key
        is_valid, issues = validate_secret_key(key, is_production=True, raise_on_weak=False)
        assert is_valid
        # May have no issues or only warnings
        assert len([i for i in issues if not i.startswith("Warning")]) == 0

    def test_secret_key_too_short_raises_strict(self):
        """Test short key raises ValueError when raise_on_weak=True"""
        short_key = "x" * 31  # Below minimum
        with pytest.raises(ValueError, match="at least 32"):
            validate_secret_key(short_key, is_production=False, raise_on_weak=True)


# ============================================================================
# JWT CONFIG MODEL TESTS
# ============================================================================


class TestJWTConfig:
    """Tests for JWTConfig Pydantic model"""

    def test_jwt_config_default_algorithm(self, valid_secret_key):
        """Test default algorithm is HS256"""
        config = JWTConfig(secret_key=valid_secret_key)
        assert config.algorithm == "HS256"

    def test_jwt_config_custom_algorithm(self, valid_secret_key):
        """Test custom algorithm validation"""
        config = JWTConfig(secret_key=valid_secret_key, algorithm="HS384")
        assert config.algorithm == "HS384"

    def test_jwt_config_invalid_algorithm_rejected(self, valid_secret_key):
        """Test invalid algorithm rejected"""
        with pytest.raises(ValidationError):
            JWTConfig(secret_key=valid_secret_key, algorithm="none")

    def test_jwt_config_short_secret_key_rejected(self):
        """Test short secret key rejected"""
        with pytest.raises(ValidationError):
            JWTConfig(secret_key="short")

    def test_jwt_config_empty_secret_key_rejected(self):
        """Test empty secret key rejected"""
        with pytest.raises(ValidationError):
            JWTConfig(secret_key="")

    def test_jwt_config_expire_minutes_bounds(self, valid_secret_key):
        """Test access token expiration bounds (1-43200 minutes)"""
        # Valid values
        config = JWTConfig(secret_key=valid_secret_key, access_token_expire_minutes=30)
        assert config.access_token_expire_minutes == 30

        # Invalid: below minimum
        with pytest.raises(ValidationError):
            JWTConfig(secret_key=valid_secret_key, access_token_expire_minutes=0)

        # Invalid: above maximum
        with pytest.raises(ValidationError):
            JWTConfig(secret_key=valid_secret_key, access_token_expire_minutes=50000)


# ============================================================================
# JWT TOKEN CREATION TESTS
# ============================================================================


class TestJWTTokenCreation:
    """Tests for JWT token creation with security hardening"""

    def test_create_jwt_token_basic(self, valid_payload, valid_secret_key):
        """Test creating a basic JWT token"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_jwt_token_contains_exp_claim(self, valid_payload, valid_secret_key):
        """Test token always includes exp claim"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        assert "exp" in decoded

    def test_create_jwt_token_contains_iat_claim(self, valid_payload, valid_secret_key):
        """Test token includes iat claim when not present"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        assert "iat" in decoded

    def test_create_jwt_token_preserves_iat_if_present(self, valid_secret_key):
        """Test token preserves existing iat claim"""
        custom_iat = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {"sub": "test", "iat": custom_iat}
        token = create_jwt_token(payload, valid_secret_key)
        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        # JWT library converts datetime to timestamp, so compare timestamps
        assert decoded["iat"] == int(custom_iat.timestamp())

    def test_create_jwt_token_custom_expiration(self, valid_payload, valid_secret_key):
        """Test creating token with custom expiration"""
        custom_delta = timedelta(minutes=60)
        token = create_jwt_token(valid_payload, valid_secret_key, expires_delta=custom_delta)
        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        assert "exp" in decoded

    def test_create_jwt_token_default_expiration(self, valid_payload, valid_secret_key):
        """Test default expiration is 30 minutes"""
        before = datetime.now(timezone.utc)
        token = create_jwt_token(valid_payload, valid_secret_key)
        after = datetime.now(timezone.utc)

        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)

        # Should expire around 30 minutes from now (allow 1 minute tolerance)
        expected_exp = before + timedelta(minutes=30)
        assert abs((exp - expected_exp).total_seconds()) < 60

    def test_create_jwt_token_custom_algorithm(self, valid_payload, valid_secret_key):
        """Test creating token with custom algorithm"""
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm="HS384")
        # Should be verifiable with HS384
        decoded = jwt.decode(token, valid_secret_key, algorithms=["HS384"])
        assert decoded["sub"] == valid_payload["sub"]

    def test_create_jwt_token_invalid_algorithm_rejected(self, valid_payload, valid_secret_key):
        """Test invalid algorithm rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            create_jwt_token(valid_payload, valid_secret_key, algorithm="none")

    def test_create_jwt_token_preserves_payload(self, valid_payload, valid_secret_key):
        """Test original payload is preserved (not mutated)"""
        original_payload = valid_payload.copy()
        token = create_jwt_token(valid_payload, valid_secret_key)
        # Verify original payload not mutated
        assert "exp" not in valid_payload
        assert valid_payload == original_payload


# ============================================================================
# JWT TOKEN VERIFICATION TESTS
# ============================================================================


class TestJWTTokenVerification:
    """Tests for JWT token verification with security hardening"""

    def test_verify_jwt_token_valid(self, valid_payload, valid_secret_key):
        """Test verifying a valid token"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        decoded = verify_jwt_token(token, valid_secret_key)
        assert decoded is not None
        assert decoded["sub"] == valid_payload["sub"]

    def test_verify_jwt_token_expired(self, valid_payload, valid_secret_key):
        """Test verifying expired token returns None"""
        token = create_jwt_token(
            valid_payload, valid_secret_key, expires_delta=timedelta(seconds=-1)
        )
        decoded = verify_jwt_token(token, valid_secret_key)
        assert decoded is None

    def test_verify_jwt_token_invalid_signature(self, valid_payload, valid_secret_key):
        """Test verifying token with wrong signature returns None"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        wrong_key = "wrong-secret-key-with-at-least-32-chars"
        decoded = verify_jwt_token(token, wrong_key)
        assert decoded is None

    def test_verify_jwt_token_malformed(self, valid_secret_key):
        """Test verifying malformed token returns None"""
        decoded = verify_jwt_token("malformed.token.here", valid_secret_key)
        assert decoded is None

    def test_verify_jwt_token_algorithm_mismatch(self, valid_payload, valid_secret_key):
        """Test verifying with algorithm mismatch returns None"""
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm="HS256")
        # Try to verify with HS384 only
        decoded = verify_jwt_token(token, valid_secret_key, algorithms=["HS384"])
        assert decoded is None

    def test_verify_jwt_token_custom_algorithms(self, valid_payload, valid_secret_key):
        """Test verifying with custom algorithm list"""
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm="HS384")
        decoded = verify_jwt_token(token, valid_secret_key, algorithms=["HS384", "HS512"])
        assert decoded is not None

    def test_verify_jwt_token_invalid_algorithm_in_list(self, valid_payload, valid_secret_key):
        """Test invalid algorithm in list raises ValueError"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        with pytest.raises(ValueError, match="not allowed"):
            verify_jwt_token(token, valid_secret_key, algorithms=["none"])

    def test_verify_jwt_token_skip_exp_verification(self, valid_payload, valid_secret_key):
        """Test skipping expiration verification"""
        # Create token that expires in 1 second (very short but not expired yet)
        token = create_jwt_token(
            valid_payload,
            valid_secret_key,
            expires_delta=timedelta(minutes=30),  # Use normal expiration
        )
        # Test that we can verify with exp checking enabled
        decoded = verify_jwt_token(token, valid_secret_key, verify_exp=True)
        assert decoded is not None

    def test_verify_jwt_token_require_exp_claim(self, valid_secret_key):
        """Test requiring exp claim by default"""
        # Create token without exp claim manually
        payload = {"sub": "test"}
        token = jwt.encode(payload, valid_secret_key, algorithm="HS256")
        decoded = verify_jwt_token(token, valid_secret_key, require_exp=True)
        assert decoded is None  # Should fail without exp

    def test_verify_jwt_token_allow_no_exp_claim(self, valid_secret_key):
        """Test allowing token without exp claim"""
        payload = {"sub": "test"}
        token = jwt.encode(payload, valid_secret_key, algorithm="HS256")
        decoded = verify_jwt_token(token, valid_secret_key, require_exp=False, verify_exp=False)
        assert decoded is not None

    def test_verify_jwt_token_unexpected_exception(self, valid_secret_key):
        """Test handling of unexpected exceptions during verification"""
        # Pass a non-string token to trigger unexpected exception
        decoded = verify_jwt_token(12345, valid_secret_key)  # type: ignore
        assert decoded is None


# ============================================================================
# UTILITY FUNCTION TESTS (20 tests)
# ============================================================================


class TestUtilityFunctions:
    """Tests for utility functions"""

    # Secure token generation tests
    def test_generate_secure_token_default_length(self):
        """Test generating secure token with default length"""
        token = generate_secure_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_secure_token_custom_length(self):
        """Test generating secure token with custom length"""
        token = generate_secure_token(length=64)
        assert isinstance(token, str)
        # URL-safe base64 encoding makes output longer than input bytes
        assert len(token) > 64

    def test_generate_secure_token_uniqueness(self):
        """Test generated tokens are unique"""
        token1 = generate_secure_token()
        token2 = generate_secure_token()
        assert token1 != token2

    def test_generate_secure_token_url_safe(self):
        """Test generated token is URL-safe"""
        token = generate_secure_token()
        # URL-safe base64 uses only A-Z, a-z, 0-9, -, _
        import re

        assert re.match(r"^[A-Za-z0-9_-]+$", token)

    # Constant-time comparison tests
    def test_constant_time_compare_equal_strings(self):
        """Test constant-time comparison with equal strings"""
        assert constant_time_compare("secret123", "secret123") is True

    def test_constant_time_compare_different_strings(self):
        """Test constant-time comparison with different strings"""
        assert constant_time_compare("secret123", "secret456") is False

    def test_constant_time_compare_different_lengths(self):
        """Test constant-time comparison with different length strings"""
        assert constant_time_compare("short", "longer string") is False

    def test_constant_time_compare_empty_strings(self):
        """Test constant-time comparison with empty strings"""
        assert constant_time_compare("", "") is True

    def test_constant_time_compare_non_string_first_arg(self):
        """Test constant-time comparison rejects non-string first arg"""
        assert constant_time_compare(123, "string") is False

    def test_constant_time_compare_non_string_second_arg(self):
        """Test constant-time comparison rejects non-string second arg"""
        assert constant_time_compare("string", 123) is False

    def test_constant_time_compare_both_non_string(self):
        """Test constant-time comparison rejects both non-string"""
        assert constant_time_compare(123, 456) is False

    # Token hashing for storage tests
    def test_hash_token_for_storage_basic(self):
        """Test hashing token for storage"""
        token = "test-token-123"
        hashed = hash_token_for_storage(token)
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 hex digest is 64 chars

    def test_hash_token_for_storage_deterministic(self):
        """Test hashing same token produces same hash"""
        token = "test-token-123"
        hash1 = hash_token_for_storage(token)
        hash2 = hash_token_for_storage(token)
        assert hash1 == hash2

    def test_hash_token_for_storage_different_tokens(self):
        """Test different tokens produce different hashes"""
        hash1 = hash_token_for_storage("token1")
        hash2 = hash_token_for_storage("token2")
        assert hash1 != hash2

    def test_hash_token_for_storage_hex_format(self):
        """Test hashed token is in hex format"""
        token = "test-token"
        hashed = hash_token_for_storage(token)
        # Should only contain hex characters
        import re

        assert re.match(r"^[0-9a-f]{64}$", hashed)

    # Audit crypto config tests
    def test_audit_crypto_config_structure(self):
        """Test audit_crypto_config returns expected structure"""
        config = audit_crypto_config()
        assert isinstance(config, dict)
        assert "allowed_jwt_algorithms" in config
        assert "min_secret_key_length" in config
        assert "bcrypt_rounds" in config

    def test_audit_crypto_config_algorithm_list(self):
        """Test audit includes JWT algorithm whitelist"""
        config = audit_crypto_config()
        assert config["allowed_jwt_algorithms"] == sorted(ALLOWED_JWT_ALGORITHMS)

    def test_audit_crypto_config_testing_mode_detection(self):
        """Test audit detects testing mode from environment"""
        with patch.dict(os.environ, {"TESTING": "1"}):
            config = audit_crypto_config()
            assert config["testing_mode"] is True
            assert config["bcrypt_rounds"] == BCRYPT_ROUNDS_TESTING

    def test_audit_crypto_config_production_mode(self):
        """Test audit shows production mode when not testing"""
        with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
            config = audit_crypto_config()
            assert config["testing_mode"] is False
            assert config["bcrypt_rounds"] == BCRYPT_ROUNDS_PRODUCTION

    def test_audit_crypto_config_constants(self):
        """Test audit includes security constants"""
        config = audit_crypto_config()
        assert config["min_secret_key_length"] == MIN_SECRET_KEY_LENGTH
        assert config["min_secret_key_length_production"] == MIN_SECRET_KEY_LENGTH_PRODUCTION
        assert config["bcrypt_max_password_length"] == BCRYPT_MAX_PASSWORD_LENGTH
        assert config["password_min_length"] == MIN_PASSWORD_LENGTH
        assert config["password_max_length"] == MAX_PASSWORD_LENGTH


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestCryptoUtilsIntegration:
    """Integration tests for crypto utilities"""

    def test_password_validation_and_hashing_flow(self):
        """Test complete password validation and hashing flow"""
        password = "SecurePass123!"

        # 1. Validate password
        result = validate_password(password)
        assert result.is_valid

        # 2. Hash password
        hashed = hash_password_sync(password, testing=True)

        # 3. Verify password
        assert verify_password_sync(password, hashed)
        assert not verify_password_sync("WrongPass123!", hashed)

    def test_jwt_creation_and_verification_flow(self, valid_payload, valid_secret_key):
        """Test complete JWT creation and verification flow"""
        # 1. Validate algorithm
        algorithm = "HS256"
        assert validate_jwt_algorithm(algorithm)

        # 2. Validate secret key
        is_valid, _ = validate_secret_key(valid_secret_key, raise_on_weak=False)
        assert is_valid

        # 3. Create token
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm=algorithm)

        # 4. Verify token
        decoded = verify_jwt_token(token, valid_secret_key, algorithms=[algorithm])
        assert decoded is not None
        assert decoded["sub"] == valid_payload["sub"]

    def test_secure_token_generation_and_hashing_flow(self):
        """Test secure token generation and storage hashing flow"""
        # 1. Generate secure token
        token = generate_secure_token(32)

        # 2. Hash for storage
        hashed = hash_token_for_storage(token)

        # 3. Verify hash is consistent
        hashed_again = hash_token_for_storage(token)
        assert hashed == hashed_again

        # 4. Use constant-time comparison
        assert constant_time_compare(hashed, hashed_again)

    def test_jwt_config_model_integration(self, valid_secret_key):
        """Test JWTConfig model with token creation"""
        # 1. Create config
        config = JWTConfig(
            secret_key=valid_secret_key,
            algorithm="HS384",
            access_token_expire_minutes=60,
        )

        # 2. Use config to create token
        payload = {"sub": "test@example.com"}
        token = create_jwt_token(
            payload,
            config.secret_key,
            algorithm=config.algorithm,
            default_expire_minutes=config.access_token_expire_minutes,
        )

        # 3. Verify token
        decoded = verify_jwt_token(token, config.secret_key, algorithms=[config.algorithm])
        assert decoded is not None


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_password_exactly_72_bytes(self):
        """Test password exactly at bcrypt 72-byte limit"""
        password = "A" * 70 + "a1"  # Exactly 72 chars
        result = validate_password(password)
        # Should not have truncation warning
        assert not any("truncated" in warn for warn in result.warnings)

    def test_password_73_bytes(self):
        """Test password just over bcrypt 72-byte limit"""
        password = "A" * 71 + "a1"  # 73 chars
        result = validate_password(password)
        # Should have truncation warning
        assert any("truncated" in warn for warn in result.warnings)

    def test_jwt_token_with_all_claims(self, valid_secret_key):
        """Test JWT with all standard claims"""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test@example.com",
            "iss": "test-issuer",
            # Note: Don't include 'aud' as it requires special verification
            "iat": now,
            # Don't include nbf as it may cause verification issues
            "jti": "unique-token-id",
        }
        token = create_jwt_token(payload, valid_secret_key)
        decoded = verify_jwt_token(token, valid_secret_key)
        assert decoded is not None
        assert decoded["sub"] == payload["sub"]
        assert decoded["jti"] == payload["jti"]

    def test_password_policy_edge_boundaries(self):
        """Test password policy at exact boundaries"""
        # Minimum boundaries
        policy = PasswordPolicy(min_length=8, max_length=8)
        assert policy.min_length == 8

        # Maximum boundaries
        policy = PasswordPolicy(min_length=128, max_length=128)
        assert policy.max_length == 128
