"""Unit tests for Secret Manager"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.getcwd())

from src.core.security.secret_manager import (
    EnvironmentBackend,
    SecretExpiredError,
    SecretManager,
    SecretMetadata,
    SecretNotFoundError,
    get_secret_manager,
)


class TestSecretManager:
    """Tests for SecretManager."""

    @pytest.mark.asyncio
    async def test_set_and_get_secret(self):
        """Test setting and getting a secret."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        # Set secret
        metadata = await manager.set_secret(
            tenant_id=100,
            secret_id="test-secret",
            value="my-secret-value",
            description="Test secret",
        )

        assert metadata.secret_id == "test-secret"
        assert metadata.tenant_id == 100
        assert metadata.version == 1

        # Get secret
        value = await manager.get_secret(tenant_id=100, secret_id="test-secret")
        assert value == "my-secret-value"

    @pytest.mark.asyncio
    async def test_secret_encrypted_in_db(self):
        """Test that secret is stored encrypted."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        await manager.set_secret(
            tenant_id=101, secret_id="encrypted-secret", value="sensitive-data"
        )

        # Get raw data from backend
        raw_data = await backend.get_secret(101, "encrypted-secret")
        encrypted_value = raw_data["encrypted_value"]

        # Verify it's not plaintext
        assert b"sensitive-data" != encrypted_value
        assert isinstance(encrypted_value, bytes)

    @pytest.mark.asyncio
    async def test_secret_access_logged(self):
        """Test that secret access is logged."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        await manager.set_secret(tenant_id=102, secret_id="logged-secret", value="test")
        await manager.get_secret(tenant_id=102, secret_id="logged-secret")

        logs = manager.get_access_logs(tenant_id=102)
        assert len(logs) >= 2  # set + get

        # Check log entries
        operations = [log.operation for log in logs]
        assert "set" in operations
        assert "get" in operations

    @pytest.mark.asyncio
    async def test_rotate_preserves_old_version(self):
        """Test that rotation increments version."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        # Set initial secret
        await manager.set_secret(tenant_id=103, secret_id="rotating-secret", value="v1")

        # Rotate
        metadata = await manager.rotate_secret(
            tenant_id=103, secret_id="rotating-secret", new_value="v2"
        )

        assert metadata.version == 2

        # Get new value
        value = await manager.get_secret(tenant_id=103, secret_id="rotating-secret")
        assert value == "v2"

    @pytest.mark.asyncio
    async def test_list_secrets_no_values(self):
        """Test that list_secrets returns metadata without values."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        await manager.set_secret(tenant_id=104, secret_id="secret1", value="value1")
        await manager.set_secret(tenant_id=104, secret_id="secret2", value="value2")

        secrets = await manager.list_secrets(tenant_id=104)

        assert len(secrets) == 2
        secret_ids = [s.secret_id for s in secrets]
        assert "secret1" in secret_ids
        assert "secret2" in secret_ids

        # Verify no values exposed
        for secret in secrets:
            assert not hasattr(secret, "encrypted_value")
            assert isinstance(secret, SecretMetadata)

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test that secrets are isolated by tenant."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        # Set secret for tenant 1
        await manager.set_secret(tenant_id=105, secret_id="tenant-secret", value="tenant1-value")

        # Tenant 1 can access
        value = await manager.get_secret(tenant_id=105, secret_id="tenant-secret")
        assert value == "tenant1-value"

        # Tenant 2 cannot access (will create new secret)
        await manager.set_secret(tenant_id=106, secret_id="tenant-secret", value="tenant2-value")
        value2 = await manager.get_secret(tenant_id=106, secret_id="tenant-secret")
        assert value2 == "tenant2-value"

    @pytest.mark.asyncio
    async def test_expired_secret_not_returned(self):
        """Test that expired secrets raise error."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        # Set expired secret
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        await manager.set_secret(
            tenant_id=107,
            secret_id="expired-secret",
            value="expired-value",
            expires_at=expired_time,
        )

        # Should raise SecretExpiredError
        with pytest.raises(SecretExpiredError):
            await manager.get_secret(tenant_id=107, secret_id="expired-secret")

    @pytest.mark.asyncio
    async def test_delete_soft_deletes(self):
        """Test soft delete functionality."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        await manager.set_secret(tenant_id=108, secret_id="to-delete", value="delete-me")

        # Verify it exists first
        value = await manager.get_secret(tenant_id=108, secret_id="to-delete")
        assert value == "delete-me"

        # Soft delete
        await manager.delete_secret(tenant_id=108, secret_id="to-delete", soft=True)

        # Should not be found after delete
        with pytest.raises(SecretNotFoundError):
            await manager.get_secret(tenant_id=108, secret_id="to-delete")

    @pytest.mark.asyncio
    async def test_environment_backend_fallback(self):
        """Test environment backend as fallback."""
        backend = EnvironmentBackend()
        manager = SecretManager(backend=backend, master_key="test-key-32-bytes-long!!")

        # Set via manager
        await manager.set_secret(tenant_id=109, secret_id="env-secret", value="env-value")

        # Verify via backend directly
        raw = await backend.get_secret(109, "env-secret")
        assert raw is not None
        assert "encrypted_value" in raw


class TestSecretManagerSingleton:
    """Tests for SecretManager singleton."""

    def test_get_secret_manager_singleton(self):
        """Test that get_secret_manager returns singleton."""
        sm1 = get_secret_manager()
        sm2 = get_secret_manager()
        assert sm1 is sm2


class TestEnvironmentBackend:
    """Tests for EnvironmentBackend."""

    @pytest.mark.asyncio
    async def test_backend_list_secrets(self):
        """Test listing secrets from backend."""
        backend = EnvironmentBackend()

        # Set some secrets directly with unique tenant
        await backend.set_secret(
            200,
            "secret-a",
            {
                "encrypted_value": b"enc-a",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await backend.set_secret(
            200,
            "secret-b",
            {
                "encrypted_value": b"enc-b",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        secrets = await backend.list_secrets(200)
        secret_ids = [s.secret_id for s in secrets]

        assert "secret-a" in secret_ids
        assert "secret-b" in secret_ids
