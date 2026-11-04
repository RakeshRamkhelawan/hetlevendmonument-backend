"""
Unit tests for TokenEncryptionService.

Tests Fernet-based encryption/decryption of OAuth tokens.
"""

import pytest
from cryptography.fernet import InvalidToken

from src.core.scheduling.integrations.token_encryption import TokenEncryptionService


class TestTokenEncryptionService:
    """Tests for the TokenEncryptionService."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test that encrypt/decrypt roundtrip preserves data."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        plaintext = "sensitive-oauth-token-12345"

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext
        assert encrypted != plaintext

    def test_encrypt_produces_different_ciphertexts(self) -> None:
        """Test that encrypting same plaintext produces different ciphertexts."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        plaintext = "sensitive-oauth-token-12345"

        encrypted1 = service.encrypt(plaintext)
        encrypted2 = service.encrypt(plaintext)

        assert encrypted1 != encrypted2
        assert service.decrypt(encrypted1) == plaintext
        assert service.decrypt(encrypted2) == plaintext

    def test_decrypt_with_wrong_key_fails(self) -> None:
        """Test that decrypting with wrong key raises InvalidToken."""
        service1 = TokenEncryptionService(master_key="correct-key-32-chars-long!!")
        service2 = TokenEncryptionService(master_key="wrong-key-32-chars-long!!!")
        plaintext = "sensitive-oauth-token-12345"

        encrypted = service1.encrypt(plaintext)

        with pytest.raises(InvalidToken):
            service2.decrypt(encrypted)

    def test_decrypt_corrupted_ciphertext_fails(self) -> None:
        """Test that decrypting corrupted ciphertext raises InvalidToken."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        plaintext = "sensitive-oauth-token-12345"

        encrypted = service.encrypt(plaintext)
        corrupted = encrypted[:-5] + "XXXXX"

        with pytest.raises(InvalidToken):
            service.decrypt(corrupted)

    def test_empty_string_roundtrip(self) -> None:
        """Test that empty string can be encrypted/decrypted."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        plaintext = ""

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_unicode_characters_roundtrip(self) -> None:
        """Test that unicode characters are preserved."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        plaintext = "token-with-unicode-\u00e9-\u00f1-\u4e2d"  # é, ñ, 中

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_different_master_keys_produce_different_results(self) -> None:
        """Test that different master keys produce different encryption."""
        key1 = "master-key-1-32-chars-long!!!"
        key2 = "master-key-2-32-chars-long!!!"
        service1 = TokenEncryptionService(master_key=key1)
        service2 = TokenEncryptionService(master_key=key2)
        plaintext = "sensitive-oauth-token-12345"

        encrypted1 = service1.encrypt(plaintext)
        encrypted2 = service2.encrypt(plaintext)

        assert encrypted1 != encrypted2

    def test_same_key_same_instance_consistency(self) -> None:
        """Test that same key produces consistent service behavior."""
        key = "master-key-32-chars-long!!!!"
        service1 = TokenEncryptionService(master_key=key)
        service2 = TokenEncryptionService(master_key=key)
        plaintext = "sensitive-oauth-token-12345"

        encrypted = service1.encrypt(plaintext)
        decrypted = service2.decrypt(encrypted)

        assert decrypted == plaintext

    def test_long_token_roundtrip(self) -> None:
        """Test that long tokens (e.g., JWT) can be encrypted/decrypted."""
        service = TokenEncryptionService(master_key="test-master-key-32-chars-long!!")
        # Simulate a long JWT-like token
        plaintext = "eyJhbGciOiJSUzI1NiIs" + "A" * 500 + ".eyJzdWIiOiIxMjM0NTY3ODkwIiw" + "B" * 500

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_service_uses_env_var_when_no_key_provided(self, monkeypatch) -> None:
        """Test that service uses MASTER_ENCRYPTION_KEY env var."""
        monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "env-master-key-32-chars-long")
        service = TokenEncryptionService()
        plaintext = "sensitive-oauth-token-12345"

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext
