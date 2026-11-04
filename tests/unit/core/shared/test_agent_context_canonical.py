"""Tests for the canonical src.core.shared.agent_context import path.

Ensures the extracted module is independently importable -- not just via the
backward-compat re-export in src.core.company.context.
"""

import uuid

import pytest
from pydantic import ValidationError

from src.core.shared.agent_context import (
    AgentExecutionContext,
    BudgetScope,
    GoalChain,
    PolicyScope,
)


def test_agent_execution_context_canonical_import() -> None:
    """AgentExecutionContext is importable directly from shared.agent_context."""
    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
    )
    assert ctx.tenant_id == 1
    assert ctx.is_degraded is False


def test_agent_execution_context_is_same_class_as_reexport() -> None:
    """Re-export in company.context must point to the same class object."""
    from src.core.company.context import AgentExecutionContext as AECReexport

    assert AgentExecutionContext is AECReexport


def test_goal_chain_default_is_incomplete() -> None:
    """Empty GoalChain reports incomplete."""
    chain = GoalChain()
    assert chain.is_complete() is False
    assert chain.depth() == 0


def test_goal_chain_complete_when_mission_and_task_set() -> None:
    chain = GoalChain(mission_id=uuid.uuid4(), task_goal_id=uuid.uuid4())
    assert chain.is_complete() is True
    assert chain.depth() == 2


def test_policy_scope_literal_rejects_invalid_risk_level() -> None:
    """Pydantic Literal annotation rejects invalid risk_level values."""
    with pytest.raises(ValidationError):
        PolicyScope(risk_level="INVALID")


def test_policy_scope_valid_risk_levels() -> None:
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        scope = PolicyScope(risk_level=level)
        assert scope.risk_level == level


def test_budget_scope_calculates_remaining_pct() -> None:
    scope = BudgetScope(monthly_token_budget=1000, tokens_consumed_this_month=250)
    assert scope.budget_remaining_pct == pytest.approx(0.75)


def test_agent_execution_context_validate_completeness_degraded() -> None:
    ctx = AgentExecutionContext(
        tenant_id=5,
        task_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
    )
    is_valid, missing = ctx.validate_completeness()
    assert is_valid is False
    assert "company_id" in missing
    assert ctx.is_degraded is True


def test_agent_execution_context_uuid_string_coercion() -> None:
    """UUID strings must be coerced to UUID objects by field_validator."""
    task_id = uuid.uuid4()
    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=str(task_id),
        trace_id=str(uuid.uuid4()),
    )
    assert ctx.task_id == task_id
