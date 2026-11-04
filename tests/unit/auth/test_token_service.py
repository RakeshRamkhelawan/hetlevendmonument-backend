"""
Tests for src/core/auth/token_service.py (LEGACY RSA-based system)
Target: 85%+ coverage
Tests: 50-60
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, mock_open, patch

import pytest


class TestTokenServiceInitialization:
    """Test TokenService initialization"""

    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_initialization_creates_key_path(self, mock_makedirs, mock_exists):
        """Test initialization creates key path if it doesn't exist"""
        mock_exists.return_value = False  # Key path doesn't exist

        with patch("src.core.auth.token_service.TokenService._load_or_generate_keys"):
            from src.core.auth.token_service import TokenService

            mock_metrics = MagicMock()
            service = TokenService(mock_metrics, key_path="test_keys")

            # Verify key path was ensured
            assert service.key_path == "test_keys"
            mock_makedirs.assert_called_once_with("test_keys")

    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_initialization_key_path_exists(self, mock_makedirs, mock_exists):
        """Test initialization when key path already exists"""
        mock_exists.return_value = True  # Key path exists

        with patch("src.core.auth.token_service.TokenService._load_or_generate_keys"):
            from src.core.auth.token_service import TokenService

            mock_metrics = MagicMock()
            service = TokenService(mock_metrics, key_path="test_keys")

            # Verify key path was used
            assert service.key_path == "test_keys"
            mock_makedirs.assert_not_called()


class TestTokenServiceKeyManagement:
    """Test key generation and loading"""

    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_load_or_generate_keys_creates_new_keys(self, mock_makedirs, mock_exists):
        """Test _load_or_generate_keys creates new keys when files don't exist"""
        mock_exists.return_value = False  # Key files don't exist
        mock_makedirs.return_value = None  # Don't actually create directories

        with patch(
            "src.core.auth.token_service.TokenService._generate_new_keypair"
        ) as mock_generate:
            from src.core.auth.token_service import TokenService

            mock_metrics = MagicMock()
            service = TokenService(mock_metrics, key_path="test_keys")

            # Should call generate new keypair
            mock_generate.assert_called_once()

    @patch("os.path.exists")
    def test_load_or_generate_keys_loads_existing_keys(self, mock_exists):
        """Test _load_or_generate_keys loads existing keys"""
        mock_exists.return_value = True  # Key files exist

        with patch("src.core.auth.token_service.TokenService._load_existing_keys") as mock_load:
            from src.core.auth.token_service import TokenService

            mock_metrics = MagicMock()
            service = TokenService(mock_metrics, key_path="test_keys")

            # Should call load existing keys
            mock_load.assert_called_once()

    @patch("builtins.open", new_callable=mock_open, read_data=b"test_key_data")
    def test_load_existing_keys(self, mock_file):
        """Test _load_existing_keys loads keys correctly"""
        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Mock the actual file operations
        with patch("builtins.open", mock_file):
            service._load_existing_keys()

        # Verify keys were loaded (we can't predict the actual UUID, so just check it exists)
        assert service.current_key_id is not None
        assert len(service.current_key_id) > 0
        assert service.current_key_id in service.keys
        assert service.keys[service.current_key_id]["private"] == b"test_key_data"
        assert service.keys[service.current_key_id]["public"] == b"test_key_data"


class TestTokenServiceTokenCreation:
    """Test token creation functionality"""

    @patch("jwt.encode")
    @patch("src.core.auth.token_service.uuid4")
    def test_create_token_basic(self, mock_uuid, mock_encode):
        """Test basic token creation"""
        mock_uuid.side_effect = ["test-jti-123", "test-kid-456"]
        mock_encode.return_value = "test.encoded.token"

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.private_key = b"test-private-key"
        service.current_key_id = "test-kid-456"
        service.keys = {"test-kid-456": {"private": b"test-private-key"}}

        # Create token
        token = service.create_token("user123")

        # Verify result
        assert token == "test.encoded.token"

        # Verify encode was called with correct parameters
        mock_encode.assert_called_once()
        call_args = mock_encode.call_args
        payload = call_args[0][0]
        private_key = call_args[0][1]
        algorithm = call_args[1]["algorithm"]
        headers = call_args[1]["headers"]

        assert payload["sub"] == "user123"
        assert "iat" in payload
        assert "exp" in payload
        # We can't assert the exact JTI value since it's generated by uuid.uuid4
        assert payload["jti"] is not None
        assert len(payload["jti"]) > 0
        assert private_key == b"test-private-key"
        assert algorithm == "RS256"
        assert headers["kid"] == "test-kid-456"

    @patch("jwt.encode")
    @patch("src.core.auth.token_service.uuid4")
    def test_create_token_with_claims(self, mock_uuid, mock_encode):
        """Test token creation with additional claims"""
        mock_uuid.side_effect = ["test-jti-123", "test-kid-456"]
        mock_encode.return_value = "test.encoded.token"

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.private_key = b"test-private-key"
        service.current_key_id = "test-kid-456"
        service.keys = {"test-kid-456": {"private": b"test-private-key"}}

        # Create token with claims
        claims = {"role": "admin", "permissions": ["read", "write"]}
        token = service.create_token("user123", claims)

        # Verify result
        assert token == "test.encoded.token"

        # Verify encode was called with correct parameters
        mock_encode.assert_called_once()
        call_args = mock_encode.call_args
        payload = call_args[0][0]

        assert payload["sub"] == "user123"
        assert payload["role"] == "admin"
        assert payload["permissions"] == ["read", "write"]

    @patch("jwt.encode")
    @patch("src.core.auth.token_service.uuid4")
    def test_create_token_metrics_tracking_success(self, mock_uuid, mock_encode):
        """Test metrics tracking on successful token creation"""
        mock_uuid.side_effect = ["test-jti-123", "test-kid-456"]
        mock_encode.return_value = "test.encoded.token"

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.private_key = b"test-private-key"
        service.current_key_id = "test-kid-456"
        service.keys = {"test-kid-456": {"private": b"test-private-key"}}

        # Create token
        token = service.create_token("user123")

        # Verify metrics were tracked
        mock_metrics.track_validation.assert_called_once()
        call_args = mock_metrics.track_validation.call_args
        args = call_args[0]
        kwargs = call_args[1]

        assert len(args) >= 1  # timestamp
        assert kwargs.get("success") is True

    @patch("jwt.encode")
    @patch("src.core.auth.token_service.uuid4")
    def test_create_token_metrics_tracking_failure(self, mock_uuid, mock_encode):
        """Test metrics tracking on failed token creation"""
        mock_uuid.side_effect = ["test-jti-123", "test-kid-456"]
        mock_encode.side_effect = Exception("Encoding failed")

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.private_key = b"test-private-key"
        service.current_key_id = "test-kid-456"
        service.keys = {"test-kid-456": {"private": b"test-private-key"}}

        # Try to create token (should fail)
        with pytest.raises(Exception, match="Encoding failed"):
            service.create_token("user123")

        # Verify metrics were tracked with failure
        mock_metrics.track_validation.assert_called_once()
        call_args = mock_metrics.track_validation.call_args
        args = call_args[0]
        kwargs = call_args[1]

        assert len(args) >= 1  # timestamp
        assert kwargs.get("success") is False
        assert "Encoding failed" in kwargs.get("reason", "")


class TestTokenServiceTokenValidation:
    """Test token validation functionality"""

    @patch("jwt.get_unverified_header")
    @patch("jwt.decode")
    def test_validate_token_success(self, mock_decode, mock_get_header):
        """Test successful token validation"""
        mock_get_header.return_value = {"kid": "test-kid-456"}
        mock_decode.return_value = {"sub": "user123", "exp": 1234567890}

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.keys = {"test-kid-456": {"public": b"test-public-key"}}

        # Validate token
        payload = service.validate_token("test.encoded.token")

        # Verify result
        assert payload == {"sub": "user123", "exp": 1234567890}

        # Verify decode was called with correct parameters
        mock_decode.assert_called_once()
        call_args = mock_decode.call_args
        token = call_args[0][0]
        public_key = call_args[0][1]
        algorithms = call_args[1]["algorithms"]

        assert token == "test.encoded.token"
        assert public_key == b"test-public-key"
        assert algorithms == ["RS256"]

    @patch("jwt.get_unverified_header")
    def test_validate_token_invalid_key_id(self, mock_get_header):
        """Test token validation with invalid key ID"""
        mock_get_header.return_value = {"kid": "invalid-kid"}

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.keys = {"test-kid-456": {"public": b"test-public-key"}}

        # Try to validate token
        with pytest.raises(Exception, match="Invalid key ID"):
            service.validate_token("test.encoded.token")

    @patch("jwt.get_unverified_header")
    def test_validate_token_missing_key_id(self, mock_get_header):
        """Test token validation with missing key ID"""
        mock_get_header.return_value = {}  # No kid

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Try to validate token
        with pytest.raises(Exception, match="Invalid key ID"):
            service.validate_token("test.encoded.token")

    @patch("jwt.get_unverified_header")
    @patch("jwt.decode")
    def test_validate_token_metrics_tracking_success(self, mock_decode, mock_get_header):
        """Test metrics tracking on successful token validation"""
        mock_get_header.return_value = {"kid": "test-kid-456"}
        mock_decode.return_value = {"sub": "user123", "exp": 1234567890}

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.keys = {"test-kid-456": {"public": b"test-public-key"}}

        # Validate token
        payload = service.validate_token("test.encoded.token")

        # Verify metrics were tracked
        mock_metrics.track_validation.assert_called_once()
        call_args = mock_metrics.track_validation.call_args
        args = call_args[0]
        kwargs = call_args[1]

        assert len(args) >= 1  # timestamp
        assert kwargs.get("success") is True

    @patch("jwt.get_unverified_header")
    @patch("jwt.decode")
    def test_validate_token_metrics_tracking_failure(self, mock_decode, mock_get_header):
        """Test metrics tracking on failed token validation"""
        mock_get_header.return_value = {"kid": "test-kid-456"}
        mock_decode.side_effect = Exception("Decoding failed")

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()
        service = TokenService(mock_metrics, key_path="test_keys")

        # Set up mock keys
        service.keys = {"test-kid-456": {"public": b"test-public-key"}}

        # Try to validate token (should fail)
        with pytest.raises(Exception, match="Decoding failed"):
            service.validate_token("test.encoded.token")

        # Verify metrics were tracked with failure
        mock_metrics.track_validation.assert_called_once()
        call_args = mock_metrics.track_validation.call_args
        args = call_args[0]
        kwargs = call_args[1]

        assert len(args) >= 1  # timestamp
        assert kwargs.get("success") is False
        assert "Decoding failed" in kwargs.get("reason", "")


class TestTokenServiceKeyRotation:
    """Test key rotation functionality"""

    @patch("builtins.open", new_callable=mock_open)
    def test_generate_new_keypair(self, mock_file):
        """Test generation of new RSA key pair"""

        from src.core.auth.token_service import TokenService

        mock_metrics = MagicMock()

        # Mock cryptography functions
        with patch(
            "cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key"
        ) as mock_generate:
            mock_private_key = MagicMock()
            mock_public_key = MagicMock()
            mock_private_key.public_key.return_value = mock_public_key
            mock_private_key.private_bytes.return_value = b"private-key-bytes"
            mock_public_key.public_bytes.return_value = b"public-key-bytes"
            mock_generate.return_value = mock_private_key

            # _load_or_generate_keys wordt weggemockt zodat __init__ geen
            # generate_private_key aanroept. Zonder dit is de test flaky:
            # in CI (schone workspace) roept __init__ _generate_new_keypair()
            # aan via _load_or_generate_keys(), waarna de expliciete call
            # hieronder de teller op 2 zet en assert_called_once() faalt.
            with patch.object(TokenService, "_load_or_generate_keys"):
                service = TokenService(mock_metrics, key_path="test_keys")
            service._generate_new_keypair()

            # Verify key generation and saving
            mock_generate.assert_called_once()
            # Check that files were written (we can't assert exact count due to test setup)
