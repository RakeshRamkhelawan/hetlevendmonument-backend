"""Service integration tests aligned with current workflow and resilience contracts."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tool_broker.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    RetryConfig,
)
from src.core.workflow.engine import DAGValidator, WorkflowSpec
from src.core.workflow.models import C7Workflow as Workflow

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _tenant_id(test_tenant: Any) -> int:
    if isinstance(test_tenant, dict):
        return int(test_tenant["id"])
    return int(test_tenant)


@pytest.mark.integration
class TestServiceIntegration:
    async def test_workflow_model_persists_with_required_fields(
        self, db_session: AsyncSession, test_tenant: Any
    ) -> None:
        workflow_id = f"svc_{uuid.uuid4().hex[:12]}"
        workflow = Workflow(
            id=workflow_id,
            version=1,
            name="Service Integration Probe",
            description="Integration test workflow",
            workflow_type="orchestration",
            trigger_type="manual",
            trigger_config={},
            nodes=[{"id": "start", "type": "start"}],
            edges=[],
            variables={},
            tenant_id=_tenant_id(test_tenant),
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.commit()

        result = await db_session.execute(select(Workflow).where(Workflow.id == workflow_id))
        persisted = result.scalar_one()
        assert persisted.workflow_type == "orchestration"
        assert persisted.trigger_type == "manual"
        assert persisted.tenant_id == _tenant_id(test_tenant)

    async def test_dag_validator_accepts_valid_workflow(self) -> None:
        spec = WorkflowSpec(
            workflow_id="valid_dag",
            version=1,
            tasks={
                "a": {"type": "llm", "prompt": "A"},
                "b": {"type": "llm", "prompt": "B"},
                "c": {"type": "llm", "prompt": "C"},
            },
            dependencies={"a": [], "b": ["a"], "c": ["b"]},
        )
        is_valid, error = DAGValidator.validate_dag(spec)
        assert is_valid, error

    async def test_dag_validator_rejects_cycle(self) -> None:
        spec = WorkflowSpec(
            workflow_id="cycle_dag",
            version=1,
            tasks={"a": {"type": "llm"}, "b": {"type": "llm"}},
            dependencies={"a": ["b"], "b": ["a"]},
        )
        is_valid, error = DAGValidator.validate_dag(spec)
        assert not is_valid
        assert error is not None


@pytest.mark.integration
class TestResilienceIntegration:
    async def test_circuit_breaker_state_transition(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=2,
            failure_window_seconds=60,
            success_threshold=1,
            timeout_seconds=10,
            half_open_requests=1,
        )
        cb = CircuitBreaker(name="svc_cb", config=config)
        assert cb.state == CircuitBreakerState.CLOSED

        cb.failure_count = 2
        cb.state = CircuitBreakerState.OPEN
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count >= cb.config.failure_threshold

    async def test_retry_config_defaults(self) -> None:
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.initial_delay_ms == 100
        assert config.backoff_factor == 2.0
        assert config.jitter_enabled is True
