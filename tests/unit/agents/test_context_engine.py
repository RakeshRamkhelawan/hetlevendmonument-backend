import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_ai_context_engine_stores_tenant_id():
    from src.core.agents.context_engine import AIContextEngine

    mock_session = AsyncMock()
    engine = AIContextEngine(db=mock_session, tenant_id=42)
    assert engine._tenant_id == 42


def test_enriched_context_defaults_are_empty():
    from src.core.agents.context_engine import EnrichedContext

    ctx = EnrichedContext()
    assert ctx.context == {}
    assert ctx.twin_profile == {}
    assert ctx.surface == ""
    assert ctx.query == ""


@pytest.mark.asyncio
async def test_enrich_returns_enriched_context():
    from src.core.agents.context_engine import AIContextEngine, EnrichedContext

    mock_session = AsyncMock()
    with patch("src.core.agents.context_engine.ContextPackerService") as MockPacker:
        mock_packer_instance = AsyncMock()
        mock_packer_instance.build.return_value = {"profile": None}
        MockPacker.return_value = mock_packer_instance

        engine = AIContextEngine(db=mock_session, tenant_id=1)
        result = await engine.enrich(
            agent_id="cva",
            query="wat zijn mijn openstaande taken?",
            surface="copilot",
        )
        assert isinstance(result, EnrichedContext)


@pytest.mark.asyncio
async def test_enriched_context_has_twin_profile_from_agent_memory_profile():
    from src.core.agents.context_engine import AIContextEngine

    mock_session = AsyncMock()
    with patch("src.core.agents.context_engine.ContextPackerService") as MockPacker:
        mock_profile = MagicMock()
        mock_profile.persona_name = "Sprint Helper"
        mock_profile.persona_description = "Assists with sprint planning"
        mock_profile.active_goals = [{"id": "g1", "title": "finish sprint"}]
        mock_profile.operating_rules = []
        mock_profile.domain_expertise = []
        mock_profile.agent_type = "copilot"

        mock_packer_instance = AsyncMock()
        mock_packer_instance.build.return_value = {"profile": mock_profile}
        MockPacker.return_value = mock_packer_instance

        engine = AIContextEngine(db=mock_session, tenant_id=1)
        result = await engine.enrich(agent_id="cva", query="test", surface="copilot")

        assert isinstance(result.twin_profile, dict)
        assert result.twin_profile.get("persona_name") == "Sprint Helper"


@pytest.mark.asyncio
async def test_enrich_calls_context_packer_service():
    from src.core.agents.context_engine import AIContextEngine

    mock_session = AsyncMock()
    with patch("src.core.agents.context_engine.ContextPackerService") as MockPacker:
        mock_packer_instance = AsyncMock()
        mock_packer_instance.build.return_value = {"profile": None, "memory": "test_context"}
        MockPacker.return_value = mock_packer_instance

        engine = AIContextEngine(db=mock_session, tenant_id=42)
        await engine.enrich(agent_id="cva", query="test", surface="copilot")

        MockPacker.assert_called_once_with(db=mock_session, tenant_id=42)
        mock_packer_instance.build.assert_called_once_with(agent_id="cva")


@pytest.mark.asyncio
async def test_enrich_graceful_on_packer_failure():
    from src.core.agents.context_engine import AIContextEngine, EnrichedContext

    mock_session = AsyncMock()
    with patch("src.core.agents.context_engine.ContextPackerService") as MockPacker:
        mock_packer_instance = AsyncMock()
        mock_packer_instance.build.side_effect = Exception("DB fout")
        MockPacker.return_value = mock_packer_instance

        engine = AIContextEngine(db=mock_session, tenant_id=1)
        result = await engine.enrich(agent_id="cva", query="test", surface="copilot")

        assert isinstance(result, EnrichedContext)
        assert result.context == {}
        assert result.surface == "copilot"
        assert result.query == "test"
