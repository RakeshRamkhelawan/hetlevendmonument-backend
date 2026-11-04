"""
Tool Registry Unit Tests - TDD Phase 2

Tests for ToolRegistry with Clean Architecture (DTOs).
Run: pytest tests/unit/agentic/test_tool_registry.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import ToolDefinition as ToolModel
from src.domains.agentic.schemas import ToolDefinition as ToolDTO
from src.domains.agentic.services.tool_registry import ToolRegistry


class TestToolRegistry:
    @pytest.mark.asyncio
    async def test_get_tool_by_name(self):
        """Test retrieving a single tool by name with DTO mapping."""
        # Setup DB Model
        mock_model = ToolModel(
            id=1,
            name="test_tool",
            description="Test Tool",
            category="general",
            function_schema={"type": "object", "properties": {}},
            implementation_type="python_function",
            implementation_config={
                "module_path": "src.tools.test",
                "function_name": "run_test",
                "version": "1.0.0",
            },
            required_permissions=["read:test"],
            is_active=True,
        )

        # Mock DB
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_db.execute.return_value = mock_result

        registry = ToolRegistry()

        # Act
        dto = await registry.get_tool(mock_db, "test_tool")

        # Assert
        assert isinstance(dto, ToolDTO)
        assert dto.name == "test_tool"
        assert dto.parameters_schema == {"type": "object", "properties": {}}
        assert dto.module_path == "src.tools.test"
        assert dto.function_name == "run_test"
        assert dto.version == "1.0.0"
        assert "read:test" in dto.required_permissions

    @pytest.mark.asyncio
    async def test_load_tools_batch(self):
        """Test loading multiple tools."""
        # Setup Models
        t1 = ToolModel(
            id=1,
            name="t1",
            description="d1",
            function_schema={},
            implementation_config={"module": "m1", "func": "f1", "version": "1"},
            is_active=True,
        )
        t2 = ToolModel(
            id=2,
            name="t2",
            description="d2",
            function_schema={},
            implementation_config={"module": "m2", "func": "f2", "version": "1"},
            is_active=True,
        )

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [t1, t2]
        mock_db.execute.return_value = mock_result

        registry = ToolRegistry()
        dtos = await registry.load_tools(mock_db, ["t1", "t2"])

        assert len(dtos) == 2
        assert dtos[0].name == "t1"
        assert dtos[1].name == "t2"
