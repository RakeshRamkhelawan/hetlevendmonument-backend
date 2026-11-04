"""Encryption Service for Memory Embeddings."""

import base64
import logging
from typing import Any, Optional, cast

logger = logging.getLogger(__name__)

# Lazy imports
_numpy: Any = None


def _get_numpy() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy-load numpy library"""
    global _numpy
    if _numpy is None:
        import numpy as np_lib

        _numpy = np_lib
    return _numpy


class EncryptionService:
    """Service for encrypting and decrypting memory embeddings."""

    def __init__(self, encryption_key: bytes | None = None) -> None:
        self._encryption_key = encryption_key
        self._enabled = encryption_key is not None

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._enabled and self._encryption_key is not None

    def enable(self, key: bytes) -> None:
        """Enable encryption with the provided key."""
        self._encryption_key = key
        self._enabled = True

    def disable(self) -> None:
        """Disable encryption."""
        self._enabled = False

    def encrypt_embedding(
        self,
        embedding: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:  # TODO(TYPE): replace Any with concrete type
        """Encrypt an embedding using the configured key.

        P2 FIX: Encrypt embeddings before storage to prevent data exposure.

        Args:
            embedding: Numpy array or None

        Returns:
            Base64-encoded encrypted string or None if encryption disabled
        """
        if not self.is_enabled or embedding is None:
            return None

        try:
            from cryptography.fernet import Fernet

            assert self._encryption_key is not None  # guarded by self.is_enabled check above
            f = Fernet(self._encryption_key)

            # Convert embedding to bytes
            embedding_bytes = embedding.tobytes()

            # Encrypt
            encrypted = f.encrypt(embedding_bytes)

            # Return base64-encoded string
            return base64.b64encode(encrypted).decode("utf-8")

        except ImportError:
            logger.warning("cryptography library not installed, skipping embedding encryption")
            return None
        except Exception as exc:
            logger.error("Failed to encrypt embedding: %s", exc)
            return None

    def decrypt_embedding(
        self, encrypted_data: str
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Decrypt an embedding using the configured key.

        P2 FIX: Decrypt embeddings after retrieval from storage.

        Args:
            encrypted_data: Base64-encoded encrypted string

        Returns:
            Numpy array or None if decryption fails
        """
        if not self.is_enabled or encrypted_data is None:
            return None

        try:
            from cryptography.fernet import Fernet

            assert self._encryption_key is not None  # guarded by self.is_enabled check above
            f = Fernet(self._encryption_key)

            # Decode base64
            encrypted = base64.b64decode(encrypted_data)

            # Decrypt
            decrypted_bytes = f.decrypt(encrypted)

            # Convert back to numpy array
            return _get_numpy().frombuffer(decrypted_bytes, dtype=_get_numpy().float32)

        except ImportError:
            logger.warning("cryptography library not installed, cannot decrypt embedding")
            return None
        except Exception as exc:
            logger.error("Failed to decrypt embedding: %s", exc)
            return None

    def encrypt_embeddings_batch(
        self,
        embeddings: list[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str | None]:  # TODO(TYPE): replace Any with concrete type
        """Encrypt multiple embeddings."""
        return [self.encrypt_embedding(emb) for emb in embeddings]

    def decrypt_embeddings_batch(
        self, encrypted_data_list: list[str]
    ) -> list[Any | None]:  # TODO(TYPE): replace Any with concrete type
        """Decrypt multiple embeddings."""
        return [self.decrypt_embedding(data) for data in encrypted_data_list if data]
