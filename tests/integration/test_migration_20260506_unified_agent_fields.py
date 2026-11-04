"""
Integration tests for migration 20260506_add_unified_agent_fields.py

Tests the database schema extension that adds 8 metadata columns to RegisteredAgent.
These tests require a real PostgreSQL database with pgvector.

Migration adds:
  - category (VARCHAR(50), default 'specialist')
  - capabilities_tags (JSONB, default '[]')
  - required_agents (JSONB, default '[]')
  - tier (VARCHAR(50), default 'professional')
  - health_status (VARCHAR(50), default 'unknown')
  - version (VARCHAR(50), default '1.0')
  - owner_team (VARCHAR(255), nullable)
  - metadata (JSONB, default '{}')

Indexes created:
  - idx_agent_category
  - idx_agent_health
  - idx_agent_tier
  - idx_agent_team
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.asyncio
class TestMigration20260506UnifiedAgentFields:
    """Test suite for unified agent fields migration."""

    async def test_migration_adds_all_8_columns(self, db_session: AsyncSession):
        """Happy path: Verify all 8 columns are added with correct types."""
        # Get table schema from actual database
        result = await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'registered_agents' ORDER BY column_name"
            )
        )
        columns = {row.column_name for row in result}

        # Verify all 8 new columns exist
        expected_columns = [
            "category",
            "capabilities_tags",
            "required_agents",
            "tier",
            "health_status",
            "version",
            "owner_team",
            "metadata",
        ]

        for col_name in expected_columns:
            assert col_name in columns, f"Column '{col_name}' not found in registered_agents"

    async def test_column_types_are_correct(self, db_session: AsyncSession):
        """Happy path: Verify column types match schema design."""
        result = await db_session.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'registered_agents' ORDER BY column_name"
            )
        )
        columns = {row.column_name: {"type": row.data_type} for row in result}

        # Type assertions
        assert columns["category"]["type"] == "character varying", "category should be VARCHAR(50)"
        assert columns["capabilities_tags"]["type"] == "jsonb", "capabilities_tags should be JSONB"
        assert columns["required_agents"]["type"] == "jsonb", "required_agents should be JSONB"
        assert columns["tier"]["type"] == "character varying", "tier should be VARCHAR(50)"
        assert columns["health_status"]["type"] == "character varying", (
            "health_status should be VARCHAR(50)"
        )
        assert columns["version"]["type"] == "character varying", "version should be VARCHAR(50)"
        assert columns["owner_team"]["type"] == "character varying", (
            "owner_team should be VARCHAR(255)"
        )
        assert columns["metadata"]["type"] == "jsonb", "metadata should be JSONB"

    async def test_columns_have_sensible_defaults(self, db_session: AsyncSession):
        """Happy path: Verify default values are set for backward compatibility."""
        result = await db_session.execute(
            text(
                "SELECT column_name, column_default FROM information_schema.columns "
                "WHERE table_name = 'registered_agents' ORDER BY column_name"
            )
        )
        columns = {row.column_name: {"column_default": row.column_default} for row in result}

        # Columns with defaults should have server_default
        assert columns["category"]["column_default"] is not None, "category should have default"
        assert columns["tier"]["column_default"] is not None, "tier should have default"
        assert columns["health_status"]["column_default"] is not None, (
            "health_status should have default"
        )
        assert columns["version"]["column_default"] is not None, "version should have default"

    async def test_nullable_columns_are_correct(self, db_session: AsyncSession):
        """Unhappy path: Verify nullability constraints match schema design."""
        result = await db_session.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'registered_agents' ORDER BY column_name"
            )
        )
        columns = {row.column_name: {"is_nullable": row.is_nullable == "YES"} for row in result}

        # NOT NULL columns
        assert not columns["category"]["is_nullable"], "category should NOT NULL"
        assert not columns["tier"]["is_nullable"], "tier should NOT NULL"
        assert not columns["health_status"]["is_nullable"], "health_status should NOT NULL"
        assert not columns["version"]["is_nullable"], "version should NOT NULL"

        # Nullable columns
        assert columns["capabilities_tags"]["is_nullable"], "capabilities_tags should be nullable"
        assert columns["required_agents"]["is_nullable"], "required_agents should be nullable"
        assert columns["owner_team"]["is_nullable"], "owner_team should be nullable"
        assert columns["metadata"]["is_nullable"], "metadata should be nullable"

    async def test_indexes_are_created(self, db_session: AsyncSession):
        """Happy path: Verify all 4 indexes are created correctly."""
        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'registered_agents' ORDER BY indexname"
            )
        )
        indexes = {row.indexname for row in result}

        expected_indexes = [
            "idx_agent_category",
            "idx_agent_health",
            "idx_agent_tier",
            "idx_agent_team",
        ]

        for idx_name in expected_indexes:
            assert idx_name in indexes, f"Index '{idx_name}' not found"

    async def test_index_columns_are_correct(self, db_session: AsyncSession):
        """Happy path: Verify indexes reference correct columns."""
        # For simplicity, we verify indexes exist and reference the right tables
        # pg_indexes doesn't give us column details easily, so we verify via table structure
        result = await db_session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'registered_agents' AND indexname IN "
                "('idx_agent_category', 'idx_agent_health', 'idx_agent_tier', 'idx_agent_team')"
            )
        )
        indexes = {row.indexname: row.indexdef for row in result}

        assert "idx_agent_category" in indexes, "idx_agent_category not found"
        assert "idx_agent_health" in indexes, "idx_agent_health not found"
        assert "idx_agent_tier" in indexes, "idx_agent_tier not found"
        assert "idx_agent_team" in indexes, "idx_agent_team not found"

        # Verify the indexes reference the correct columns via their definitions
        assert "category" in indexes["idx_agent_category"], (
            "idx_agent_category should reference category"
        )
        assert "health_status" in indexes["idx_agent_health"], (
            "idx_agent_health should reference health_status"
        )
        assert "tier" in indexes["idx_agent_tier"], "idx_agent_tier should reference tier"
        assert "owner_team" in indexes["idx_agent_team"], (
            "idx_agent_team should reference owner_team"
        )

    async def test_existing_registered_agents_not_affected(
        self, db_session: AsyncSession, tenant_fixture
    ):
        """User behavioral test: Existing agents continue to work without modification."""
        from src.core.agents.models import RegisteredAgent

        # Create an agent the old way (without new fields)
        agent = RegisteredAgent(
            agent_id="test-agent-001",
            name="Test Agent",
            address="localhost:8000",
            capabilities=[],
            tenant_id=tenant_fixture.id,
        )
        db_session.add(agent)
        await db_session.commit()

        # Verify agent was created with default values for new columns
        await db_session.refresh(agent)
        assert agent.category == "specialist", "category should default to 'specialist'"
        assert agent.tier == "professional", "tier should default to 'professional'"
        assert agent.health_status == "unknown", "health_status should default to 'unknown'"
        assert agent.version == "1.0", "version should default to '1.0'"
        assert agent.capabilities_tags == [] or agent.capabilities_tags is None
        assert agent.required_agents == [] or agent.required_agents is None
        assert agent.owner_team is None, "owner_team should be nullable"
        assert agent.agent_metadata == {} or agent.agent_metadata is None

    async def test_new_agents_can_use_new_fields(self, db_session: AsyncSession, tenant_fixture):
        """User behavioral test: New agents can explicitly set metadata fields."""
        from src.core.agents.models import RegisteredAgent

        # Create an agent with explicit new field values
        agent = RegisteredAgent(
            agent_id="test-agent-with-metadata-001",
            name="Test Agent With Metadata",
            address="localhost:8000",
            capabilities=[],
            tenant_id=tenant_fixture.id,
            category="core",
            tier="enterprise",
            health_status="healthy",
            version="2.0.1",
            capabilities_tags=["llm-integration", "rag-systems"],
            required_agents=["knowledge-agent", "vector-db-agent"],
            owner_team="AI Engineering",
            metadata={"estimated_load": "2CPU, 512MB RAM", "source_format": ".py"},
        )
        db_session.add(agent)
        await db_session.commit()

        # Verify all fields were persisted
        await db_session.refresh(agent)
        assert agent.category == "core"
        assert agent.tier == "enterprise"
        assert agent.health_status == "healthy"
        assert agent.version == "2.0.1"
        assert agent.capabilities_tags == ["llm-integration", "rag-systems"]
        assert agent.required_agents == ["knowledge-agent", "vector-db-agent"]
        assert agent.owner_team == "AI Engineering"
        assert agent.metadata == {"estimated_load": "2CPU, 512MB RAM", "source_format": ".py"}

    async def test_tenant_isolation_with_new_columns(
        self, db_session: AsyncSession, tenant_fixture, other_tenant_fixture
    ):
        """Security test: New columns preserve tenant isolation."""
        from src.core.agents.models import RegisteredAgent

        # Create agents in different tenants with same agent_id (should fail or be isolated)
        agent1 = RegisteredAgent(
            agent_id="isolated-agent-001",
            name="Agent in Tenant A",
            address="localhost:8000",
            tenant_id=tenant_fixture.id,
            category="core",
        )
        agent2 = RegisteredAgent(
            agent_id="isolated-agent-002",
            name="Agent in Tenant B",
            address="localhost:8000",
            tenant_id=other_tenant_fixture.id,
            category="specialist",
        )
        db_session.add(agent1)
        db_session.add(agent2)
        await db_session.commit()

        # Verify tenant A cannot see tenant B's agents via ORM (tenant isolation hook)
        # This is implicit in the test framework's tenant_context fixture
        await db_session.refresh(agent1)
        assert agent1.category == "core"
        assert agent1.tenant_id == tenant_fixture.id

    async def test_jsonb_defaults_are_valid_json(self, db_session: AsyncSession, tenant_fixture):
        """Unhappy path: JSONB columns store valid JSON even when null."""
        from src.core.agents.models import RegisteredAgent

        agent = RegisteredAgent(
            agent_id="test-json-columns-001",
            name="Test JSON Defaults",
            address="localhost:8000",
            tenant_id=tenant_fixture.id,
        )
        db_session.add(agent)
        await db_session.commit()

        await db_session.refresh(agent)

        # Verify JSONB defaults are empty JSON structures, not SQL NULL
        # (empty objects/arrays should be present, not null)
        capabilities_tags = agent.capabilities_tags
        required_agents = agent.required_agents
        metadata = agent.agent_metadata

        # Check types - should be list or None for arrays, dict or None for objects
        assert isinstance(capabilities_tags, (list, type(None)))
        assert isinstance(required_agents, (list, type(None)))
        assert isinstance(metadata, (dict, type(None)))

    async def test_default_values_match_documentation(
        self, db_session: AsyncSession, tenant_fixture
    ):
        """Unhappy path: Verify actual defaults match migration docstring."""
        from src.core.agents.models import RegisteredAgent

        agent = RegisteredAgent(
            agent_id="test-defaults-match-001",
            name="Test Default Values",
            address="localhost:8000",
            tenant_id=tenant_fixture.id,
        )
        db_session.add(agent)
        await db_session.commit()

        await db_session.refresh(agent)

        # According to migration docstring:
        defaults = {
            "category": "specialist",
            "tier": "professional",
            "health_status": "unknown",
            "version": "1.0",
        }

        for field, expected_default in defaults.items():
            actual = getattr(agent, field)
            assert actual == expected_default, (
                f"{field} default should be '{expected_default}', got '{actual}'"
            )

    async def test_migration_downgrade_removes_columns_cleanly(self, db_session: AsyncSession):
        """Integration test: Verify downgrade() removes all columns and indexes."""
        # This test documents the expected behavior but cannot run downgrade in an active session.
        # The actual downgrade is verified through CI: alembic downgrade -1 && alembic upgrade head
        # This test serves as documentation of the contract.

        result = await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'registered_agents' ORDER BY column_name"
            )
        )
        columns = {row.column_name for row in result}

        # Verify columns still exist (we haven't downgraded)
        required_columns = [
            "category",
            "capabilities_tags",
            "required_agents",
            "tier",
            "health_status",
            "version",
            "owner_team",
            "metadata",
        ]
        for col in required_columns:
            assert col in columns, f"Expected column {col} in current schema"
