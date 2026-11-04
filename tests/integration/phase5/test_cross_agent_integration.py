from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.agents.learning_loop import LearningPattern, LearningType
from src.core.als.synapse.synapse_network import SynapseNetwork
from src.core.learning.cross_agent_service import CrossAgentLearningService
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.services.pattern_service import PatternService


def _pattern(agent_type: str) -> LearningPattern:
    return LearningPattern(
        id=f"pattern-{agent_type}",
        pattern_type=LearningType.PATTERN_RECOGNITION,
        description=f"Integration pattern for {agent_type}",
        trigger_conditions={
            "agent_id": f"{agent_type}-agent",
            "agent_type": agent_type,
            "task_type": "tool_execution",
            "source": "task_execution",
        },
        learned_behavior={"recommended_action": "reuse_path", "source": "task_execution"},
        success_rate=0.92,
        confidence_score=0.88,
        observation_count=14,
        last_updated=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cross_agent_sharing_persists_related_patterns(
    phase5_learning_env, phase5_session_factory
) -> None:
    repo = LearningRepository(phase5_session_factory)
    pattern_service = PatternService(tenant_id=17, repository=repo)
    cross_agent_service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    pattern = await pattern_service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions=_pattern("python_pro").trigger_conditions,
        learned_behavior=_pattern("python_pro").learned_behavior,
        observation_count=14,
        success_rate=0.92,
        confidence_score=0.88,
    )
    shared = await cross_agent_service.share_pattern(pattern, "python_pro")

    reloaded = PatternService(tenant_id=17, repository=repo)
    await reloaded.load_from_db()
    shared_agent_types = {
        item.trigger_conditions.get("agent_type")
        for item in reloaded.get_patterns_by_agent_type(None)
        if item.learned_behavior.get("shared_pattern")
    }

    assert len(shared) == 3
    assert shared_agent_types == {"ai_engineer", "data_scientist", "ml_engineer"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cross_agent_sharing_preserves_tenant_isolation(
    phase5_learning_env, phase5_session_factory
) -> None:
    repo = LearningRepository(phase5_session_factory)
    tenant_a_patterns = PatternService(tenant_id=17, repository=repo)
    tenant_b_patterns = PatternService(tenant_id=99, repository=repo)
    sharing = CrossAgentLearningService(tenant_id=17, pattern_service=tenant_a_patterns)

    pattern = await tenant_a_patterns.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions=_pattern("python_pro").trigger_conditions,
        learned_behavior=_pattern("python_pro").learned_behavior,
        observation_count=14,
        success_rate=0.92,
        confidence_score=0.88,
    )
    await sharing.share_pattern(pattern, "python_pro")

    await tenant_b_patterns.load_from_db()

    assert tenant_b_patterns.get_patterns_by_agent_type(None) == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cross_agent_sharing_uses_dynamic_synapse_relations(
    phase5_learning_env, phase5_session_factory
) -> None:
    repo = LearningRepository(phase5_session_factory)
    pattern_service = PatternService(tenant_id=17, repository=repo)
    synapse_network = SynapseNetwork(tenant_id=17)
    await synapse_network.record_collaboration(
        agent_a_id="custom_agent_a",
        agent_b_id="custom_agent_b",
        task_type="tool_execution",
        success=True,
        quality_score=0.9,
    )
    service = CrossAgentLearningService(
        tenant_id=17,
        pattern_service=pattern_service,
        synapse_network=synapse_network,
    )

    pattern = await pattern_service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions=_pattern("custom_agent_a").trigger_conditions,
        learned_behavior=_pattern("custom_agent_a").learned_behavior,
        observation_count=14,
        success_rate=0.92,
        confidence_score=0.88,
    )
    shared = await service.share_pattern(pattern, "custom_agent_a")

    assert [item.trigger_conditions.get("agent_type") for item in shared] == ["custom_agent_b"]
