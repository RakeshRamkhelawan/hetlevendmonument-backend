"""
Unit Tests for Corrective RAG (CRAG) Graph

Tests the full LangGraph workflow logic, including conditional routing
and state transitions. Uses mocks for external services.
"""

import asyncio
import warnings
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Suppress langchain_community sunset DeprecationWarning at import time before
# pytest's "error" default filter can turn it into a collection failure.
warnings.filterwarnings(
    "ignore",
    message=".*langchain[-_]community.*being sunset.*",
    category=DeprecationWarning,
)

from src.core.agents.crag_graph import (
    GraphState,
    create_crag_graph,
    decide_to_generate,
    generate,
    grade_documents,
    retrieve,
    transform_query,
    web_search,
)
from src.core.search.hybrid_search import HybridSearchResult


class TestCRAGNodes:
    """Tests for individual graph nodes"""

    @pytest.mark.asyncio
    async def test_retrieve_node(self):
        """Test document retrieval and state update"""
        mock_result = HybridSearchResult(
            document_id="doc1",
            content="content1",
            metadata={},
            vector_score=0.9,
            bm25_score=0.8,
            hybrid_score=0.85,
            source="both",
        )

        with patch(
            "src.core.agents.crag_graph.hybrid_search", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [mock_result]

            state = {"query": "test query", "tenant_id": 1}
            result = await retrieve(state)

            assert "documents" in result
            assert len(result["documents"]) == 1
            assert result["documents"][0]["id"] == "doc1"
            assert result["documents"][0]["score"] == 0.85

    @pytest.mark.asyncio
    async def test_grade_documents_all_relevant(self):
        """Test grading when all docs are relevant"""
        state = {
            "query": "test",
            "documents": [{"id": "d1", "content": "relevant content"}],
            "tenant_id": 1,
        }

        mock_llm_response = {"content": "yes"}

        with patch("src.core.agents.crag_graph.TenantTaalmodel") as MockService:
            instance = MockService.return_value
            instance.generate_response = AsyncMock(return_value=mock_llm_response)

            result = await grade_documents(state)

            assert len(result["documents"]) == 1
            assert result["web_search_needed"] is False

    @pytest.mark.asyncio
    async def test_grade_documents_all_irrelevant(self):
        """Test grading when docs are irrelevant -> trigger web search"""
        state = {
            "query": "test",
            "documents": [{"id": "d1", "content": "irrelevant garbage"}],
            "tenant_id": 1,
        }

        mock_llm_response = {"content": "no"}

        with patch("src.core.agents.crag_graph.TenantTaalmodel") as MockService:
            instance = MockService.return_value
            instance.generate_response = AsyncMock(return_value=mock_llm_response)

            result = await grade_documents(state)

            assert len(result["documents"]) == 0
            assert result["web_search_needed"] is True

    @pytest.mark.asyncio
    async def test_web_search_node(self):
        """Test web search execution"""
        state = {"query": "web query", "documents": []}

        mock_tool_resp = [{"content": "web content", "url": "http://test.com"}]

        with patch("src.core.agents.crag_graph.TavilySearchResults") as MockTool:
            instance = MockTool.return_value
            instance.ainvoke = AsyncMock(return_value=mock_tool_resp)

            result = await web_search(state)

            assert len(result["documents"]) == 1
            assert result["documents"][0]["metadata"]["source"] == "web"

    def test_decide_to_generate(self):
        """Test conditional logic"""
        assert decide_to_generate({"web_search_needed": True}) == "web_search"
        assert decide_to_generate({"web_search_needed": False}) == "generate"


class TestCRAGWorkflow:
    """Tests for the full compiled graph execution"""

    @pytest.mark.asyncio
    async def test_full_graph_relevant_path(self):
        """Verify graph takes the happy path when docs are relevant"""
        # We mock the nodes directly to test the flow logic without side effects

        # 1. Retrieve returns docs
        # 2. Grade keeps docs, web_search_needed=False
        # 3. Router -> Generate

        app = create_crag_graph()

        # We need to mock the internals called by the graph
        # Since graph compiles the functions, we must patch where they are IMPORTED or DEFINED
        # But we already defined them in the module.
        # So we patch the external calls INSIDE the nodes.

        mock_search_res = [HybridSearchResult("d1", "content", {}, 1.0, 1.0, 1.0, "vector")]
        mock_grade_res = {"content": "yes"}  # Relevant
        mock_gen_res = {"content": "Final Answer"}

        with (
            patch(
                "src.core.agents.crag_graph.hybrid_search",
                new_callable=AsyncMock,
                return_value=mock_search_res,
            ),
            patch("src.core.agents.crag_graph.TenantTaalmodel") as MockService,
        ):
            service = MockService.return_value
            # Sequence: Grade -> Generate
            service.generate_response = AsyncMock(side_effect=[mock_grade_res, mock_gen_res])

            inputs = {"query": "test", "tenant_id": 1}
            # LangGraph ainvoke execution
            result = await app.ainvoke(inputs)

            assert result["generation"] == "Final Answer"
            assert result["web_search_needed"] is False
            assert len(result["documents"]) == 1

    @pytest.mark.asyncio
    async def test_full_graph_corrective_path(self):
        """Verify graph takes the web search path when docs are irrelevant"""

        app = create_crag_graph()

        mock_search_res = [HybridSearchResult("d1", "content", {}, 1.0, 1.0, 1.0, "vector")]

        # Sequence of LLM calls:
        # 1. Grade -> "no" (Irrelevant)
        # 2. Transform Query -> "better query"
        # 3. Generate -> "Final Answer"
        llm_responses = [
            {"content": "no"},
            {"content": "better query"},
            {"content": "Final Answer"},
        ]

        mock_web_res = [{"content": "web info", "url": "http://web"}]

        with (
            patch(
                "src.core.agents.crag_graph.hybrid_search",
                new_callable=AsyncMock,
                return_value=mock_search_res,
            ),
            patch("src.core.agents.crag_graph.TenantTaalmodel") as MockService,
            patch("src.core.agents.crag_graph.TavilySearchResults") as MockTool,
        ):
            service = MockService.return_value
            service.generate_response = AsyncMock(side_effect=llm_responses)

            tool = MockTool.return_value
            tool.ainvoke = AsyncMock(return_value=mock_web_res)

            inputs = {"query": "test", "tenant_id": 1}
            result = await app.ainvoke(inputs)

            assert result["generation"] == "Final Answer"
            assert result["web_search_needed"] is True
            # Documents should contain ONLY web results (since d1 was filtered out)
            assert len(result["documents"]) == 1
            assert result["documents"][0]["metadata"]["source"] == "web"
            assert result["query"] == "better query"
