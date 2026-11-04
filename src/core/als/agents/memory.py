import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.core.als.infrastructure.signal_bus import Signal
from src.core.database.database import db_manager
from src.core.services.llm.service import LLMService

logger = logging.getLogger(__name__)


class ContextCompressor:
    """
    Manages agent context window by compressing history and storing long-term insights.

    Features:
    - Rolling window summarization
    - Long-term memory via pgvector (collective_knowledge)
    """

    def __init__(self, window_size: int = 5) -> None:
        self.window_size = window_size

    async def _llm_voor(self, tenant_id: int) -> LLMService:
        """Het taalmodel van de tenant van deze gegevens (brief 2026-10-19, ADR-041 B14).

        Hier stond `LLMService()` in de constructor: het platformmodel voor elke klant.
        """
        return await LLMService.for_tenant(tenant_id)

    async def compress(self, history: list[Signal]) -> str:
        """
        Compresses a list of signals into a string.
        Keeps the most recent N signals intact, summarizes the rest.
        """
        if not history:
            return ""

        if len(history) <= self.window_size:
            return self._serialize_signals(history)

        # Split history
        to_summarize = history[: -self.window_size]
        recent_signals = history[-self.window_size :]

        # 1. Summarize older context
        summary = await self._summarize_signals(to_summarize)

        # 2. Combine with recent raw signals
        recent_text = self._serialize_signals(recent_signals)

        return f"PREVIOUS CONTEXT SUMMARY: {summary}\n\nRECENT EVENTS:\n{recent_text}"

    async def store_insight(self, tenant_id: int, agent_id: str, insight: str) -> None:
        """
        Stores an important insight into the long-term collective knowledge (vector DB).
        """
        try:
            # Generate embedding for the insight
            llm_service = await self._llm_voor(tenant_id)
            embedding: list[float] | None = await llm_service.get_embeddings(insight)

            # Generate content hash for deduplication
            content_hash = hashlib.sha256(insight.encode()).hexdigest()

            # De tenant wordt expliciet AANGENOMEN (ADR-036 OP-155). Dit is een RUWE
            # INSERT op een eigen sessie, buiten elk verzoek. `collective_knowledge` heeft
            # sinds `20260915_rls_resterende_tabellen.py` een RLS-policy die zonder aparte
            # `WITH CHECK` ook voor INSERT geldt; zonder tenantcontext faalt deze schrijf na
            # de omschakeling. `tenant_id` is hier een parameter van de aanroeper.
            from src.core.database.bypass_session import adopt_tenant

            async with db_manager.get_session() as db, adopt_tenant(db, tenant_id):
                stmt = text(
                    """
                    INSERT INTO collective_knowledge
                    (tenant_id, knowledge_type, content_hash, content,
                     embedding, source_agent, created_at)
                    VALUES (:tenant_id, :knowledge_type, :content_hash, :content,
                            :embedding, :source_agent, NOW())
                """
                )

                await db.execute(
                    stmt,
                    {
                        "tenant_id": tenant_id,
                        "knowledge_type": "insight",
                        "content_hash": content_hash,
                        "content": json.dumps({"insight": insight}),
                        "embedding": embedding,
                        "source_agent": agent_id,
                    },
                )
                await db.commit()

            logger.info(f"Stored long-term insight for agent {agent_id}")
        except Exception as e:
            # `exc_info=True` en het exceptietype erbij (backend-patterns regel 10). Zonder
            # die twee is een RLS-overtreding hier niet te onderscheiden van een netwerkfout
            # of een typefout in de SQL -- en na de omschakeling is dat precies het verschil
            # dat je wilt zien. De f-string liet allebei weg.
            logger.error(
                "Failed to store long-term insight: %s: %s", type(e).__name__, e, exc_info=True
            )

    async def _summarize_signals(self, signals: list[Signal]) -> str:
        """Uses LLM to condense multiple signals into a single summary."""
        raw_text = self._serialize_signals(signals)
        prompt = f"Summarize the following agent history into a concise paragraph:\n\n{raw_text}"

        summary: str | None = None
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        llm_service = await self._llm_voor(signals[0].tenant_id)
        result: Any = await llm_service.generate(messages)  # TODO(TYPE): replace Any with concrete type
        if isinstance(result, tuple):
            summary = result[0] if result else None
        else:
            summary = str(result) if result else None

        return summary if summary else "No summary available"

    def _serialize_signals(self, signals: list[Signal]) -> str:
        """Helper to convert signals to a readable text format."""
        lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for s in signals:
            lines.append(f"[{s.timestamp}] {s.source_agent_id}: {json.dumps(s.payload)}")
        return "\n".join(lines)
