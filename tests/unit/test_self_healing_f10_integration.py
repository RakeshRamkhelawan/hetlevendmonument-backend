"""F10 integration tests for self-healing pipeline.

These assertions validate real behavior in core modules and endpoint contracts,
without relying on placeholder expectations.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.autonomy.self_healing_system import (
    FailureType,
    RepairStrategy,
    SelfHealingSystem,
    SystemFailure,
)


def _build_failure(failure_id: str, failure_type: FailureType) -> SystemFailure:
    return SystemFailure(
        failure_id=failure_id,
        failure_type=failure_type,
        component="test_component",
        severity=7,
        timestamp=datetime.now(timezone.utc),
        description="integration test failure",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_healing_pipeline_critical_agent():
    system = SelfHealingSystem()
    failure = _build_failure("f10_critical", FailureType.AGENT_CRASH)
    plan = await system.detect_and_diagnose_failure(failure)
    result = await system.execute_repair_plan(plan)

    assert plan.strategy == RepairStrategy.RESTART
    assert result.success is True
    assert "f10_critical" not in system.failures


@pytest.mark.integration
def test_healing_metrics_recorded():
    from src.core.monitoring.healing_metrics import (
        record_failure_detected,
        record_repair_executed,
        set_active_failures,
        set_success_rate,
    )

    record_failure_detected("connection_timeout")
    record_repair_executed("restart", True)
    set_success_rate(0.75)
    set_active_failures(2)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_state_persistence_e2e():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)

    system = SelfHealingSystem(redis_client=mock_redis)
    failure = _build_failure("f10_redis", FailureType.AGENT_CRASH)
    plan = await system.detect_and_diagnose_failure(failure)
    await system.execute_repair_plan(plan)

    assert mock_redis.set.await_count >= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repair_strategy_dispatch_all_types():
    system = SelfHealingSystem()
    expected = {
        FailureType.AGENT_CRASH: RepairStrategy.RESTART,
        FailureType.DATA_CORRUPTION: RepairStrategy.ROLLBACK,
        FailureType.SECURITY_BREACH: RepairStrategy.MANUAL,
        FailureType.PERFORMANCE_DEGRADATION: RepairStrategy.PATCH,
        FailureType.INTEGRATION_FAILURE: RepairStrategy.REPLACE,
    }

    for failure_type, strategy in expected.items():
        failure = _build_failure(f"f10_{failure_type.value}", failure_type)
        plan = await system.detect_and_diagnose_failure(failure)
        assert plan.strategy == strategy


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cooldown_enforcement_multiagent():
    system = SelfHealingSystem()
    failure = _build_failure("f10_cooldown", FailureType.AGENT_CRASH)
    plan = await system.detect_and_diagnose_failure(failure)
    first = await system.execute_repair_plan(plan)
    second = await system.execute_repair_plan(plan)

    assert first.success is True
    assert second.success is False
    assert "cooldown_active" in second.final_status


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_attempts_escalation():
    system = SelfHealingSystem()
    failure = _build_failure("f10_attempts", FailureType.AGENT_CRASH)
    plan = await system.detect_and_diagnose_failure(failure)

    # Simulate four attempts by expiring cooldown manually.
    for _ in range(3):
        await system.execute_repair_plan(plan)
        system._repair_cooldowns["f10_attempts"] = datetime.now(timezone.utc).replace(year=2000)

    rejected = await system.execute_repair_plan(plan)
    assert rejected.success is False
    assert "max_attempts_exceeded" in rejected.final_status


@pytest.mark.integration
@pytest.mark.asyncio
async def test_autonomy_level_reflects_implementation(client, admin_auth_headers):
    with (
        patch("src.core.api.v1.autonomous.agents_router.get_agent_factory") as mock_factory,
        patch("src.core.api.v1.autonomous.agents_router.get_self_healing_system") as mock_healing,
        patch("src.core.api.v1.autonomous.agents_router.get_code_generator") as mock_codegen,
        patch("src.core.api.v1.autonomous.agents_router.get_emergent_intelligence") as mock_emergence,
    ):
        for dep in (mock_factory, mock_healing, mock_codegen, mock_emergence):
            instance = AsyncMock()
            instance.get_system_status = AsyncMock(return_value={"status": "operational"})
            dep.return_value = instance

        response = client.get("/api/v1/autonomous/health", headers=admin_auth_headers)
        assert response.status_code == 200
        autonomy_level = response.json().get("autonomy_level")
        assert autonomy_level in {"stub_phase4", "limited"}
        assert autonomy_level != "full"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_status_reflects_repair_history():
    system = SelfHealingSystem()
    failure = _build_failure("f10_status", FailureType.AGENT_CRASH)
    plan = await system.detect_and_diagnose_failure(failure)
    await system.execute_repair_plan(plan)
    status = await system.get_system_status()

    assert status["repair_history_count"] == 1
    assert status["total_repairs"] == 1
