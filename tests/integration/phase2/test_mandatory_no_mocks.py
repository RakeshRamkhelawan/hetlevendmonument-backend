from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for integration tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.learning.services.observation_service import ObservationService
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


class RecordingPublisher:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event, routing_key=None) -> None:
        self.events.append((event, routing_key))


class NullClient:
    async def call(self, tool_name, payload):
        raise RuntimeError(f"Unexpected external tool call: {tool_name}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_tool_event_flows_to_observation(phase2_learning_env, phase2_session_factory) -> None:
    repo = LearningRepository(phase2_session_factory)
    observation_service = ObservationService(
        tenant_id=17,
        repository=repo,
        observation_threshold=999,
    )
    handler = LearningEventHandler(observation_service=observation_service, tenant_id=17)
    publisher = RecordingPublisher()
    broker = ToolBrokerService(
        serena_client=NullClient(),
        seq_thinking_client=NullClient(),
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )

    # De tenant hoort in de EXECUTIECONTEXT, niet in de payload (ADR-036 OP-27, ronde 2). De
    # payload is modeluitvoer; hem daar lezen betekent dat een model zijn eigen tenant kan kiezen.
    # Deze test gaf hem eerder als payload-sleutel mee en liep daarop stuk zodra de broker dat
    # weigerde -- de test legde dus de onveilige vorm vast.
    result = await broker.execute_tool(
        "test__echo",
        {"index": 1},
        agent_id="phase2-agent",
        context={"tenant_id": 17},
    )
    assert result["tool"] == "test__echo"
    await asyncio.sleep(0)
    assert len(publisher.events) == 1

    event, routing_key = publisher.events[0]
    event.metadata = {"agent_type": "python_pro", "source": "tool_broker"}
    event.timestamp = datetime.now(timezone.utc)
    assert routing_key == "tool.executed"

    observation_id = await handler.handle_tool_executed(event)

    async with phase2_session_factory() as session:
        rows = (await session.execute(select(LearningExperience))).scalars().all()

    assert observation_id is not None
    assert len(rows) == 1
    assert rows[0].task_type == "tool_execution"
    assert rows[0].context["tool_name"] == "test__echo"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_full_service_chain(phase2_learning_env, phase2_session_factory) -> None:
    repo = LearningRepository(phase2_session_factory)
    observation_service = ObservationService(
        tenant_id=17,
        repository=repo,
        observation_threshold=3,
    )

    for index in range(3):
        await observation_service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
            context={
                "agent_id": "phase2-chain-agent",
                "agent_type": "python_pro",
                "task_type": "tool_execution",
            },
            observation_data={
                "tool_name": "test__echo",
                "payload": {"index": index},
                "result": {"ok": True},
                "success": True,
            },
            outcome_metrics={"execution_time": 0.1, "success": 1.0, "error_count": 0.0},
        )

    async with phase2_session_factory() as session:
        patterns = (await session.execute(select(LearningPatternModel))).scalars().all()
        rules = (await session.execute(select(AdaptationRuleModel))).scalars().all()
        insights = (await session.execute(select(LearningInsightModel))).scalars().all()

    assert len(patterns) >= 1
    assert len(rules) >= 1
    assert len(insights) >= 1
