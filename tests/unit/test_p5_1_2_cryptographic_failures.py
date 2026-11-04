"""
Security Tests for OWASP A02: Cryptographic Failures

Tests for:
- JWT validation vulnerabilities (algorithm confusion, none attack)
- Password hashing security (bcrypt configuration, ASCII validation)
- Secret key strength validation
- Token expiration enforcement

Reference: https://owasp.org/Top10/A02_2021-Cryptographic_Failures/
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

# Import crypto utilities being tested
from src.core.security.crypto_utils import (  # Password validation; JWT security; Constants
    MIN_SECRET_KEY_LENGTH,
    JWTConfig,
    PasswordPolicy,
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
    """Generate a valid secret key for testing"""
    return "this-is-a-valid-secret-key-with-at-least-32-chars"


@pytest.fixture
def weak_secret_key():
    """A weak/short secret key"""
    return "short"


@pytest.fixture
def valid_password():
    """A valid password meeting all requirements"""
    return "ValidPassword123!"


@pytest.fixture
def valid_payload():
    """Valid JWT payload"""
    return {"sub": "test@example.com", "user_id": 123, "tenant_id": 1}


# ============================================================================
# JWT ALGORITHM CONFUSION TESTS (OWASP A02)
# ============================================================================


class TestJWTAlgorithmSecurity:
    """Tests for JWT algorithm confusion vulnerability prevention"""

    def test_none_algorithm_rejected(self):
        """CRITICAL: Reject 'none' algorithm (CVE-2015-9235)"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("none")

    def test_none_algorithm_case_insensitive(self):
        """Reject 'none' regardless of case"""
        for variant in ["None", "NONE", "NoNe", "nOnE"]:
            with pytest.raises(ValueError, match="not allowed"):
                validate_jwt_algorithm(variant)

    def test_empty_algorithm_rejected(self):
        """Reject empty algorithm string"""
        with pytest.raises(ValueError):
            validate_jwt_algorithm("")

    def test_null_algorithm_rejected(self):
        """Reject None algorithm"""
        with pytest.raises(ValueError):
            validate_jwt_algorithm(None)

    def test_allowed_algorithms_whitelist(self):
        """Only HMAC-SHA algorithms are allowed"""
        # These should pass
        for algo in ["HS256", "HS384", "HS512"]:
            assert validate_jwt_algorithm(algo) is True

    def test_disallowed_algorithms_rejected(self):
        """Non-HMAC algorithms are rejected"""
        disallowed = ["RS256", "RS384", "RS512", "ES256", "PS256", "EdDSA"]
        for algo in disallowed:
            with pytest.raises(ValueError, match="not allowed"):
                validate_jwt_algorithm(algo)

    def test_algorithm_type_validation(self):
        """Algorithm must be a string"""
        with pytest.raises(TypeError):
            validate_jwt_algorithm(123)
        with pytest.raises(TypeError):
            validate_jwt_algorithm(["HS256"])

    def test_create_token_validates_algorithm(self, valid_secret_key, valid_payload):
        """Token creation validates algorithm"""
        # Valid algorithm should work
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm="HS256")
        assert token is not None

        # Invalid algorithm should fail
        with pytest.raises(ValueError, match="not allowed"):
            create_jwt_token(valid_payload, valid_secret_key, algorithm="none")

    def test_verify_token_validates_algorithm(self, valid_secret_key, valid_payload):
        """Token verification validates algorithm list"""
        token = create_jwt_token(valid_payload, valid_secret_key, algorithm="HS256")

        # Valid algorithm should work
        payload = verify_jwt_token(token, valid_secret_key, algorithms=["HS256"])
        assert payload is not None

        # Invalid algorithm in list should fail
        with pytest.raises(ValueError, match="not allowed"):
            verify_jwt_token(token, valid_secret_key, algorithms=["none"])


class TestJWTExpirationSecurity:
    """Tests for JWT expiration enforcement"""

    def test_token_always_has_expiration(self, valid_secret_key, valid_payload):
        """Tokens must always have expiration set"""
        token = create_jwt_token(valid_payload, valid_secret_key)

        # Decode without verification to check exp
        payload = jwt.decode(token, valid_secret_key, algorithms=["HS256"])
        assert "exp" in payload
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()

    def test_expired_token_rejected(self, valid_secret_key, valid_payload):
        """Expired tokens must be rejected"""
        # Create token that's already expired
        expired_delta = timedelta(minutes=-1)
        token = create_jwt_token(valid_payload, valid_secret_key, expires_delta=expired_delta)

        # Should return None (invalid)
        result = verify_jwt_token(token, valid_secret_key)
        assert result is None

    def test_token_with_custom_expiration(self, valid_secret_key, valid_payload):
        """Custom expiration is respected"""
        custom_delta = timedelta(hours=2)
        token = create_jwt_token(valid_payload, valid_secret_key, expires_delta=custom_delta)

        payload = verify_jwt_token(token, valid_secret_key)
        assert payload is not None

        # Verify expiration is approximately 2 hours from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = exp_time - now
        assert 1.9 < diff.total_seconds() / 3600 < 2.1  # Within 2 hours +/- 6 minutes

    def test_token_has_issued_at(self, valid_secret_key, valid_payload):
        """Tokens should have issued-at (iat) claim"""
        token = create_jwt_token(valid_payload, valid_secret_key)
        payload = jwt.decode(token, valid_secret_key, algorithms=["HS256"])

        assert "iat" in payload


class TestSecretKeyValidation:
    """Tests for secret key strength validation"""

    def test_short_key_rejected(self):
        """Keys shorter than minimum are rejected"""
        short_key = "a" * (MIN_SECRET_KEY_LENGTH - 1)
        is_valid, issues = validate_secret_key(short_key, raise_on_weak=False)
        assert is_valid is False
        assert any("at least" in issue for issue in issues)

    def test_empty_key_rejected(self):
        """Empty keys are rejected"""
        with pytest.raises(ValueError, match="empty"):
            validate_secret_key("", raise_on_weak=True)

    def test_production_key_length_enforced(self):
        """Production requires longer keys"""
        # Key that passes development but fails production
        dev_ok_key = "a" * MIN_SECRET_KEY_LENGTH

        is_valid_dev, _ = validate_secret_key(dev_ok_key, is_production=False, raise_on_weak=False)
        is_valid_prod, _ = validate_secret_key(dev_ok_key, is_production=True, raise_on_weak=False)

        assert is_valid_dev is True
        assert is_valid_prod is False  # Not long enough for production

    def test_development_key_patterns_detected(self):
        """Development key patterns are detected"""
        dev_patterns = [
            "dev-secret-key-123456789012345",
            "test-secret-key-12345678901234",
            "my-secret-change-in-production",
        ]

        for key in dev_patterns:
            _, issues = validate_secret_key(key, is_production=False, raise_on_weak=False)
            assert len(issues) > 0  # Should have warnings

    def test_development_keys_rejected_in_production(self):
        """Development keys are rejected in production mode"""
        dev_key = "dev-secret-key-this-is-long-enough-for-testing"

        with pytest.raises(ValueError):
            validate_secret_key(
                dev_key + "extra-length-for-prod",
                is_production=True,
                raise_on_weak=True,
            )

    def test_valid_production_key_accepted(self):
        """Valid production keys are accepted"""
        # Generate a proper production key
        import secrets

        prod_key = secrets.token_urlsafe(64)

        is_valid, issues = validate_secret_key(prod_key, is_production=True, raise_on_weak=False)
        # Should be valid (no errors, may have warnings)
        assert is_valid is True


# ============================================================================
# PASSWORD HASHING TESTS (OWASP A02)
# ============================================================================


class TestPasswordValidation:
    """Tests for password policy validation"""

    def test_valid_password_accepted(self, valid_password):
        """Valid passwords pass validation"""
        result = validate_password(valid_password)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_short_password_rejected(self):
        """Short passwords are rejected"""
        result = validate_password("Ab1!")
        assert result.is_valid is False
        assert any("at least" in e for e in result.errors)

    def test_no_uppercase_rejected(self):
        """Passwords without uppercase are rejected (default policy)"""
        result = validate_password("validpassword123!")
        assert result.is_valid is False
        assert any("uppercase" in e.lower() for e in result.errors)

    def test_no_lowercase_rejected(self):
        """Passwords without lowercase are rejected (default policy)"""
        result = validate_password("VALIDPASSWORD123!")
        assert result.is_valid is False
        assert any("lowercase" in e.lower() for e in result.errors)

    def test_no_digit_rejected(self):
        """Passwords without digits are rejected (default policy)"""
        result = validate_password("ValidPassword!")
        assert result.is_valid is False
        assert any("digit" in e.lower() for e in result.errors)

    def test_non_ascii_password_rejected(self):
        """Non-ASCII passwords are rejected (bcrypt compatibility)"""
        result = validate_password("ValidPassword123\u00e9")  # é is non-ASCII
        assert result.is_valid is False
        assert any("ascii" in e.lower() for e in result.errors)

    def test_common_password_rejected(self):
        """Common/weak passwords are rejected"""
        common_passwords = ["password123A", "123456abcDEF", "qwertyABC123"]
        for pwd in common_passwords:
            result = validate_password(pwd)
            # Should either be invalid or have low strength score
            assert result.is_valid is False or result.strength_score < 50

    def test_long_password_warning(self):
        """Passwords over 72 chars get truncation warning"""
        long_password = "Valid1!" + "a" * 70  # Over 72 chars
        result = validate_password(long_password)
        assert any("truncat" in w.lower() for w in result.warnings)

    def test_strength_score_calculation(self):
        """Strength score increases with complexity"""
        weak = validate_password("Password1")
        medium = validate_password("Password123")
        strong = validate_password("MyP@ssword123!")

        assert weak.strength_score <= medium.strength_score <= strong.strength_score

    def test_custom_policy_respected(self):
        """Custom password policies are respected"""
        lenient_policy = PasswordPolicy(
            min_length=8,  # Must be at least 8 per security requirements
            require_uppercase=False,
            require_lowercase=False,
            require_digit=False,
            require_special=False,
            reject_common_passwords=False,
        )

        result = validate_password(
            "simplepw", policy=lenient_policy
        )  # 8 chars, no special requirements
        assert result.is_valid is True

    def test_non_string_password_rejected(self):
        """Non-string passwords are rejected"""
        result = validate_password(12345678)
        assert result.is_valid is False
        assert any("string" in e.lower() for e in result.errors)


class TestPasswordHashing:
    """Tests for bcrypt password hashing"""

    def test_password_hashed_correctly(self, valid_password):
        """Passwords are hashed with bcrypt"""
        hashed = hash_password_sync(valid_password, testing=True)

        # Bcrypt hashes start with $2b$ or $2a$
        assert hashed.startswith("$2")
        assert hashed != valid_password

    def test_password_verification_works(self, valid_password):
        """Hashed passwords can be verified"""
        hashed = hash_password_sync(valid_password, testing=True)

        assert verify_password_sync(valid_password, hashed) is True
        assert verify_password_sync("wrong_password", hashed) is False

    def test_non_ascii_password_hash_rejected(self):
        """Non-ASCII passwords are rejected during hashing"""
        with pytest.raises(ValueError, match="[Aa][Ss][Cc][Ii][Ii]"):
            hash_password_sync("password\u00e9")

    def test_empty_password_rejected(self):
        """Empty passwords are rejected"""
        with pytest.raises(ValueError, match="empty"):
            hash_password_sync("")

    def test_none_password_rejected(self):
        """None passwords are rejected"""
        with pytest.raises(ValueError):
            hash_password_sync(None)

    def test_password_truncation_at_72_bytes(self):
        """Passwords are truncated at 72 bytes for bcrypt"""
        # Two passwords that differ after 72 chars should hash to same value
        base = "ValidPassword1!" + "a" * 60  # 75 chars total
        password1 = base
        password2 = base + "xyz"  # Different after 72 chars

        # Prepare both (truncate)
        prep1 = _prepare_password_for_bcrypt(password1)
        prep2 = _prepare_password_for_bcrypt(password2)

        assert len(prep1) == 72
        assert len(prep2) == 72
        assert prep1 == prep2  # Both truncated to same value

    def test_hashing_in_test_mode_uses_fewer_rounds(self):
        """Test mode uses fewer bcrypt rounds for performance"""
        import time

        # Time hash with testing=True vs testing=False
        start = time.time()
        hash_password_sync("TestPassword123!", testing=True)
        test_time = time.time() - start

        # Test mode should be significantly faster
        # We can't test production timing easily without slowing tests
        assert test_time < 0.5  # Should be very fast in test mode

    def test_verification_with_invalid_hash(self, valid_password):
        """Verification with invalid hash returns False (no exception)"""
        assert verify_password_sync(valid_password, "not-a-valid-hash") is False

    def test_verification_with_empty_hash_rejected(self, valid_password):
        """Empty hash is rejected"""
        with pytest.raises(ValueError, match="empty"):
            verify_password_sync(valid_password, "")

    def test_verification_with_none_hash_rejected(self, valid_password):
        """None hash is rejected"""
        with pytest.raises(ValueError):
            verify_password_sync(valid_password, None)


# ============================================================================
# JWT CONFIG VALIDATION TESTS
# ============================================================================


class TestJWTConfig:
    """Tests for JWT configuration validation"""

    def test_valid_config_accepted(self, valid_secret_key):
        """Valid configuration is accepted"""
        config = JWTConfig(
            secret_key=valid_secret_key,
            algorithm="HS256",
            access_token_expire_minutes=30,
        )
        assert config.secret_key == valid_secret_key
        assert config.algorithm == "HS256"

    def test_none_algorithm_rejected(self, valid_secret_key):
        """Configuration with 'none' algorithm is rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            JWTConfig(secret_key=valid_secret_key, algorithm="none")

    def test_short_secret_rejected(self):
        """Short secret keys are rejected"""
        with pytest.raises(ValueError, match="at least"):
            JWTConfig(secret_key="short", algorithm="HS256")

    def test_empty_secret_rejected(self):
        """Empty secret keys are rejected"""
        with pytest.raises(ValueError, match="empty"):
            JWTConfig(secret_key="", algorithm="HS256")

    def test_expiration_bounds(self, valid_secret_key):
        """Token expiration is within bounds"""
        # Too short (0) should fail
        with pytest.raises(ValueError):
            JWTConfig(
                secret_key=valid_secret_key,
                algorithm="HS256",
                access_token_expire_minutes=0,
            )

        # Too long (over 30 days) should fail
        with pytest.raises(ValueError):
            JWTConfig(
                secret_key=valid_secret_key,
                algorithm="HS256",
                access_token_expire_minutes=50000,  # Over 30 days
            )


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================


class TestCryptoUtilities:
    """Tests for cryptographic utility functions"""

    def test_secure_token_generation(self):
        """Secure tokens are generated correctly"""
        token1 = generate_secure_token()
        token2 = generate_secure_token()

        # Tokens should be different
        assert token1 != token2

        # Tokens should be URL-safe
        assert all(c.isalnum() or c in "-_" for c in token1)

    def test_secure_token_length(self):
        """Token length corresponds to requested bytes"""
        token_16 = generate_secure_token(16)
        token_32 = generate_secure_token(32)

        # URL-safe base64 encoding expands size
        assert len(token_16) < len(token_32)

    def test_constant_time_compare_equal(self):
        """Constant time compare works for equal strings"""
        assert constant_time_compare("test", "test") is True

    def test_constant_time_compare_not_equal(self):
        """Constant time compare works for unequal strings"""
        assert constant_time_compare("test", "Test") is False
        assert constant_time_compare("test", "test1") is False

    def test_constant_time_compare_type_safety(self):
        """Constant time compare handles non-strings safely"""
        assert constant_time_compare("test", 123) is False
        assert constant_time_compare(None, "test") is False

    def test_token_hash_for_storage(self):
        """Token hashing for storage produces consistent results"""
        token = "my-secret-refresh-token"

        hash1 = hash_token_for_storage(token)
        hash2 = hash_token_for_storage(token)

        # Same input produces same hash
        assert hash1 == hash2

        # Hash is hex-encoded SHA256 (64 chars)
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_audit_crypto_config(self):
        """Crypto config audit returns expected information"""
        config = audit_crypto_config()

        assert "allowed_jwt_algorithms" in config
        assert "bcrypt_rounds" in config
        assert "password_min_length" in config
        assert "HS256" in config["allowed_jwt_algorithms"]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestCryptoIntegration:
    """Integration tests for crypto utilities"""

    def test_full_jwt_lifecycle(self, valid_secret_key):
        """Test complete JWT create -> verify lifecycle"""
        payload = {
            "sub": "user@example.com",
            "user_id": 123,
            "roles": ["user", "admin"],
        }

        # Create token
        token = create_jwt_token(
            payload,
            valid_secret_key,
            algorithm="HS256",
            expires_delta=timedelta(hours=1),
        )

        # Verify token
        decoded = verify_jwt_token(token, valid_secret_key, algorithms=["HS256"])

        assert decoded is not None
        assert decoded["sub"] == "user@example.com"
        assert decoded["user_id"] == 123
        assert decoded["roles"] == ["user", "admin"]
        assert "exp" in decoded
        assert "iat" in decoded

    def test_full_password_lifecycle(self):
        """Test complete password validate -> hash -> verify lifecycle"""
        password = "SecurePassword123!"

        # Validate
        validation = validate_password(password)
        assert validation.is_valid is True

        # Hash
        hashed = hash_password_sync(password, testing=True)

        # Verify
        assert verify_password_sync(password, hashed) is True
        assert verify_password_sync("wrong", hashed) is False

    def test_tampered_token_rejected(self, valid_secret_key):
        """Tampered tokens are rejected"""
        payload = {"sub": "user@example.com", "user_id": 123}
        token = create_jwt_token(payload, valid_secret_key)

        # Tamper with token (change a character)
        parts = token.split(".")
        tampered_payload = parts[1][:-1] + ("a" if parts[1][-1] != "a" else "b")
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

        # Should be rejected
        result = verify_jwt_token(tampered_token, valid_secret_key)
        assert result is None

    def test_wrong_secret_key_rejected(self, valid_secret_key):
        """Tokens signed with different key are rejected"""
        payload = {"sub": "user@example.com"}
        token = create_jwt_token(payload, valid_secret_key)

        # Try to verify with different key
        different_key = "completely-different-secret-key-here"
        result = verify_jwt_token(token, different_key)
        assert result is None


# ============================================================================
# ATTACK SIMULATION TESTS
# ============================================================================


class TestSecurityAttackPrevention:
    """Tests that simulate actual attack scenarios"""

    def test_none_algorithm_attack_prevention(self, valid_secret_key):
        """
        Simulate CVE-2015-9235: 'none' algorithm attack

        Attack: Attacker modifies token header to use 'none' algorithm,
        strips signature, and bypasses authentication.
        """
        # Create a valid token
        payload = {"sub": "admin@example.com", "role": "admin"}
        valid_token = create_jwt_token(payload, valid_secret_key)

        # Simulate attack: create token with 'none' algorithm
        attack_header = {"alg": "none", "typ": "JWT"}
        attack_payload = {"sub": "attacker@example.com", "role": "admin"}

        # Manually construct attack token
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(attack_header).encode()).rstrip(b"=").decode()
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(attack_payload).encode()).rstrip(b"=").decode()
        )
        attack_token = f"{header_b64}.{payload_b64}."  # Empty signature

        # Our verify function should reject this
        result = verify_jwt_token(attack_token, valid_secret_key, algorithms=["HS256"])
        assert result is None  # Attack prevented

    def test_algorithm_confusion_attack_prevention(self, valid_secret_key):
        """
        Simulate algorithm confusion attack

        Attack: System expects RS256 but attacker sends HS256 token
        signed with the public key.
        """
        # Our system only allows HS256/384/512, so this attack vector
        # is prevented by not supporting RS* algorithms at all
        with pytest.raises(ValueError, match="not allowed"):
            validate_jwt_algorithm("RS256")

    def test_timing_attack_prevention_password(self):
        """
        Verify password comparison is delegated to passlib's bcrypt.

        The constant-time guarantee is a property of bcrypt, not something a unit
        test can establish by timing calls: this assertion therefore checks the
        MECHANISM that provides it, not a wall-clock outcome.

        Until 2026-09-17 this test averaged five `time.time()` samples of a correct
        and an incorrect verification and asserted `0.5 < correct/wrong < 2.0`. That
        measured the machine rather than the code, and it went red in the full port
        (`-n 4`, 2026-09-17: ratio 0.42) while passing 10/10 in isolation. Measured
        distribution of that ratio on an idle machine, 40 samples: median 0.995, but
        min 0.627 -- the tail already wanders towards the bound without any load, so
        under four parallel workers the boundary is reached by scheduling noise. Two
        ~2.6ms measurements averaged over five samples cannot distinguish a timing
        leak from a context switch.

        Mutation proof (2026-09-17), both directions:
          schemes=["bcrypt"] -> ["sha256_crypt"] in get_password_context -> RED
          unmodified                                                     -> GREEN
        """
        password = "TestPassword123!"
        hashed = hash_password_sync(password, testing=True)

        # A modular-crypt hash names its own scheme in the first field; bcrypt uses
        # the 2a/2b/2y variants. Reading it back off the produced hash proves which
        # primitive actually ran, not merely which one the configuration asked for.
        scheme_marker = hashed.split("$")[1] if hashed.count("$") >= 2 else ""
        assert scheme_marker in {
            "2a",
            "2b",
            "2y",
        }, f"Password hashing must use bcrypt, got scheme marker {scheme_marker!r}"

        # Verification runs through the same passlib context, and that context is what
        # makes the comparison constant-time. Both outcomes must come out of it.
        context = get_password_context(testing=False)
        assert context.schemes() == ("bcrypt",), (
            f"Verification context must offer bcrypt only, got {context.schemes()}"
        )
        assert verify_password_sync(password, hashed) is True
        assert verify_password_sync("WrongPassword123!", hashed) is False


# ============================================================================
# REGRESSION TESTS
# ============================================================================


class TestSecurityRegressions:
    """Tests to prevent regression of security fixes"""

    def test_jwt_handler_uses_explicit_algorithms(self):
        """Verify JWTHandler uses explicit algorithm list"""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()

        # Create a token
        token = handler.create_access_token({"sub": "test@example.com", "tenant_id": 1})

        # Verify uses explicit algorithm
        payload = handler.verify_token(token)
        assert payload is not None

    def test_security_manager_uses_explicit_algorithms(self):
        """Verify SecurityManager uses explicit algorithm list"""
        from src.core.security.security_manager import get_security_manager

        manager = get_security_manager()

        # Create a token
        token = manager.generate_token("user_test@example.com")

        # Verify uses explicit algorithm
        payload = manager.verify_token(token)
        assert payload is not None
        assert "user_id" in payload
