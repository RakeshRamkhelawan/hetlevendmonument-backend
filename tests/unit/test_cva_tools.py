"""
TDD Unit Tests for CVA Tool Definitions and ToolExecutor
Tests written BEFORE implementation (TDD approach)

Coverage Target: 95%+
"""

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestWorkflowNodeModel:
    """Test cases for WorkflowNode Pydantic model"""

    def test_workflow_node_valid_creation(self):
        """WorkflowNode should create with valid parameters"""
        from src.core.agents.ultimate_cva.tools import WorkflowNode

        node = WorkflowNode(id="node_1", agent_name="email_agent", label="Send Email")

        assert node.id == "node_1"
        assert node.agent_name == "email_agent"
        assert node.label == "Send Email"

    def test_workflow_node_default_config(self):
        """WorkflowNode should have empty dict as default config"""
        from src.core.agents.ultimate_cva.tools import WorkflowNode

        node = WorkflowNode(id="n1", agent_name="a", label="l")

        assert node.config == {}

    def test_workflow_node_default_position(self):
        """WorkflowNode should have default position {x: 0, y: 0}"""
        from src.core.agents.ultimate_cva.tools import WorkflowNode

        node = WorkflowNode(id="n1", agent_name="a", label="l")

        assert node.position == {"x": 0, "y": 0}


class TestWorkflowEdgeModel:
    """Test cases for WorkflowEdge Pydantic model"""

    def test_workflow_edge_valid_creation(self):
        """WorkflowEdge should create with source and target"""
        from src.core.agents.ultimate_cva.tools import WorkflowEdge

        edge = WorkflowEdge(source="node_1", target="node_2")

        assert edge.source == "node_1"
        assert edge.target == "node_2"

    def test_workflow_edge_optional_condition(self):
        """WorkflowEdge condition should be optional"""
        from src.core.agents.ultimate_cva.tools import WorkflowEdge

        edge = WorkflowEdge(source="a", target="b")

        assert edge.condition is None

    def test_workflow_edge_with_condition(self):
        """WorkflowEdge should accept condition"""
        from src.core.agents.ultimate_cva.tools import WorkflowEdge

        edge = WorkflowEdge(source="a", target="b", condition="success")

        assert edge.condition == "success"


class TestCreateWorkflowParamsModel:
    """Test cases for CreateWorkflowParams model"""

    def test_create_workflow_params_valid(self):
        """CreateWorkflowParams should create with required params"""
        from src.core.agents.ultimate_cva.tools import (
            CreateWorkflowParams,
            WorkflowEdge,
            WorkflowNode,
        )

        params = CreateWorkflowParams(
            name="Test Workflow",
            description="A test",
            nodes=[WorkflowNode(id="n1", agent_name="a", label="l")],
            edges=[WorkflowEdge(source="n1", target="n2")],
        )

        assert params.name == "Test Workflow"
        assert len(params.nodes) == 1
        assert len(params.edges) == 1


class TestNavigateToParamsModel:
    """Test cases for NavigateToParams model"""

    def test_navigate_to_valid_routes(self):
        """NavigateToParams should accept valid routes"""
        from src.core.agents.ultimate_cva.tools import NavigateToParams

        valid_routes = [
            "/dashboard",
            "/workflows",
            "/vibe",
            "/agents",
            "/settings",
            "/analytics",
        ]

        for route in valid_routes:
            params = NavigateToParams(route=route)
            assert params.route == route


class TestGenerateContentParamsModel:
    """Test cases for GenerateContentParams model"""

    def test_generate_content_valid_types(self):
        """Should accept valid content types"""
        from src.core.agents.ultimate_cva.tools import GenerateContentParams

        valid_types = ["newsletter", "website_article", "linkedin_post"]

        for ctype in valid_types:
            params = GenerateContentParams(content_type=ctype, topic="Test Topic")
            assert params.content_type == ctype

    def test_generate_content_default_language(self):
        """Default language should be en-GB"""
        from src.core.agents.ultimate_cva.tools import GenerateContentParams

        params = GenerateContentParams(content_type="newsletter", topic="Test")

        assert params.language == "en-GB"


# ============================================================================
# Tool Definitions Tests
# ============================================================================


class TestToolDefinitions:
    """Test cases for TOOL_DEFINITIONS constant"""

    def test_tool_definitions_is_list(self):
        """TOOL_DEFINITIONS should be a list"""
        from src.core.agents.ultimate_cva.tools import TOOL_DEFINITIONS

        assert isinstance(TOOL_DEFINITIONS, list)

    def test_tool_definitions_has_required_tools(self):
        """Should include all 5 required tools"""
        from src.core.agents.ultimate_cva.tools import TOOL_DEFINITIONS

        tool_names = [t["name"] for t in TOOL_DEFINITIONS]
        required = [
            "create_workflow",
            "navigate_to",
            "generate_content",
            "get_system_status",
            "search_workflows",
        ]

        for name in required:
            assert name in tool_names, f"Missing tool: {name}"

    def test_tool_definition_structure(self):
        """Each tool should have name, description, parameters_schema"""
        from src.core.agents.ultimate_cva.tools import TOOL_DEFINITIONS

        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "parameters_schema" in tool


# ============================================================================
# ToolExecutor Tests
# ============================================================================


class TestToolExecutor:
    """Test cases for ToolExecutor class"""

    def test_tool_executor_initialization(self):
        """ToolExecutor should initialize with agent reference"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        executor = ToolExecutor(mock_agent)

        assert executor.agent == mock_agent

    @pytest.mark.asyncio
    async def test_execute_create_workflow(self):
        """execute should handle create_workflow"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        executor = ToolExecutor(mock_agent)

        result = await executor.execute(
            "create_workflow",
            {"name": "Test", "description": "Desc", "nodes": [], "edges": []},
        )

        assert result["success"] is True
        assert result["action"] == "navigate_to_vibe"

    @pytest.mark.asyncio
    async def test_execute_navigate_to(self):
        """execute should handle navigate_to"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        executor = ToolExecutor(mock_agent)

        result = await executor.execute("navigate_to", {"route": "/dashboard"})

        assert result["success"] is True
        assert result["action"] == "navigate"
        assert result["route"] == "/dashboard"

    @pytest.mark.asyncio
    async def test_execute_get_system_status(self):
        """execute should handle get_system_status"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        mock_agent.orchestrator.get_dashboard_data = AsyncMock(
            return_value={"status": "ok"}
        )
        executor = ToolExecutor(mock_agent)

        result = await executor.execute("get_system_status", {})

        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_execute_search_workflows(self):
        """execute should handle search_workflows"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        executor = ToolExecutor(mock_agent)

        result = await executor.execute("search_workflows", {"query": "test"})

        assert result["success"] is True
        assert "results" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """execute should return error for unknown tool"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        executor = ToolExecutor(mock_agent)

        result = await executor.execute("nonexistent_tool", {})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_generate_content(self):
        """execute should handle generate_content"""
        from src.core.agents.ultimate_cva.tools import ToolExecutor

        mock_agent = MagicMock()
        mock_agent.llm_service = MagicMock()
        mock_agent.llm_service.generate_response = AsyncMock(return_value="Generated content")
        executor = ToolExecutor(mock_agent)

        result = await executor.execute(
            "generate_content", {"content_type": "newsletter", "topic": "AI trends"}
        )

        assert result["success"] is True
        assert result["content"] == "Generated content"


# ============================================================================
# Integration Tests
# ============================================================================


class TestToolsIntegration:
    """Integration tests for tools module"""

    def test_create_workflow_params_to_dict(self):
        """CreateWorkflowParams should serialize to dict"""
        from src.core.agents.ultimate_cva.tools import (
            CreateWorkflowParams,
            WorkflowEdge,
            WorkflowNode,
        )

        params = CreateWorkflowParams(
            name="Test",
            description="Desc",
            nodes=[WorkflowNode(id="n1", agent_name="a", label="l")],
            edges=[],
        )

        data = params.model_dump()

        assert data["name"] == "Test"
        assert len(data["nodes"]) == 1

    def test_tool_definitions_json_schema(self):
        """Tool definitions should include valid JSON schemas"""
        from src.core.agents.ultimate_cva.tools import TOOL_DEFINITIONS

        for tool in TOOL_DEFINITIONS:
            schema = tool["parameters_schema"]
            assert "type" in schema or "properties" in schema
