"""
Company Layer - Paperclip AI Symbiotic Integration

This module provides enterprise organizational concepts for the SanskritiSetu platform:
- Company management
- Department hierarchy
- Goal tracking (Mission -> Strategic -> Project -> Task)
- External agent integration via heartbeat protocol
- Board governance
- Company templates

Usage:
    from src.core.company import Company, Department, Goal
    from src.core.company import CompanyService, DepartmentService
"""

from typing import TYPE_CHECKING

from src.core.company.models import (
    BoardDecision,
    BoardDecisionStatus,
    Company,
    CompanyTemplate,
    CompanyType,
    Department,
    ExternalAgent,
    ExternalAgentStatus,
    Goal,
    GoalStatus,
    GoalType,
    PackActivationAuditLog,
)

# Context objects (Taak 1.3)
if TYPE_CHECKING:
    from src.core.company.context import AgentExecutionContext, BudgetScope, GoalChain, PolicyScope
else:
    try:
        from src.core.company.context import AgentExecutionContext, BudgetScope, GoalChain, PolicyScope
    except ImportError:
        AgentExecutionContext = None  # type: ignore[assignment]
        BudgetScope = None  # type: ignore[assignment]
        GoalChain = None  # type: ignore[assignment]
        PolicyScope = None  # type: ignore[assignment]