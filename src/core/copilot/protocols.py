"""
Protocol interfaces for CopilotService dependencies.

These Protocols enable structural subtyping (duck typing) for the
three external services that CopilotService depends on.  They follow
the same convention as ISerenaClient, ISequentialThinkingClient, and
ILLMSuggestionProvider elsewhere in the codebase.

Per Beslissing 2 (Sprint 4 Dag 1):
    - CopilotService.__init__ accepts these as optional params (default None).
    - Day 1 only exercises IHITLRepository (HITL_REQUIRED branch).
    - IToolBroker and ITwinService remain None until Day 2 / Day 3.
    - Concrete adapter around GatekeeperRepository + HITLRequestModel
      comes Day 2 (~30 lines).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from src.core.agents.context_engine import EnrichedContext


class IToolBroker(Protocol):
    """Tool execution contract (ADR-015)."""

    async def execute_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        agent_id: str | None = None,
        timeout_seconds: int | None = None,
        context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        | None = None,  # tenant_id, user_id, etc.  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class ITwinService(Protocol):
    """Digital Twin profile contract (ADR-025, ADR-026)."""

    async def get_profile(
        self,
        user_id: str,
        tenant_id: int,
        db: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class IHITLRepository(Protocol):
    """Human-in-the-Loop request persistence contract (ADR-017)."""

    async def create_hitl_request(
        self,
        *,
        tenant_id: int,
        user_id: int,
        decision_id: str,
        reason: str,
        action_type: str,
        action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        # Default is een string-literaal en geen import van `hitl_repository._UITVOERENDE_
        # IDENTITEIT` (ADR-033/034-grens: dit protocol mag niet naar een concrete tool_broker-
        # module wijzen). Moet wel dezelfde default blijven -- anders type-checkt de bestaande
        # aanroep in copilot/service.py (die dit argument weglaat) niet meer tegen dit Protocol.
        executing_identity: str = "copilot",
    ) -> str:
        """Returns request_id (UUID string)."""
        ...


class IAuditWriter(Protocol):
    """Audit writing protocol."""

    async def log_user_response(
        self,
        *,
        signal_id: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
        user_id: int,
        action_type: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None: ...

    async def bind_execution_result(
        self,
        *,
        decision_id: UUID,
        tenant_id: int,
        result_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        status: str = "success",
    ) -> None:
        """Hash and bind tool execution output to an existing decision record."""
        ...


class IRateLimiter(Protocol):
    async def check(
        self,
        tenant_id: int,
        user_id: int,
        action_type: str,
    ) -> bool: ...


class IPranaService(Protocol):
    async def has_budget(
        self,
        tenant_id: int,
        action_type: str,
    ) -> bool: ...


class IAIContextEngine(Protocol):
    """Context enrichment contract (ADR-034, ADR-027 S.11-14).

    Replaces direct ITwinService.get_profile() calls in CopilotService.
    Enriches a copilot turn with twin memory, ContextPacker data, and platform context.
    """

    async def enrich(
        self,
        agent_id: str,
        query: str,
        surface: str,
    ) -> EnrichedContext: ...
