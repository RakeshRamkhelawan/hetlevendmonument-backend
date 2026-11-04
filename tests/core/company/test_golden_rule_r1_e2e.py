"""End-to-end smoke test: Golden Rule R1 — context flows through TaskData."""

from uuid import uuid4

from src.core.company.context import AgentExecutionContext, BudgetScope, GoalChain, PolicyScope
from src.core.shared.interfaces import TaskData


def test_r1_context_roundtrip():
    """AgentExecutionContext attached to TaskData is accessible after creation."""
    ctx = AgentExecutionContext(
        tenant_id=42,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
        policy_scope=PolicyScope(),
        budget_scope=BudgetScope(),
    )

    task = TaskData(
        title="Analyse Q1 financials",
        description="Run financial analysis for Q1",
        company_context=ctx,
    )

    assert task.company_context is not None
    assert task.company_context.tenant_id == 42
    assert task.company_context.goal_chain.mission_id == ctx.goal_chain.mission_id


def test_r1_context_validate_completeness():
    """Context attached to task can validate its own completeness."""
    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4(), task_goal_id=uuid4()),
    )

    task = TaskData(title="t", description="d", company_context=ctx)
    is_complete, missing = task.company_context.validate_completeness()

    # Should be complete with company_id + mission_id + task_goal_id
    assert is_complete, f"Context incomplete: {missing}"


def test_r1_backward_compat_no_context():
    """TaskData without company_context still works — no breaking change."""
    task = TaskData(title="legacy", description="old code path")
    assert task.company_context is None
    assert task.context == {}  # existing property alias still works


def test_r1_context_with_full_goal_chain():
    """Complete goal chain from mission to task."""
    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(
            mission_id=uuid4(),
            mission_title="Company Mission",
            strategic_goal_id=uuid4(),
            strategic_goal_title="Strategic Goal",
            project_goal_id=uuid4(),
            project_goal_title="Project Goal",
            task_goal_id=uuid4(),
            task_goal_title="Task Goal",
        ),
        policy_scope=PolicyScope(risk_level="MEDIUM"),
        budget_scope=BudgetScope(monthly_token_budget=10000, tokens_consumed_this_month=1000),
    )

    task = TaskData(title="Full test", description="Test", company_context=ctx)

    assert task.company_context.goal_chain.is_complete()
    assert task.company_context.goal_chain.depth() == 4
    assert task.company_context.policy_scope.risk_level == "MEDIUM"
    assert task.company_context.budget_scope.budget_remaining_pct == 0.9
