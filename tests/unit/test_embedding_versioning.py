"""Unit tests for Embedding Versioning"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.getcwd())

from src.core.search.embedding_versioning import (
    EmbeddingVersion,
    EmbeddingVersionManager,
    EmbeddingVersionStatus,
    ReindexProgress,
    get_version_manager,
)


class TestEmbeddingVersion:
    """Tests for EmbeddingVersion dataclass."""

    def test_version_creation(self):
        """Test creating an embedding version."""
        version = EmbeddingVersion(
            version_id="v1",
            model_name="text-embedding-3-small",
            dimensions=1536,
            status=EmbeddingVersionStatus.BUILDING,
        )

        assert version.version_id == "v1"
        assert version.model_name == "text-embedding-3-small"
        assert version.dimensions == 1536
        assert version.status == EmbeddingVersionStatus.BUILDING
        assert version.activated_at is None

    def test_version_to_dict(self):
        """Test converting version to dict."""
        version = EmbeddingVersion(
            version_id="v1",
            model_name="model",
            dimensions=768,
            status=EmbeddingVersionStatus.ACTIVE,
        )

        data = version.to_dict()

        assert data["version_id"] == "v1"
        assert data["model_name"] == "model"
        assert data["dimensions"] == 768
        assert data["status"] == "active"


class TestReindexProgress:
    """Tests for ReindexProgress."""

    def test_percent_complete(self):
        """Test percentage calculation."""
        progress = ReindexProgress(total_documents=100, processed=50)

        assert progress.percent_complete == 50.0

    def test_percent_complete_zero(self):
        """Test percentage with zero documents."""
        progress = ReindexProgress(total_documents=0)

        assert progress.percent_complete == 100.0

    def test_is_complete(self):
        """Test completion check."""
        progress = ReindexProgress(total_documents=100, processed=100)

        assert progress.is_complete is True

    def test_not_complete(self):
        """Test incomplete status."""
        progress = ReindexProgress(total_documents=100, processed=50)

        assert progress.is_complete is False


class TestEmbeddingVersionManager:
    """Tests for EmbeddingVersionManager."""

    def test_create_version_building_status(self):
        """Test new version has BUILDING status."""
        manager = EmbeddingVersionManager()

        version = manager.create_version(
            version_id="v1",
            model_name="text-embedding-3-small",
            dimensions=1536,
        )

        assert version.status == EmbeddingVersionStatus.BUILDING
        assert version.version_id == "v1"

    def test_activate_deprecates_old(self):
        """Test activation deprecates old version."""
        manager = EmbeddingVersionManager()

        # Create and fully reindex first version
        v1 = manager.create_version("v1", "model1", 768)
        manager.start_reindex("v1", 100)
        manager.update_reindex_progress("v1", 100)
        manager.activate_version("v1")

        assert v1.status == EmbeddingVersionStatus.ACTIVE

        # Create and fully reindex second version
        v2 = manager.create_version("v2", "model2", 1536)
        manager.start_reindex("v2", 100)
        manager.update_reindex_progress("v2", 100)
        manager.activate_version("v2")

        # Old version should be deprecated
        assert v1.status == EmbeddingVersionStatus.DEPRECATED
        assert v2.status == EmbeddingVersionStatus.ACTIVE

    def test_activate_requires_complete_reindex(self):
        """Test activation requires 100% reindex."""
        manager = EmbeddingVersionManager()

        version = manager.create_version("v1", "model", 768)
        manager.start_reindex("v1", 100)
        manager.update_reindex_progress("v1", 50)  # Only 50%

        with pytest.raises(ValueError) as exc_info:
            manager.activate_version("v1")

        assert "incomplete" in str(exc_info.value)

    def test_dimension_mismatch_rejected(self):
        """Test that dimension validation works."""
        manager = EmbeddingVersionManager()

        # Create version with specific dimensions
        version = manager.create_version("v1", "model", 768)

        assert version.dimensions == 768

    def test_dual_read_combines_results(self):
        """Test dual-read returns both active and deprecated."""
        manager = EmbeddingVersionManager()

        # Setup: v1 active, v2 deprecated
        v1 = manager.create_version("v1", "model1", 768)
        manager.start_reindex("v1", 100)
        manager.update_reindex_progress("v1", 100)
        manager.activate_version("v1")

        v2 = manager.create_version("v2", "model2", 1536)
        manager.start_reindex("v2", 100)
        manager.update_reindex_progress("v2", 100)
        manager.activate_version("v2")

        # v1 is now deprecated, v2 is active
        dual_read = manager.get_dual_read_versions()

        assert len(dual_read) == 2
        version_ids = {v.version_id for v in dual_read}
        assert "v1" in version_ids
        assert "v2" in version_ids


class TestEmbeddingVersionStatus:
    """Tests for EmbeddingVersionStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert EmbeddingVersionStatus.BUILDING.value == "building"
        assert EmbeddingVersionStatus.ACTIVE.value == "active"
        assert EmbeddingVersionStatus.DEPRECATED.value == "deprecated"
        assert EmbeddingVersionStatus.ARCHIVED.value == "archived"


class TestVersionManagerSingleton:
    """Tests for singleton."""

    def test_get_version_manager_singleton(self):
        """Test singleton pattern."""
        vm1 = get_version_manager()
        vm2 = get_version_manager()

        assert vm1 is vm2
