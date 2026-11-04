"""
Hybrid Search: Vector + BM25 Score Fusion

Combines semantic similarity (ChromaDB) with lexical matching (BM25)
for improved retrieval quality.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.core.evaluation.evaluation_service import QualityGateConfig, evaluation_service
from src.core.knowledge.knowledge_manager import knowledge_manager
from src.core.knowledge.retrieval_engine import SearchQuery
from src.core.observability.metrics import SEARCH_CROSS_TENANT_LEAKAGE_DETECTED_TOTAL
from src.core.search.bm25_service import bm25_service
from src.core.search.cross_encoder_reranker import CrossEncoderReranker, get_reranker

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchConfig:
    """Configuration for hybrid search behavior"""

    # Fusion method: 'rrf' or 'weighted'
    fusion_method: str = "rrf"

    # Alpha: balance between vector (1.0) and BM25 (0.0)
    alpha: float = 0.5

    # RRF parameters
    rrf_k: int = 60
    rrf_vector_boost: float = 1.0
    rrf_bm25_boost: float = 1.0

    # Weighted fusion parameters
    normalize_scores: bool = True
    normalization_method: str = "minmax"  # or "softmax"

    # Search behavior
    fetch_multiplier: int = 3  # Fetch top_k * multiplier candidates
    max_candidates: int = 100

    # Reranking configuration
    use_reranking: bool = False  # Enable cross-encoder reranking
    rerank_multiplier: int = 3  # Fetch top_k * multiplier for reranking stage

    # Evaluation & Safety
    evaluate_results: bool = False
    quality_config: QualityGateConfig | None = None

    def validate(self) -> None:
        """Validate configuration values"""
        if self.fusion_method not in ["rrf", "weighted"]:
            raise ValueError(f"Invalid fusion_method: {self.fusion_method}")
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError(f"Alpha must be in [0, 1]: {self.alpha}")
        if self.rrf_k < 1:
            raise ValueError(f"RRF k must be >= 1: {self.rrf_k}")
        if self.rerank_multiplier < 1:
            raise ValueError(f"Rerank multiplier must be >= 1: {self.rerank_multiplier}")


# Default configuration
DEFAULT_HYBRID_CONFIG = HybridSearchConfig()


@dataclass
class HybridSearchResult:
    """Single result from hybrid search"""

    document_id: str
    content: str
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    vector_score: float
    bm25_score: float
    hybrid_score: float
    source: str  # 'vector', 'bm25', or 'both'


async def hybrid_search(
    tenant_id: int,
    query: str,
    top_k: int = 10,
    config: HybridSearchConfig | None = None,
) -> list[HybridSearchResult]:
    """
    Perform hybrid search combining vector and BM25 retrieval
    """
    if config is None:
        config = DEFAULT_HYBRID_CONFIG

    config.validate()
    logger.info(f"Hybrid search for tenant {tenant_id}: '{query}' using {config.fusion_method}")

    # Fetch more candidates than needed for better fusion
    fetch_k = min(top_k * config.fetch_multiplier, config.max_candidates)

    # Run both searches in parallel
    vector_task = asyncio.create_task(_vector_search(tenant_id, query, fetch_k))
    bm25_task = asyncio.create_task(_bm25_search(tenant_id, query, fetch_k))

    _gathered = await asyncio.gather(vector_task, bm25_task, return_exceptions=True)
    vector_results: Any = _gathered[0]  # TODO(TYPE): replace Any with concrete type
    bm25_results: Any = _gathered[1]  # TODO(TYPE): replace Any with concrete type

    # Handle errors gracefully
    vector_error = isinstance(vector_results, Exception)
    bm25_error = isinstance(bm25_results, Exception)

    # Propagate tenant-specific ValueErrors (e.g. "No index for tenant")
    if isinstance(bm25_results, ValueError):
        raise bm25_results
    if isinstance(vector_results, ValueError):
        raise vector_results

    if vector_error:
        logger.warning(f"Vector search failed: {vector_results}")
        vector_results = []
    if bm25_error:
        logger.warning(f"BM25 search failed: {bm25_results}")
        bm25_results = []
    # Fail if BOTH sources failed
    if vector_error and bm25_error:
        raise RuntimeError("Both vector and BM25 search failed")

    if not isinstance(vector_results, list):
        vector_results = []
    if not isinstance(bm25_results, list):
        bm25_results = []
    # Fuse results
    if config.fusion_method == "rrf":
        fused = _reciprocal_rank_fusion(
            vector_results,
            bm25_results,
            k=config.rrf_k,
            vector_boost=config.rrf_vector_boost,
            bm25_boost=config.rrf_bm25_boost,
        )
    else:
        fused = _weighted_fusion(
            vector_results,
            bm25_results,
            alpha=config.alpha,
            normalize=config.normalize_scores,
        )

    # Sort by hybrid score and return top_k
    fused.sort(key=lambda x: x.hybrid_score, reverse=True)
    top_results = fused[:top_k]

    # Post-fusion tenant validation
    validated_results: list[HybridSearchResult] = []
    for result in top_results:
        result_tenant_id = result.metadata.get("tenant_id")
        if result_tenant_id != tenant_id:
            SEARCH_CROSS_TENANT_LEAKAGE_DETECTED_TOTAL.labels(source="fusion").inc()
            logger.critical(
                f"Cross-tenant leak detected in fusion: result tenant={result_tenant_id}, "
                f"query tenant={tenant_id}"
            )
            continue
        validated_results.append(result)
    top_results = validated_results

    # Optional: Run retrieval evaluation
    if config and config.evaluate_results and top_results:
        try:
            # We evaluate the retrieval quality (context relevance)
            # Since we don't have a final response yet, we pass the top result's content as a proxy
            contexts = [r.content for r in top_results]
            await evaluation_service.evaluate_rag_response(
                tenant_id=tenant_id,
                query=query,
                response=top_results[0].content,  # Top doc as proxy response
                contexts=contexts,
                quality_config=config.quality_config,
                metadata={"source": "hybrid_search_auto_eval"},
            )
        except Exception as e:
            logger.warning(f"Automatic search evaluation failed: {e}")
            # Re-raise if it's a quality gate failure
            if "Quality Gate FAILED" in str(e) or "quality gate" in str(e).lower():
                raise

    logger.info(f"Hybrid search returned {len(top_results)} results")
    return top_results


async def _vector_search(
    tenant_id: int, query: str, top_k: int
) -> list[tuple[str, dict[str, Any], float]]:  # TODO(TYPE): replace Any with concrete type
    """Get vector search results from KnowledgeManager"""
    try:
        # Initialize if needed
        if not knowledge_manager._initialized:
            await knowledge_manager.initialize()

        engine = knowledge_manager.retrieval_engine
        if not engine:
            return []

        # Create search query
        search_query = SearchQuery(query=query, tenant_id=tenant_id, limit=top_k)

        results = await engine.search(search_query)

        return [
            (
                res.entry_id,
                {"content": res.entry.content, **res.entry.metadata},
                res.similarity_score,
            )
            for res in results
        ]
    except Exception as e:
        logger.error(f"Vector search error: {e}")
        raise


async def _bm25_search(
    tenant_id: int, query: str, top_k: int
) -> list[tuple[str, dict[str, Any], float]]:  # TODO(TYPE): replace Any with concrete type
    """Get BM25 search results"""
    try:
        results = await bm25_service.search(
            tenant_id=tenant_id, query=query, top_k=top_k, use_cache=True
        )
        # Inject tenant_id into each doc so post-fusion validation can verify
        # tenant isolation. Without this, metadata.get("tenant_id") returns None
        # and every BM25 result is incorrectly rejected as a cross-tenant leak.
        return [(doc["id"], {**doc, "tenant_id": tenant_id}, score) for doc, score in results]
    except Exception as e:
        logger.error(f"BM25 search error: {e}")
        raise


def _reciprocal_rank_fusion(
    vector_results: list[
        tuple[str, dict[str, Any], float]  # TODO(TYPE): replace Any with concrete type
    ],  # TODO(TYPE): replace Any with concrete type
    bm25_results: list[
        tuple[str, dict[str, Any], float]
    ],  # TODO(TYPE): replace Any with concrete type
    k: int = 60,
    vector_boost: float = 1.0,
    bm25_boost: float = 1.0,
) -> list[HybridSearchResult]:
    """
    Combine results using Reciprocal Rank Fusion (RRF)
    """
    doc_scores: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    for rank, (doc_id, doc_data, score) in enumerate(vector_results, 1):
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {
                "content": doc_data.get("content", ""),
                "metadata": doc_data,
                "vector_score": 0.0,
                "bm25_score": 0.0,
                "rrf_score": 0.0,
                "source": "vector",
            }
        doc_scores[doc_id]["rrf_score"] += vector_boost / (k + rank)
        doc_scores[doc_id]["vector_score"] = score

    for rank, (doc_id, doc_data, score) in enumerate(bm25_results, 1):
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {
                "content": doc_data.get("content", ""),
                "metadata": doc_data,
                "vector_score": 0.0,
                "bm25_score": 0.0,
                "rrf_score": 0.0,
                "source": "bm25",
            }
        else:
            doc_scores[doc_id]["source"] = "both"

        doc_scores[doc_id]["rrf_score"] += bm25_boost / (k + rank)
        doc_scores[doc_id]["bm25_score"] = score

    results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for doc_id, data in doc_scores.items():
        results.append(
            HybridSearchResult(
                document_id=doc_id,
                content=data["content"],
                metadata=data["metadata"],
                vector_score=data["vector_score"],
                bm25_score=data["bm25_score"],
                hybrid_score=data["rrf_score"],
                source=data["source"],
            )
        )

    return results


def _weighted_fusion(
    vector_results: list[
        tuple[str, dict[str, Any], float]  # TODO(TYPE): replace Any with concrete type
    ],  # TODO(TYPE): replace Any with concrete type
    bm25_results: list[
        tuple[str, dict[str, Any], float]
    ],  # TODO(TYPE): replace Any with concrete type
    alpha: float = 0.5,
    vector_weight: float = 1.0,
    bm25_weight: float = 1.0,
    normalize: bool = True,
) -> list[HybridSearchResult]:
    """
    Combine results using weighted score fusion
    """
    vector_scores = [score for _, _, score in vector_results]
    bm25_scores = [score for _, _, score in bm25_results]

    if normalize:
        norm_vector = _normalize_scores_minmax(vector_scores)
        norm_bm25 = _normalize_scores_minmax(bm25_scores)
    else:
        norm_vector = vector_scores
        norm_bm25 = bm25_scores

    doc_scores: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    for i, (doc_id, doc_data, _) in enumerate(vector_results):
        norm_score = norm_vector[i] if i < len(norm_vector) else 0.0
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {
                "content": doc_data.get("content", ""),
                "metadata": doc_data,
                "vector_score": norm_score,
                "bm25_score": 0.0,
                "source": "vector",
            }
        doc_scores[doc_id]["vector_score"] = norm_score

    for i, (doc_id, doc_data, _) in enumerate(bm25_results):
        norm_score = norm_bm25[i] if i < len(norm_bm25) else 0.0
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {
                "content": doc_data.get("content", ""),
                "metadata": doc_data,
                "vector_score": 0.0,
                "bm25_score": norm_score,
                "source": "bm25",
            }
        else:
            doc_scores[doc_id]["source"] = "both"
        doc_scores[doc_id]["bm25_score"] = norm_score

    results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for doc_id, data in doc_scores.items():
        hybrid = (
            alpha * vector_weight * data["vector_score"]
            + (1 - alpha) * bm25_weight * data["bm25_score"]
        )
        results.append(
            HybridSearchResult(
                document_id=doc_id,
                content=data["content"],
                metadata=data["metadata"],
                vector_score=data["vector_score"],
                bm25_score=data["bm25_score"],
                hybrid_score=hybrid,
                source=data["source"],
            )
        )

    return results


def _normalize_scores_minmax(scores: list[float]) -> list[float]:
    """Normalize to [0, 1] range"""
    if not scores:
        return []
    min_s, max_s = min(scores), max(scores)
    if max_s == min_s:
        return [1.0] * len(scores)
    return [(s - min_s) / (max_s - min_s) for s in scores]


def _normalize_scores_softmax(scores: list[float], temp: float = 1.0) -> list[float]:
    """Normalize using softmax"""
    import math

    if not scores:
        return []
    max_s = max(scores)
    exp_s = [math.exp((s - max_s) / temp) for s in scores]
    sum_e = sum(exp_s)
    return [e / sum_e for e in exp_s]


class HybridSearcher:
    """
    Enhanced Hybrid Search with optional cross-encoder reranking

    Implements two-stage retrieval:
    1. Stage 1: Hybrid search (vector + BM25 fusion)
    2. Stage 2: Cross-encoder reranking (optional)

    Usage:
        searcher = HybridSearcher(use_reranking=True)
        results = await searcher.search(tenant_id=1, query="test", top_k=10)
    """

    def __init__(
        self,
        config: HybridSearchConfig | None = None,
        use_reranking: bool = False,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        """
        Initialize hybrid searcher

        Args:
            config: Hybrid search configuration
            use_reranking: Enable cross-encoder reranking
            reranker: Custom reranker instance (uses singleton if not provided)
        """
        self.config = config or HybridSearchConfig()
        self.config.use_reranking = use_reranking or self.config.use_reranking
        self.reranker = reranker or (get_reranker() if self.config.use_reranking else None)

        logger.info(
            f"HybridSearcher initialized (reranking={'enabled' if self.config.use_reranking else 'disabled'})"
        )

    async def search(
        self,
        tenant_id: int,
        query: str,
        top_k: int = 10,
        skip_reranking: bool = False,
        config_override: HybridSearchConfig | None = None,
    ) -> list[HybridSearchResult]:
        """
        Perform hybrid search with optional reranking

        Args:
            tenant_id: Tenant ID for isolation
            query: Search query
            top_k: Final number of results to return
            skip_reranking: Skip reranking even if enabled
            config_override: Override default config for this search

        Returns: List[Any] of HybridSearchResult objects  # TODO(TYPE): replace Any with concrete type
        """
        config = config_override or self.config

        # Determine number of candidates to fetch
        if config.use_reranking and not skip_reranking:
            # Stage 1: Fetch 3x candidates for reranking
            fetch_k = min(top_k * config.rerank_multiplier, config.max_candidates)
            logger.debug(
                f"Two-stage search: fetching {fetch_k} candidates for reranking to top {top_k}"
            )
        else:
            # Single stage: fetch with normal multiplier
            fetch_k = min(top_k * config.fetch_multiplier, config.max_candidates)
            logger.debug(f"Single-stage search: fetching {fetch_k} candidates")

        # Stage 1: Hybrid search (vector + BM25)
        candidates = await hybrid_search(
            tenant_id=tenant_id, query=query, top_k=fetch_k, config=config
        )

        # Stage 2: Rerank if enabled
        if config.use_reranking and not skip_reranking and self.reranker:
            candidates = await self._rerank(query, candidates, top_k)
            logger.info(f"Reranked {len(candidates)} results for query: '{query[:50]}'")
        else:
            # Just take top_k from candidates
            candidates = candidates[:top_k]

        return candidates

    async def _rerank(
        self, query: str, candidates: list[HybridSearchResult], top_k: int
    ) -> list[HybridSearchResult]:
        """
        Stage 2: Cross-encoder reranking

        Args:
            query: Search query
            candidates: Candidate results from hybrid search
            top_k: Number of results to return after reranking

        Returns:
            Reranked list of HybridSearchResult objects
        """
        if not candidates:
            return []

        # Convert HybridSearchResult to reranker format
        docs = [
            {
                "id": c.document_id,
                "content": c.content,
                "score": c.hybrid_score,
                "metadata": c.metadata,
            }
            for c in candidates
        ]

        # Rerank using cross-encoder
        if self.reranker is None:
            return candidates[:top_k]
        reranked = await self.reranker.rerank_async(query, docs, top_k=top_k)

        # Convert back to HybridSearchResult
        # Find original candidates to preserve vector/bm25 scores
        candidate_map = {c.document_id: c for c in candidates}

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for r in reranked:
            original = candidate_map.get(r.doc_id)
            if original:
                # Create new result with rerank score
                results.append(
                    HybridSearchResult(
                        document_id=r.doc_id,
                        content=r.content,
                        metadata=r.metadata,
                        vector_score=original.vector_score,
                        bm25_score=original.bm25_score,
                        hybrid_score=r.rerank_score,  # Use rerank score as final score
                        source=original.source,
                    )
                )

        return results
