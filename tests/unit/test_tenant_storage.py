"""Unit tests for Tenant Storage"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.getcwd())

from src.core.storage.tenant_storage import (
    LocalTenantStorage,
    PathTraversalError,
    S3TenantStorage,
    StorageObject,
    get_storage,
    reset_storage,
)


class TestLocalTenantStorage:
    """Tests for LocalTenantStorage."""

    @pytest.fixture
    def storage(self):
        """Create temporary storage for tests."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalTenantStorage(temp_dir)
        yield storage
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, storage):
        """Test storing and retrieving data."""
        # Store
        data = b"Hello, World!"
        obj = await storage.store(
            tenant_id=1, path="test/file.txt", data=data, content_type="text/plain"
        )

        assert obj.path == "test/file.txt"
        assert obj.tenant_id == 1
        assert obj.size == len(data)
        assert obj.content_type == "text/plain"

        # Retrieve
        retrieved = await storage.retrieve(tenant_id=1, path="test/file.txt")
        assert retrieved == data

    @pytest.mark.asyncio
    async def test_list_files_tenant_scoped(self, storage):
        """Test listing files is scoped to tenant."""
        # Create files for tenant 1
        await storage.store(tenant_id=1, path="file1.txt", data=b"data1")
        await storage.store(tenant_id=1, path="dir/file2.txt", data=b"data2")

        # Create file for tenant 2
        await storage.store(tenant_id=2, path="file3.txt", data=b"data3")

        # List tenant 1
        files = await storage.list(tenant_id=1)
        paths = [f.path.replace("\\", "/") for f in files]  # Normalize Windows paths

        assert "file1.txt" in paths
        assert "dir/file2.txt" in paths
        assert "file3.txt" not in paths  # Belongs to tenant 2

    @pytest.mark.asyncio
    async def test_delete_own_file(self, storage):
        """Test tenant can delete their own file."""
        await storage.store(tenant_id=1, path="to-delete.txt", data=b"delete me")

        # Verify exists
        assert await storage.exists(tenant_id=1, path="to-delete.txt")

        # Delete
        await storage.delete(tenant_id=1, path="to-delete.txt")

        # Verify deleted
        assert not await storage.exists(tenant_id=1, path="to-delete.txt")

    @pytest.mark.asyncio
    async def test_exists_check(self, storage):
        """Test exists check."""
        # Non-existent
        assert not await storage.exists(tenant_id=1, path="nonexistent.txt")

        # Create
        await storage.store(tenant_id=1, path="exists.txt", data=b"data")

        # Exists
        assert await storage.exists(tenant_id=1, path="exists.txt")

    @pytest.mark.asyncio
    async def test_cross_tenant_read_blocked(self, storage):
        """Test cross-tenant read is blocked by path isolation."""
        # Store for tenant 1
        await storage.store(tenant_id=1, path="secret.txt", data=b"secret")

        # Tenant 2 tries to read - should not find it
        # (Each tenant has separate directory)
        with pytest.raises(Exception):
            await storage.retrieve(tenant_id=2, path="secret.txt")

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, storage):
        """Test path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            await storage.store(tenant_id=1, path="../../../etc/passwd", data=b"hacked")

    @pytest.mark.asyncio
    async def test_null_bytes_blocked(self, storage):
        """Test null bytes in path are blocked."""
        with pytest.raises(PathTraversalError):
            await storage.store(tenant_id=1, path="file\x00.txt", data=b"data")

    @pytest.mark.asyncio
    async def test_cross_tenant_delete_blocked(self, storage):
        """Test tenant cannot delete other tenant's files."""
        # Store for tenant 1
        await storage.store(tenant_id=1, path="important.txt", data=b"important")

        # Tenant 2 tries to delete - should not affect tenant 1
        with pytest.raises(Exception):
            await storage.delete(tenant_id=2, path="important.txt")

        # Verify tenant 1's file still exists
        assert await storage.exists(tenant_id=1, path="important.txt")


class TestPathValidation:
    """Tests for path validation."""

    def test_empty_path_blocked(self):
        """Test empty path is blocked."""
        storage = LocalTenantStorage("/tmp/test")

        with pytest.raises(PathTraversalError):
            storage._validate_path("")

    def test_absolute_path_blocked(self):
        """Test absolute paths are blocked."""
        storage = LocalTenantStorage("/tmp/test")

        with pytest.raises(PathTraversalError):
            storage._validate_path("/etc/passwd")

        with pytest.raises(PathTraversalError):
            storage._validate_path("C:/Windows/system32")

    def test_parent_directory_blocked(self):
        """Test parent directory references are blocked."""
        storage = LocalTenantStorage("/tmp/test")

        with pytest.raises(PathTraversalError):
            storage._validate_path("../secret.txt")

        with pytest.raises(PathTraversalError):
            storage._validate_path("dir/../../secret.txt")

    def test_valid_paths_allowed(self):
        """Test valid paths are allowed."""
        storage = LocalTenantStorage("/tmp/test")

        # These should not raise
        storage._validate_path("file.txt")
        storage._validate_path("dir/file.txt")
        storage._validate_path("a/b/c/d/file.txt")
        storage._validate_path("file-with-dashes.txt")
        storage._validate_path("file_with_underscores.txt")


class TestS3TenantStorage:
    """Tests for S3TenantStorage stub."""

    def test_s3_key_generation(self):
        """Test S3 key includes tenant prefix."""
        storage = S3TenantStorage(bucket="test-bucket", prefix="tenants")

        key = storage._get_key(tenant_id=42, path="documents/file.pdf")

        assert key == "tenants/42/documents/file.pdf"
        assert "42" in key  # Tenant ID in path
        assert "documents/file.pdf" in key

    @pytest.mark.asyncio
    async def test_s3_store_returns_object(self):
        """Test S3 store returns StorageObject."""
        storage = S3TenantStorage(bucket="test-bucket")

        obj = await storage.store(
            tenant_id=1, path="test.txt", data=b"test data", content_type="text/plain"
        )

        assert isinstance(obj, StorageObject)
        assert obj.tenant_id == 1
        assert obj.path == "test.txt"


class TestStorageSingleton:
    """Tests for storage singleton."""

    def test_get_storage_singleton(self):
        """Test that get_storage returns singleton."""
        reset_storage()

        storage1 = get_storage(backend="local", base_path="/tmp/test1")
        storage2 = get_storage(backend="local", base_path="/tmp/test2")

        # Should return same instance
        assert storage1 is storage2

        reset_storage()

    def test_reset_storage(self):
        """Test reset_storage clears singleton."""
        reset_storage()

        storage1 = get_storage(backend="local", base_path="/tmp/test1")
        reset_storage()
        storage2 = get_storage(backend="local", base_path="/tmp/test1")

        # After reset, should be different instance
        assert storage1 is not storage2

        reset_storage()


class TestStorageObject:
    """Tests for StorageObject dataclass."""

    def test_storage_object_creation(self):
        """Test StorageObject creation."""
        from datetime import datetime, timezone

        obj = StorageObject(
            path="test/file.txt",
            tenant_id=1,
            size=1024,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            content_type="text/plain",
        )

        assert obj.path == "test/file.txt"
        assert obj.tenant_id == 1
        assert obj.size == 1024
        assert obj.content_type == "text/plain"
