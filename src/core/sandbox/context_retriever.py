"""
Context Retriever for Self-Healing Sandbox.

This module retrieves relevant code snippets and documentation
from the tenant's knowledge base to assist the Doctor Agent.
It acts as the "RAG" (Retrieval Augmented Generation) provider.
"""

import logging
from typing import Any, Optional

from src.core.knowledge.embedding_service import EmbeddingService, default_embedding_service
from src.core.knowledge.tenant_vector_manager import (
    TenantVectorManager,
    get_tenant_vector_manager,
)

logger = logging.getLogger(__name__)


class ContextRetriever:
    """
    Retrieves contextual information for error diagnosis.
    Connects Sandbox Runtime -> Vector Database.
    """

    def __init__(
        self,
        vector_manager: TenantVectorManager | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        # `get_tenant_vector_manager()` en niet een module-level exemplaar: dat deed schijf-I/O
        # bij de IMPORT van `tenant_vector_manager`, en daar viel de CI-poort twee keer om
        # (ADR-036 OP-220 -- het mechanisme is niet aangetoond, het faaloppervlak is weg).
        # Wie een eigen manager meegeeft, bouwt er ook nu geen.
        self.vector_manager = vector_manager or get_tenant_vector_manager()
        self.embedding_service = embedding_service or default_embedding_service

    async def get_diagnostic_context(
        self, tenant_id: int, error: str, code: str, limit: int = 3
    ) -> str:
        """
        Fetch relevant context for an error.

        Args:
            tenant_id: Owner of the data
            error: The error message / stack trace
            code: The failing code
            limit: How many snippets to retrieve

        Returns:
            A formatted string suitable for LLM context injection.
        """
        try:
            # 1. Construct Search Query
            # We focus on the error message as the primary semantic signal.
            # We might extract the last line of the error for better precision.
            query_text = f"Fix error: {error[:200]}"

            # 2. Generate Embedding
            embedding = await self.embedding_service.generate_embedding(query_text)

            if embedding is None:
                logger.warning("Failed to generate embedding for validation context.")
                return "Context unavailable (Embedding failure)"

            # 3. Search Vector Store
            # Convert numpy array to list for ChromaDB
            results = self.vector_manager.search(
                tenant_id=tenant_id, query_embedding=embedding.tolist(), top_k=limit
            )

            # 4. Format Results
            if (
                not results
                or not results.get("documents")
                or not results["documents"]
                or len(results["documents"]) == 0
                or not results["documents"][0]
            ):
                return "No relevant context found in knowledge base."

            documents = results["documents"][0]  # ChromaDB returns list of lists
            raw_metadatas = results.get("metadatas")
            metadatas: Any = (  # TODO(TYPE): replace Any with concrete type
                raw_metadatas[0] if raw_metadatas is not None and len(raw_metadatas) > 0 else []
            )
            context_parts = ["Found relevant snippets from knowledge base:"]

            for i, doc in enumerate(documents):
                meta = metadatas[i] if i < len(metadatas) else {}
                source = meta.get("source", "unknown")
                context_parts.append(f"\n[Snippet {i + 1} from {source}]:\n{doc}\n")

            return "\n".join(context_parts)

        except Exception as e:
            logger.error(f"Context retrieval failed for tenant {tenant_id}: {e}")
            return f"Context retrieval error: {e}"


# Hier stond `context_retriever = ContextRetriever()` op moduleniveau. Verwijderd 2026-09-09,
# als aanvulling op ADR-036 OP-220 -- die rij is met een ONVOLLEDIGE fix gesloten en dit maakt
# hem af.
#
# Wat er misging in mijn eerste poging. OP-220 haalde het module-exemplaar uit
# `tenant_vector_manager.py` weg zodat het IMPORTEREN van die module geen ChromaDB-database op
# schijf meer aanmaakt. Dat werkte, maar het exemplaar HIER deed hetzelfde een niveau hoger:
# `ContextRetriever.__init__` roept `get_tenant_vector_manager()` aan, dus het importeren van
# DIT bestand bouwde die database alsnog. Ik had alleen gezocht naar wie het oude exemplaar
# LAS, niet naar wie een `ContextRetriever` op moduleniveau CONSTRUEERDE.
#
# Gemeten 2026-09-09, met de map `data/chromadb` weggeschoven en per module een verse
# interpreter: `import src.core.knowledge.tenant_vector_manager` -> map NIET aangemaakt;
# `import src.core.knowledge.embedding_service` -> NIET aangemaakt;
# `import src.core.sandbox.context_retriever` -> WEL aangemaakt. Daarmee was deze regel de
# laatste overgebleven bron, en dat verklaart waarom de collectie van
# `tests/unit/test_context_retriever.py` in een volledige parallelle run nog steeds omvalt met
# `InternalError: table collections already exists`.
#
# Verwijderen kan zonder gevolg: dit exemplaar had NUL gebruikers. Een scan over `src/`,
# `tests/` en `scripts/` op `context_retriever` vindt alleen deze regel zelf en een import van
# de KLASSE in de test. Wie een retriever nodig heeft, bouwt er een.
