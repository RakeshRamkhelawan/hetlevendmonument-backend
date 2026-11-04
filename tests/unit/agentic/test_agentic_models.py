"""
Agentic Models Unit Tests - TDD Phase 1

These tests are written BEFORE implementation (RED phase).
Run: pytest tests/unit/agentic/test_agentic_models.py -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.asyncio(loop_scope="function")]


class TestFeatureModel:
    """Tests for Feature model."""

    async def test_create_feature_minimal(self, db_session: AsyncSession, isolated_tenant):
        """Feature can be created with minimal required fields."""
        from src.domains.agentic.models import Feature

        feature = Feature(
            id="test_feature_001",
            name="Test Feature",
            description="A test feature for TDD",
            category="general",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature)
        await db_session.commit()
        await db_session.refresh(feature)

        assert feature.id == "test_feature_001"
        assert feature.name == "Test Feature"
        assert feature.is_active is True  # default value

    async def test_feature_with_tenant_fk(self, db_session: AsyncSession, isolated_tenant):
        """Feature can be linked to tenant via FK column."""
        from src.domains.agentic.models import Feature

        feature = Feature(
            id="tenant_feature_001",
            name="Tenant Feature",
            description="Feature with tenant FK",
            category="workflow",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature)
        await db_session.commit()

        assert feature.tenant_id == isolated_tenant["tenant_id"]

    async def test_feature_unique_id(self, db_session: AsyncSession, isolated_tenant):
        """Feature ID must be unique."""
        from sqlalchemy.exc import IntegrityError

        from src.domains.agentic.models import Feature

        feature1 = Feature(
            id="unique_test",
            name="Feature 1",
            description="First",
            category="general",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature1)
        await db_session.commit()
        db_session.expunge(feature1)

        feature2 = Feature(
            id="unique_test",  # Same ID - should fail
            name="Feature 2",
            description="Second",
            category="general",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestPromptTemplateModel:
    """Tests for PromptTemplate model."""

    async def test_create_prompt_template_minimal(self, db_session: AsyncSession, isolated_tenant):
        """PromptTemplate can be created with minimal fields."""
        from src.domains.agentic.models import PromptTemplate

        template = PromptTemplate(
            name="test_template",
            version="1.0.0",
            system_prompt="You are a helpful assistant.",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)

        assert template.name == "test_template"
        assert template.version == "1.0.0"
        assert template.status == "draft"  # default value

    async def test_prompt_template_with_context(self, db_session: AsyncSession, isolated_tenant):
        """PromptTemplate can have context template."""
        from src.domains.agentic.models import PromptTemplate

        template = PromptTemplate(
            name="context_template",
            version="1.0.0",
            system_prompt="System prompt here",
            context_template="Context: {context}",
            output_format="json",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(template)
        await db_session.commit()

        assert template.context_template == "Context: {context}"
        assert template.output_format == "json"


class TestToolDefinitionModel:
    """Tests for ToolDefinition model."""

    async def test_create_tool_definition(self, db_session: AsyncSession, isolated_tenant):
        """ToolDefinition can be created."""
        from src.domains.agentic.models import ToolDefinition

        tool = ToolDefinition(
            name="search_tool",
            display_name="Search Tool",
            description="Searches the web",
            category="search",
            function_schema={"type": "function", "name": "search"},
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(tool)
        await db_session.commit()
        await db_session.refresh(tool)

        assert tool.name == "search_tool"
        assert tool.is_active is True
        assert tool.function_schema["type"] == "function"

    async def test_tool_definition_unique_name(self, db_session: AsyncSession, isolated_tenant):
        """ToolDefinition name must be unique."""
        from sqlalchemy.exc import IntegrityError

        from src.domains.agentic.models import ToolDefinition

        tool1 = ToolDefinition(
            name="unique_tool",
            display_name="Tool 1",
            description="First",
            category="test",
            function_schema={},
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(tool1)
        await db_session.commit()
        db_session.expunge(tool1)

        tool2 = ToolDefinition(
            name="unique_tool",  # Same name - should fail
            display_name="Tool 2",
            description="Second",
            category="test",
            function_schema={},
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(tool2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestAgentSessionModel:
    """Tests for AgentSession model."""

    async def test_create_agent_session(self, db_session: AsyncSession, isolated_tenant):
        """AgentSession can be created with user and tenant FK."""
        from src.domains.agentic.models import AgentSession

        session = AgentSession(
            id="session_001",
            user_id=isolated_tenant["user_id"],
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(session)
        await db_session.commit()

        assert session.id == "session_001"
        assert session.message_count == 0  # default


class TestSessionMessageModel:
    """Tests for SessionMessage model."""

    async def test_create_session_message(self, db_session: AsyncSession, isolated_tenant):
        """SessionMessage can be created within a session."""
        from src.domains.agentic.models import AgentSession, SessionMessage

        # First create session
        agent_session = AgentSession(
            id="msg_test_session",
            user_id=isolated_tenant["user_id"],
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(agent_session)
        await db_session.commit()

        # Then create message
        message = SessionMessage(
            session_id="msg_test_session",
            role="user",
            content="Hello, this is a test message",
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        assert message.role == "user"
        assert message.content == "Hello, this is a test message"
        assert message.session_id == "msg_test_session"
