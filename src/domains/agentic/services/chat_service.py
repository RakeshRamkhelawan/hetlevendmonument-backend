"""
Chat Service - Main orchestration service for the agentic chat system.

Orchestrates:
- Feature detection
- Session management
- Prompt composition
- LLM interaction
- Tool execution
- Metrics collection
"""

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm.llm_client import LLMMessage, create_llm_client
from src.core.models.rbac_models import Tenant
from src.core.services.noodstop_toegang import KlantStilgezet, eis_chat_actief
from src.domains.agentic.models import PromptMetrics, UserPersona
from src.domains.agentic.schemas.core_schemas import FeatureDefinition
from src.domains.agentic.services.feature_registry import get_feature_registry
from src.domains.agentic.services.feature_router import (
    DetectionRequest,
    create_feature_detector,
)
from src.domains.agentic.services.prompt_composer import ComposedPrompt, get_prompt_composer
from src.domains.agentic.services.session_manager import (
    AgenticSessionManager,
    Session,
    create_session_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class ChatRequest:
    """Incoming chat request."""

    message: str
    user_id: int
    tenant_id: int
    session_id: str | None = None
    feature_context: str | None = None
    locale: str | None = None
    route_path: str | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


@dataclass
class ToolCallResult:
    """Result of a tool execution."""

    tool_name: str | None
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    result: Any = None
    success: bool = True
    error: str | None = None


@dataclass
class ChatResponse:
    """Chat response to return to client."""

    response: str
    session_id: str
    feature_context: str
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class AgentChatService:
    """
    Main chat service orchestrating all agentic components.

    Flow:
    1. Get/Create session
    2. Detect feature context
    3. Load feature and tenant config
    4. Compose prompt
    5. Call LLM
    6. Execute tools (if needed)
    7. Save messages
    8. Record metrics
    9. Return response
    """

    def __init__(
        self,
        session_manager: AgenticSessionManager,
        redis_url: str = "redis://localhost:6379",
        enable_metrics: bool = True,
    ) -> None:
        """
        Initialize chat service.

        Args:
            session_manager: Session manager instance
            redis_url: Redis URL for session storage
            enable_metrics: Whether to record metrics
        """
        self.session_manager = session_manager
        self.feature_registry = get_feature_registry()
        self.prompt_composer = get_prompt_composer()
        self.feature_detector = create_feature_detector(session_manager)
        self.llm_client = create_llm_client(provider_name="google")
        self.enable_metrics = enable_metrics

    async def process_chat(self, db: AsyncSession, request: ChatRequest) -> ChatResponse:
        """
        Process a chat request end-to-end.

        Args:
            db: Database session
            request: Chat request

        Returns:
            ChatResponse with agent's reply
        """
        start_time = time.time()
        tool_calls: list[ToolCallResult] = []

        # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): de chat is een deur. De weigering
        # (`KlantStilgezet`, met de vaste chatmelding) komt uit de service; het endpoint maakt er
        # HTTP 403 (stil) of 503 (stand onbekend) van. Voor de sessie, de detectie en het model.
        await eis_chat_actief(request.tenant_id)

        try:
            # 1. Get or create session
            session = await self._get_or_create_session(request)

            # 2. Detect feature context
            detection_request = DetectionRequest(
                message=request.message,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                session_id=session.id,
                explicit_feature=request.feature_context,
                route_path=request.route_path,
                locale=request.locale or "en",
            )

            feature_context = await self.feature_detector.detect_context(db, detection_request)

            # 3. Load feature and tenant config
            feature = self.feature_registry.get_feature(
                request.tenant_id, feature_context.feature_id
            )

            if not feature:
                logger.warning(f"Feature {feature_context.feature_id} not found, using fallback")
                feature = await self._create_fallback_feature(db, request.tenant_id)

            tenant = await self._load_tenant(db, request.tenant_id)
            user_persona = await self._load_user_persona(db, request.user_id)

            # Determine locale
            locale: str = (
                request.locale or (tenant.primary_locale if tenant else "en_US") or "en_US"
            )

            # 4. Compose prompt
            composed_prompt = await self.prompt_composer.compose_prompt(
                db=db,
                feature=feature,
                tenant_industry=tenant.industry if tenant else None,
                user_locale=locale,
                user_persona=user_persona,
                additional_context=request.metadata.get("context") if request.metadata else None,
            )

            # 5. Build messages for LLM
            messages = await self._build_llm_messages(
                session=session,
                system_prompt=composed_prompt.system_prompt,
                user_message=request.message,
            )

            # 6. Call LLM
            llm_response = await self.llm_client.chat_completion(
                messages=messages,
                tools=composed_prompt.tools if composed_prompt.tools else None,
                max_tokens=2048,
                temperature=0.7,
            )

            if not llm_response.success:
                raise Exception(f"LLM error: {llm_response.error_message}")

            response_text = llm_response.content

            # 7. Execute tools if needed
            raw_tool_calls = getattr(llm_response, "tool_calls", None)
            if raw_tool_calls:
                tool_calls = await self._execute_tools(
                    raw_tool_calls,
                    feature,
                    request.user_id,
                )

                # If tools were executed, may need another LLM call
                if tool_calls:
                    response_text = await self._complete_with_tool_results(
                        messages, composed_prompt, tool_calls
                    )

            # 8. Save messages to session
            await self._save_messages(
                session_id=session.id,
                user_message=request.message,
                assistant_message=response_text,
                feature_context=feature_context.feature_id,
                tool_calls=tool_calls,
            )

            # 9. Generate suggestions
            suggestions = self._generate_suggestions(feature, response_text)

            # 10. Record metrics
            if self.enable_metrics:
                await self._record_metrics(
                    db=db,
                    session_id=session.id,
                    user_id=request.user_id,
                    feature_context=feature_context.feature_id,
                    composed_prompt=composed_prompt,
                    duration_ms=int((time.time() - start_time) * 1000),
                    tool_calls=tool_calls,
                )

            return ChatResponse(
                response=response_text,
                session_id=session.id,
                feature_context=feature_context.feature_id,
                tool_calls=tool_calls,
                suggestions=suggestions,
                metadata={
                    "detection_layer": feature_context.detection_layer,
                    "detection_confidence": feature_context.confidence,
                    "locale": locale,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )

        except Exception as e:
            logger.error(f"Chat processing error: {e}", exc_info=True)
            raise

    async def process_chat_stream(
        self, db: AsyncSession, request: ChatRequest
    ) -> AsyncGenerator[dict[str, Any], None]:  # TODO(TYPE): replace Any with concrete type
        """
        Process chat with streaming response.

        Yields chunks of the response for real-time display.
        """
        start_time = time.time()

        # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): zie `process_chat`. Een stream
        # geeft geen HTTP-status, dus de weigering is een foutkader met code NOODSTOP.
        try:
            await eis_chat_actief(request.tenant_id)
        except KlantStilgezet as stop:
            yield {"type": "error", "error": stop.bericht, "code": "NOODSTOP"}
            return

        # Setup (same as non-streaming)
        session = await self._get_or_create_session(request)

        detection_request = DetectionRequest(
            message=request.message,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=session.id,
            explicit_feature=request.feature_context,
            locale=request.locale or "en",
        )

        feature_context = await self.feature_detector.detect_context(db, detection_request)

        feature = self.feature_registry.get_feature(request.tenant_id, feature_context.feature_id)

        if not feature:
            feature = await self._create_fallback_feature(db, request.tenant_id)

        tenant = await self._load_tenant(db, request.tenant_id)
        user_persona = await self._load_user_persona(db, request.user_id)
        locale: str = request.locale or (tenant.primary_locale if tenant else "en_US") or "en_US"

        composed_prompt = await self.prompt_composer.compose_prompt(
            db=db,
            feature=feature,
            tenant_industry=tenant.industry if tenant else None,
            user_locale=locale,
            user_persona=user_persona,
        )

        messages = await self._build_llm_messages(
            session=session,
            system_prompt=composed_prompt.system_prompt,
            user_message=request.message,
        )

        # Yield metadata first
        yield {
            "type": "metadata",
            "session_id": session.id,
            "feature_context": feature_context.feature_id,
        }

        # Stream LLM response
        llm_client_any: Any = self.llm_client  # TODO(TYPE): replace Any with concrete type
        full_response: str = ""
        async for chunk in llm_client_any.stream_chat_completion(
            messages=messages,
            tools=composed_prompt.tools if composed_prompt.tools else None,
            max_tokens=2048,
            temperature=0.7,
        ):
            if chunk.content:
                full_response += chunk.content
                yield {"type": "chunk", "content": chunk.content}

            if chunk.tool_calls:
                for tc in chunk.tool_calls:
                    yield {
                        "type": "tool_call",
                        "tool_call": {
                            "tool_name": tc.name,
                            "parameters": tc.parameters,
                        },
                    }

        # Save to session
        await self._save_messages(
            session_id=session.id,
            user_message=request.message,
            assistant_message=full_response,
            feature_context=feature_context.feature_id,
        )

        # Final done signal
        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    async def _get_or_create_session(self, request: ChatRequest) -> Session:
        """Get existing session or create new one."""
        if request.session_id:
            session = await self.session_manager.get_session(request.session_id)
            if session:
                return session

        return await self.session_manager.create_session(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            initial_feature=request.feature_context,
            metadata=request.metadata,
        )

    async def _load_tenant(self, db: AsyncSession, tenant_id: int) -> Tenant | None:
        """Load tenant configuration."""
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_user_persona(self, db: AsyncSession, user_id: int) -> UserPersona | None:
        """Load user persona for personalization."""
        stmt = select(UserPersona).where(UserPersona.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_fallback_feature(self, db: AsyncSession, tenant_id: int) -> FeatureDefinition:
        """Create a fallback feature for when detection fails."""
        return FeatureDefinition(
            id="general_assistant",
            category="general",
            display_name={"en": "General Assistant", "nl": "Algemene Assistent"},
            description={"en": "General purpose assistant", "nl": "Algemene assistent"},
            is_active=True,
        )

    async def _build_llm_messages(
        self, session: Session, system_prompt: str, user_message: str
    ) -> list[LLMMessage]:
        """Build message list for LLM including history."""
        messages = [LLMMessage(role="system", content=system_prompt)]

        # Add recent history
        for msg in session.messages[-10:]:
            if msg.role in ("user", "assistant"):
                messages.append(LLMMessage(role=msg.role, content=msg.content))

        # Add current message
        messages.append(LLMMessage(role="user", content=user_message))

        return messages

    async def _execute_tools(
        self,
        tool_calls: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        feature: FeatureDefinition,
        user_id: int,  # TODO(TYPE): replace Any with concrete type
    ) -> list[ToolCallResult]:
        """Execute requested tools."""
        results: list[ToolCallResult] = []

        for tc in tool_calls:
            tool_name: str | None = tc.get("name")
            parameters: dict[str, Any] = tc.get(  # TODO(TYPE): replace Any with concrete type
                "parameters", {}
            )  # TODO(TYPE): replace Any with concrete type

            try:
                # TODO: Implement actual tool execution
                # For now, return placeholder
                result = ToolCallResult(
                    tool_name=tool_name if tool_name else "unknown",
                    parameters=parameters,
                    result={"status": "executed"},
                    success=True,
                )
            except Exception as e:
                result = ToolCallResult(
                    tool_name=tool_name if tool_name else "unknown",
                    parameters=parameters,
                    success=False,
                    error=str(e),
                )

            results.append(result)

        return results

    async def _complete_with_tool_results(
        self,
        original_messages: list[LLMMessage],
        composed_prompt: ComposedPrompt,
        tool_calls: list[ToolCallResult],
    ) -> str:
        """Complete response after tool execution."""
        # Add tool results to messages
        tool_results = "\n".join(
            [
                f"Tool '{tc.tool_name}' result: {tc.result if tc.success else tc.error}"
                for tc in tool_calls
            ]
        )

        messages = original_messages + [
            LLMMessage(role="assistant", content="[Tool calls executed]"),
            LLMMessage(role="system", content=f"Tool results:\n{tool_results}"),
        ]

        response = await self.llm_client.chat_completion(
            messages=messages, max_tokens=1024, temperature=0.7
        )

        return response.content if response.success else "Error completing response"

    async def _save_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        feature_context: str,
        tool_calls: list[ToolCallResult] | None = None,
    ) -> None:
        """Save messages to session."""
        await self.session_manager.add_message(
            session_id=session_id,
            role="user",
            content=user_message,
            feature_context=feature_context,
        )

        serialized_tool_calls: list[dict[str, Any]] | None = (  # TODO(TYPE): replace Any with concrete type
            [tc.__dict__ for tc in tool_calls] if tool_calls else None
        )  # TODO(TYPE): replace Any with concrete type
        await self.session_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            feature_context=feature_context,
            tool_calls=serialized_tool_calls,
        )

    def _generate_suggestions(self, feature: FeatureDefinition, response: str) -> list[str]:
        """Generate follow-up suggestions based on response."""
        # Simple keyword-based suggestion generation
        suggestions: list[str] = []

        if "workflow" in response.lower():
            suggestions.append("Show me my existing workflows")

        if "data" in response.lower() or "analysis" in response.lower():
            suggestions.append("Generate a report")

        if len(suggestions) == 0:
            suggestions.append("Tell me more")
            suggestions.append("What else can you help with?")

        return suggestions[:3]

    async def _record_metrics(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: int,
        feature_context: str,
        composed_prompt: ComposedPrompt,
        duration_ms: int,
        tool_calls: list[ToolCallResult],
    ) -> None:
        """Record metrics for prompt optimization."""
        metric = PromptMetrics(
            template_id=composed_prompt.metadata.get("template_id"),
            session_id=session_id,
            user_id=user_id,
            feature_context=feature_context,
            generation_time_ms=duration_ms,
            tools_used=[tc.tool_name for tc in tool_calls] if tool_calls else None,
            tool_errors=len([tc for tc in tool_calls if not tc.success]),
        )

        db.add(metric)
        await db.commit()


# Factory function
def create_chat_service(
    redis_url: str = "redis://localhost:6379", enable_metrics: bool = True
) -> AgentChatService:
    """Create a chat service instance."""
    session_manager = create_session_manager(redis_url)
    return AgentChatService(
        session_manager=session_manager,
        redis_url=redis_url,
        enable_metrics=enable_metrics,
    )
