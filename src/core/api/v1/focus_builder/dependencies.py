"""
Dependency injection helpers for the Focus Builder router.

Provides the AgentCouncil instance used to gate flow executions
before they reach ActivePieces.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent
from src.core.agents.focus_builder_tool_agent import FocusBuilderToolAgent
from src.core.als.agents.focus_builder_agents import _get_internal_agents
from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.factory import build_council
from src.core.copilot.council.governance_gate import require_council_approval
from src.core.copilot.council.types import (
    DataClassification,  # noqa: F401 -- re-exported for router files (ADR-033)
    DecisionVerdict,  # noqa: F401
    Proposal,  # noqa: F401
    ProposalTrigger,  # noqa: F401
)
from src.core.database.database import get_db
from src.core.learning.services.twin_service_factory import (
    create_practical_twin_service,  # noqa: F401
)
from src.core.services.focus_suggestion_service import (
    FocusSuggestionService,
    SuggestionRequest,
    SuggestionResponse,
)
from src.core.services.noodstop_toegang import (  # re-exported for ws_chat_router (ADR-033)
    KlantStilgezet,
    eis_chat_actief,
)


async def get_focus_builder_council(
    db: AsyncSession = Depends(get_db),
) -> AgentCouncil:
    """Build and return an AgentCouncil instance for Focus Builder governance checks."""
    return await build_council(db)


__all__ = [
    "AgentCouncil",
    "DataClassification",
    "DecisionVerdict",
    "FocusBuilderChatAgent",
    "FocusBuilderToolAgent",
    "FocusSuggestionService",
    "KlantStilgezet",
    "Proposal",
    "ProposalTrigger",
    "SuggestionRequest",
    "SuggestionResponse",
    "_get_internal_agents",
    "create_practical_twin_service",
    "eis_chat_actief",
    "get_db",
    "get_focus_builder_council",
    "require_council_approval",
]
