"""AgentExecutionContext and GoalChain -- re-exported from src.core.shared.agent_context.

Backward-compatible re-export module. All callers of
    from src.core.company.context import AgentExecutionContext
continue to work without changes. The canonical definitions live in
src.core.shared.agent_context to avoid a shared -> domain_pack circular import.
"""

from src.core.shared.agent_context import (
    AgentExecutionContext as AgentExecutionContext,
    BudgetScope as BudgetScope,
    GoalChain as GoalChain,
    PolicyScope as PolicyScope,
)

__all__ = ["GoalChain", "PolicyScope", "BudgetScope", "AgentExecutionContext"]
