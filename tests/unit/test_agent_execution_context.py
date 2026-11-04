"""Tests for AgentExecutionContext and GoalChain - Taak 1.3

TDD tests for the canonical AgentExecutionContext object and GoalChain hierarchy validator.
"""

import uuid
from datetime import datetime
from typing import Optional

import pytest
from pydantic import ValidationError

# These imports will fail until we create the context.py file
# from src.core.company.context import (
#     AgentExecutionContext,
#     BudgetScope,
#     GoalChain,
#     PolicyScope,
# )


# ============================================================================
# Happy Path Tests
# ============================================================================


class TestGoalChainHappyPath:
    """Happy path tests for GoalChain"""

    def test_goal_chain_complete(self):
        """GoalChain with mission_id + task_goal_id → is_complete() == True"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            mission_id=uuid.uuid4(),
            mission_title="Company Mission",
            strategic_goal_id=uuid.uuid4(),
            strategic_goal_title="Strategic Goal",
            project_goal_id=uuid.uuid4(),
            project_goal_title="Project Goal",
            task_goal_id=uuid.uuid4(),
            task_goal_title="Task Goal",
        )

        assert chain.is_complete() is True

    def test_goal_chain_depth_four_levels(self):
        """GoalChain with 4 levels → depth() == 4"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            mission_id=uuid.uuid4(),
            strategic_goal_id=uuid.uuid4(),
            project_goal_id=uuid.uuid4(),
            task_goal_id=uuid.uuid4(),
        )

        assert chain.depth() == 4

    def test_goal_chain_depth_three_levels(self):
        """GoalChain with 3 levels → depth() == 3"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            mission_id=uuid.uuid4(),
            strategic_goal_id=uuid.uuid4(),
            project_goal_id=uuid.uuid4(),
        )

        assert chain.depth() == 3

    def test_goal_chain_depth_two_levels(self):
        """GoalChain with 2 levels → depth() == 2"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            mission_id=uuid.uuid4(),
            strategic_goal_id=uuid.uuid4(),
        )

        assert chain.depth() == 2

    def test_goal_chain_depth_one_level(self):
        """GoalChain with 1 level → depth() == 1"""
        from src.core.company.context import GoalChain

        chain = GoalChain(mission_id=uuid.uuid4())

        assert chain.depth() == 1

    def test_goal_chain_depth_zero(self):
        """Empty GoalChain → depth() == 0"""
        from src.core.company.context import GoalChain

        chain = GoalChain()

        assert chain.depth() == 0

    def test_goal_chain_from_ancestry(self):
        """List of goals → correct GoalChain built via class method"""
        from src.core.company.context import GoalChain

        # Simulate ancestry list from parent to child
        goals = [
            {"id": uuid.uuid4(), "title": "Mission", "goal_type": "mission"},
            {"id": uuid.uuid4(), "title": "Strategic", "goal_type": "strategic"},
            {"id": uuid.uuid4(), "title": "Project", "goal_type": "project"},
            {"id": uuid.uuid4(), "title": "Task", "goal_type": "task"},
        ]

        chain = GoalChain.from_ancestry(goals)

        assert chain.mission_id == goals[0]["id"]
        assert chain.mission_title == "Mission"
        assert chain.strategic_goal_id == goals[1]["id"]
        assert chain.strategic_goal_title == "Strategic"
        assert chain.project_goal_id == goals[2]["id"]
        assert chain.project_goal_title == "Project"
        assert chain.task_goal_id == goals[3]["id"]
        assert chain.task_goal_title == "Task"
        assert chain.is_complete() is True

    def test_goal_chain_from_ancestry_partial(self):
        """Partial ancestry list → GoalChain with only available levels"""
        from src.core.company.context import GoalChain

        goals = [
            {"id": uuid.uuid4(), "title": "Mission", "goal_type": "mission"},
            {"id": uuid.uuid4(), "title": "Strategic", "goal_type": "strategic"},
        ]

        chain = GoalChain.from_ancestry(goals)

        assert chain.mission_id is not None
        assert chain.strategic_goal_id is not None
        assert chain.project_goal_id is None
        assert chain.task_goal_id is None
        assert chain.depth() == 2

    def test_goal_chain_from_ancestry_empty(self):
        """Empty ancestry list → empty GoalChain"""
        from src.core.company.context import GoalChain

        chain = GoalChain.from_ancestry([])

        assert chain.mission_id is None
        assert chain.depth() == 0

    def test_goal_chain_default_constructor(self):
        """GoalChain with no arguments → all fields None"""
        from src.core.company.context import GoalChain

        chain = GoalChain()

        assert chain.mission_id is None
        assert chain.mission_title is None
        assert chain.strategic_goal_id is None
        assert chain.strategic_goal_title is None
        assert chain.project_goal_id is None
        assert chain.project_goal_title is None
        assert chain.task_goal_id is None
        assert chain.task_goal_title is None


class TestPolicyScopeHappyPath:
    """Happy path tests for PolicyScope"""

    def test_policy_scope_defaults(self):
        """Default risk_level is LOW"""
        from src.core.company.context import PolicyScope

        scope = PolicyScope()

        assert scope.risk_level == "LOW"
        assert scope.requires_approval is False
        assert scope.approval_board_role is None
        assert scope.allowed_actions == []
        assert scope.forbidden_actions == []

    def test_policy_scope_high_risk(self):
        """PolicyScope with HIGH risk level"""
        from src.core.company.context import PolicyScope

        scope = PolicyScope(
            risk_level="HIGH",
            requires_approval=True,
            approval_board_role="CTO",
            allowed_actions=["read", "write"],
            forbidden_actions=["delete"],
        )

        assert scope.risk_level == "HIGH"
        assert scope.requires_approval is True
        assert scope.approval_board_role == "CTO"
        assert scope.allowed_actions == ["read", "write"]
        assert scope.forbidden_actions == ["delete"]


class TestBudgetScopeHappyPath:
    """Happy path tests for BudgetScope"""

    def test_budget_scope_defaults(self):
        """Default BudgetScope has None values"""
        from src.core.company.context import BudgetScope

        scope = BudgetScope()

        assert scope.monthly_token_budget is None
        assert scope.tokens_consumed_this_month is None
        assert scope.budget_remaining_pct is None

    def test_budget_scope_remaining_pct_calculation(self):
        """Correct remaining percentage calculation"""
        from src.core.company.context import BudgetScope

        scope = BudgetScope(
            monthly_token_budget=10000,
            tokens_consumed_this_month=2500,
        )

        assert scope.budget_remaining_pct == 0.75  # 75% remaining

    def test_budget_scope_remaining_pct_zero_consumed(self):
        """Budget with zero consumed → 100% remaining"""
        from src.core.company.context import BudgetScope

        scope = BudgetScope(
            monthly_token_budget=10000,
            tokens_consumed_this_month=0,
        )

        assert scope.budget_remaining_pct == 1.0

    def test_budget_scope_remaining_pct_fully_consumed(self):
        """Budget fully consumed → 0% remaining"""
        from src.core.company.context import BudgetScope

        scope = BudgetScope(
            monthly_token_budget=10000,
            tokens_consumed_this_month=10000,
        )

        assert scope.budget_remaining_pct == 0.0

    def test_budget_scope_remaining_pct_no_budget(self):
        """No budget set → None remaining percentage"""
        from src.core.company.context import BudgetScope

        scope = BudgetScope(tokens_consumed_this_month=5000)

        assert scope.budget_remaining_pct is None


class TestAgentExecutionContextHappyPath:
    """Happy path tests for AgentExecutionContext"""

    def test_context_valid_complete(self):
        """Complete context → validate_completeness() == (True, [])"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=uuid.uuid4(),
            company_type="mkb",
            sector="technology",
            department_id=uuid.uuid4(),
            department_name="Engineering",
            board_role="CTO",
            pack_id=uuid.uuid4(),
            pack_name="IT Operations",
            procedure_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
            # policy_scope and budget_scope use defaults (not None)
            sla_seconds=3600,
        )

        is_valid, missing_fields = context.validate_completeness()

        assert is_valid is True
        assert missing_fields == []
        assert context.is_degraded is False

    def test_context_json_serializable(self):
        """context.model_dump_json() works"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(mission_id=uuid.uuid4()),
        )

        json_str = context.model_dump_json()

        assert isinstance(json_str, str)
        assert "tenant_id" in json_str
        assert "company_id" in json_str
        assert "goal_chain" in json_str

    def test_context_with_default_goal_chain(self):
        """Context without explicit goal_chain gets default empty GoalChain"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
        )

        assert isinstance(context.goal_chain, GoalChain)
        assert context.goal_chain.depth() == 0

    def test_context_with_default_policy_scope(self):
        """Context without explicit policy_scope gets default PolicyScope"""
        from src.core.company.context import AgentExecutionContext, PolicyScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
        )

        assert isinstance(context.policy_scope, PolicyScope)
        assert context.policy_scope.risk_level == "LOW"

    def test_context_with_default_budget_scope(self):
        """Context without explicit budget_scope gets default BudgetScope"""
        from src.core.company.context import AgentExecutionContext, BudgetScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
        )

        assert isinstance(context.budget_scope, BudgetScope)

    def test_context_optional_fields_none(self):
        """Context with only required fields works"""
        from src.core.company.context import AgentExecutionContext

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            # All other fields are optional
        )

        assert context.company_id is None
        assert context.department_id is None
        assert context.pack_id is None


# ============================================================================
# Unhappy Path Tests
# ============================================================================


class TestGoalChainUnhappyPath:
    """Unhappy path tests for GoalChain"""

    def test_goal_chain_incomplete_no_mission(self):
        """GoalChain without mission_id → is_complete() == False"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            strategic_goal_id=uuid.uuid4(),
            task_goal_id=uuid.uuid4(),
        )

        assert chain.is_complete() is False

    def test_goal_chain_incomplete_no_task(self):
        """GoalChain without task_goal_id → is_complete() == False"""
        from src.core.company.context import GoalChain

        chain = GoalChain(
            mission_id=uuid.uuid4(),
            strategic_goal_id=uuid.uuid4(),
            project_goal_id=uuid.uuid4(),
        )

        assert chain.is_complete() is False


class TestAgentExecutionContextUnhappyPath:
    """Unhappy path tests for AgentExecutionContext"""

    def test_context_missing_company(self):
        """company_id=None → validate_completeness() gives missing fields"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=None,  # Missing
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
        )

        is_valid, missing_fields = context.validate_completeness()

        assert is_valid is False
        assert "company_id" in missing_fields
        assert context.is_degraded is True

    def test_context_missing_goal_chain(self):
        """Empty goal_chain → validate_completeness() gives incomplete"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(),  # Empty
        )

        is_valid, missing_fields = context.validate_completeness()

        assert is_valid is False
        assert "goal_chain" in missing_fields
        assert context.is_degraded is True

    def test_context_missing_both(self):
        """Both company_id and goal_chain missing → both in missing_fields"""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=None,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(),
        )

        is_valid, missing_fields = context.validate_completeness()

        assert is_valid is False
        assert "company_id" in missing_fields
        assert "goal_chain" in missing_fields


class TestPolicyScopeUnhappyPath:
    """Unhappy path tests for PolicyScope"""

    def test_invalid_risk_level(self):
        """PolicyScope with invalid risk_level → validation error"""
        from src.core.company.context import PolicyScope

        with pytest.raises(ValidationError) as exc_info:
            PolicyScope(risk_level="INVALID")

        assert "risk_level" in str(exc_info.value)


class TestBudgetScopeUnhappyPath:
    """Unhappy path tests for BudgetScope"""

    def test_budget_consumed_negative_validation_error(self):
        """tokens_consumed_this_month < 0 → validation error"""
        from src.core.company.context import BudgetScope

        # Negative consumption is not allowed (ge=0 validation)
        with pytest.raises(ValidationError) as exc_info:
            BudgetScope(
                monthly_token_budget=100,
                tokens_consumed_this_month=-50,
            )

        assert "tokens_consumed_this_month" in str(exc_info.value)


# ============================================================================
# Edge Cases
# ============================================================================


class TestGoalChainEdgeCases:
    """Edge case tests for GoalChain"""

    def test_goal_chain_from_ancestry_invalid_goal_type(self):
        """Ancestry with invalid goal_type → skip or handle gracefully"""
        from src.core.company.context import GoalChain

        goals = [
            {"id": uuid.uuid4(), "title": "Unknown", "goal_type": "unknown_type"},
        ]

        # Should not raise, but might not populate any fields
        chain = GoalChain.from_ancestry(goals)
        assert chain.depth() == 0  # Unknown types are ignored

    def test_goal_chain_from_ancestry_wrong_order(self):
        """Ancestry in wrong order → still builds correctly by goal_type"""
        from src.core.company.context import GoalChain

        # Goals in random order
        goals = [
            {"id": uuid.uuid4(), "title": "Task", "goal_type": "task"},
            {"id": uuid.uuid4(), "title": "Mission", "goal_type": "mission"},
            {"id": uuid.uuid4(), "title": "Strategic", "goal_type": "strategic"},
        ]

        chain = GoalChain.from_ancestry(goals)

        # Should be sorted/assigned by goal_type, not order
        assert chain.mission_title == "Mission"
        assert chain.strategic_goal_title == "Strategic"
        assert chain.task_goal_title == "Task"

    def test_goal_chain_from_ancestry_extra_fields_ignored(self):
        """Goals with extra fields → extra fields are ignored"""
        from src.core.company.context import GoalChain

        goals = [
            {
                "id": uuid.uuid4(),
                "title": "Mission",
                "goal_type": "mission",
                "extra_field": "should_be_ignored",
                "another_extra": 123,
            },
        ]

        chain = GoalChain.from_ancestry(goals)

        assert chain.mission_title == "Mission"
        assert chain.depth() == 1


class TestAgentExecutionContextEdgeCases:
    """Edge case tests for AgentExecutionContext"""

    def test_context_uuid_string_conversion(self):
        """UUID fields accept string UUIDs and convert them"""
        from src.core.company.context import AgentExecutionContext

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"

        context = AgentExecutionContext(
            tenant_id=1,
            company_id=uuid_str,  # String instead of UUID
            task_id=uuid_str,
            trace_id=uuid_str,
        )

        assert isinstance(context.company_id, uuid.UUID)
        assert str(context.company_id) == uuid_str

    def test_context_negative_sla_validation_error(self):
        """Negative SLA seconds → validation error"""
        from src.core.company.context import AgentExecutionContext

        # Negative SLA is not allowed (ge=0 validation)
        with pytest.raises(ValidationError) as exc_info:
            AgentExecutionContext(
                tenant_id=1,
                task_id=uuid.uuid4(),
                trace_id=uuid.uuid4(),
                sla_seconds=-100,
            )

        assert "sla_seconds" in str(exc_info.value)
