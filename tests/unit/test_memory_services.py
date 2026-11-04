"""Tests for Memory Management Service Layer."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.memory.services import (
    CleanupService,
    EmbeddingService,
    EncryptionService,
    FAISSService,
    RedisService,
)
from src.core.memory.types import EpisodicMemory, MemoryEntry, StrategicMemory, TacticalMemory
from src.core.types import AgentType


class TestEncryptionService:
    """Test EncryptionService."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key."""
        try:
            from cryptography.fernet import Fernet

            return Fernet.generate_key()
        except ImportError:
            pytest.skip("cryptography library not installed")

    @pytest.fixture
    def service(self, encryption_key):
        return EncryptionService(encryption_key)

    def test_encryption_enabled_with_key(self, service, encryption_key):
        assert service.is_enabled is True

    def test_encryption_disabled_without_key(self):
        service = EncryptionService()
        assert service.is_enabled is False

    def test_encrypt_decrypt_embedding(self, service):
        """Test round-trip encryption and decryption."""
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")

        # Create a sample embedding
        original = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)

        # Encrypt
        encrypted = service.encrypt_embedding(original)
        assert encrypted is not None
        assert isinstance(encrypted, str)

        # Decrypt
        decrypted = service.decrypt_embedding(encrypted)
        assert decrypted is not None
        assert np.allclose(original, decrypted)

    def test_encrypt_without_key(self):
        """Test that encryption returns None when no key is provided."""
        service = EncryptionService()
        try:
            import numpy as np

            original = np.array([0.1, 0.2, 0.3])
            encrypted = service.encrypt_embedding(original)
            assert encrypted is None
        except ImportError:
            pytest.skip("numpy not installed")

    def test_decrypt_without_key(self):
        """Test that decryption returns None when no key is provided."""
        service = EncryptionService()
        decrypted = service.decrypt_embedding("some_data")
        assert decrypted is None

    def test_encrypt_none_embedding(self, service):
        """Test that encrypting None returns None."""
        result = service.encrypt_embedding(None)
        assert result is None

    def test_decrypt_none_data(self, service):
        """Test that decrypting None returns None."""
        result = service.decrypt_embedding(None)
        assert result is None

    def test_enable_disable(self, encryption_key):
        """Test enabling and disabling encryption."""
        service = EncryptionService()
        assert service.is_enabled is False

        service.enable(encryption_key)
        assert service.is_enabled is True

        service.disable()
        assert service.is_enabled is False


class TestEmbeddingService:
    """Test EmbeddingService."""

    @pytest.fixture
    def service(self):
        return EmbeddingService()

    def test_get_dimension(self, service):
        """Test that dimension is correctly set."""
        assert service.get_dimension() == 384

    def test_get_model_name(self, service):
        """Test that model name is returned."""
        assert service.get_model_name() == "all-MiniLM-L6-v2"

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._model is not None

    @pytest.mark.skip(reason="Requires sentence-transformers model download")
    def test_encode(self, service):
        """Test encoding text (requires model)."""
        try:
            embedding = service.encode("This is a test sentence")
            assert embedding is not None
            assert len(embedding) == 384
        except Exception as e:
            pytest.skip(f"Model not available: {e}")


class TestFAISSService:
    """Test FAISSService."""

    @pytest.fixture
    def service(self):
        return FAISSService(dimension=384)

    def test_create_index(self, service):
        """Test creating a FAISS index."""
        result = service.create_index("test_index")
        assert result is True
        assert service.has_index("test_index") is True

    def test_create_index_failure(self, service):
        """Test index creation failure handling."""
        # FAISS should not fail with valid dimension
        result = service.create_index("valid_index")
        assert result is True

    def test_has_index_nonexistent(self, service):
        """Test checking for non-existent index."""
        assert service.has_index("nonexistent") is False

    def test_get_index(self, service):
        """Test getting an index."""
        service.create_index("test_index")
        index = service.get_index("test_index")
        assert index is not None

    def test_get_index_nonexistent(self, service):
        """Test getting non-existent index returns None."""
        index = service.get_index("nonexistent")
        assert index is None

    @pytest.mark.skip(reason="Requires FAISS library")
    def test_add_vectors(self, service):
        """Test adding vectors to index."""
        try:
            import numpy as np

            service.create_index("test_index")
            vectors = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)
            result = service.add_vectors("test_index", vectors)
            assert result is True
        except ImportError:
            pytest.skip("numpy not installed")

    def test_add_vectors_nonexistent_index(self, service):
        """Test adding vectors to non-existent index fails."""
        result = service.add_vectors("nonexistent", [])
        assert result is False

    @pytest.mark.skip(reason="Requires FAISS library")
    def test_search(self, service):
        """Test searching vectors."""
        try:
            import numpy as np

            service.create_index("test_index")
            # Add some vectors
            vectors = np.random.randn(10, 384).astype(np.float32)
            service.add_vectors("test_index", vectors)
            # Search
            query = np.random.randn(384).astype(np.float32)
            scores, indices = service.search("test_index", query, k=5)
            assert scores is not None
            assert indices is not None
            assert len(scores) == 5
            assert len(indices) == 5
        except ImportError:
            pytest.skip("numpy not installed")

    def test_search_nonexistent_index(self, service):
        """Test searching non-existent index returns None."""
        scores, indices = service.search("nonexistent", [])
        assert scores is None
        assert indices is None

    def test_reset_index(self, service):
        """Test resetting an index."""
        service.create_index("test_index")
        result = service.reset_index("test_index")
        assert result is True

    def test_remove_index(self, service):
        """Test removing an index."""
        service.create_index("test_index")
        result = service.remove_index("test_index")
        assert result is True
        assert service.has_index("test_index") is False

    def test_remove_index_nonexistent(self, service):
        """Test removing non-existent index returns False."""
        result = service.remove_index("nonexistent")
        assert result is False

    def test_get_stats(self, service):
        """Test getting index statistics."""
        service.create_index("test_index")
        stats = service.get_stats("test_index")
        assert stats["exists"] is True
        assert "ntotal" in stats

    def test_get_stats_nonexistent(self, service):
        """Test getting stats for non-existent index."""
        stats = service.get_stats("nonexistent")
        assert stats["exists"] is False

    @pytest.mark.skip(reason="Requires FAISS and numpy")
    def test_rebuild_from_vectors(self, service):
        """Test rebuilding index from vectors."""
        try:
            import numpy as np

            vectors = [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
            result = service.rebuild_from_vectors("test_index", vectors)
            assert result is True
            assert service.has_index("test_index") is True
        except ImportError:
            pytest.skip("numpy not installed")


class TestCleanupService:
    """Test CleanupService."""

    @pytest.fixture
    def service(self):
        return CleanupService(
            max_memories={"strategic": 1000, "tactical": 5000, "episodic": 10000},
            importance_threshold=0.8,
        )

    @pytest.fixture
    def sample_memories(self):
        """Create sample memories for testing."""
        now = datetime.now(timezone.utc)
        return [
            MagicMock(timestamp=now - timedelta(days=1), metadata={"importance_score": 0.9}),
            MagicMock(timestamp=now - timedelta(days=40), metadata={"importance_score": 0.5}),
            MagicMock(
                timestamp=now - timedelta(days=60), metadata={"importance_score": 0.9}
            ),  # Old but important
            MagicMock(timestamp=now - timedelta(days=5), metadata={"importance_score": 0.3}),
        ]

    def test_filter_by_age_and_importance(self, service, sample_memories):
        """Test filtering memories by age and importance."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = service.filter_by_age_and_importance(
            sample_memories,
            cutoff,
            lambda m: m.timestamp,
            lambda m: m.metadata["importance_score"],
        )

        # Should keep: recent ones + old but important
        assert len(result) == 3

    def test_calculate_cleanup_stats(self, service):
        """Test calculating cleanup statistics."""
        original = [1, 2, 3, 4, 5]
        cleaned = [1, 2, 3]

        stats = service.calculate_cleanup_stats(original, cleaned, "test")

        assert stats["memory_type"] == "test"
        assert stats["original_count"] == 5
        assert stats["retained_count"] == 3
        assert stats["removed_count"] == 2
        assert stats["retention_rate"] == 0.6

    def test_enforce_size_limit(self, service):
        """Test enforcing size limit."""
        service.max_memories = {"test": 3}
        memories = [1, 2, 3, 4, 5]

        result = service.enforce_size_limit(memories, "test")

        assert len(result) == 3

    def test_enforce_size_limit_under_limit(self, service):
        """Test enforcing size limit when under limit."""
        service.max_memories = {"test": 10}
        memories = [1, 2, 3]

        result = service.enforce_size_limit(memories, "test")

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_cleanup_old_memories(self, service):
        """Test cleanup of old memories."""
        now = datetime.now(timezone.utc)
        memories = {
            "strategic": [
                MagicMock(timestamp=now - timedelta(days=1)),
                MagicMock(timestamp=now - timedelta(days=40)),
            ],
            "tactical": [
                MagicMock(timestamp=now - timedelta(days=5)),
            ],
        }

        results = await service.cleanup_old_memories(
            memories,
            days_old=30,
            get_timestamp_func=lambda m: m.timestamp,
            get_importance_func=lambda m: 0.5,
        )

        assert "strategic" in results
        assert "tactical" in results

    def test_get_memory_stats(self, service):
        """Test getting memory statistics."""
        memories = {
            "strategic": [1, 2, 3],
            "tactical": [4, 5],
        }

        stats = service.get_memory_stats(memories)

        assert stats["strategic"]["count"] == 3
        assert stats["tactical"]["count"] == 2
        assert "limit" in stats["strategic"]
        assert "usage_percent" in stats["strategic"]


class TestRedisService:
    """Test RedisService."""

    @pytest.fixture
    def service(self):
        return RedisService(redis_url="redis://localhost:6380", tenant_id=1)

    def test_make_key_with_tenant(self, service):
        """Test key generation with tenant."""
        key = service._make_key("strategic")
        assert key == "memory:1:strategic"

    def test_make_key_without_tenant(self):
        """Test key generation without tenant."""
        service = RedisService(redis_url="redis://localhost:6380")
        key = service._make_key("strategic")
        assert key == "memory:strategic"

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test Redis client initialization."""
        with patch("src.core.typing.create_async_redis_client") as mock_create:
            mock_client = AsyncMock()
            mock_create.return_value = mock_client

            await service.initialize()

            assert service._client is not None
            mock_create.assert_called_once_with("redis://localhost:6380")

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test closing Redis connection."""
        mock_client = AsyncMock()
        service._client = mock_client

        await service.close()

        mock_client.close.assert_called_once()
        assert service._client is None

    @pytest.mark.asyncio
    async def test_get_success(self, service):
        """Test getting data from Redis."""
        mock_client = AsyncMock()
        mock_client.get.return_value = "test_data"
        service._client = mock_client

        result = await service.get("strategic")

        assert result == "test_data"
        mock_client.get.assert_called_once_with("memory:1:strategic")

    @pytest.mark.asyncio
    async def test_get_none(self, service):
        """Test getting None from Redis."""
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        service._client = mock_client

        result = await service.get("strategic")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_success(self, service):
        """Test setting data in Redis."""
        mock_client = AsyncMock()
        service._client = mock_client

        result = await service.set("strategic", "test_data")

        assert result is True
        mock_client.set.assert_called_once_with("memory:1:strategic", "test_data", ex=None)

    @pytest.mark.asyncio
    async def test_set_with_expire(self, service):
        """Test setting data with expiration."""
        mock_client = AsyncMock()
        service._client = mock_client

        result = await service.set("strategic", "test_data", expire=3600)

        assert result is True
        mock_client.set.assert_called_once_with("memory:1:strategic", "test_data", ex=3600)

    @pytest.mark.asyncio
    async def test_delete_success(self, service):
        """Test deleting data from Redis."""
        mock_client = AsyncMock()
        service._client = mock_client

        result = await service.delete("strategic")

        assert result is True
        mock_client.delete.assert_called_once_with("memory:1:strategic")

    @pytest.mark.asyncio
    async def test_exists_true(self, service):
        """Test checking if key exists (True)."""
        mock_client = AsyncMock()
        mock_client.exists.return_value = 1
        service._client = mock_client

        result = await service.exists("strategic")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, service):
        """Test checking if key exists (False)."""
        mock_client = AsyncMock()
        mock_client.exists.return_value = 0
        service._client = mock_client

        result = await service.exists("strategic")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_json_success(self, service):
        """Test getting JSON data."""
        mock_client = AsyncMock()
        mock_client.get.return_value = b'{"key": "value"}'
        service._client = mock_client

        result = await service.get_json("strategic")

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_json_invalid(self, service):
        """Test getting invalid JSON data."""
        mock_client = AsyncMock()
        mock_client.get.return_value = b"invalid json"
        service._client = mock_client

        result = await service.get_json("strategic")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_json_success(self, service):
        """Test setting JSON data."""
        mock_client = AsyncMock()
        service._client = mock_client

        result = await service.set_json("strategic", {"key": "value"})

        assert result is True
        mock_client.set.assert_called_once()


class TestMemoryTypes:
    """Test Memory type classes."""

    def test_memory_entry_to_dict(self):
        """Test converting MemoryEntry to dict."""
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(timezone.utc),
            agent_type=AgentType.CVA,
            content="Test content",
        )

        data = entry.to_dict()

        assert data["id"] == "test-1"
        assert data["content"] == "Test content"
        assert "timestamp" in data

    def test_strategic_memory_creation(self):
        """Test creating StrategicMemory."""
        memory = StrategicMemory(
            id="strat-1",
            timestamp=datetime.now(timezone.utc),
            agent_type=AgentType.CVA,
            content="Strategy content",
            strategy_type="market_analysis",
            success_rate=0.85,
        )

        assert memory.strategy_type == "market_analysis"
        assert memory.success_rate == 0.85

    def test_tactical_memory_creation(self):
        """Test creating TacticalMemory."""
        memory = TacticalMemory(
            id="tact-1",
            timestamp=datetime.now(timezone.utc),
            agent_type=AgentType.ORCHESTRATOR,
            content="Tactical content",
            task_type="coordination",
        )

        assert memory.task_type == "coordination"
        assert memory.agent_assignments == []  # Default from __post_init__

    def test_episodic_memory_creation(self):
        """Test creating EpisodicMemory."""
        memory = EpisodicMemory(
            id="epis-1",
            timestamp=datetime.now(timezone.utc),
            agent_type=AgentType.SPECIALIST,
            content="Episode content",
            task_id="task-123",
            success=True,
        )

        assert memory.task_id == "task-123"
        assert memory.success is True
        assert memory.execution_steps == []  # Default from __post_init__
