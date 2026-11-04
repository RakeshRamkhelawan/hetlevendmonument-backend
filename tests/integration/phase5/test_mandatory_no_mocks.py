from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.agents.learning_loop import LearningType
from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.publisher import DomainEvent
from src.core.learning.cross_agent_service import CrossAgentLearningService
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_cross_agent_sharing_with_real_db(
    phase5_learning_env, phase5_session_factory
) -> None:
    repo = LearningRepository(phase5_session_factory)
    pattern_service = PatternService(tenant_id=17, repository=repo)
    cross_agent_service = CrossAgentLearningService(tenant_id=17, pattern_service=pattern_service)

    pattern = await pattern_service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions={
            "agent_id": "python-agent",
            "agent_type": "python_pro",
            "task_type": "tool_execution",
            "source": "task_execution",
        },
        learned_behavior={"recommended_action": "reuse_path", "source": "task_execution"},
        observation_count=12,
        success_rate=0.9,
        confidence_score=0.88,
    )

    shared = await cross_agent_service.share_pattern(pattern, "python_pro")

    reloaded = PatternService(tenant_id=17, repository=repo)
    await reloaded.load_from_db()
    assert len(shared) == 3
    assert len(reloaded.get_patterns_by_agent_type("ai_engineer")) == 1


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_tool_pattern_detection_from_real_observations(
    phase5_learning_env, phase5_session_factory
) -> None:
    repo = LearningRepository(phase5_session_factory)
    observation_service = ObservationService(
        tenant_id=17,
        repository=repo,
        observation_threshold=999,
    )
    handler = LearningEventHandler(observation_service=observation_service, tenant_id=17)

    for index in range(10):
        event = DomainEvent(
            event_id=f"tool-event-{index}",
            event_type="tool.executed",
            aggregate_id="python-agent",
            aggregate_type="ToolExecution",
            data={
                "tool_name": "test__echo",
                "agent_id": "python-agent",
                "payload": {"index": index},
                "result": {"ok": True},
                "duration_seconds": 0.1,
                "success": True,
                "tenant_id": 17,
            },
            timestamp=datetime.now(timezone.utc),
            metadata={"agent_type": "python_pro", "source": "tool_broker"},
        )
        await handler.handle_tool_executed(event)

    patterns = await observation_service.pattern_service.analyze_tool_patterns(
        list(observation_service.observation_buffer)
    )
    reloaded = PatternService(tenant_id=17, repository=repo)
    await reloaded.load_from_db()

    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "tool_usage_frequency"
        for pattern in patterns
    )
    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "tool_usage_frequency"
        for pattern in reloaded.get_patterns_by_agent_type("python_pro")
    )
