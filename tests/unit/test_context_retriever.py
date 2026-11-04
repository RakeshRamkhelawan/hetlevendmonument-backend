from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.core.knowledge.embedding_service import EmbeddingService
from src.core.knowledge.tenant_vector_manager import TenantVectorManager
from src.core.sandbox.context_retriever import ContextRetriever


@pytest.fixture
def mock_vector_manager():
    vm = MagicMock(spec=TenantVectorManager)
    vm.search = MagicMock()
    return vm


@pytest.fixture
def mock_embedding_service():
    es = MagicMock(spec=EmbeddingService)
    es.generate_embedding = AsyncMock()
    return es


@pytest.fixture
def retriever(mock_vector_manager, mock_embedding_service):
    return ContextRetriever(mock_vector_manager, mock_embedding_service)


@pytest.mark.asyncio
async def test_get_diagnostic_context_success(
    retriever, mock_vector_manager, mock_embedding_service
):
    """Test successful retrieval flow"""
    # Setup mocks
    mock_embedding = np.array([0.1, 0.2, 0.3])
    mock_embedding_service.generate_embedding.return_value = mock_embedding

    mock_vector_manager.search.return_value = {
        "documents": [["Snippet 1", "Snippet 2"]],
        "metadatas": [[{"source": "file1.py"}, {"source": "file2.py"}]],
    }

    context = await retriever.get_diagnostic_context(1, "Error Trace", "print('fail')", limit=2)

    # Verify embedding call
    mock_embedding_service.generate_embedding.assert_called_once()
    assert "Error Trace" in mock_embedding_service.generate_embedding.call_args[0][0]

    # Verify search call
    mock_vector_manager.search.assert_called_once()
    kwargs = mock_vector_manager.search.call_args.kwargs
    assert kwargs["tenant_id"] == 1
    assert kwargs["query_embedding"] == mock_embedding.tolist()
    assert kwargs["top_k"] == 2

    # Verify output format
    assert "Found relevant snippets" in context
    assert "[Snippet 1 from file1.py]:" in context
    assert "Snippet 1" in context
    assert "[Snippet 2 from file2.py]:" in context


@pytest.mark.asyncio
async def test_get_diagnostic_context_no_results(
    retriever, mock_vector_manager, mock_embedding_service
):
    """Test when no results found"""
    mock_embedding_service.generate_embedding.return_value = np.array([0.1])
    mock_vector_manager.search.return_value = {"documents": [[]]}  # Empty docs

    context = await retriever.get_diagnostic_context(1, "Err", "Code")
    assert "No relevant context found" in context


@pytest.mark.asyncio
async def test_get_diagnostic_context_embedding_failure(
    retriever, mock_vector_manager, mock_embedding_service
):
    """Test handling of embedding failure"""
    mock_embedding_service.generate_embedding.return_value = None

    context = await retriever.get_diagnostic_context(1, "Err", "Code")
    assert "Context unavailable" in context
    mock_vector_manager.search.assert_not_called()


@pytest.mark.asyncio
async def test_get_diagnostic_context_search_exception(
    retriever, mock_vector_manager, mock_embedding_service
):
    """Test handling of database exception"""
    mock_embedding_service.generate_embedding.return_value = np.array([0.1])
    mock_vector_manager.search.side_effect = Exception("DB Down")

    context = await retriever.get_diagnostic_context(1, "Err", "Code")
    assert "Context retrieval error: DB Down" in context
