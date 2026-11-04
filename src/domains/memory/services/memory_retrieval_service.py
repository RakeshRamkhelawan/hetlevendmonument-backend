"""
MemoryRetrievalService
======================

Hybrid retrieval over persisted MemoryItems.

Sprint A: PostgreSQL full-text search + recency/importance ranking.
Sprint B: pgvector ANN cosine-similarity search added as the preferred path.

Retrieval pipeline (Sprint B):
  1. [Primary]  pgvector ANN -- cosine similarity on content_embedding
  2. [Fallback] Full-text search via tsvector / plainto_tsquery
  3. [Fallback] ILIKE -- for SQLite / test environments

Ranking within each path:
  - importance DESC, confidence DESC, created_at DESC

All queries are ALWAYS tenant-scoped. This is non-negotiable.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import MemoryItem, MemoryRetrievalTrace
from src.domains.memory.observability import RETRIEVAL_LATENCY, RETRIEVAL_RESULTS
from src.domains.memory.schemas import MemoryQueryRequest

# pgvector operators are not importable at module level; we use raw SQL text()
# for ANN queries so no hard dependency on the pgvector Python package.

logger = logging.getLogger(__name__)


class MemoryRetrievalService:
    """
    Retrieval service -- instantiate per request.

    Usage:
        service = MemoryRetrievalService(db=session, tenant_id=tenant_id)
        results = await service.query(request)
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def query(
        self,
        request: MemoryQueryRequest,
        session_id: int | None = None,
        user_id: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute hybrid retrieval and return ranked results.

        Writes a MemoryRetrievalTrace for every query (eval + audit support).
        Returns a dict compatible with MemoryQueryResponse schema.
        """
        start = time.perf_counter()

        # Sprint B: prefer vector ANN if embedding is provided; fall back to FTS
        if query_embedding:
            items = await self._vector_query(request, query_embedding)
            retrieval_method = "vector"
            if not items:
                # Hybrid fallback: also run FTS when vector returns nothing
                items = await self._fulltext_query(request)
                retrieval_method = "hybrid_fallback"
        else:
            items = await self._fulltext_query(request)
            retrieval_method = "fulltext"

        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.debug(
            "MemoryRetrievalService: query complete",
            extra={
                "tenant_id": self._tenant_id,
                "query_len": len(request.query),
                "results": len(items),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        # Write retrieval trace (append-only, never raises)
        try:
            trace = MemoryRetrievalTrace(
                tenant_id=self._tenant_id,
                agent_id=request.agent_id,
                session_id=session_id,
                user_id=user_id,
                query_text=request.query,
                query_tokens=max(1, len(request.query) // 4),
                result_item_ids=[item.id for item in items],
                result_count=len(items),
                retrieval_method=retrieval_method,
                top_k_requested=request.top_k,
                query_time_ms=elapsed_ms,
            )
            self._db.add(trace)
            await self._db.flush()
        except Exception as exc:
            logger.warning(
                "MemoryRetrievalService: failed to write retrieval trace",
                extra={"tenant_id": self._tenant_id, "error": str(exc)},
            )

        RETRIEVAL_LATENCY.labels(tenant_id=str(self._tenant_id), method=retrieval_method).observe(
            elapsed_ms / 1000
        )
        RETRIEVAL_RESULTS.labels(tenant_id=str(self._tenant_id), method=retrieval_method).observe(
            len(items)
        )

        return {
            "items": items,
            "total_candidates": len(items),
            "query_time_ms": round(elapsed_ms, 2),
            "retrieval_method": retrieval_method,
        }

    async def get_by_type(
        self,
        agent_id: str | None,
        memory_types: list[str],
        limit: int = 20,
    ) -> list[MemoryItem]:
        """Return accepted memory items for requested types."""
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.memory_type.in_(memory_types),
                MemoryItem.status == "accepted",
                MemoryItem.deleted_at.is_(None),
            )
            .order_by(
                desc(MemoryItem.importance),
                desc(MemoryItem.created_at),
            )
            .limit(limit)
        )
        if agent_id:
            stmt = stmt.where(MemoryItem.agent_id == agent_id)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_episodes(
        self,
        agent_id: str | None,
        days: int = 7,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """Recent episodic memory for a given agent."""
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.memory_type == "episodic",
                MemoryItem.status == "accepted",
                MemoryItem.deleted_at.is_(None),
                text("memory_items.created_at > NOW() - make_interval(days => :days)").bindparams(
                    days=int(days)
                ),
            )
            .order_by(desc(MemoryItem.created_at))
            .limit(limit)
        )
        if agent_id:
            stmt = stmt.where(MemoryItem.agent_id == agent_id)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fulltext_query(self, request: MemoryQueryRequest) -> list[MemoryItem]:
        """
        PostgreSQL full-text search over memory_items.content.

        Uses plainto_tsquery for safe parameterised search.
        Falls back to ILIKE if tsvector is not yet set up.
        """
        status_filter = request.status_filter or "accepted"
        memory_types = request.memory_types or []

        # Build base filter
        base_conditions = [
            MemoryItem.tenant_id == self._tenant_id,
            MemoryItem.status == status_filter,
            MemoryItem.deleted_at.is_(None),
            MemoryItem.confidence >= request.min_confidence,
        ]

        if request.agent_id:
            base_conditions.append(
                or_(
                    MemoryItem.agent_id == request.agent_id,
                    MemoryItem.agent_id.is_(None),
                )
            )

        if request.privacy_scope:
            # Accept items equal to or broader than requested scope
            scope_hierarchy = ["private", "user", "workspace", "tenant"]
            try:
                scope_idx = scope_hierarchy.index(request.privacy_scope)
                allowed_scopes = scope_hierarchy[scope_idx:]
            except ValueError:
                allowed_scopes = ["tenant"]
            base_conditions.append(MemoryItem.privacy_scope.in_(allowed_scopes))

        if memory_types:
            base_conditions.append(MemoryItem.memory_type.in_(memory_types))

        # Try full-text search first; fall back to ILIKE
        try:
            # PostgreSQL tsvector search
            fts_condition = text(
                "to_tsvector('english', memory_items.content) @@ plainto_tsquery('english', :query)"
            ).bindparams(query=request.query)

            stmt = (
                select(MemoryItem)
                .where(*base_conditions, fts_condition)
                .order_by(
                    desc(MemoryItem.importance),
                    desc(MemoryItem.confidence),
                    desc(MemoryItem.created_at),
                )
                .limit(request.top_k)
            )
            result = await self._db.execute(stmt)
            items = list(result.scalars().all())

            # Fall back to ILIKE if FTS returns nothing
            if not items:
                items = await self._ilike_query(base_conditions, request)

        except Exception:
            # SQLite (testing) or tsvector not available
            items = await self._ilike_query(base_conditions, request)

        return items

    async def _vector_query(
        self,
        request: MemoryQueryRequest,
        embedding: list[float],
    ) -> list[MemoryItem]:
        """
        pgvector ANN search: cosine distance (<=>).

        Uses a raw SQL query so we can ORDER BY the operator result without
        importing the pgvector Python package at module level.

        Only runs when content_embedding IS NOT NULL. Items without embeddings
        are invisible to this path and will surface via FTS fallback instead.

        Distance threshold: 0.5 (cosine similarity >= 0.5).  Items further than
        that are excluded to avoid noisy matches.
        """
        status_filter = request.status_filter or "accepted"
        memory_types = request.memory_types or []
        top_k = request.top_k

        # Build parameterised embedding literal recognised by pgvector
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Scope hierarchy filter (parameterized)
        scope_clause = ""
        scope_params: dict[str, str] = {}
        if request.privacy_scope:
            scope_hierarchy = ["private", "user", "workspace", "tenant"]
            try:
                idx = scope_hierarchy.index(request.privacy_scope)
                allowed = scope_hierarchy[idx:]
            except ValueError:
                allowed = ["tenant"]
            scope_params = {f"scope_{i}": s for i, s in enumerate(allowed)}
            placeholders = ", ".join(f":scope_{i}" for i in range(len(allowed)))
            scope_clause = "AND mi.privacy_scope IN (" + placeholders + ")"

        agent_clause = ""
        if request.agent_id:
            agent_clause = "AND (mi.agent_id = :agent_id OR mi.agent_id IS NULL)"

        # Memory type filter (parameterized)
        type_clause = ""
        type_params: dict[str, str] = {}
        if memory_types:
            type_params = {f"mtype_{i}": t for i, t in enumerate(memory_types)}
            type_placeholders = ", ".join(f":mtype_{i}" for i in range(len(memory_types)))
            type_clause = "AND mi.memory_type IN (" + type_placeholders + ")"

        sql_parts = [
            "SELECT mi.* FROM memory_items mi",
            "WHERE mi.tenant_id = :tenant_id",
            "AND mi.status = :status",
            "AND mi.deleted_at IS NULL",
            "AND mi.confidence >= :min_confidence",
            "AND mi.content_embedding IS NOT NULL",
        ]
        if agent_clause:
            sql_parts.append(agent_clause)
        if scope_clause:
            sql_parts.append(scope_clause)
        if type_clause:
            sql_parts.append(type_clause)
        sql_parts.extend(
            [
                "AND (mi.content_embedding <=> CAST(:embedding AS vector)) < 0.5",
                "ORDER BY (mi.content_embedding <=> CAST(:embedding AS vector)) ASC,",
                "mi.importance DESC,",
                "mi.confidence DESC",
                "LIMIT :top_k",
            ]
        )
        sql = text(" ".join(sql_parts))

        params: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": self._tenant_id,
            "status": status_filter,
            "min_confidence": request.min_confidence,
            "embedding": embedding_str,
            "top_k": top_k,
            **scope_params,
            **type_params,
        }
        if request.agent_id:
            params["agent_id"] = request.agent_id

        try:
            result = await self._db.execute(sql, params)
            rows = result.fetchall()
            if not rows:
                return []
            # Re-fetch as ORM objects so callers get MemoryItem instances
            ids = [r[0] for r in rows]
            orm_result = await self._db.execute(select(MemoryItem).where(MemoryItem.id.in_(ids)))
            items = {i.id: i for i in orm_result.scalars().all()}
            # Preserve ANN order
            return [items[i] for i in ids if i in items]
        except Exception as exc:
            logger.warning(
                f"MemoryRetrievalService: vector query failed, falling back to FTS: {exc}"
            )
            return []

    async def _ilike_query(
        self,
        base_conditions: list[Any],  # TODO(TYPE): replace Any with concrete type
        request: MemoryQueryRequest,
    ) -> list[MemoryItem]:
        """ILIKE fallback for SQLite/test environments."""
        like_pattern = f"%{request.query}%"
        stmt = (
            select(MemoryItem)
            .where(
                *base_conditions,
                MemoryItem.content.ilike(like_pattern),
            )
            .order_by(
                desc(MemoryItem.importance),
                desc(MemoryItem.confidence),
                desc(MemoryItem.created_at),
            )
            .limit(request.top_k)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
