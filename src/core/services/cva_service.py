"""
CVA Service - Business logic for Conversational Virtual Assistant
Handles conversation management and chat orchestration
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversations.models import Conversation, ConversationMessage
from src.core.copilot.council.factory import build_council
from src.core.copilot.council.governance_gate import require_council_approval
from src.core.exceptions import GovernanceVetoError

# RC-SUP-2: default fail-SECURE. On a Council infrastructure error the request is
# blocked, not silently allowed through. Set CVA_GOVERNANCE_FAIL_SECURE=false only
# for explicitly-accepted degraded-mode operation.
_CVA_FAIL_SECURE = os.getenv("CVA_GOVERNANCE_FAIL_SECURE", "true").lower() == "true"
from src.core.monitoring.cva_metrics import cva_chat_duration_seconds, cva_chat_requests_total
from src.core.services.llm.service import LLMService
from src.core.services.noodstop_toegang import KlantStilgezet, eis_chat_actief
from src.core.shared.consent_categories import ConsentCategory
from src.core.shared.events.governance_bus import governance_bus
from src.core.shared.events.governance_events import AuditLogEmitEvent
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

_PROVIDER_DISPLAY: dict[str, str] = {
    "gemini": "gemini",
    "deepseek": "deepseek",
    "ollama": "ollama",
    "mistral": "mistral",
}



async def _write_memory_candidate(
    tenant_id: int,
    user_id: int,
    conversation_id: int,
    user_message: str,
    assistant_response: str,
    db_factory: Callable[..., contextlib.AbstractAsyncContextManager[AsyncSession]],
) -> None:
    """
    Background helper: write an episodic MemoryItem candidate from a CVA turn.

    Called with asyncio.create_task() so it never blocks the chat response.
    Uses its own DB session (opened via db_factory) so it doesn't share the
    already-committed chat session.

    The item is created with status='proposed' and source='cva_turn'.
    Auto-accept is NOT applied (source is not in the whitelist).
    """
    try:
        async with db_factory() as session:
            import importlib

            _ccm = importlib.import_module("src.core.governance.cookie_consent")
            from src.domains.memory.schemas import MemoryItemWrite
            from src.domains.memory.services.memory_write_service import MemoryWriteService

            consent_mgr = _ccm.CookieConsentManager(session)
            has_consent = await consent_mgr.is_consent_given(
                str(user_id), tenant_id, ConsentCategory.PERSONALIZATION
            )
            if not has_consent:
                logger.info(
                    "cva.memory_write_skipped user_id=%d reason=no_personalization_consent",
                    user_id,
                )
                return

            content = f"User: {user_message}\n\nAssistant: {assistant_response}"
            payload = MemoryItemWrite(
                content=content,
                memory_type="episodic",
                source_type="chat",
                source_ref=str(conversation_id),
                agent_id="cva",
                privacy_scope="user",
                confidence=0.7,
                importance=0.5,
                user_id=user_id,
            )
            write_svc = MemoryWriteService(db=session, tenant_id=tenant_id)
            await write_svc.write(payload=payload)
            await session.commit()
    except Exception as exc:
        # Never propagate -- memory write is best-effort
        logger.warning(
            "CVAService: background memory write failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )


# ADR-022 exempt: service-laag, geen agent. Learning via council agents in call chain.
class CVAService:
    """
    CVA Service for managing conversations and chat

    Responsibilities:
    - Create/retrieve conversations
    - Generate chat responses via LLM
    - Store message history
    - Enforce tenant isolation
    """

    def __init__(
        self,
        db_session: AsyncSession,
        llm_service: Optional[LLMService] = None,
        db_factory: Optional[
            Callable[..., contextlib.AbstractAsyncContextManager[AsyncSession]]
        ] = None,
    ) -> None:
        self.db = db_session
        # Zonder meegegeven dienst wordt het taalmodel per verzoek van de TENANT opgevraagd (`_llm_voor`).
        # Hier stond `LLMService()`: het platformmodel voor elke klant, en een fout bij het bouwen van
        # de service zelf, ook voor wie alleen gesprekken ophaalt (brief 2026-10-19).
        self._llm = llm_service
        # db_factory enables the background memory write task.
        # Injected by the endpoint; None = memory integration disabled (safe default).
        self._db_factory = db_factory
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def chat(
        self,
        message: str,
        user_id: int,
        tenant_id: int,
        conversation_id: Optional[int] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Process chat message and return response

        Args:
            message: User message
            user_id: Current user ID
            tenant_id: Tenant ID (for isolation)
            conversation_id: Continue existing conversation (optional)
            system_prompt: Custom system prompt (optional, admin only)

        Returns:
            {
                "response": "Assistant response",
                "conversation_id": 123,
                "metadata": {...}
            }

        Raises:
            ValueError: Invalid conversation ID or access denied
        """
        # Start metrics timing
        start_time = time.time()
        tenant_id_str = str(tenant_id)
        status = "success"

        # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): de chat is een deur. Een
        # stilgezette klant krijgt GEEN gesprek, GEEN Council-aanroep (en dus geen Prana-
        # afschrijving) en GEEN modelaanroep, alleen de vaste melding. Fail-closed: een stand die
        # niet te lezen is geeft 503 in plaats van 403. Ook de CVA-actor komt hier langs.
        try:
            await eis_chat_actief(tenant_id)
        except KlantStilgezet as stop:
            raise HTTPException(
                status_code=503 if stop.onbekend else 403, detail=stop.bericht
            ) from stop

        try:
            # Get or create conversation
            if conversation_id:
                conversation = await self._get_conversation(conversation_id, user_id, tenant_id)
                if not conversation:
                    raise ValueError("Conversation not found or access denied")
            else:
                conversation = await self._create_conversation(user_id, tenant_id)

            # Build message history for context
            message_history = await self._get_message_history(conversation.id, tenant_id)

            # Add current user message to history
            message_history.append({"role": "user", "content": message})

            # Use model override if provided and in allowlist, otherwise use configured LLM
            effective_llm = await self._llm_voor(tenant_id)

            # Governance gate: EU AI Act Art. 14 -- council deliberation voor LLM generate
            # Shadow CEO is al ingebakken in build_council() via factory.py:331 (_ShadowCEOAdapter).
            # Degraded mode: als council niet beschikbaar is gaat chat door met decision_id=None
            # (tenzij CVA_GOVERNANCE_FAIL_SECURE=true -- dan wordt het request geblokkeerd).
            # GovernanceVetoError wordt altijd gepropageerd (nooit geslikt).
            decision_id: str | None = None
            try:
                council = await build_council(self.db)
                decision = await require_council_approval(
                    council=council,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action_type="cva.chat",
                    action_params={"conversation_id": conversation_id},
                    reasoning=message[:500],
                    model_id=getattr(effective_llm, "model", "unknown"),
                    db=self.db,
                )
                decision_id = str(decision.decision_id)
            except GovernanceVetoError:
                raise  # Governance veto -- altijd propageren, nooit degraded mode
            except HTTPException as http_exc:
                # Council infrastructure fout (500+)
                if _CVA_FAIL_SECURE:
                    raise HTTPException(
                        status_code=503,
                        detail="governance gate unavailable (fail-secure mode)",
                    ) from http_exc
                logger.error(
                    "council gate unavailable, proceeding without approval: %s",
                    http_exc.detail,
                    exc_info=True,
                )
                async with best_effort("council degraded mode audit log"):
                    await governance_bus.emit(
                        AuditLogEmitEvent(
                            tenant_id=tenant_id,
                            event_type="council_degraded_mode",
                            threat_level="warning",
                            client_ip="service",
                            endpoint="/api/v1/cva/chat",
                            description="council gate unavailable, chat proceeds without approval",
                            event_metadata={"user_id": user_id, "reason": str(http_exc.detail)},
                        )
                    )
            except Exception as e:
                # Infrastructure fout voor council call
                if _CVA_FAIL_SECURE:
                    raise HTTPException(
                        status_code=503,
                        detail="governance gate unavailable (fail-secure mode)",
                    ) from e
                logger.error(
                    "council gate error, proceeding: %s: %s",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                async with best_effort("council degraded mode audit log"):
                    await governance_bus.emit(
                        AuditLogEmitEvent(
                            tenant_id=tenant_id,
                            event_type="council_degraded_mode",
                            threat_level="warning",
                            client_ip="service",
                            endpoint="/api/v1/cva/chat",
                            description="council gate error, chat proceeds without approval",
                            event_metadata={"user_id": user_id, "error_type": type(e).__name__},
                        )
                    )

            # Generate response from LLM
            result = await effective_llm.generate(
                messages=message_history,
                system_prompt=system_prompt,
                return_usage=True,
            )
            # return_usage=True guarantees Tuple[str, Dict] return
            assert isinstance(result, tuple)
            content, usage = result

            # Store user message
            user_msg = ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content=message,
                tenant_id=tenant_id,
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(user_msg)

            # Store assistant response
            assistant_msg = ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=content,
                tenant_id=tenant_id,
                tokens_used=usage["total_tokens"],
                model=usage.get("model", "unknown"),
                timestamp=datetime.now(timezone.utc),
            )
            self.db.add(assistant_msg)

            # Update conversation title if first message
            if not conversation.title:
                conversation.title = self._generate_title(message)

            conversation.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(conversation)

            # Check GDPR Art. 6(1)(a) consent for personalization features.
            # Basic chat always works (Art. 6(1)(b) contract); only memory writes need consent.
            # Result is surfaced in metadata so the frontend can show a consent banner.
            import importlib

            _ccm = importlib.import_module("src.core.governance.cookie_consent")
            consent_mgr = _ccm.CookieConsentManager(self.db)
            has_personalization = await consent_mgr.is_consent_given(
                str(user_id), tenant_id, ConsentCategory.PERSONALIZATION
            )
            personalization_consent_status = "granted" if has_personalization else "required"

            # ADR-019: audit trail for every CVA chat turn via best_effort
            # (audit failure must never block the chat response)
            async with best_effort("cva chat audit log"):
                await governance_bus.emit(
                    AuditLogEmitEvent(
                        tenant_id=tenant_id,
                        event_type="cva_chat",
                        threat_level="info",
                        client_ip="service",
                        endpoint="/api/v1/cva/chat",
                        description=f"CVA chat turn conversation_id={conversation.id}",
                        event_metadata={
                            "user_id": user_id,
                            "resource": f"conversation:{conversation.id}",
                            "tokens": usage["total_tokens"],
                        },
                    )
                )

            # Fire-and-forget: write episodic memory candidate for this turn.
            # Uses self._db_factory if available (injected for production), skips
            # gracefully in environments where it is not configured.
            if getattr(self, "_db_factory", None) is not None:
                db_factory = self._db_factory
                assert db_factory is not None  # guarded above
                task = asyncio.create_task(
                    _write_memory_candidate(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        conversation_id=conversation.id,
                        user_message=message,
                        assistant_response=content,
                        db_factory=db_factory,
                    )
                )

                # Track task to prevent "destroyed but pending" warning
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

                # Log errors but don't crash the main request
                def _handle_task_exception(
                    t: asyncio.Task[None],
                ) -> None:
                    exc = t.exception()
                    if exc:
                        logger.warning(
                            "Background memory write failed",
                            extra={"error": str(exc), "error_type": type(exc).__name__},
                        )

                task.add_done_callback(_handle_task_exception)

            return {
                "response": content,
                "conversation_id": conversation.id,
                "metadata": {
                    "tokens_used": usage["total_tokens"],
                    "model": usage.get("model", "unknown"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "personalization_consent_status": personalization_consent_status,
                },
                "confidence": None,
                "suggestions": [],
                "actions": [],
                "llm_provider_used": _PROVIDER_DISPLAY.get(effective_llm.provider.provider_name),
                "decision_id": decision_id,
            }
        except Exception:
            status = "error"
            raise
        finally:
            # Record metrics (always executed, even on exception)
            duration = time.time() - start_time
            if cva_chat_duration_seconds:
                cva_chat_duration_seconds.labels(tenant_id=tenant_id_str).observe(duration)
            if cva_chat_requests_total:
                cva_chat_requests_total.labels(tenant_id=tenant_id_str, status=status).inc()

    async def chat_stream(
        self,
        message: str,
        user_id: int,
        tenant_id: int,
        conversation_id: Optional[int] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response as JSON-encoded SSE data strings.

        Yields JSON strings (without the "data: " SSE prefix):
          - First yield: {"conversation_id": <int>}
          - Subsequent yields: {"content": "<chunk>"}

        User message is flushed to DB before streaming starts.
        Assistant message is committed in a finally block -- partial
        responses are persisted even on client disconnect.
        """
        # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): zie `chat`. Een stream kan na de
        # eerste yield geen HTTP-status meer geven, dus een weigering is een foutkader met code
        # NOODSTOP en daarna niets: geen gesprek, geen Council, geen model.
        try:
            await eis_chat_actief(tenant_id)
        except KlantStilgezet as stop:
            yield json.dumps({"error": stop.bericht, "code": "NOODSTOP"})
            return

        # Get or create conversation
        if conversation_id:
            conversation = await self._get_conversation(conversation_id, user_id, tenant_id)
            if not conversation:
                raise ValueError("Conversation not found or access denied")
        else:
            conversation = await self._create_conversation(user_id, tenant_id)

        # Governance gate: EU AI Act Art. 14 -- council deliberation voor LLM stream
        # Degraded mode: als council niet beschikbaar is gaat stream door met decision_id=None
        # (tenzij CVA_GOVERNANCE_FAIL_SECURE=true -- dan wordt het request geblokkeerd).
        # GovernanceVetoError wordt altijd gepropageerd.
        decision_id: str | None = None
        _stream_model_id = getattr(await self._llm_voor(tenant_id), "model", "unknown")
        try:
            council = await build_council(self.db)
            decision = await require_council_approval(
                council=council,
                tenant_id=tenant_id,
                user_id=user_id,
                action_type="cva.chat_stream",
                action_params={"conversation_id": conversation.id},
                reasoning=message[:500],
                model_id=_stream_model_id,
                db=self.db,
            )
            decision_id = str(decision.decision_id)
        except GovernanceVetoError:
            raise  # Governance veto -- altijd propageren, nooit degraded mode
        except HTTPException as http_exc:
            # Council infrastructure fout (500+)
            if _CVA_FAIL_SECURE:
                raise HTTPException(
                    status_code=503,
                    detail="governance gate unavailable (fail-secure mode)",
                ) from http_exc
            logger.error(
                "council gate unavailable for stream, proceeding: %s",
                http_exc.detail,
                exc_info=True,
            )
        except Exception as e:
            if _CVA_FAIL_SECURE:
                raise HTTPException(
                    status_code=503,
                    detail="governance gate unavailable (fail-secure mode)",
                ) from e
            logger.error(
                "council gate error for stream, proceeding: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )

        # Signal conversation_id and decision_id to the client before the LLM call
        yield json.dumps({"conversation_id": conversation.id, "decision_id": decision_id})

        # Build message history and append current message
        message_history = await self._get_message_history(conversation.id, tenant_id)
        message_history.append({"role": "user", "content": message})

        # Persist user message before streaming (survives client disconnect)
        user_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            tenant_id=tenant_id,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Model override (same allowlist check as chat())
        effective_llm = await self._llm_voor(tenant_id)

        # Stream tokens and persist assistant response in finally
        full_chunks: list[str] = []
        try:
            async for chunk in effective_llm.stream_generate(
                messages=message_history,
                system_prompt=system_prompt,
            ):
                full_chunks.append(chunk)
                yield json.dumps({"content": chunk})
        finally:
            content = "".join(full_chunks)
            if content:
                assistant_msg = ConversationMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=content,
                    tenant_id=tenant_id,
                    timestamp=datetime.now(timezone.utc),
                )
                self.db.add(assistant_msg)
                if not conversation.title:
                    conversation.title = self._generate_title(message)
                conversation.updated_at = datetime.now(timezone.utc)
                try:
                    await self.db.commit()
                except Exception:
                    logger.error(
                        "CVAService: failed to commit streaming result for conversation %d",
                        conversation.id,
                        exc_info=True,
                    )
                    await self.db.rollback()
            else:
                await self.db.rollback()

    async def _llm_voor(self, tenant_id: int) -> LLMService:
        """Het taalmodel van de tenant: de meegegeven dienst, anders de keuze van de klant.

        Een `model=` van de aanroeper kiest GEEN ander model meer. Het verzoek mocht kiezen uit drie
        Gemini-modellen (Google, VS) en omzeilde daarmee de keuze van de klant (mistral of ollama);
        brief 2026-10-19, ADR-041 B14. Het model volgt de tenant, niet het verzoek.
        """
        if self._llm is not None:
            return self._llm
        return await LLMService.for_tenant(tenant_id)

    async def _get_conversation(
        self,
        conversation_id: int,
        user_id: int,
        tenant_id: int,
        include_inactive: bool = False,
    ) -> Conversation:
        """
        Get conversation with tenant/user isolation in a single query.
        Never reveals whether a conversation_id exists for another tenant.

        Args:
            conversation_id: ID of the conversation
            user_id: User ID for access control
            tenant_id: Tenant ID for isolation
            include_inactive: If True, include soft-deleted conversations
        """
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.tenant_id == tenant_id,
        )

        if not include_inactive:
            query = query.where(Conversation.is_active.is_(True))

        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise ValueError("Conversation not found or access denied")
        return conversation

    async def _create_conversation(
        self, user_id: int, tenant_id: int, agent_id: str = "cva"
    ) -> Conversation:
        """Create new conversation"""
        conversation = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            is_active=True,
        )
        self.db.add(conversation)
        await self.db.flush()  # Get ID without committing
        return conversation

    async def hard_delete_conversation(
        self, conversation_id: int, user_id: int, tenant_id: int
    ) -> None:
        """GDPR Art. 17: Permanently delete conversation and all messages.

        This is a hard delete (not soft delete) for right-to-erasure requests.
        Messages are deleted first due to foreign key constraints.
        """
        # Verify conversation exists and user has access
        # include_inactive=True allows deleting soft-deleted conversations
        conversation = await self._get_conversation(
            conversation_id, user_id, tenant_id, include_inactive=True
        )

        # Delete messages first (FK constraint)
        await self.db.execute(
            delete(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.tenant_id == tenant_id,
            )
        )

        # Delete conversation -- commit before audit so audit failure never blocks erasure
        await self.db.delete(conversation)
        await self.db.commit()

        # ADR-019: audit trail for GDPR Art.17 erasure via best_effort
        # (audit failure must never block the deletion)
        async with best_effort("gdpr hard delete audit log"):
            await governance_bus.emit(
                AuditLogEmitEvent(
                    tenant_id=tenant_id,
                    event_type="gdpr_erasure",
                    threat_level="info",
                    client_ip="service",
                    endpoint=f"/api/v1/cva/conversations/{conversation_id}",
                    description=f"GDPR Art.17 hard delete conversation:{conversation_id}",
                    event_metadata={
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "deleted_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )

        logger.info(
            "GDPR hard delete: conversation %s deleted for user %s",
            conversation_id,
            user_id,
        )

    async def _get_message_history(
        self, conversation_id: int, tenant_id: int, limit: int = 20
    ) -> list[dict[str, str]]:
        """
        Get conversation message history for LLM context

        Returns: list[dict[str, str]] of messages in format: [{"role": "user", "content": "..."}]
        """
        result = await self.db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.tenant_id == tenant_id,
            )
            .order_by(ConversationMessage.timestamp.asc())
            .limit(limit)
        )
        messages = result.scalars().all()

        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _generate_title(self, first_message: str, max_length: int = 50) -> str:
        """Generate conversation title from first message"""
        title = first_message[:max_length]
        if len(first_message) > max_length:
            title += "..."
        return title

    async def list_conversations(
        self, user_id: int, tenant_id: int, limit: int = 20, offset: int = 0
    ) -> dict[str, list[dict[str, int | str | None | datetime]] | int]:
        """
        List user's conversations with pagination

        Args:
            user_id: Current user ID
            tenant_id: Tenant ID for isolation
            limit: Max conversations to return (1-100)
            offset: Pagination offset

        Returns: dict[str, list[dict[str, int | str | None | datetime]] | int] with conversations list, total count, pagination info

        Optimization:
            Uses LEFT JOIN with COUNT to avoid N+1 query problem
        """
        # Count total conversations for user in this tenant
        count_query = select(func.count(Conversation.id)).where(
            Conversation.user_id == user_id,
            Conversation.tenant_id == tenant_id,
            Conversation.is_active.is_(True),
        )
        result = await self.db.execute(count_query)
        total = result.scalar() or 0

        # OPTIMIZED: Get conversations with message counts in single query
        # Uses LEFT JOIN to avoid N+1 query problem
        query = (
            select(Conversation, func.count(ConversationMessage.id).label("message_count"))
            .outerjoin(
                ConversationMessage,
                Conversation.id == ConversationMessage.conversation_id,
            )
            .where(
                Conversation.user_id == user_id,
                Conversation.tenant_id == tenant_id,
                Conversation.is_active.is_(True),
            )
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        rows = result.all()

        # Build response list from query results
        conv_list: list[dict[str, int | str | None | datetime]] = []
        for conv, message_count in rows:
            conv_list.append(
                {
                    "id": conv.id,
                    "title": conv.title,
                    "agent_id": conv.agent_id,
                    "message_count": message_count,
                    "created_at": conv.created_at.isoformat() if conv.created_at else None,
                    "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                    "tenant_id": conv.tenant_id,  # For tenant isolation verification
                }
            )

        return {
            "conversations": conv_list,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_conversation(
        self, conversation_id: int, user_id: int, tenant_id: int
    ) -> dict[str, int | str | bool | None | list[dict[str, int | str | None]]]:
        """
        Get single conversation with all messages

        Args:
            conversation_id: Conversation ID
            user_id: Current user ID
            tenant_id: Tenant ID for isolation

        Returns: dict[str, int | str | bool | None | list[dict[str, int | str | None]]] with conversation details and messages

        Raises:
            ValueError: If conversation not found or access denied
        """
        conversation = await self._get_conversation(conversation_id, user_id, tenant_id)

        # Get all messages for this conversation, ordered chronologically
        msg_query = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.tenant_id == tenant_id,
            )
            .order_by(ConversationMessage.timestamp.asc())
        )

        result = await self.db.execute(msg_query)
        messages = result.scalars().all()

        return {
            "id": conversation.id,
            "title": conversation.title,
            "agent_id": conversation.agent_id,
            "is_active": conversation.is_active,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "tokens_used": msg.tokens_used,
                    "model": msg.model,
                }
                for msg in messages
            ],
        }

    async def delete_conversation(self, conversation_id: int, user_id: int, tenant_id: int) -> bool:
        """
        Soft delete conversation (set is_active=False)

        Args:
            conversation_id: Conversation ID to delete
            user_id: Current user ID
            tenant_id: Tenant ID for isolation

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If conversation not found or access denied

        Notes:
            - Soft delete: sets is_active=False, does NOT delete messages
            - Idempotent: Can be called multiple times safely
            - Tenant isolation: Only deletes if user owns conversation in their tenant
        """
        # Reuse _get_conversation for authorization checks
        # This will raise ValueError if not found or access denied
        try:
            conversation = await self._get_conversation(conversation_id, user_id, tenant_id)
        except ValueError as e:
            # If conversation not active, still treat as success (idempotent)
            # But if truly not found or access denied, re-raise
            if "not active" in str(e):
                return True  # Already deleted, idempotent success
            raise

        if conversation is None:
            raise ValueError("Conversation not found")

        # Soft delete: set is_active to False
        conversation.is_active = False
        conversation.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        # Audit trail: emit after commit so delete is never blocked by audit failure
        async with best_effort("cva delete_conversation audit"):
            await governance_bus.emit(
                AuditLogEmitEvent(
                    tenant_id=tenant_id,
                    event_type="cva_conversation_deleted",
                    threat_level="info",
                    client_ip="service",
                    endpoint=f"/api/v1/cva/conversations/{conversation_id}",
                    description=f"CVA soft delete conversation:{conversation_id}",
                    event_metadata={"user_id": user_id, "conversation_id": conversation_id},
                )
            )

        return True

    async def get_explain_for_decision(
        self, decision_id: str, tenant_id: int
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """EU AI Act Art. 13: Return council explanation for a decision_id.

        Returns None if the decision_id is not a valid UUID or not found for this tenant.
        """
        import importlib
        from uuid import UUID

        _gov_models = importlib.import_module("src.core.governance.models")
        CouncilDecisionRow = _gov_models.CouncilDecisionRow

        try:
            uid = UUID(decision_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(CouncilDecisionRow).where(
                CouncilDecisionRow.decision_id == uid,
                CouncilDecisionRow.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "decision_id": str(row.decision_id),
            "verdict": row.verdict,
            "explanation_for_user": row.explanation_for_user,
            "deliberation_ms": row.deliberation_ms,
        }
