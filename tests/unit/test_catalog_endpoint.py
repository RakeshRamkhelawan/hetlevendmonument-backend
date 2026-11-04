"""
Unit Tests for Enterprise Catalog Endpoint

Tests the GET /api/v1/agents/catalog endpoint that returns
135 agents and 80 domain packs from YAML config.

Coverage Target: catalog endpoint in agent_endpoints.py
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.als.agents.loader import AgentConfig, DomainPack, WorkflowStep
from src.core.api.agent_endpoints import (
    CatalogMetadataResponse,
    EnterpriseCatalogResponse,
    get_enterprise_catalog,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_current_user():
    """Mock authenticated user for catalog access."""
    user = Mock()
    user.id = 1
    user.email = "admin@sanskritisetu.org"
    user.tenant_id = 1
    return user


@pytest.fixture
def sample_agents():
    """Sample agent configs mimicking YAML data."""
    return {
        "crisismanager": AgentConfig(
            agent_id="ext.communications_pr.crisismanager.001",
            name="CrisisManagerAgent",
            department="communications_pr",
            technology="gemini",
            class_name="CrisisManagerAgent",
            description="Handles crisis communication workflows",
            is_active=True,
            priority="HIGH",
            allowed_tools=["comms_drafting_tool", "media_monitor"],
            ooda_profile={
                "observe": {"data_sources": ["news_feed", "social_media"]},
                "orient": {"model": "gemini-2.0-flash"},
                "decide": {"confidence_threshold": 0.85},
                "act": {"tools": ["press_release_tool"]},
            },
        ),
        "budgetoptimizer": AgentConfig(
            agent_id="core.finance_treasury.budgetoptimizer.001",
            name="BudgetOptimizerAgent",
            department="finance_treasury",
            technology="ollama",
            class_name="BudgetOptimizerAgent",
            description="Optimizes departmental budgets",
            is_active=False,
            priority="MEDIUM",
            allowed_tools=["spreadsheet_tool"],
            ooda_profile={
                "observe": {"data_sources": ["financial_reports"]},
                "orient": {"model": "llama3"},
                "decide": {"confidence_threshold": 0.90},
                "act": {"tools": ["budget_report_tool"]},
            },
        ),
    }


@pytest.fixture
def sample_packs():
    """Sample domain packs mimicking YAML data."""
    return {
        "finance.monthly_close": DomainPack(
            pack_id="finance.monthly_close",
            name="Monthly Financial Close",
            steps=[
                WorkflowStep(
                    agent_id="core.finance_treasury.budgetoptimizer.001",
                    mode="sequential",
                    sla_seconds=60.0,
                ),
                WorkflowStep(
                    agent_id="ext.communications_pr.crisismanager.001",
                    mode="parallel",
                    sla_seconds=30.0,
                ),
            ],
        ),
    }


@pytest.fixture
def mock_loader(sample_agents, sample_packs):
    """Mock EnterpriseCatalogLoader with sample data."""
    loader = MagicMock()
    loader.agents = sample_agents
    loader.packs = sample_packs
    loader.load_all = MagicMock(return_value=loader)
    return loader


# ============================================================================
# TEST CLASS: CATALOG ENDPOINT SUCCESS PATHS
# ============================================================================


class TestCatalogEndpointSuccess:
    """Tests for successful catalog retrieval."""

    @pytest.mark.asyncio
    async def test_catalog_returns_all_agents(self, mock_current_user, mock_loader):
        """Verify endpoint returns all agents from loader."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        assert len(result.agents) == 2

    @pytest.mark.asyncio
    async def test_catalog_returns_all_packs(self, mock_current_user, mock_loader):
        """Verify endpoint returns all packs from loader."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        assert len(result.packs) == 1

    @pytest.mark.asyncio
    async def test_catalog_metadata_counts(self, mock_current_user, mock_loader):
        """Verify metadata contains correct counts."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        assert result.metadata.totalAgents == 2
        assert result.metadata.totalPacks == 1
        assert result.metadata.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_agent_fields_mapping(self, mock_current_user, mock_loader):
        """Verify agent fields are correctly mapped from AgentConfig."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agents_by_id = {a["id"]: a for a in result.agents}
        crisis = agents_by_id["ext.communications_pr.crisismanager.001"]

        assert crisis["name"] == "CrisisManagerAgent"
        assert crisis["department"] == "communications_pr"
        assert crisis["description"] == "Handles crisis communication workflows"
        assert crisis["status"] == "active"
        assert crisis["version"] == "1.0.0"
        assert "comms_drafting_tool" in crisis["capabilities"]
        assert "press_release_tool" in crisis["capabilities"]

    @pytest.mark.asyncio
    async def test_inactive_agent_status_deprecated(self, mock_current_user, mock_loader):
        """Verify inactive agent gets 'deprecated' status."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agents_by_id = {a["id"]: a for a in result.agents}
        budget = agents_by_id["core.finance_treasury.budgetoptimizer.001"]
        assert budget["status"] == "deprecated"

    @pytest.mark.asyncio
    async def test_agent_inputs_from_ooda(self, mock_current_user, mock_loader):
        """Verify inputs are extracted from OODA observe.data_sources."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agents_by_id = {a["id"]: a for a in result.agents}
        crisis = agents_by_id["ext.communications_pr.crisismanager.001"]
        input_names = [inp["name"] for inp in crisis["inputs"]]
        assert "news_feed" in input_names
        assert "social_media" in input_names

    @pytest.mark.asyncio
    async def test_agent_outputs_from_ooda(self, mock_current_user, mock_loader):
        """Verify outputs are extracted from OODA act.tools."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agents_by_id = {a["id"]: a for a in result.agents}
        crisis = agents_by_id["ext.communications_pr.crisismanager.001"]
        output_names = [out["name"] for out in crisis["outputs"]]
        assert "press_release_tool" in output_names

    @pytest.mark.asyncio
    async def test_pack_fields_mapping(self, mock_current_user, mock_loader):
        """Verify pack fields are correctly mapped from DomainPack."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        pack = result.packs[0]
        assert pack["id"] == "finance.monthly_close"
        assert pack["name"] == "Monthly Financial Close"
        assert pack["category"] == "finance"
        assert len(pack["agents"]) == 2
        assert pack["metadata"]["step_count"] == 2

    @pytest.mark.asyncio
    async def test_pack_category_from_pack_id(self, mock_current_user, mock_loader):
        """Verify category is extracted from pack_id prefix."""
        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=mock_loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        pack = result.packs[0]
        assert pack["category"] == "finance"

    @pytest.mark.asyncio
    async def test_capabilities_deduplication(self, mock_current_user):
        """Verify capabilities from allowed_tools and ooda act.tools are deduplicated."""
        agents = {
            "testdup": AgentConfig(
                agent_id="test.dup.001",
                name="DupAgent",
                department="it_security",
                technology="ollama",
                class_name="DupAgent",
                allowed_tools=["shared_tool", "unique_a"],
                ooda_profile={
                    "act": {"tools": ["shared_tool", "unique_b"]},
                },
            ),
        }
        loader = MagicMock()
        loader.agents = agents
        loader.packs = {}
        loader.load_all = MagicMock(return_value=loader)

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agent = result.agents[0]
        assert len(agent["capabilities"]) == 3
        assert set(agent["capabilities"]) == {"shared_tool", "unique_a", "unique_b"}


# ============================================================================
# TEST CLASS: CATALOG ENDPOINT ERROR PATHS
# ============================================================================


class TestCatalogEndpointErrors:
    """Tests for error handling in catalog endpoint."""

    @pytest.mark.asyncio
    async def test_catalog_integrity_error_returns_500(self, mock_current_user):
        """Verify ValueError from loader raises HTTP 500."""
        loader = MagicMock()
        loader.load_all.side_effect = ValueError("Missing agent reference")

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_enterprise_catalog(current_user=mock_current_user, _=1)

            assert exc_info.value.status_code == 500
            assert "integrity error" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_catalog_general_error_returns_503(self, mock_current_user):
        """Verify unexpected exceptions raise HTTP 503."""
        loader = MagicMock()
        loader.load_all.side_effect = RuntimeError("YAML parse failed")

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_enterprise_catalog(current_user=mock_current_user, _=1)

            assert exc_info.value.status_code == 503
            assert "temporarily unavailable" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_catalog_empty_agents(self, mock_current_user):
        """Verify endpoint handles empty agent directory gracefully."""
        loader = MagicMock()
        loader.agents = {}
        loader.packs = {}
        loader.load_all = MagicMock(return_value=loader)

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        assert len(result.agents) == 0
        assert len(result.packs) == 0
        assert result.metadata.totalAgents == 0
        assert result.metadata.totalPacks == 0


# ============================================================================
# TEST CLASS: RESPONSE MODEL VALIDATION
# ============================================================================


class TestCatalogResponseModels:
    """Tests for Pydantic response models."""

    def test_metadata_response_valid(self):
        """Verify CatalogMetadataResponse accepts valid data."""
        meta = CatalogMetadataResponse(
            version="2.0.0",
            last_updated="2026-03-10T00:00:00Z",
            totalAgents=135,
            totalPacks=80,
        )
        assert meta.version == "2.0.0"
        assert meta.totalAgents == 135

    def test_enterprise_catalog_response_valid(self):
        """Verify EnterpriseCatalogResponse accepts valid data."""
        resp = EnterpriseCatalogResponse(
            agents=[{"id": "test", "name": "Test"}],
            packs=[{"id": "pack1", "name": "Pack"}],
            metadata=CatalogMetadataResponse(
                version="1.0.0",
                last_updated="2026-01-01",
                totalAgents=1,
                totalPacks=1,
            ),
        )
        assert len(resp.agents) == 1
        assert len(resp.packs) == 1


# ============================================================================
# TEST CLASS: AGENT METADATA
# ============================================================================


class TestAgentMetadata:
    """Tests for agent metadata extraction."""

    @pytest.mark.asyncio
    async def test_agent_metadata_includes_technology(self, mock_current_user):
        """Verify metadata includes technology field."""
        agents = {
            "test": AgentConfig(
                agent_id="test.001",
                name="TestAgent",
                department="it_security",
                technology="gemini",
                class_name="TestAgent",
            ),
        }
        loader = MagicMock()
        loader.agents = agents
        loader.packs = {}
        loader.load_all = MagicMock(return_value=loader)

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        assert result.agents[0]["metadata"]["technology"] == "gemini"

    @pytest.mark.asyncio
    async def test_agent_without_ooda_profile(self, mock_current_user):
        """Verify agent without OODA profile gets empty capabilities/inputs/outputs."""
        agents = {
            "simple": AgentConfig(
                agent_id="test.simple.001",
                name="SimpleAgent",
                department="admin_lite",
                technology="ollama",
                class_name="SimpleAgent",
                ooda_profile=None,
            ),
        }
        loader = MagicMock()
        loader.agents = agents
        loader.packs = {}
        loader.load_all = MagicMock(return_value=loader)

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        agent = result.agents[0]
        assert agent["capabilities"] == []
        assert agent["inputs"] == []
        assert agent["outputs"] == []

    @pytest.mark.asyncio
    async def test_pack_modes_unique(self, mock_current_user):
        """Verify pack metadata modes are unique set."""
        packs = {
            "test.pack": DomainPack(
                pack_id="test.pack",
                name="Test Pack",
                steps=[
                    WorkflowStep(agent_id="a1", mode="sequential", sla_seconds=10),
                    WorkflowStep(agent_id="a2", mode="sequential", sla_seconds=20),
                    WorkflowStep(agent_id="a3", mode="parallel", sla_seconds=15),
                ],
            ),
        }
        loader = MagicMock()
        loader.agents = {}
        loader.packs = packs
        loader.load_all = MagicMock(return_value=loader)

        with patch(
            "src.core.als.agents.loader.EnterpriseCatalogLoader",
            return_value=loader,
        ):
            result = await get_enterprise_catalog(current_user=mock_current_user, _=1)

        modes = result.packs[0]["metadata"]["modes"]
        assert set(modes) == {"sequential", "parallel"}
        assert result.packs[0]["metadata"]["total_sla_seconds"] == 45
