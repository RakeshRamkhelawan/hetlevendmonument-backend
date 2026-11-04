from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.core.agents.learning_loop import LearningObservation, LearningSource, LearningType
from src.core.learning.services.pattern_service import PatternService


def _tool_observation(
    tool_name: str,
    *,
    agent_id: str = "python-agent",
    agent_type: str = "python_pro",
    success: bool = True,
    error: str | None = None,
    payload: dict | None = None,
    timestamp_offset: int = 0,
) -> LearningObservation:
    return LearningObservation(
        id=f"obs-{tool_name}-{timestamp_offset}-{success}",
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=timestamp_offset),
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
        context={
            "agent_id": agent_id,
            "agent_type": agent_type,
            "task_type": "tool_execution",
        },
        observation_data={
            "tool_name": tool_name,
            "payload": payload or {"value": tool_name},
            "success": success,
            "error": error,
        },
        outcome_metrics={
            "success": 1.0 if success else 0.0,
            "execution_time": 0.1,
            "error_count": 0.0 if success else 1.0,
        },
        confidence_score=0.8,
        importance_score=0.5,
    )


def test_toolbroker_pattern_types_are_defined() -> None:
    assert PatternService.TOOLBROKER_PATTERN_TYPES == (
        "tool_usage_frequency",
        "tool_failure_correlation",
        "circuit_breaker_trigger",
        "tool_chain_optimization",
    )


@pytest.mark.asyncio
async def test_analyze_tool_patterns_detects_usage_frequency() -> None:
    service = PatternService(tenant_id=17)
    observations = [_tool_observation("test__echo", timestamp_offset=index) for index in range(10)]

    patterns = await service.analyze_tool_patterns(observations)

    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "tool_usage_frequency"
        for pattern in patterns
    )


@pytest.mark.asyncio
async def test_analyze_tool_patterns_detects_failure_correlation() -> None:
    service = PatternService(tenant_id=17)
    observations = [
        _tool_observation(
            "test__fail",
            success=False,
            error="validation failed",
            payload={"kind": "bad-input"},
            timestamp_offset=index,
        )
        for index in range(3)
    ]

    patterns = await service.analyze_tool_patterns(observations)

    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "tool_failure_correlation"
        for pattern in patterns
    )


@pytest.mark.asyncio
async def test_analyze_tool_patterns_detects_circuit_breaker_trigger() -> None:
    service = PatternService(tenant_id=17)
    observations = [
        _tool_observation(
            "serena__search",
            success=False,
            error="Circuit breaker open for serena__search",
            timestamp_offset=index,
        )
        for index in range(3)
    ]

    patterns = await service.analyze_tool_patterns(observations)

    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "circuit_breaker_trigger"
        for pattern in patterns
    )


@pytest.mark.asyncio
async def test_analyze_tool_patterns_detects_tool_chain_optimization() -> None:
    service = PatternService(tenant_id=17)
    observations = []
    for index in range(6):
        observations.append(_tool_observation("test__echo", timestamp_offset=index * 2))
        observations.append(_tool_observation("test__slow", timestamp_offset=index * 2 + 1))

    patterns = await service.analyze_tool_patterns(observations)

    assert any(
        pattern.learned_behavior.get("pattern_subtype") == "tool_chain_optimization"
        for pattern in patterns
    )


@pytest.mark.asyncio
async def test_analyze_tool_patterns_skips_insufficient_data() -> None:
    service = PatternService(tenant_id=17)
    observations = [_tool_observation("test__echo", timestamp_offset=index) for index in range(3)]

    patterns = await service.analyze_tool_patterns(observations)

    assert patterns == []
