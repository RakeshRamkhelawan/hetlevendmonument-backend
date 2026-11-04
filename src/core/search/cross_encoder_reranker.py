"""
Cross-Encoder Reranker for Second-Stage Ranking

Uses a cross-encoder model to rerank initial retrieval results
for improved relevance.

Note: Requires sentence_transformers package for full functionality.
Falls back to passthrough (no reranking) if not available.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy import wrapper - sentence_transformers is heavy (pulls PyTorch ~2GB)
_CrossEncoder: Any = None


def _get_cross_encoder() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy import CrossEncoder to avoid heavy import at module load time."""
    global _CrossEncoder
    if _CrossEncoder is None:
        try:
            from sentence_transformers import CrossEncoder as _CE

            _CrossEncoder = _CE
        except ImportError:
            _CrossEncoder = None
            logger.warning(
                "sentence_transformers not installed - CrossEncoderReranker will use passthrough mode"
            )
    return _CrossEncoder


@dataclass
class RerankResult:
    """Result from reranking"""

    doc_id: str
    content: str
    original_score: float
    rerank_score: float
    rank: int
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class CrossEncoderReranker:
    """
    Cross-Encoder Reranker for improved retrieval quality

    Uses cross-encoder to jointly encode query-document pairs
    for more accurate relevance scoring than bi-encoder similarity.

    If sentence_transformers is not installed, operates in passthrough mode
    (returns documents sorted by original score).

    Usage:
        reranker = CrossEncoderReranker()
        reranked = reranker.rerank(query, documents, top_k=10)
    """

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        max_length: int = 512,
        device: str | None = None,
    ) -> None:
        """
        Initialize the reranker.

        If sentence_transformers is not available, initializes in passthrough mode.
        """
        self.model_name = model_name
        self.max_length = max_length
        self.model = None
        # Check if CrossEncoder is available (either via sentence_transformers or mocking)
        # In tests CrossEncoder is patched with a MagicMock (not _get_cross_encoder),
        # so we must avoid calling it as a zero-arg loader.
        if CrossEncoder is _get_cross_encoder:
            _CrossEncoder = CrossEncoder()
        else:
            _CrossEncoder = CrossEncoder
        self._passthrough_mode = _CrossEncoder is None

        if self._passthrough_mode:
            logger.warning("CrossEncoderReranker running in passthrough mode (no reranking)")
            return

        try:
            # Only import torch if sentence_transformers is available
            import torch

            if device == "cpu" or not torch.cuda.is_available():
                torch.set_num_threads(2)  # Limit intra-op threads

            logger.info(f"Loading cross-encoder: {model_name}")
            self.model = _CrossEncoder(model_name, max_length=max_length, device=device)  # pyright: ignore[reportCallIssue]
            logger.info("Cross-encoder loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model: {e}")
            self._passthrough_mode = True

    def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        top_k: int | None = None,
        return_all: bool = False,
    ) -> list[RerankResult]:
        """
        Rerank documents by cross-encoder relevance.

        In passthrough mode, returns documents sorted by original score.

        Args:
            query: Search query
            documents: List[Any] of docs with 'id', 'content', 'score', 'metadata'  # TODO(TYPE): replace Any with concrete type
            top_k: Return top K results (None = return all)
            return_all: If True, return all docs even if top_k specified

        Returns:
            Reranked list of RerankResult objects
        """
        if not documents:
            return []

        # Passthrough mode - just sort by original score
        if self._passthrough_mode or self.model is None:
            results: list[RerankResult] = []
            for i, doc in enumerate(documents):
                results.append(
                    RerankResult(
                        doc_id=doc.get("id", str(i)),
                        content=doc.get("content", ""),
                        original_score=doc.get("score", 0.0),
                        rerank_score=doc.get("score", 0.0),  # Use original score
                        rank=0,
                        metadata=doc.get("metadata", {}),
                    )
                )
            results.sort(key=lambda x: x.original_score, reverse=True)
            for i, r in enumerate(results):
                r.rank = i + 1
            if top_k and not return_all:
                results = results[:top_k]
            return results

        # Full reranking mode
        pairs = [(query, doc.get("content", "")[: self.max_length]) for doc in documents]

        # Get cross-encoder scores
        scores = self.model.predict(pairs, show_progress_bar=False)

        # Build results with both scores
        results = []
        for i, (doc, rerank_score) in enumerate(zip(documents, scores)):
            results.append(
                RerankResult(
                    doc_id=doc.get("id", str(i)),
                    content=doc.get("content", ""),
                    original_score=doc.get("score", 0.0),
                    rerank_score=float(rerank_score),
                    rank=0,
                    metadata=doc.get("metadata", {}),
                )
            )

        # Sort by rerank score (descending)
        results.sort(key=lambda x: x.rerank_score, reverse=True)

        # Update ranks
        for i, r in enumerate(results):
            r.rank = i + 1

        # Apply top_k
        if top_k and not return_all:
            results = results[:top_k]

        logger.debug(f"Reranked {len(documents)} docs, returning {len(results)}")
        return results

    def get_score(self, query: str, document: str) -> float:
        """Get relevance score for single query-document pair"""
        if self._passthrough_mode or self.model is None:
            return 0.5  # Neutral score in passthrough mode
        return float(self.model.predict([(query, document)])[0])

    def rerank_batch(
        self,
        queries: list[str],
        documents_per_query: list[
            list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): replace Any with concrete type
        top_k: int | None = None,
    ) -> list[list[RerankResult]]:
        """
        Batch rerank multiple queries efficiently.

        In passthrough mode, returns documents sorted by original score.

        Args:
            queries: List[Any] of queries  # TODO(TYPE): replace Any with concrete type
            documents_per_query: List[Any] of document lists (one per query)  # TODO(TYPE): replace Any with concrete type
            top_k: Return top K per query

        Returns: List[Any] of reranked results per query  # TODO(TYPE): replace Any with concrete type
        """
        if len(queries) != len(documents_per_query):
            raise ValueError("Queries and documents lists must have same length")

        # Passthrough mode
        if self._passthrough_mode or self.model is None:
            return [self.rerank(q, docs, top_k) for q, docs in zip(queries, documents_per_query)]

        all_pairs: list[tuple[str, str]] = []
        pair_indices: list[
            tuple[int, dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
        ] = []  # Track which query each pair belongs to

        for q_idx, (query, docs) in enumerate(zip(queries, documents_per_query)):
            for doc in docs:
                all_pairs.append((query, doc.get("content", "")[: self.max_length]))
                pair_indices.append((q_idx, doc))

        if not all_pairs:
            return [[] for _ in queries]

        # Batch inference
        logger.info(f"Batch reranking {len(all_pairs)} pairs across {len(queries)} queries")
        all_scores = self.model.predict(all_pairs, show_progress_bar=False, batch_size=32)

        # Group results by query
        results_by_query: list[list[RerankResult]] = [[] for _ in queries]

        for (q_idx, doc), score in zip(pair_indices, all_scores):
            results_by_query[q_idx].append(
                RerankResult(
                    doc_id=doc.get("id", ""),
                    content=doc.get("content", ""),
                    original_score=doc.get("score", 0.0),
                    rerank_score=float(score),
                    rank=0,
                    metadata=doc.get("metadata", {}),
                )
            )

        # Sort and rank each query's results
        for results in results_by_query:
            results.sort(key=lambda x: x.rerank_score, reverse=True)
            for i, r in enumerate(results):
                r.rank = i + 1
            if top_k:
                results[:] = results[:top_k]

        return results_by_query

    async def rerank_async(
        self,
        query: str,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        top_k: int | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> list[RerankResult]:
        """
        Async wrapper for rerank (runs in thread pool)
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.rerank(query, documents, top_k))


# Lazy-loaded singleton
_reranker_instance: CrossEncoderReranker | None = None


def get_reranker() -> CrossEncoderReranker:
    """Get singleton reranker instance"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = CrossEncoderReranker()
    return _reranker_instance


# Compatibility alias for legacy test patches
CrossEncoder = _get_cross_encoder
