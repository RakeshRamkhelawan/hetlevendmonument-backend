from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.agents.learning_loop import LearningPattern, LearningType
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.als.synapse.synapse_network import SynapseNetwork
from src.core.learning.cross_agent_service import CrossAgentLearningService
from src.core.learning.services.pattern_service import PatternService
from src.core.shared.config import reload_settings


def _make_pattern(agent_type: str, confidence: float = 0.85) -> LearningPattern:
    return LearningPattern(
        id=f"pattern-{agent_type}",
        pattern_type=LearningType.PATTERN_RECOGNITION,
        description=f"Pattern for {agent_type}",
        trigger_conditions={
            "agent_id": f"{agent_type}-agent",
            "agent_type": agent_type,
            "task_type": "tool_execution",
            "source": "task_execution",
        },
        learned_behavior={
            "recommended_action": "reuse_successful_path",
            "source": "task_execution",
        },
        success_rate=0.9,
        confidence_score=confidence,
        observation_count=12,
        last_updated=datetime.now(timezone.utc),
    )


@pytest.fixture
def learning_enabled_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()
    yield
    monkeypatch.delenv("FEATURE_LEARNING_ENABLED", raising=False)
    reload_settings()


def test_get_related_agent_types_is_bidirectional() -> None:
    service = CrossAgentLearningService(tenant_id=17)

    python_related = service.get_related_agent_types("python_pro")
    ai_related = service.get_related_agent_types("ai_engineer")

    assert "ai_engineer" in python_related
    assert "python_pro" in ai_related
    assert service.get_related_agent_types("unknown_agent") == []


@pytest.mark.asyncio
async def test_share_pattern_registers_patterns_for_related_agents(
    learning_enabled_env,
) -> None:
    pattern_service = PatternService(tenant_id=17)
    service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    shared = await service.share_pattern(_make_pattern("python_pro"), "python_pro")

    shared_agent_types = {pattern.trigger_conditions.get("agent_type") for pattern in shared}
    assert shared_agent_types == {"ai_engineer", "data_scientist", "ml_engineer"}
    assert all(
        pattern.learned_behavior.get("shared_from_agent_type") == "python_pro" for pattern in shared
    )


@pytest.mark.asyncio
async def test_share_pattern_rejects_low_confidence_patterns(
    learning_enabled_env,
) -> None:
    pattern_service = PatternService(tenant_id=17)
    service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    shared = await service.share_pattern(_make_pattern("python_pro", confidence=0.4), "python_pro")

    assert shared == []
    assert pattern_service.patterns == {}


@pytest.mark.asyncio
async def test_share_pattern_returns_empty_when_learning_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()
    service = CrossAgentLearningService(tenant_id=17, pattern_service=PatternService(tenant_id=17))

    shared = await service.share_pattern(_make_pattern("python_pro"), "python_pro")

    assert shared == []
    monkeypatch.delenv("FEATURE_LEARNING_ENABLED", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_share_pattern_returns_empty_without_related_agents(learning_enabled_env) -> None:
    service = CrossAgentLearningService(
        tenant_id=17,
        pattern_service=PatternService(tenant_id=17),
        relations_map={"solo_agent": set()},
    )

    shared = await service.share_pattern(_make_pattern("solo_agent"), "solo_agent")

    assert shared == []


@pytest.mark.asyncio
async def test_get_related_patterns_filters_by_related_agent_type(
    learning_enabled_env,
) -> None:
    pattern_service = PatternService(tenant_id=17)
    service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    await service.share_pattern(_make_pattern("python_pro"), "python_pro")
    pattern_service.patterns["unrelated"] = _make_pattern("finance_pro")

    patterns = await service.get_related_patterns("python_pro", task_type="tool_execution")

    assert patterns
    assert all(
        pattern.trigger_conditions.get("agent_type")
        in {"ai_engineer", "data_scientist", "ml_engineer"}
        for pattern in patterns
    )


@pytest.mark.asyncio
async def test_dynamic_synapse_relations_extend_static_map(learning_enabled_env) -> None:
    pattern_service = PatternService(tenant_id=17)
    synapse_network = SynapseNetwork(tenant_id=17)
    await synapse_network.record_collaboration(
        agent_a_id="custom_agent_a",
        agent_b_id="custom_agent_b",
        task_type="tool_execution",
        success=True,
        quality_score=0.95,
    )
    service = CrossAgentLearningService(
        tenant_id=17,
        pattern_service=pattern_service,
        synapse_network=synapse_network,
    )

    shared = await service.share_pattern(_make_pattern("custom_agent_a"), "custom_agent_a")

    assert {pattern.trigger_conditions.get("agent_type") for pattern in shared} == {
        "custom_agent_b"
    }


@pytest.mark.asyncio
async def test_dynamic_synapse_failures_are_ignored(learning_enabled_env) -> None:
    pattern_service = PatternService(tenant_id=17)

    class BrokenSynapse:
        async def get_partner_rankings(self, agent_type: str, task_type=None):
            raise RuntimeError("synapse offline")

    service = CrossAgentLearningService(
        tenant_id=17,
        pattern_service=pattern_service,
        synapse_network=BrokenSynapse(),
    )

    assert await service._get_dynamic_related_agent_types("python_pro", "tool_execution") == []


@pytest.mark.asyncio
async def test_get_related_patterns_loads_repository_once_and_filters_task_type(
    learning_enabled_env,
) -> None:
    pattern_service = PatternService(tenant_id=17)
    service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)
    service.pattern_service._repository = object()
    service.pattern_service.load_from_db = AsyncMock()
    pattern_service.patterns = {
        "matching": _make_pattern("ai_engineer"),
        "non_matching": LearningPattern(
            id="pattern-other-task",
            pattern_type=LearningType.PATTERN_RECOGNITION,
            description="Other task",
            trigger_conditions={"agent_type": "ai_engineer", "task_type": "other"},
            learned_behavior={"recommended_action": "skip"},
            success_rate=0.9,
            confidence_score=0.95,
            observation_count=4,
            last_updated=datetime.now(timezone.utc),
        ),
    }

    first = await service.get_related_patterns("python_pro", task_type="tool_execution")
    second = await service.get_related_patterns("python_pro", task_type="tool_execution")

    assert len(first) == 1
    assert len(second) == 1
    service.pattern_service.load_from_db.assert_awaited_once()


@pytest.mark.asyncio
async def test_share_pattern_registration_failures_do_not_raise(learning_enabled_env) -> None:
    pattern_service = PatternService(tenant_id=17)
    pattern_service.register = AsyncMock(side_effect=RuntimeError("db write failed"))
    service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    shared = await service.share_pattern(_make_pattern("python_pro"), "python_pro")

    assert shared == []


@pytest.mark.asyncio
async def test_specialist_cross_agent_prompt_includes_shared_patterns() -> None:
    config = {
        "agent_id": "python-specialist",
        "technology": "python_pro",
        "name": "Python Specialist",
        "description": "Handles Python tasks",
        "allowed_tools": ["test__echo"],
    }

    with (
        patch("src.core.als.agents.specialist_base.LLMService"),
        patch("src.core.als.agents.specialist_base.ToolBrokerService"),
    ):
        agent = BaseSpecialistAgent(config=config, tenant_id=17)

    agent._cross_agent_learning_service.get_related_patterns = AsyncMock(
        return_value=[
            LearningPattern(
                id="shared-1",
                pattern_type=LearningType.PATTERN_RECOGNITION,
                description="Shared AI engineer pattern",
                trigger_conditions={"agent_type": "ai_engineer", "task_type": "tool_execution"},
                learned_behavior={
                    "shared_from_agent_type": "ai_engineer",
                    "pattern_subtype": "tool_chain_optimization",
                },
                success_rate=0.9,
                confidence_score=0.9,
                observation_count=8,
                last_updated=datetime.now(timezone.utc),
            )
        ]
    )

    context = await agent._get_cross_agent_prompt_context({"metadata": {"type": "tool_execution"}})

    assert "Shared Patterns From Related Agents" in context
    assert "ai_engineer" in context
    assert "tool_chain_optimization" in context
