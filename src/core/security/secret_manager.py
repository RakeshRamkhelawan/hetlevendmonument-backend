"""
Secret Manager - Centralized, encrypted, auditable secret management

Features:
- Fernet symmetric encryption for secrets at rest
- PBKDF2 key derivation for master key
- Per-tenant secret isolation
- Secret versioning with rotation support
- Access logging for audit trail
- Pluggable backends (Environment, Database)
- Short TTL caching for performance

Security:
- Secrets never stored in plaintext
- Master key via MASTER_ENCRYPTION_KEY env var
- Tenant isolation enforced at all levels
- All access operations logged
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol, Set

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecretError(Exception):
    """Base exception for secret management errors."""

    pass


class SecretNotFoundError(SecretError):
    """Raised when a secret is not found."""

    pass


class SecretAccessDeniedError(SecretError):
    """Raised when access to a secret is denied."""

    pass


class SecretExpiredError(SecretError):
    """Raised when a secret has expired."""

    pass


@dataclass
class SecretMetadata:
    """Metadata for a secret (no sensitive values)."""

    secret_id: str
    tenant_id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    version: int
    is_deleted: bool = False


@dataclass
class SecretVersion:
    """Version information for a secret."""

    version: int
    created_at: datetime
    expires_at: datetime | None
    created_by: str | None = None


@dataclass
class SecretAccessLog:
    """Log entry for secret access."""

    secret_id: str
    tenant_id: int
    operation: str  # get, set, rotate, delete
    timestamp: datetime
    user_id: str | None = None
    success: bool = True
    error_message: str | None = None


class SecretBackend(ABC):
    """Abstract base class for secret storage backends."""

    @abstractmethod
    async def get_secret(self, tenant_id: int, secret_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get encrypted secret data."""
        pass

    @abstractmethod
    async def set_secret(self, tenant_id: int, secret_id: str, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Store encrypted secret data."""
        pass

    @abstractmethod
    async def delete_secret(self, tenant_id: int, secret_id: str, soft: bool = True) -> None:
        """Delete (soft or hard) secret."""
        pass

    @abstractmethod
    async def list_secrets(self, tenant_id: int) -> list[SecretMetadata]:
        """List all secrets for tenant (metadata only)."""
        pass


class EnvironmentBackend(SecretBackend):
    """Backend that stores secrets in environment variables (dev only)."""

    def __init__(self) -> None:
        self._secrets: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load secrets from environment variables with SECRET_ prefix."""
        for key, value in os.environ.items():
            if key.startswith("SECRET_"):
                # Format: SECRET_<tenant_id>_<secret_id>
                parts = key[7:].split("_", 1)  # Remove SECRET_ prefix
                if len(parts) == 2:
                    try:
                        tenant_id = int(parts[0])
                        secret_id = parts[1]
                        self._secrets[f"{tenant_id}:{secret_id}"] = {
                            "encrypted_value": value.encode(),
                            "version": 1,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    except ValueError:
                        continue

    async def get_secret(self, tenant_id: int, secret_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        return self._secrets.get(f"{tenant_id}:{secret_id}")

    async def set_secret(self, tenant_id: int, secret_id: str, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self._secrets[f"{tenant_id}:{secret_id}"] = data
        # Also set in environment for persistence in this session
        env_key = f"SECRET_{tenant_id}_{secret_id}"
        os.environ[env_key] = base64.b64encode(data.get("encrypted_value", b"")).decode()

    async def delete_secret(self, tenant_id: int, secret_id: str, soft: bool = True) -> None:
        key = f"{tenant_id}:{secret_id}"
        if soft and key in self._secrets:
            self._secrets[key]["is_deleted"] = True
        elif key in self._secrets:
            del self._secrets[key]

    async def list_secrets(self, tenant_id: int) -> list[SecretMetadata]:
        secrets_list: list[SecretMetadata] = []
        for key, data in self._secrets.items():
            if key.startswith(f"{tenant_id}:") and not data.get("is_deleted"):
                secret_id = key.split(":", 1)[1]
                secrets_list.append(
                    SecretMetadata(
                        secret_id=secret_id,
                        tenant_id=tenant_id,
                        name=secret_id,
                        description=None,
                        created_at=datetime.fromisoformat(
                            data.get("created_at", datetime.now(timezone.utc).isoformat())
                        ),
                        updated_at=datetime.now(timezone.utc),
                        expires_at=None,
                        version=data.get("version", 1),
                        is_deleted=data.get("is_deleted", False),
                    )
                )
        return secrets_list


class SecretManager:
    """
    Centralized secret manager with encryption, versioning, and audit logging.

    Features:
    - Fernet symmetric encryption
    - PBKDF2 key derivation
    - Tenant isolation
    - Secret versioning
    - Access logging
    - Short TTL caching
    - Pluggable backends
    """

    # Cache TTL in seconds
    CACHE_TTL = 300  # 5 minutes

    def __init__(
        self,
        backend: SecretBackend | None = None,
        master_key: str | None = None,
    ) -> None:
        """
        Initialize SecretManager.

        Args:
            backend: Storage backend (defaults to EnvironmentBackend for dev)
            master_key: Master encryption key (defaults to MASTER_ENCRYPTION_KEY env var)
        """
        self._backend = backend or EnvironmentBackend()
        self._master_key = master_key or os.getenv("MASTER_ENCRYPTION_KEY")

        if not self._master_key:
            logger.warning(
                "MASTER_ENCRYPTION_KEY not set - secrets will use a generated key "
                "(not suitable for production!)"
            )
            self._master_key = secrets.token_hex(32)

        self._fernet = self._create_fernet(self._master_key)

        # In-memory cache: {(tenant_id, secret_id): (value, timestamp)}
        self._cache: dict[tuple[int, str], tuple[str, float]] = {}

        # Access log buffer
        self._access_logs: list[SecretAccessLog] = []

    def _create_fernet(self, master_key: str) -> Fernet:
        """Create Fernet cipher from master key using PBKDF2."""
        # Derive a 32-byte key from the master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=hashlib.sha256(b"sanskritisetu_secret_manager").digest(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def _encrypt(self, value: str) -> bytes:
        """Encrypt a string value."""
        return self._fernet.encrypt(value.encode())

    def _decrypt(self, encrypted_value: bytes) -> str:
        """Decrypt an encrypted value."""
        try:
            return self._fernet.decrypt(encrypted_value).decode()
        except InvalidToken:
            raise SecretError("Failed to decrypt secret - invalid key or corrupted data")

    def _log_access(
        self,
        secret_id: str,
        tenant_id: int,
        operation: str,
        success: bool = True,
        error_message: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Log a secret access operation."""
        log_entry = SecretAccessLog(
            secret_id=secret_id,
            tenant_id=tenant_id,
            operation=operation,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            success=success,
            error_message=error_message,
        )
        self._access_logs.append(log_entry)

        # Also log to standard logger
        log_msg = f"Secret {operation}: tenant={tenant_id}, secret={secret_id}, success={success}"
        if success:
            logger.info(log_msg)
        else:
            logger.warning(f"{log_msg}, error={error_message}")

    def _get_from_cache(self, tenant_id: int, secret_id: str) -> str | None:
        """Get secret from cache if not expired."""
        cache_key = (tenant_id, secret_id)
        if cache_key in self._cache:
            value, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.CACHE_TTL:
                return value
            else:
                # Expired, remove from cache
                del self._cache[cache_key]
        return None

    def _set_cache(self, tenant_id: int, secret_id: str, value: str) -> None:
        """Set secret in cache."""
        self._cache[(tenant_id, secret_id)] = (value, time.time())

    async def get_secret(
        self,
        tenant_id: int,
        secret_id: str,
        user_id: str | None = None,
    ) -> str:
        """
        Get a secret value.

        Args:
            tenant_id: Tenant ID for isolation
            secret_id: Secret identifier
            user_id: Optional user ID for audit log

        Returns:
            Decrypted secret value

        Raises:
            SecretNotFoundError: If secret doesn't exist
            SecretExpiredError: If secret has expired
            SecretAccessDeniedError: If tenant doesn't match
        """
        # Check cache first
        cached_value = self._get_from_cache(tenant_id, secret_id)
        if cached_value:
            self._log_access(secret_id, tenant_id, "get", user_id=user_id)
            return cached_value

        # Get from backend
        data = await self._backend.get_secret(tenant_id, secret_id)

        if not data:
            self._log_access(
                secret_id,
                tenant_id,
                "get",
                success=False,
                error_message="Secret not found",
                user_id=user_id,
            )
            raise SecretNotFoundError(f"Secret '{secret_id}' not found for tenant {tenant_id}")

        if data.get("is_deleted"):
            self._log_access(
                secret_id,
                tenant_id,
                "get",
                success=False,
                error_message="Secret has been deleted",
                user_id=user_id,
            )
            raise SecretNotFoundError(f"Secret '{secret_id}' has been deleted")

        # Check expiration
        expires_at = data.get("expires_at")
        if expires_at:
            expiry = (
                datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
            )
            if expiry < datetime.now(timezone.utc):
                self._log_access(
                    secret_id,
                    tenant_id,
                    "get",
                    success=False,
                    error_message="Secret has expired",
                    user_id=user_id,
                )
                raise SecretExpiredError(f"Secret '{secret_id}' has expired")

        # Decrypt and cache
        try:
            decrypted_value = self._decrypt(data["encrypted_value"])
            self._set_cache(tenant_id, secret_id, decrypted_value)
            self._log_access(secret_id, tenant_id, "get", user_id=user_id)
            return decrypted_value
        except Exception as e:
            self._log_access(
                secret_id,
                tenant_id,
                "get",
                success=False,
                error_message=str(e),
                user_id=user_id,
            )
            raise

    async def set_secret(
        self,
        tenant_id: int,
        secret_id: str,
        value: str,
        description: str | None = None,
        expires_at: datetime | None = None,
        user_id: str | None = None,
    ) -> SecretMetadata:
        """
        Set a secret value.

        Args:
            tenant_id: Tenant ID for isolation
            secret_id: Secret identifier
            value: Secret value (will be encrypted)
            description: Optional description
            expires_at: Optional expiration time
            user_id: Optional user ID for audit log

        Returns:
            SecretMetadata for the stored secret
        """
        # Check if secret exists to determine version
        existing = await self._backend.get_secret(tenant_id, secret_id)
        version = 1
        created_at = datetime.now(timezone.utc)

        if existing and not existing.get("is_deleted"):
            version = existing.get("version", 0) + 1
            created_at_raw = existing.get("created_at")
            if isinstance(created_at_raw, str):
                created_at = datetime.fromisoformat(created_at_raw)

        # Encrypt value
        encrypted_value = self._encrypt(value)

        # Store
        data = {
            "encrypted_value": encrypted_value,
            "version": version,
            "created_at": (
                created_at.isoformat() if isinstance(created_at, datetime) else created_at
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "description": description,
            "is_deleted": False,
            "previous_versions": [],  # Could store previous versions here
        }

        await self._backend.set_secret(tenant_id, secret_id, data)

        # Clear cache
        cache_key = (tenant_id, secret_id)
        if cache_key in self._cache:
            del self._cache[cache_key]

        self._log_access(secret_id, tenant_id, "set", user_id=user_id)

        return SecretMetadata(
            secret_id=secret_id,
            tenant_id=tenant_id,
            name=secret_id,
            description=description,
            created_at=(
                created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc)
            ),
            updated_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            version=version,
        )

    async def rotate_secret(
        self,
        tenant_id: int,
        secret_id: str,
        new_value: str,
        user_id: str | None = None,
    ) -> SecretMetadata:
        """
        Rotate a secret (create new version).

        Args:
            tenant_id: Tenant ID
            secret_id: Secret to rotate
            new_value: New secret value
            user_id: Optional user ID for audit log

        Returns:
            SecretMetadata with new version
        """
        # Verify secret exists
        existing = await self._backend.get_secret(tenant_id, secret_id)
        if not existing or existing.get("is_deleted"):
            raise SecretNotFoundError(f"Secret '{secret_id}' not found")

        # Set new value (will increment version)
        result = await self.set_secret(
            tenant_id=tenant_id,
            secret_id=secret_id,
            value=new_value,
            description=existing.get("description"),
            user_id=user_id,
        )

        self._log_access(secret_id, tenant_id, "rotate", user_id=user_id)
        return result

    async def delete_secret(
        self,
        tenant_id: int,
        secret_id: str,
        soft: bool = True,
        user_id: str | None = None,
    ) -> None:
        """
        Delete a secret.

        Args:
            tenant_id: Tenant ID
            secret_id: Secret to delete
            soft: If True, soft delete; if False, hard delete
            user_id: Optional user ID for audit log
        """
        await self._backend.delete_secret(tenant_id, secret_id, soft=soft)

        # Clear cache
        cache_key = (tenant_id, secret_id)
        if cache_key in self._cache:
            del self._cache[cache_key]

        operation = "soft_delete" if soft else "hard_delete"
        self._log_access(secret_id, tenant_id, operation, user_id=user_id)

    async def list_secrets(
        self,
        tenant_id: int,
        include_deleted: bool = False,
    ) -> list[SecretMetadata]:
        """
        List all secrets for a tenant (metadata only, no values).

        Args:
            tenant_id: Tenant ID
            include_deleted: Whether to include soft-deleted secrets

        Returns:
            List of SecretMetadata
        """
        secrets_list = await self._backend.list_secrets(tenant_id)

        if not include_deleted:
            secrets_list = [s for s in secrets_list if not s.is_deleted]

        return secrets_list

    def get_access_logs(
        self,
        tenant_id: int | None = None,
        secret_id: str | None = None,
        since: datetime | None = None,
    ) -> list[SecretAccessLog]:
        """
        Get access logs (optionally filtered).

        Args:
            tenant_id: Filter by tenant
            secret_id: Filter by secret
            since: Filter by timestamp

        Returns:
            List of SecretAccessLog entries
        """
        logs = self._access_logs

        if tenant_id is not None:
            logs = [log for log in logs if log.tenant_id == tenant_id]

        if secret_id is not None:
            logs = [log for log in logs if log.secret_id == secret_id]

        if since is not None:
            logs = [log for log in logs if log.timestamp >= since]

        return logs


# Singleton instance for application-wide use
_secret_manager_instance: SecretManager | None = None


def get_secret_manager() -> SecretManager:
    """Get singleton SecretManager instance."""
    global _secret_manager_instance
    if _secret_manager_instance is None:
        _secret_manager_instance = SecretManager()
    return _secret_manager_instance
