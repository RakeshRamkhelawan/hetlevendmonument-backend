"""
Comprehensive tests for src/core/auth/token_service.py
Coverage target: 100% of token service
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, mock_open, patch

import jwt
import pytest

from src.core.auth.token_service import TokenService


class TestTokenServiceInitialization:
    """Test TokenService initialization"""

    def test_initialization_with_metrics(self):
        """Test TokenService initialization with metrics"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            assert service.metrics == mock_metrics
            assert service.key_path == tmpdir

    def test_initialization_creates_key_path(self):
        """Test initialization creates key directory"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "keys")
            service = TokenService(mock_metrics, key_path=key_path)

            assert os.path.exists(key_path)

    def test_initialization_generates_keys_if_missing(self):
        """Test initialization generates keys if not found"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            assert os.path.exists(os.path.join(tmpdir, "private.pem"))
            assert os.path.exists(os.path.join(tmpdir, "public.pem"))

    def test_initialization_loads_existing_keys(self):
        """Test initialization loads existing keys"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create service first to generate keys
            service1 = TokenService(mock_metrics, key_path=tmpdir)
            key_id1 = service1.current_key_id

            # Create new service with same path
            service2 = TokenService(mock_metrics, key_path=tmpdir)

            # Should load keys (but new key_id)
            assert service2.private_key is not None
            assert service2.public_key is not None


class TestKeyGeneration:
    """Test key generation methods"""

    def test_generate_new_keypair_creates_files(self):
        """Test _generate_new_keypair creates key files"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            # Files should exist
            assert os.path.isfile(os.path.join(tmpdir, "private.pem"))
            assert os.path.isfile(os.path.join(tmpdir, "public.pem"))

    def test_generate_new_keypair_creates_valid_rsa_keys(self):
        """Test generated keys are valid RSA keys"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            # Read keys
            with open(os.path.join(tmpdir, "private.pem"), "rb") as f:
                private_pem = f.read()
            with open(os.path.join(tmpdir, "public.pem"), "rb") as f:
                public_pem = f.read()

            # Should start with PEM markers
            assert b"-----BEGIN PRIVATE KEY-----" in private_pem
            assert b"-----BEGIN PUBLIC KEY-----" in public_pem


class TestCreateToken:
    """Test create_token method"""

    def test_create_token_basic(self):
        """Test basic token creation"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            assert isinstance(token, str)
            assert len(token) > 0

    def test_create_token_with_claims(self):
        """Test token creation with additional claims"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            claims = {"role": "admin", "tenant_id": 456}
            token = service.create_token("user-123", claims=claims)

            # Verify token contains claims
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            assert unverified_payload["role"] == "admin"
            assert unverified_payload["tenant_id"] == 456

    def test_create_token_includes_sub(self):
        """Test token includes subject claim"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            payload = jwt.decode(token, options={"verify_signature": False})
            assert payload["sub"] == "user-123"

    def test_create_token_includes_iat(self):
        """Test token includes issued-at claim"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            payload = jwt.decode(token, options={"verify_signature": False})
            assert "iat" in payload

    def test_create_token_includes_exp(self):
        """Test token includes expiration claim"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            payload = jwt.decode(token, options={"verify_signature": False})
            assert "exp" in payload

    def test_create_token_includes_jti(self):
        """Test token includes JWT ID claim"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            payload = jwt.decode(token, options={"verify_signature": False})
            assert "jti" in payload

    def test_create_token_includes_kid(self):
        """Test token includes key ID in header"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")

            header = jwt.get_unverified_header(token)
            assert "kid" in header
            assert header["kid"] == service.current_key_id

    def test_create_token_tracks_metrics_success(self):
        """Test successful token creation tracks metrics"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            service.create_token("user-123")

            mock_metrics.track_validation.assert_called_once()
            call_args = mock_metrics.track_validation.call_args[1]
            assert call_args["success"] is True

    def test_create_token_tracks_metrics_failure(self):
        """Test failed token creation tracks metrics"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)
            service.private_key = None  # Force error

            with pytest.raises(Exception):
                service.create_token("user-123")

            mock_metrics.track_validation.assert_called_once()
            call_args = mock_metrics.track_validation.call_args[1]
            assert call_args["success"] is False


class TestValidateToken:
    """Test validate_token method"""

    def test_validate_token_success(self):
        """Test successful token validation"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")
            payload = service.validate_token(token)

            assert payload["sub"] == "user-123"

    def test_validate_token_with_claims(self):
        """Test validating token with additional claims"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            claims = {"role": "admin"}
            token = service.create_token("user-123", claims=claims)
            payload = service.validate_token(token)

            assert payload["role"] == "admin"

    def test_validate_token_invalid_signature(self):
        """Test validating token with invalid signature"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")
            # Tamper with token
            tampered = token[:-10] + "XXXXXXXXXX"

            with pytest.raises(Exception):
                service.validate_token(tampered)

    def test_validate_token_invalid_key_id(self):
        """Test validating token with invalid key ID"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            # Create token with fake key ID
            payload = {
                "sub": "user-123",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "kid": "invalid-key-id",
            }
            fake_token = jwt.encode(
                payload,
                service.private_key,
                algorithm="RS256",
                headers={"kid": "invalid-key-id"},
            )

            with pytest.raises(jwt.InvalidTokenError):
                service.validate_token(fake_token)

    def test_validate_token_tracks_metrics_success(self):
        """Test successful validation tracks metrics"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")
            mock_metrics.track_validation.reset_mock()

            service.validate_token(token)

            mock_metrics.track_validation.assert_called_once()
            call_args = mock_metrics.track_validation.call_args[1]
            assert call_args["success"] is True

    def test_validate_token_tracks_metrics_failure(self):
        """Test failed validation tracks metrics"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            with pytest.raises(Exception):
                service.validate_token("invalid-token")

            call_args = mock_metrics.track_validation.call_args[1]
            assert call_args["success"] is False
            assert "reason" in call_args


class TestEdgeCases:
    """Test edge cases"""

    def test_token_expiry(self):
        """Test token expiration is set correctly"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token = service.create_token("user-123")
            payload = jwt.decode(token, options={"verify_signature": False})

            # Check expiry is ~1 hour from now
            exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            now = datetime.now(timezone.utc)
            time_diff = (exp_time - now).total_seconds()

            # Should be approximately 1 hour (3600 seconds)
            assert 3500 < time_diff < 3700

    def test_multiple_tokens_different_jti(self):
        """Test multiple tokens have different JWT IDs"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            token1 = service.create_token("user-123")
            token2 = service.create_token("user-123")

            payload1 = jwt.decode(token1, options={"verify_signature": False})
            payload2 = jwt.decode(token2, options={"verify_signature": False})

            assert payload1["jti"] != payload2["jti"]

    def test_keys_stored_in_service(self):
        """Test keys are stored in service"""
        mock_metrics = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = TokenService(mock_metrics, key_path=tmpdir)

            assert service.current_key_id in service.keys
            assert "private" in service.keys[service.current_key_id]
            assert "public" in service.keys[service.current_key_id]
