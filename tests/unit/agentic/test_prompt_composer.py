"""
Prompt Composer Unit Tests - TDD Phase 2

Tests for DomainAgnosticPromptComposer with Clean Architecture (DTOs).
Run: pytest tests/unit/agentic/test_prompt_composer.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import PromptTemplate, ToolDefinition
from src.domains.agentic.schemas import FeatureDefinition, PromptContext
from src.domains.agentic.services.prompt_composer import (
    ComposedPrompt,
    DomainAgnosticPromptComposer,
)


class TestPromptComposer:
    @pytest.mark.asyncio
    async def test_compose_prompt_basic(self):
        """Test basic prompt composition with DTO."""
        # Setup DTO
        feature_dto = FeatureDefinition(
            id="test_feat",
            category="general",
            display_name={"en": "Test Feature"},
            description={"en": "A test feature"},
            domain_context="testing",
            is_active=True,
            tenant_id=1,
            available_tools=["tool_a"],
            prompt_template_id=10,  # Set explicitly
        )

        # Mock DB
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock Template Query Result
        mock_template = PromptTemplate(
            id=10,
            # feature_context="test_feat", # Removed
            system_prompt="System Prompt Content",  # Exists
            # feature_role="You are a helper", # Removed
            status="active",
            version=1,
        )
        # Note: capabilities and constraints are also missing from model, so test shouldn't check them.

        # Mock Tool Query Result
        mock_tool = ToolDefinition(
            id=1,  # Integer PK
            name="tool_a",
            display_name="Tool A",  # Missing in prev snippet? Check model.
            description="Tool A",
            category="general",
            function_schema={"type": "object"},  # Correct field
        )

        # Setup DB execute returns
        # The service makes 2 DB calls: _load_template and _load_tools
        # We need to mock the results for these calls

        # Mock result scalars().all() and scalar_one_or_none()
        mock_result_template = MagicMock()
        mock_result_template.scalar_one_or_none.return_value = mock_template

        mock_result_tools = MagicMock()
        mock_result_tools.scalars.return_value.all.return_value = [mock_tool]

        # side_effect to return different results depending on call?
        # Typically complex with AsyncMock.
        # Simpler approach: Allow both calls to return their respective types if queries differ.
        # But both call db.execute(stmt).

        # We can inspect the statement in side_effect, or just chain side_effects.
        # Call 1: Template, Call 2: Tools.
        mock_db.execute.side_effect = [mock_result_template, mock_result_tools]

        composer = DomainAgnosticPromptComposer()

        # Act
        result = await composer.compose_prompt(db=mock_db, feature=feature_dto, user_locale="en_US")

        # Assert
        assert isinstance(result, ComposedPrompt)
        assert "System Prompt Content" in result.system_prompt
        assert "Tool A" not in result.system_prompt  # Tools are in .tools list, not text?
        # Note: tools list is returned separate.
        assert len(result.tools) == 1
        assert result.tools[0]["name"] == "tool_a"
        assert result.metadata["feature_id"] == "test_feat"
