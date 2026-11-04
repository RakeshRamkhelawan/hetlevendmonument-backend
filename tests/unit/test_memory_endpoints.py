"""
Tests for Memory API Endpoints
==============================

Comprehensive test suite for /api/v1/memory/* endpoints.
Target: 100% code coverage
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Import the module under test
from src.core.api.memory_endpoints import (  # Enums; Models; Storage functions; Helper functions; Endpoints; Router; Storage (for cleanup)
    ChunkingConfig,
    ChunkingStrategy,
    DeleteIndexResponse,
    DocumentStatus,
    EmbeddingModel,
    IndexDocumentRequest,
    IndexDocumentResponse,
    IndexedDocument,
    IndexResponse,
    IndexStats,
    IndexStatus,
    RAGConfig,
    RAGConfigResponse,
    RetrievalConfig,
    _tenant_configs,
    _tenant_indexes,
    calculate_index_stats,
    delete_from_index,
    get_config,
    get_index,
    get_tenant,
    get_tenant_config,
    get_tenant_index,
    get_user_id,
    index_document,
    router,
    save_tenant_config,
    simulate_document_indexing,
    update_config,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_storage():
    """Clean up storage before and after each test"""
    _tenant_configs.clear()
    _tenant_indexes.clear()
    yield
    _tenant_configs.clear()
    _tenant_indexes.clear()


# ============================================================================
# Test Enums
# ============================================================================


class TestEnums:
    """Test all enum definitions"""

    def test_embedding_model_values(self):
        """Test EmbeddingModel enum has all expected values"""
        assert EmbeddingModel.OPENAI_ADA_002 == "text-embedding-ada-002"
        assert EmbeddingModel.OPENAI_3_SMALL == "text-embedding-3-small"
        assert EmbeddingModel.OPENAI_3_LARGE == "text-embedding-3-large"
        assert EmbeddingModel.COHERE_ENGLISH == "embed-english-v3.0"
        assert EmbeddingModel.COHERE_MULTILINGUAL == "embed-multilingual-v3.0"
        assert (
            EmbeddingModel.LOCAL_SENTENCE_TRANSFORMERS == "sentence-transformers/all-MiniLM-L6-v2"
        )

    def test_chunking_strategy_values(self):
        """Test ChunkingStrategy enum has all expected values"""
        assert ChunkingStrategy.FIXED_SIZE == "fixed_size"
        assert ChunkingStrategy.SEMANTIC == "semantic"
        assert ChunkingStrategy.SENTENCE == "sentence"
        assert ChunkingStrategy.PARAGRAPH == "paragraph"
        assert ChunkingStrategy.RECURSIVE == "recursive"

    def test_index_status_values(self):
        """Test IndexStatus enum has all expected values"""
        assert IndexStatus.HEALTHY == "healthy"
        assert IndexStatus.DEGRADED == "degraded"
        assert IndexStatus.BUILDING == "building"
        assert IndexStatus.FAILED == "failed"
        assert IndexStatus.EMPTY == "empty"

    def test_document_status_values(self):
        """Test DocumentStatus enum has all expected values"""
        assert DocumentStatus.PENDING == "pending"
        assert DocumentStatus.INDEXING == "indexing"
        assert DocumentStatus.INDEXED == "indexed"
        assert DocumentStatus.FAILED == "failed"
        assert DocumentStatus.DELETED == "deleted"


# ============================================================================
# Test Pydantic Models
# ============================================================================


class TestPydanticModels:
    """Test Pydantic model creation and validation"""

    def test_chunking_config_defaults(self):
        """Test ChunkingConfig default values"""
        config = ChunkingConfig()
        assert config.strategy == ChunkingStrategy.RECURSIVE
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.min_chunk_size == 100

    def test_chunking_config_custom(self):
        """Test ChunkingConfig with custom values"""
        config = ChunkingConfig(
            strategy=ChunkingStrategy.SEMANTIC,
            chunk_size=1024,
            chunk_overlap=100,
            min_chunk_size=200,
        )
        assert config.strategy == ChunkingStrategy.SEMANTIC
        assert config.chunk_size == 1024

    def test_retrieval_config_defaults(self):
        """Test RetrievalConfig default values"""
        config = RetrievalConfig()
        assert config.top_k == 5
        assert config.similarity_threshold == 0.7
        assert config.rerank_enabled is False
        assert config.hybrid_search is False
        assert config.mmr_enabled is False
        assert config.mmr_lambda == 0.5

    def test_retrieval_config_custom(self):
        """Test RetrievalConfig with custom values"""
        config = RetrievalConfig(
            top_k=10,
            similarity_threshold=0.8,
            rerank_enabled=True,
            hybrid_search=True,
            mmr_enabled=True,
            mmr_lambda=0.7,
        )
        assert config.top_k == 10
        assert config.rerank_enabled is True

    def test_rag_config_defaults(self):
        """Test RAGConfig default values"""
        config = RAGConfig()
        assert config.embedding_model == EmbeddingModel.OPENAI_3_SMALL
        assert config.embedding_dimensions == 1536
        assert config.index_name == "default"
        assert config.namespace is None
        assert config.metadata_fields == []

    def test_rag_config_with_nested_configs(self):
        """Test RAGConfig with nested configurations"""
        config = RAGConfig(
            embedding_model=EmbeddingModel.OPENAI_3_LARGE,
            chunking=ChunkingConfig(strategy=ChunkingStrategy.SEMANTIC),
            retrieval=RetrievalConfig(top_k=10),
        )
        assert config.embedding_model == EmbeddingModel.OPENAI_3_LARGE
        assert config.chunking.strategy == ChunkingStrategy.SEMANTIC
        assert config.retrieval.top_k == 10

    def test_rag_config_response_creation(self):
        """Test RAGConfigResponse model creation"""
        config = RAGConfig()
        response = RAGConfigResponse(config=config, tenant_id=1, message="Success")
        assert response.tenant_id == 1
        assert response.message == "Success"

    def test_indexed_document_creation(self):
        """Test IndexedDocument model creation"""
        doc = IndexedDocument(
            id="doc_123", source="/path/to/file.txt", status=DocumentStatus.INDEXED
        )
        assert doc.id == "doc_123"
        assert doc.chunk_count == 0
        assert doc.token_count == 0

    def test_indexed_document_with_all_fields(self):
        """Test IndexedDocument with all fields"""
        doc = IndexedDocument(
            id="doc_456",
            source="/path/to/file.txt",
            title="Test Document",
            status=DocumentStatus.INDEXED,
            chunk_count=10,
            token_count=5000,
            indexed_at="2025-12-17T10:00:00Z",
            metadata={"key": "value"},
        )
        assert doc.title == "Test Document"
        assert doc.chunk_count == 10
        assert doc.metadata == {"key": "value"}

    def test_index_stats_defaults(self):
        """Test IndexStats default values"""
        stats = IndexStats()
        assert stats.total_documents == 0
        assert stats.total_chunks == 0
        assert stats.status == IndexStatus.EMPTY

    def test_index_response_creation(self):
        """Test IndexResponse model creation"""
        stats = IndexStats()
        response = IndexResponse(stats=stats, documents=[], tenant_id=1, message="Success")
        assert response.tenant_id == 1

    def test_index_document_request_creation(self):
        """Test IndexDocumentRequest model creation"""
        request = IndexDocumentRequest(source="/path/to/file.txt")
        assert request.source == "/path/to/file.txt"
        assert request.force_reindex is False

    def test_index_document_request_with_content(self):
        """Test IndexDocumentRequest with content"""
        request = IndexDocumentRequest(
            source="custom",
            title="Test",
            content="This is test content",
            metadata={"type": "test"},
        )
        assert request.content == "This is test content"
        assert request.metadata == {"type": "test"}

    def test_index_document_response_creation(self):
        """Test IndexDocumentResponse model creation"""
        doc = IndexedDocument(id="doc_123", source="/test", status=DocumentStatus.INDEXED)
        response = IndexDocumentResponse(document=doc, message="Success", success=True)
        assert response.success is True

    def test_delete_index_response_creation(self):
        """Test DeleteIndexResponse model creation"""
        response = DeleteIndexResponse(
            deleted_documents=5, deleted_chunks=100, message="Deleted", success=True
        )
        assert response.deleted_documents == 5
        assert response.deleted_chunks == 100


# ============================================================================
# Test Storage Functions
# ============================================================================


class TestStorageFunctions:
    """Test in-memory storage functions"""

    def test_get_tenant_config_creates_default(self):
        """Test get_tenant_config creates default config"""
        config = get_tenant_config(1)
        assert config is not None
        assert config.embedding_model == EmbeddingModel.OPENAI_3_SMALL

    def test_get_tenant_config_returns_existing(self):
        """Test get_tenant_config returns existing config"""
        custom_config = RAGConfig(embedding_model=EmbeddingModel.OPENAI_3_LARGE)
        _tenant_configs[1] = custom_config

        config = get_tenant_config(1)
        assert config.embedding_model == EmbeddingModel.OPENAI_3_LARGE

    def test_save_tenant_config(self):
        """Test save_tenant_config saves configuration"""
        config = RAGConfig(embedding_model=EmbeddingModel.COHERE_ENGLISH)
        save_tenant_config(1, config)

        assert 1 in _tenant_configs
        assert _tenant_configs[1].embedding_model == EmbeddingModel.COHERE_ENGLISH

    def test_get_tenant_index_creates_empty(self):
        """Test get_tenant_index creates empty index"""
        index = get_tenant_index(1)
        assert index == {}

    def test_get_tenant_index_returns_existing(self):
        """Test get_tenant_index returns existing index"""
        doc = IndexedDocument(id="doc_1", source="/test", status=DocumentStatus.INDEXED)
        _tenant_indexes[1] = {"doc_1": doc}

        index = get_tenant_index(1)
        assert "doc_1" in index


# ============================================================================
# Test Helper Functions
# ============================================================================


class TestHelperFunctions:
    """Test helper functions"""

    @pytest.mark.asyncio
    async def test_get_tenant_success(self):
        """Test get_tenant returns tenant ID when available"""
        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            tenant_id = await get_tenant()
            assert tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_tenant_missing(self):
        """Test get_tenant raises exception when tenant missing"""
        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant()
            assert exc_info.value.status_code == 400
            assert "Tenant context required" in str(exc_info.value.detail)

    def test_get_user_id_from_dict_user_id(self):
        """Test get_user_id extracts user_id from dict"""
        user = {"user_id": "user_123"}
        assert get_user_id(user) == "user_123"

    def test_get_user_id_from_dict_id(self):
        """Test get_user_id extracts id from dict"""
        user = {"id": "user_456"}
        assert get_user_id(user) == "user_456"

    def test_get_user_id_from_object(self):
        """Test get_user_id extracts id from object"""
        user = MagicMock()
        user.id = "user_789"
        assert get_user_id(user) == "user_789"

    def test_get_user_id_unknown(self):
        """Test get_user_id returns unknown when no id"""
        user = {}
        assert get_user_id(user) == "unknown"

    def test_get_user_id_no_id_attribute(self):
        """Test get_user_id handles object without id attribute"""
        user = MagicMock(spec=[])
        assert get_user_id(user) == "unknown"


# ============================================================================
# Test Calculate Index Stats
# ============================================================================


class TestCalculateIndexStats:
    """Test index statistics calculation"""

    def test_empty_index(self):
        """Test stats for empty index"""
        config = RAGConfig()
        stats = calculate_index_stats({}, config)
        assert stats.status == IndexStatus.EMPTY
        assert stats.total_documents == 0

    def test_healthy_index(self):
        """Test stats for healthy index"""
        config = RAGConfig()
        docs = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
                indexed_at="2025-12-17T10:00:00Z",
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.INDEXED,
                chunk_count=3,
                token_count=1500,
                indexed_at="2025-12-17T11:00:00Z",
            ),
        }
        stats = calculate_index_stats(docs, config)
        assert stats.status == IndexStatus.HEALTHY
        assert stats.total_documents == 2
        assert stats.total_chunks == 8
        assert stats.total_tokens == 4000
        assert stats.last_updated == "2025-12-17T11:00:00Z"

    def test_building_index(self):
        """Test stats for building index"""
        config = RAGConfig()
        docs = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.PENDING,
                chunk_count=0,
                token_count=0,
            ),
        }
        stats = calculate_index_stats(docs, config)
        assert stats.status == IndexStatus.BUILDING

    def test_degraded_index_with_failures(self):
        """Test stats for degraded index with failures"""
        config = RAGConfig()
        docs = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.FAILED,
                chunk_count=0,
                token_count=0,
            ),
        }
        stats = calculate_index_stats(docs, config)
        assert stats.status == IndexStatus.DEGRADED

    def test_index_size_calculation(self):
        """Test index size estimation"""
        config = RAGConfig(embedding_dimensions=1536)
        docs = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=10,
                token_count=5000,
            )
        }
        stats = calculate_index_stats(docs, config)
        # 10 chunks * 1536 dims * 4 bytes = 61440
        assert stats.index_size_bytes == 61440

    def test_indexing_status_counted_as_pending(self):
        """Test indexing status is treated as pending"""
        config = RAGConfig()
        docs = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXING,
                chunk_count=0,
                token_count=0,
            )
        }
        stats = calculate_index_stats(docs, config)
        assert stats.status == IndexStatus.BUILDING


# ============================================================================
# Test Simulate Document Indexing
# ============================================================================


class TestSimulateDocumentIndexing:
    """Test document indexing simulation"""

    def test_basic_indexing(self):
        """Test basic document indexing"""
        request = IndexDocumentRequest(source="/path/to/document.txt")
        doc = simulate_document_indexing(request)

        assert doc.id.startswith("doc_")
        assert doc.source == "/path/to/document.txt"
        assert doc.status == DocumentStatus.INDEXED
        assert doc.indexed_at is not None

    def test_indexing_with_content(self):
        """Test indexing with content"""
        content = " ".join(["word"] * 1000)  # 1000 words
        request = IndexDocumentRequest(source="custom", content=content)
        doc = simulate_document_indexing(request)

        assert doc.token_count == 1000
        assert doc.chunk_count == max(1, 1000 // 512)

    def test_indexing_with_title(self):
        """Test indexing with custom title"""
        request = IndexDocumentRequest(source="/path/to/file.txt", title="Custom Title")
        doc = simulate_document_indexing(request)
        assert doc.title == "Custom Title"

    def test_indexing_generates_title_from_source(self):
        """Test indexing generates title from source"""
        request = IndexDocumentRequest(source="/path/to/myfile.pdf")
        doc = simulate_document_indexing(request)
        assert doc.title == "myfile.pdf"

    def test_indexing_preserves_metadata(self):
        """Test indexing preserves metadata"""
        request = IndexDocumentRequest(
            source="/test", metadata={"author": "John", "date": "2025-12-17"}
        )
        doc = simulate_document_indexing(request)
        assert doc.metadata == {"author": "John", "date": "2025-12-17"}


# ============================================================================
# Test Config Endpoints
# ============================================================================


class TestConfigEndpoints:
    """Test config endpoints"""

    @pytest.mark.asyncio
    async def test_get_config_default(self):
        """Test getting default configuration"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_config(db=mock_db, tenant_id=1, current_user=mock_user)

        assert isinstance(response, RAGConfigResponse)
        assert response.tenant_id == 1
        assert response.config.embedding_model == EmbeddingModel.OPENAI_3_SMALL

    @pytest.mark.asyncio
    async def test_get_config_existing(self):
        """Test getting existing configuration"""
        # Pre-configure
        custom_config = RAGConfig(embedding_model=EmbeddingModel.COHERE_ENGLISH)
        _tenant_configs[1] = custom_config

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_config(db=mock_db, tenant_id=1, current_user=mock_user)

        assert response.config.embedding_model == EmbeddingModel.COHERE_ENGLISH

    @pytest.mark.asyncio
    async def test_update_config(self):
        """Test updating configuration"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        new_config = RAGConfig(
            embedding_model=EmbeddingModel.OPENAI_3_LARGE,
            chunking=ChunkingConfig(chunk_size=1024),
        )

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await update_config(
                config_update=new_config,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.config.embedding_model == EmbeddingModel.OPENAI_3_LARGE
        assert response.config.chunking.chunk_size == 1024
        assert response.config.updated_by == "test_user"
        assert response.config.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_config_model_change_warning(self):
        """Test updating config with model change shows warning"""
        # Pre-configure with different model
        _tenant_configs[1] = RAGConfig(embedding_model=EmbeddingModel.OPENAI_ADA_002)

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        new_config = RAGConfig(embedding_model=EmbeddingModel.OPENAI_3_LARGE)

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await update_config(
                config_update=new_config,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert "re-indexing" in response.message


# ============================================================================
# Test Index Endpoints
# ============================================================================


class TestIndexEndpoints:
    """Test index endpoints"""

    @pytest.mark.asyncio
    async def test_get_index_empty(self):
        """Test getting empty index"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_index(
                status_filter=None,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.stats.status == IndexStatus.EMPTY
        assert response.documents == []

    @pytest.mark.asyncio
    async def test_get_index_with_documents(self):
        """Test getting index with documents"""
        # Pre-populate index
        doc = IndexedDocument(
            id="doc_1",
            source="/test",
            status=DocumentStatus.INDEXED,
            chunk_count=5,
            token_count=2500,
        )
        _tenant_indexes[1] = {"doc_1": doc}

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_index(
                status_filter=None,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.stats.total_documents == 1
        assert len(response.documents) == 1

    @pytest.mark.asyncio
    async def test_get_index_with_status_filter(self):
        """Test getting index with status filter"""
        # Pre-populate with mixed statuses
        _tenant_indexes[1] = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.FAILED,
                chunk_count=0,
                token_count=0,
            ),
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_index(
                status_filter=DocumentStatus.INDEXED,
                page=1,
                page_size=20,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert len(response.documents) == 1
        assert response.documents[0].status == DocumentStatus.INDEXED

    @pytest.mark.asyncio
    async def test_get_index_pagination(self):
        """Test index pagination"""
        # Pre-populate with multiple documents
        _tenant_indexes[1] = {
            f"doc_{i}": IndexedDocument(
                id=f"doc_{i}",
                source=f"/test{i}",
                status=DocumentStatus.INDEXED,
                chunk_count=1,
                token_count=100,
            )
            for i in range(5)
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await get_index(
                status_filter=None,
                page=1,
                page_size=2,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert len(response.documents) == 2
        assert response.stats.total_documents == 5

    @pytest.mark.asyncio
    async def test_index_document_new(self):
        """Test indexing a new document"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        request = IndexDocumentRequest(
            source="/path/to/new_doc.txt",
            title="New Document",
            content="This is the content",
        )

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await index_document(
                request=request, db=mock_db, tenant_id=1, current_user=mock_user
            )

        assert response.success is True
        assert response.document.source == "/path/to/new_doc.txt"
        assert response.document.status == DocumentStatus.INDEXED

    @pytest.mark.asyncio
    async def test_index_document_duplicate_without_force(self):
        """Test indexing duplicate document without force"""
        # Pre-populate
        _tenant_indexes[1] = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/existing.txt",
                status=DocumentStatus.INDEXED,
                chunk_count=1,
                token_count=100,
            )
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        request = IndexDocumentRequest(source="/existing.txt")

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            with pytest.raises(HTTPException) as exc_info:
                await index_document(
                    request=request, db=mock_db, tenant_id=1, current_user=mock_user
                )

        assert exc_info.value.status_code == 409
        assert "already exists" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_index_document_duplicate_with_force(self):
        """Test re-indexing document with force"""
        # Pre-populate
        _tenant_indexes[1] = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/existing.txt",
                status=DocumentStatus.INDEXED,
                chunk_count=1,
                token_count=100,
            )
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        request = IndexDocumentRequest(
            source="/existing.txt",
            force_reindex=True,
            content="New content for re-indexing",
        )

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await index_document(
                request=request, db=mock_db, tenant_id=1, current_user=mock_user
            )

        assert response.success is True
        # Old doc should be replaced
        assert "doc_1" not in _tenant_indexes[1]

    @pytest.mark.asyncio
    async def test_delete_specific_document(self):
        """Test deleting specific document"""
        # Pre-populate
        _tenant_indexes[1] = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.INDEXED,
                chunk_count=3,
                token_count=1500,
            ),
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await delete_from_index(
                document_id="doc_1",
                clear_all=False,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.success is True
        assert response.deleted_documents == 1
        assert response.deleted_chunks == 5
        assert "doc_1" not in _tenant_indexes[1]
        assert "doc_2" in _tenant_indexes[1]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(self):
        """Test deleting non-existent document"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            with pytest.raises(HTTPException) as exc_info:
                await delete_from_index(
                    document_id="nonexistent",
                    clear_all=False,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_user,
                )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_clear_all_index(self):
        """Test clearing entire index"""
        # Pre-populate
        _tenant_indexes[1] = {
            "doc_1": IndexedDocument(
                id="doc_1",
                source="/test1",
                status=DocumentStatus.INDEXED,
                chunk_count=5,
                token_count=2500,
            ),
            "doc_2": IndexedDocument(
                id="doc_2",
                source="/test2",
                status=DocumentStatus.INDEXED,
                chunk_count=3,
                token_count=1500,
            ),
        }

        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            response = await delete_from_index(
                document_id=None,
                clear_all=True,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert response.success is True
        assert response.deleted_documents == 2
        assert response.deleted_chunks == 8
        assert len(_tenant_indexes[1]) == 0

    @pytest.mark.asyncio
    async def test_delete_no_action_specified(self):
        """Test delete with no action specified"""
        mock_db = AsyncMock()
        mock_user = {"user_id": "test_user"}

        with patch("src.core.api.memory_endpoints.get_current_tenant_id", return_value=1):
            with pytest.raises(HTTPException) as exc_info:
                await delete_from_index(
                    document_id=None,
                    clear_all=False,
                    db=mock_db,
                    tenant_id=1,
                    current_user=mock_user,
                )

        assert exc_info.value.status_code == 400
        assert "Specify document_id" in str(exc_info.value.detail)


# ============================================================================
# Test Router Configuration
# ============================================================================


class TestRouter:
    """Test router configuration"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        assert router.prefix == "/api/v1/memory"

    def test_router_tags(self):
        """Test router has correct tags"""
        assert "memory" in router.tags

    def test_config_route_registered(self):
        """Test config route is registered"""
        routes = [route.path for route in router.routes if hasattr(route, "path")]
        assert any("config" in path for path in routes)

    def test_index_route_registered(self):
        """Test index route is registered"""
        routes = [route.path for route in router.routes if hasattr(route, "path")]
        assert any("index" in path for path in routes)

    def test_config_get_method(self):
        """Test config endpoint supports GET"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/config":
                assert "GET" in route.methods
                break

    def test_config_put_method(self):
        """Test config endpoint supports PUT"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/config":
                assert "PUT" in route.methods
                break

    def test_index_get_method(self):
        """Test index endpoint supports GET"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/index":
                assert "GET" in route.methods
                break

    def test_index_post_method(self):
        """Test index endpoint supports POST"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/index":
                assert "POST" in route.methods
                break

    def test_index_delete_method(self):
        """Test index endpoint supports DELETE"""
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/index":
                assert "DELETE" in route.methods
                break
