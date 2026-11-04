"""CVA domain-specific FastAPI dependencies (ADR-033 Stap 0C)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# ADR-033: dependencies.py mag domeinlagen importeren
from src.core.agents.agent_registry import AgentRegistry as AgentRegistry
from src.core.agents.ultimate_cva.system_prompt import get_system_prompt as get_system_prompt
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user_dependency,
)
from src.core.database.database import db_manager, get_db
from src.core.database.redis import get_redis_client
from src.core.governance.rate_limiter import cva_chat_limit as cva_chat_limit
from src.core.services.llm.base import LLMRateLimitError, LLMServiceError, LLMTimeoutError

if TYPE_CHECKING:
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository
    from src.core.agents.ultimate_cva.memory import ConversationMemory
    from src.core.agents.cva_orchestrator import UltimateCVAAgent
    from src.core.services.cva_service import CVAService
    from src.core.services.llm.service import LLMService

logger = logging.getLogger(__name__)

__all__ = [
    "AgentRegistry",
    "AgentRegistryRepository",
    "AsyncSession",
    "ConversationMemory",
    "CVAService",
    "LLMRateLimitError",
    "LLMServiceError",
    "LLMService",
    "LLMTimeoutError",
    "UltimateCVAAgent",
    "UserResponse",
    "build_cva_service",
    "create_cva_agent_factory",
    "db_manager",
    "execute_cva_council_gate",
    "get_cva_agent_registry_dependency",
    "get_cva_agent_registry_repository_dependency",
    "get_cva_council_dependency",
    "get_cva_service_dependency",
    "get_current_user_dependency",
    "get_db",
    "get_llm_service_dependency",
    "get_optional_conversation_memory",
    "get_redis_client",
    "get_system_prompt",
    "cva_chat_limit",
    "handle_cva_value_error",
    "probe_llm_health",
]


def handle_cva_value_error(e: ValueError, context: str = "operation") -> HTTPException:
    """Convert CVAService ValueError to appropriate HTTPException."""
    error_msg = str(e).lower()
    if "not found" in error_msg:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if "access denied" in error_msg:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation",
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid request for this conversation",
    )


async def get_llm_service_dependency(
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> LLMService:
    """Het taalmodel van de TENANT van dit verzoek (`LLMService.for_tenant`); 503 bij een configuratiefout.

    Hier stond `LLMService()`: het platformmodel voor elke klant, ongeacht zijn keuze (brief 2026-10-19).
    """
    from src.core.services.llm.base import LLMProviderUnknownError
    from src.core.services.llm.service import LLMService

    try:
        return await LLMService.for_tenant(current_user.tenant_id)
    except (ValueError, LLMProviderUnknownError) as e:
        # `LLMProviderUnknownError` is bewust GEEN ValueError, zodat `LLMService.__init__` hem
        # niet opeet en stil de MockProvider teruggeeft. Gevolg dat bij Gate 2 (ronde 3) is
        # GEMETEN: hier glipte hij er ook doorheen, en dan kreeg de gebruiker een kale 500 in
        # plaats van de 503 met "Check LLM_PROVIDER and LLM_MODEL" die hier juist voor staat.
        # De fabriek maakt een uitstekende melding; dit is de enige plek waar een mens hem ziet.
        logger.error("LLM service configuration error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service not configured for this tenant. Check the tenant LLM choice and MISTRAL_API_KEY.",
        ) from e


def build_cva_service(
    db_session: AsyncSession,
    llm_service: LLMService,
) -> CVAService:
    """Build CVAService with db + llm_service + optional db_factory from db_manager.

    Sync helper (not a Depends factory) because the db_factory closure depends on
    an already-resolved session and llm_service -- it cannot be expressed as a pure
    Depends chain without adding a second session dependency that would create a
    second transaction.
    """
    from src.core.services.cva_service import CVAService

    _db_factory: Any | None = None  # TODO(TYPE): replace Any with concrete type
    try:
        if db_manager.async_session_maker is not None:
            session_maker = db_manager.async_session_maker

            @asynccontextmanager
            async def _memory_db_factory() -> AsyncGenerator[AsyncSession, None]:
                async with session_maker() as session:
                    yield session

            _db_factory = _memory_db_factory
    except Exception as e:
        logger.warning(
            "db_factory setup failed, proceeding without: %s", type(e).__name__, exc_info=True
        )
        _db_factory = None
    return CVAService(db_session=db_session, llm_service=llm_service, db_factory=_db_factory)


async def get_cva_service_dependency(
    session: AsyncSession = Depends(get_db),
) -> CVAService:
    """Provide a CVAService without LLM (for CRUD endpoints)."""
    from src.core.services.cva_service import CVAService

    return CVAService(db_session=session)


async def get_optional_conversation_memory(
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> ConversationMemory | None:
    """Provide ConversationMemory backed by Redis, or None if Redis unavailable."""
    try:
        from src.core.agents.ultimate_cva.memory import ConversationMemory

        redis = await get_redis_client()
        return ConversationMemory(redis, tenant_id=current_user.tenant_id)
    except Exception as e:
        logger.warning(
            "ConversationMemory unavailable, degrading gracefully: %s",
            type(e).__name__,
            exc_info=True,
        )
        return None


async def probe_llm_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Probe LLM availability for health checks; never raises.

    Returns dict with keys: available (bool), provider (str, if available),
    config_error (bool): waar bij een ValueError EN bij LLMProviderUnknownError --
    een verkeerde providernaam is de meest voorkomende configuratiefout.
    message (str, if unavailable).
    """
    # Boven de try: een import BINNEN het blok laat de naam in de except-clausule
    # mogelijk ongebonden, en dan valt de foutafhandeling zelf om.
    from src.core.services.llm.base import LLMProviderUnknownError

    try:
        from src.core.services.llm.service import LLMService

        service = LLMService()
        return {"available": True, "provider": type(service.provider).__name__}
    except (ValueError, LLMProviderUnknownError) as e:
        # Zonder `LLMProviderUnknownError` viel de MEEST voorkomende configuratiefout -- een
        # verkeerde providernaam -- in het `except Exception` hieronder en kwam er
        # `config_error: False` uit. De healthmelding stuurde de beheerder dan naar zijn
        # sleutel terwijl zijn providernaam fout stond. Gemeten bij Gate 2, ronde 3.
        return {"available": False, "config_error": True, "message": str(e)}
    except Exception as e:
        return {"available": False, "config_error": False, "message": str(e)}


async def get_cva_agent_registry_dependency(
    session: AsyncSession = Depends(get_db),
) -> AgentRegistry:
    """Provide AgentRegistry with repository for public CVA endpoints."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    return AgentRegistry(repository=AgentRegistryRepository(session))


async def get_cva_agent_registry_repository_dependency(
    session: AsyncSession = Depends(get_db),
) -> AgentRegistryRepository:
    """Provide AgentRegistryRepository for CVA execute handler."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    return AgentRegistryRepository(session)


async def create_cva_agent_factory() -> UltimateCVAAgent:
    """Instantiate UltimateCVAAgent via lazy import. Called from state.py cache."""
    from src.core.agents.cva_orchestrator import create_ultimate_cva_agent

    return await create_ultimate_cva_agent()


async def get_cva_council_dependency(
    session: AsyncSession = Depends(get_db),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Provide a request-scoped AgentCouncil for CVA endpoints (RC-002)."""
    from src.core.copilot.council.factory import build_council

    return await build_council(session)


async def execute_cva_council_gate(
    council: Any,  # TODO(TYPE): replace Any with concrete type
    tenant_id: int,
    user_id: int,
    action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    reasoning: str,
    model_id: str,
    db: AsyncSession,
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Call require_council_approval for CVA legacy council gate (RC-002).

    `db` (ADR-036 OP-167, sprint dag 2): zonder dit blijft een HITL_REQUIRED-verdict op
    dit legacy-pad zonder ticket, identiek aan BLOCKED -- precies het gat dat deze
    sprint dicht.
    """
    from src.core.copilot.council.governance_gate import require_council_approval

    return await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=user_id,
        action_type="cva.chat_legacy",
        action_params=action_params,
        reasoning=reasoning,
        model_id=model_id,
        db=db,
    )
