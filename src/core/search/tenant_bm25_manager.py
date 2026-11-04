"""
Tenant-specific BM25 Index Manager

Manages separate BM25 indexes per tenant for multi-tenant isolation.
Uses bm25s for high performance and mmap support.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    import bm25s
except ImportError:
    bm25s = None

logger = logging.getLogger(__name__)


class TenantBM25Manager:
    """
    Manages BM25 indexes per tenant using bm25s

    Each tenant has:
    - Separate index directory (compatible with bm25s.save)
    - Memory-mapped loading for efficiency
    - Isolated scoring

    Usage:
        manager = TenantBM25Manager()
        manager.build_index(tenant_id=1, documents=[...], doc_ids=[...])
        results = manager.search(tenant_id=1, query="test")
    """

    INDEX_DIR = "./data/bm25_indexes"
    INDEX_PREFIX = "tenant_"

    def __init__(self, index_dir: str | None = None) -> None:
        """
        Initialize the BM25 manager

        Args:
            index_dir: Directory for index storage
        """
        self.index_dir = Path(index_dir or self.INDEX_DIR)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index cache
        self._indexes: dict[int, Any] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info(f"TenantBM25Manager initialized: {self.index_dir}")

    def _get_index_path(self, tenant_id: int) -> Path:
        """Get directory path for tenant's index"""
        return self.index_dir / f"{self.INDEX_PREFIX}{tenant_id}"

    def build_index(
        self,
        tenant_id: int,
        documents: list[str],
        doc_ids: list[str],
        stopwords: str = "en",
    ) -> None:
        """
        Build BM25 index for a tenant

        Args:
            tenant_id: Tenant ID
            documents: Document texts
            doc_ids: Document IDs
            stopwords: Language for stopwords (default: "en")
        """
        if len(documents) != len(doc_ids):
            raise ValueError("Documents and doc_ids must have same length")

        # Tokenize documents
        if bm25s is None:
            raise ImportError("bm25s not installed")
        corpus_tokens = bm25s.tokenize(documents, stopwords=stopwords)

        # Build BM25 index
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        # Store in memory
        self._indexes[tenant_id] = retriever

        # Persist to disk
        self._save_index(tenant_id, retriever, documents, doc_ids)

        logger.info(f"Built BM25 index for tenant {tenant_id}: {len(documents)} docs")

    def _save_index(
        self,
        tenant_id: int,
        retriever: Any,  # TODO(TYPE): replace Any with concrete type
        corpus: list[str],
        doc_ids: list[str],
    ) -> None:
        """Save index and metadata to disk"""
        index_path = self._get_index_path(tenant_id)
        index_path.mkdir(parents=True, exist_ok=True)

        # bm25s saves index and corpus
        retriever.save(str(index_path), corpus=corpus)

        # Save ID mapping separately
        metadata = {
            "tenant_id": tenant_id,
            "doc_ids": doc_ids,
            "num_docs": len(doc_ids),
        }

        with open(index_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f)

        logger.debug(f"Saved index to {index_path}")

    def _load_index(self, tenant_id: int) -> bool:
        """Load index from disk"""
        index_path = self._get_index_path(tenant_id)

        if not index_path.exists():
            return False

        if bm25s is None:
            return False
        try:
            # Load BM25 index with mmap
            retriever = bm25s.BM25.load(str(index_path), mmap=True, load_corpus=True)
            self._indexes[tenant_id] = retriever
            logger.debug(f"Loaded index from {index_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load index for tenant {tenant_id}: {e}")
            return False

    def search(
        self, tenant_id: int, query: str, top_k: int = 10, stopwords: str = "en"
    ) -> list[tuple[str, float]]:
        """
        Search tenant's BM25 index

        Args:
            tenant_id: Tenant ID (REQUIRED)
            query: Search query
            top_k: Number of results

        Returns: List[Any] of (doc_id, score) tuples  # TODO(TYPE): replace Any with concrete type
        """
        # Load index if not in memory
        if tenant_id not in self._indexes:
            if not self._load_index(tenant_id):
                logger.warning(f"No index for tenant {tenant_id}")
                return []

        retriever = self._indexes[tenant_id]

        if bm25s is None:
            return []
        # Tokenize query
        query_tokens = bm25s.tokenize(query, stopwords=stopwords)

        # Retrieve indices and scores
        # We use return_as="tuple" to get integer indices for mapping back to doc_ids
        doc_indices, scores = retriever.retrieve(query_tokens, k=top_k, return_as="tuple")

        # Load metadata for ID mapping
        try:
            with open(self._get_index_path(tenant_id) / "metadata.json") as f:
                metadata = json.load(f)
                doc_ids_map = metadata.get("doc_ids", [])
        except Exception:
            logger.warning(f"Could not load metadata for tenant {tenant_id}")
            return []

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # bm25s returns batch results (matrix), take first query row
        for idx, score in zip(doc_indices[0], scores[0]):
            # Map integer index back to original doc_id
            if idx < len(doc_ids_map):
                result_id = doc_ids_map[idx]
            else:
                result_id = f"unknown_{idx}"

            results.append((result_id, float(score)))

        return results

    def delete_index(self, tenant_id: int) -> bool:
        """Delete tenant's index"""
        import shutil

        path = self._get_index_path(tenant_id)

        # Remove from memory
        self._indexes.pop(tenant_id, None)

        # Remove from disk
        if path.exists():
            shutil.rmtree(path)
            logger.info(f"Deleted index for tenant {tenant_id}")
            return True

        return False

    def list_tenants(self) -> list[int]:
        """List all tenants with indexes"""
        tenant_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for path in self.index_dir.glob(f"{self.INDEX_PREFIX}*"):
            if path.is_dir():
                try:
                    tid = int(path.name.replace(self.INDEX_PREFIX, ""))
                    tenant_ids.append(tid)
                except ValueError:
                    pass

        return tenant_ids

    def get_stats(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get index statistics"""
        if tenant_id not in self._indexes:
            self._load_index(tenant_id)

        if tenant_id not in self._indexes:
            return {"error": "Index not found"}

        return {
            "tenant_id": tenant_id,
            "index_path": str(self._get_index_path(tenant_id)),
            "document_count": getattr(self._indexes[tenant_id], "corpus_size", "unknown"),
        }


# Lazy singleton instance (P0 fix: defer instantiation)
_tenant_bm25_manager: TenantBM25Manager | None = None


def get_tenant_bm25_manager() -> TenantBM25Manager:
    global _tenant_bm25_manager
    if _tenant_bm25_manager is None:
        _tenant_bm25_manager = TenantBM25Manager()
    return _tenant_bm25_manager


def __getattr__(name: str) -> Any:
    if name == "tenant_bm25_manager":
        return get_tenant_bm25_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
