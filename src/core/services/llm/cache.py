import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set, cast

from prometheus_client import Counter
from sqlalchemy import text

from src.core.database.database import db_manager
from src.core.database.redis import get_redis_client
from src.core.services.llm.base import LLMMessage

logger = logging.getLogger(__name__)

# Prometheus Metrics
LLM_CACHE_HITS = Counter(
    "llm_cache_hits_total", "Total number of semantic cache hits", ["tenant_id", "match_type"]
)

LLM_CACHE_MISSES = Counter(
    "llm_cache_misses_total", "Total number of semantic cache misses", ["tenant_id"]
)


class SemanticCache:
    """
    Semantic Cache for LLM responses.
    L1: In-Memory (Fastest, per-process)
    L2: Redis (Fast, shared)
    L3: pgvector (Intelligent, persistent)
    """

    _instance: Optional["SemanticCache"] = None
    _l1_cache: dict[str, str] = {}  # Static across instances in same process

    def __new__(cls, *args: Any, **kwargs: Any) -> "SemanticCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, threshold: float = 0.98) -> None:
        self.threshold = threshold
        self.redis_prefix = "llm_cache:"

    async def get(self, tenant_id: int, messages: list[LLMMessage]) -> str | None:
        prompt_text = self._get_prompt_text(messages)
        prompt_hash = self._get_hash(prompt_text)
        cache_key = f"{tenant_id}:{prompt_hash}"

        # 1. L1: In-Memory
        if cache_key in self._l1_cache:
            LLM_CACHE_HITS.labels(tenant_id=str(tenant_id), match_type="l1").inc()
            return self._l1_cache[cache_key]

        # 2. L2: Redis
        try:
            redis = await get_redis_client()
            cached = await redis.get(f"{self.redis_prefix}{cache_key}")
            if cached:
                res = cast(str, cached.decode("utf-8"))
                self._l1_cache[cache_key] = res
                LLM_CACHE_HITS.labels(tenant_id=str(tenant_id), match_type="l2_exact").inc()
                return res
        except Exception:
            pass

        # 3. L3: pgvector
        try:
            from src.core.services.llm.factory import ProviderFactory

            provider = ProviderFactory.create_from_env()
            embedding = await provider.get_embeddings(prompt_text)

            async with db_manager.get_session() as db:
                stmt = text(
                    """
                    SELECT content->>'response' as response
                    FROM collective_knowledge
                    WHERE tenant_id = :tenant_id
                    AND knowledge_type = 'llm_cache'
                    AND (embedding <=> :embedding) < :threshold
                    ORDER BY (embedding <=> :embedding) ASC
                    LIMIT 1
                """
                )
                result = await db.execute(
                    stmt,
                    {
                        "tenant_id": tenant_id,
                        "embedding": str(embedding),
                        "threshold": 1.0 - self.threshold,
                    },
                )
                match = result.scalar_one_or_none()
                if match:
                    match_str = cast(str, match)
                    self._l1_cache[cache_key] = match_str
                    LLM_CACHE_HITS.labels(tenant_id=str(tenant_id), match_type="l3_semantic").inc()
                    asyncio.create_task(self._backfill_redis(tenant_id, prompt_hash, match_str))
                    return match_str
        except Exception:
            pass

        LLM_CACHE_MISSES.labels(tenant_id=str(tenant_id)).inc()
        return None

    async def set(self, tenant_id: int, messages: list[LLMMessage], response: str) -> None:
        if not response:
            return
        prompt_text = self._get_prompt_text(messages)
        prompt_hash = self._get_hash(prompt_text)
        cache_key = f"{tenant_id}:{prompt_hash}"

        # Set L1
        self._l1_cache[cache_key] = response

        # Set L2 (Redis)
        try:
            redis = await get_redis_client()
            await redis.setex(f"{self.redis_prefix}{cache_key}", 86400, response)
        except Exception:
            pass

        # Set L3 (DB)
        try:
            from src.core.services.llm.factory import ProviderFactory

            provider = ProviderFactory.create_from_env()
            embedding = await provider.get_embeddings(prompt_text)

            async with db_manager.get_session() as db:
                stmt = text(
                    """
                    INSERT INTO collective_knowledge
                    (tenant_id, knowledge_type, content_hash, content, embedding, created_at)
                    VALUES (:tenant_id, 'llm_cache', :hash, :content, :embedding, NOW())
                    ON CONFLICT (tenant_id, content_hash) DO NOTHING
                """
                )
                await db.execute(
                    stmt,
                    {
                        "tenant_id": tenant_id,
                        "hash": prompt_hash,
                        "content": json.dumps({"prompt": prompt_text, "response": response}),
                        "embedding": str(embedding),
                    },
                )
                await db.commit()
        except Exception:
            pass

    async def _backfill_redis(self, tenant_id: int, prompt_hash: str, response: str) -> None:
        try:
            redis = await get_redis_client()
            await redis.setex(f"{self.redis_prefix}{tenant_id}:{prompt_hash}", 86400, response)
        except Exception:
            pass

    def _get_prompt_text(self, messages: list[LLMMessage]) -> str:
        return "\n".join([f"{m.role}: {m.content}" for m in messages])

    def _get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()
