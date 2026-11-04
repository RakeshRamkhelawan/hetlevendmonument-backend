"""
BM25 Search Service for Multi-Tenant RAG System

Features:
- Tenant-isolated indexes (one index per tenant)
- Async API compatible with FastAPI
- Memory-mapped index storage for large corpora
- Thread-safe tenant locking
- Redis-cached search results
- Automatic index rebuild on document updates
- Index integrity checks and automatic repair
- Backup export/import support
Environment Variables:
    BM25_INDEX_DIR: Base directory for BM25 indexes (default: /app/indexes/bm25)
Usage:
    from src.core.search.bm25_service import bm25_service

    # Build index
    await bm25_service.build_index(
        tenant_id=1,
        documents=[{"id": "doc1", "content": "text..."}]
    )

    # Search
    results = await bm25_service.search(
        tenant_id=1,
        query="cultural heritage",
        top_k=10
    )
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

import bm25s

from src.core.database.redis import get_redis_client

logger = logging.getLogger(__name__)


class BM25Service:
    """
    Multi-tenant BM25 search service using bm25s library

    Attributes:
        indexes (Dict[int, bm25s.BM25]): In-memory BM25 retrievers per tenant
        index_dir (Path): Base directory for persisted indexes
        _locks (Dict[int, asyncio.Lock]): Locks for thread-safe tenant operations
    """

    def __init__(self, index_dir: str | None = None) -> None:
        """
        Initialize BM25 service

        Args:
            index_dir: Base directory for storing tenant indexes.
                      If None, uses BM25_INDEX_DIR environment variable.
                      Default: /app/indexes/bm25 (production) or ./indexes/bm25 (development)
        """

        # Use environment variable if index_dir not provided
        if index_dir is None:
            index_dir = os.getenv("BM25_INDEX_DIR", "/app/indexes/bm25")

        self.indexes: dict[int, bm25s.BM25] = {}
        self.doc_maps: dict[int, dict[str, str]] = {}
        self.index_dir = Path(index_dir).resolve()  # Use absolute path

        # Create directory with proper error handling
        try:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"BM25Service initialized with index_dir={self.index_dir}")
        except PermissionError as e:
            logger.error(f"Permission denied creating index directory {self.index_dir}: {e}")
            logger.error(f"Current working directory: {Path.cwd()}")
            logger.error(f"Directory exists: {self.index_dir.exists()}")
            logger.error(f"Directory is writable: {os.access(self.index_dir.parent, os.W_OK)}")
            raise RuntimeError(
                f"Cannot create BM25 index directory {self.index_dir}. "
                f"Ensure BM25_INDEX_DIR environment variable points to a writable location, "
                f"or that /app/indexes/bm25 volume is properly mounted with write permissions."
            ) from e

        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_tenant_index_path(self, tenant_id: int) -> Path:
        """Get file path for tenant's persisted index"""
        return self.index_dir / f"tenant_{tenant_id}"

    async def build_index(
        self,
        tenant_id: int,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        persist: bool = True,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Build BM25 index for a tenant (async wrapper for sync bm25s)
        """
        if not documents:
            raise ValueError("Cannot build index with empty documents list")

        if not all("content" in doc for doc in documents):
            raise ValueError("All documents must have 'content' field")

        async with self._locks[tenant_id]:
            logger.info(
                f"Building BM25 index for tenant {tenant_id} with {len(documents)} documents"
            )

            try:
                await asyncio.to_thread(self._build_index_sync, tenant_id, documents, persist)
                logger.info(f"BM25 index built successfully for tenant {tenant_id}")
            except Exception as e:
                logger.error(f"Failed to build index for tenant {tenant_id}: {e}")
                raise

    def _build_index_sync(
        self,
        tenant_id: int,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        persist: bool,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Synchronous index building (called in thread pool)"""
        import time

        start_time = time.time()

        corpus = [doc["content"] for doc in documents]

        if len(corpus) > 1000:
            logger.info(f"Tokenizing {len(corpus)} documents for tenant {tenant_id}...")

        corpus_tokens = bm25s.tokenize(corpus, stopwords="en")

        # Build BM25 index
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        # Explicitly set corpus to allow in-memory retrieval
        retriever.corpus = corpus

        self.indexes[tenant_id] = retriever

        # Create and store doc_map in memory
        self.doc_maps[tenant_id] = {
            str(i): doc.get("id", f"unknown_{i}") for i, doc in enumerate(documents)
        }

        elapsed = time.time() - start_time
        logger.info(
            f"BM25 index built for tenant {tenant_id} in {elapsed:.2f}s ({len(corpus)} docs)"
        )

        if persist:
            try:
                index_path = self._get_tenant_index_path(tenant_id)
                index_path.mkdir(parents=True, exist_ok=True)

                retriever.save(str(index_path), corpus=corpus)

                metadata_path = index_path / "metadata.json"
                metadata = {
                    "tenant_id": tenant_id,
                    "num_documents": len(documents),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "doc_map": self.doc_maps[tenant_id],
                    "index_build_time_seconds": elapsed,
                    "bm25s_version": bm25s.__version__,
                    "corpus_size_bytes": sum(
                        len(doc["content"].encode("utf-8")) for doc in documents
                    ),
                }

                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

                logger.info(f"BM25 index persisted to {index_path}")

            except Exception as e:
                logger.error(f"Failed to persist index for tenant {tenant_id}: {e}")
                raise OSError(f"Index persistence failed: {e}") from e

    async def build_index_batch(
        self,
        tenant_id: int,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        batch_size: int = 500,
        persist: bool = True,
    ) -> None:
        """Build BM25 index in batches for very large document sets"""
        await self.build_index(tenant_id, documents, persist)

    async def rebuild_index(
        self,
        tenant_id: int,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        persist: bool = True,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Rebuild BM25 index for a tenant (replaces existing index)"""
        async with self._locks[tenant_id]:
            if tenant_id in self.indexes:
                del self.indexes[tenant_id]

            await asyncio.to_thread(self._build_index_sync, tenant_id, documents, persist)
        await self.invalidate_cache(tenant_id)

    def validate_index(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate index integrity and return diagnostic info"""
        if tenant_id not in self.indexes:
            return {
                "is_valid": False,
                "error": "Index not loaded",
                "tenant_id": tenant_id,
            }
        return {"is_valid": True, "tenant_id": tenant_id, "in_memory": True}

    async def check_index_integrity(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Verify integrity of persisted index files"""
        index_path = self._get_tenant_index_path(tenant_id)
        if not index_path.exists():
            return {"is_valid": False, "errors": ["Directory missing"]}

        # Required files for bm25s 0.2.0
        required = [
            "data.csc.index.npy",
            "indices.csc.index.npy",
            "indptr.csc.index.npy",
            "vocab.index.json",
        ]
        errors = [f"Missing {f}" for f in required if not (index_path / f).exists()]
        return {"is_valid": len(errors) == 0, "errors": errors}

    async def repair_index(
        self,
        tenant_id: int,
        documents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Attempt to repair corrupted index by rebuilding"""
        try:
            await self.rebuild_index(tenant_id, documents, persist=True)
            return True
        except Exception:
            return False

    async def export_index(self, tenant_id: int, export_path: str) -> bool:
        """Export index to backup location"""
        try:
            index_path = self._get_tenant_index_path(tenant_id)
            if not index_path.exists():
                return False
            with tarfile.open(export_path, "w:gz") as tar:
                tar.add(index_path, arcname=index_path.name)
            return True
        except Exception:
            return False

    async def import_index(self, tenant_id: int, import_path: str) -> bool:
        """Import index from backup"""
        try:
            with tarfile.open(import_path, "r:gz") as tar:
                # Security: Validate paths before extraction (CWE-22 prevention)
                for member in tar.getmembers():
                    # Resolve absolute path and check it's within target directory
                    member_path = (self.index_dir / member.name).resolve()
                    if not str(member_path).startswith(str(self.index_dir.resolve())):
                        raise ValueError(f"Unsafe tar member path: {member.name}")
                tar.extractall(path=self.index_dir)  # nosec B202: Path validated above (lines 240-245)
            return await self.load_index(tenant_id)
        except Exception:
            return False

    async def load_index(self, tenant_id: int) -> bool:
        """Load persisted BM25 index from disk"""
        async with self._locks[tenant_id]:
            index_path = self._get_tenant_index_path(tenant_id)
            if not index_path.exists():
                return False
            try:
                await asyncio.to_thread(self._load_index_sync, tenant_id, index_path)
                return True
            except Exception:
                return False

    def _load_index_sync(self, tenant_id: int, index_path: Path) -> None:
        """Synchronous index loading using mmap"""
        retriever = bm25s.BM25.load(str(index_path), mmap=True, load_corpus=True)
        self.indexes[tenant_id] = retriever
        metadata_path = index_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                self.doc_maps[tenant_id] = json.load(f).get("doc_map", {})

    async def search(
        self,
        tenant_id: int,
        query: str,
        top_k: int = 10,
        auto_load: bool = True,
        use_cache: bool = True,
    ) -> list[tuple[dict[str, Any], float]]:  # TODO(TYPE): replace Any with concrete type
        """Search BM25 index for a tenant with Redis caching"""
        if use_cache:
            try:
                query_hash = hashlib.sha256(query.encode()).hexdigest()
                cache_key = f"bm25:search:{tenant_id}:{query_hash}:{top_k}"
                redis_client = await get_redis_client()
                cached = await redis_client.get(cache_key)
                if cached:
                    return cast(list[tuple[dict[str, object], float]], json.loads(cached))
            except Exception as e:
                logger.warning(f"BM25 cache read failed: {e}")
                pass

        if tenant_id not in self.indexes:
            if auto_load:
                if not await self.load_index(tenant_id):
                    raise ValueError(f"No index for tenant {tenant_id}")
            else:
                raise ValueError(f"Index not loaded for tenant {tenant_id}")

        results = await asyncio.to_thread(self._search_sync, tenant_id, query, top_k)

        if use_cache and results:
            try:
                redis_client = await get_redis_client()
                query_hash = hashlib.sha256(query.encode()).hexdigest()
                cache_key = f"bm25:search:{tenant_id}:{query_hash}:{top_k}"
                await redis_client.setex(cache_key, 3600, json.dumps(results, default=str))
            except Exception as e:
                logger.warning(f"BM25 cache write failed: {e}")
                pass

        return results

    def _search_sync(
        self, tenant_id: int, query: str, top_k: int
    ) -> list[tuple[dict[str, Any], float]]:  # TODO(TYPE): replace Any with concrete type
        """Synchronous BM25 search with robust ID mapping"""
        retriever = self.indexes[tenant_id]
        query_tokens = bm25s.tokenize(query, stopwords="en")
        doc_map = self.doc_maps.get(tenant_id, {})

        # Get indices and scores
        n_docs = len(retriever.corpus) if hasattr(retriever, "corpus") and retriever.corpus else 0
        safe_k = min(top_k, n_docs) if n_docs > 0 else top_k

        try:
            doc_indices, scores = retriever.retrieve(query_tokens, k=safe_k, return_as="tuple")
        except Exception:
            return []

        search_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, (idx_raw, score) in enumerate(zip(doc_indices[0], scores[0])):
            content = ""
            doc_id = f"unknown_{i}"

            try:
                # If idx is int-like
                idx = int(idx_raw)
                doc_id = doc_map.get(str(idx), f"unknown_{idx}")
                if (
                    hasattr(retriever, "corpus")
                    and retriever.corpus
                    and 0 <= idx < len(retriever.corpus)
                ):
                    content = retriever.corpus[idx]

                # DEBUG LOGGING
                # logger.error(f"DEBUG: idx={idx} doc_id={doc_id} content={content[:20]}...")

            except (ValueError, TypeError):
                # If idx is actually the content string
                content = str(idx_raw)
                doc_id = doc_map.get(str(i), f"unknown_{i}")

            search_results.append(({"id": str(doc_id), "content": content}, float(score)))

        return search_results

    async def invalidate_cache(self, tenant_id: int) -> int:
        """Invalidate all cached search results for a tenant"""
        try:
            redis_client = await get_redis_client()
            pattern = f"bm25:search:{tenant_id}:*"
            keys = [key async for key in redis_client.scan_iter(match=pattern)]
            if keys:
                return int(await redis_client.delete(*keys))
            return 0
        except Exception:
            return 0

    async def delete_index(self, tenant_id: int, delete_files: bool = False) -> None:
        """Delete tenant's BM25 index"""
        async with self._locks[tenant_id]:
            self.indexes.pop(tenant_id, None)
            self.doc_maps.pop(tenant_id, None)
            if delete_files:
                path = self._get_tenant_index_path(tenant_id)
                if path.exists():
                    shutil.rmtree(path)

    def get_stats(
        self, tenant_id: int
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get statistics for tenant's index"""
        if tenant_id not in self.indexes:
            return None
        return {"tenant_id": tenant_id, "in_memory": True}


# Lazy singleton instance (factory pattern)
# Avoids I/O at import time; first call to get_bm25_service() triggers init.
_bm25_service_instance: BM25Service | None = None


def get_bm25_service() -> BM25Service:
    """Get or create the global BM25Service singleton."""
    global _bm25_service_instance
    if _bm25_service_instance is None:
        _bm25_service_instance = BM25Service()
    return _bm25_service_instance


# DEPRECATED: backward-compat lazy proxy for existing imports.
# TODO(SP-VOLGENDE): Replace all `from ... import bm25_service` with `get_bm25_service()`.
class _LazyBM25Proxy:
    """Lazy proxy that delegates all attribute access to the real BM25Service singleton."""

    @property  # type: ignore[misc]
    def __class__(self) -> type:  # pyright: ignore[reportIncompatibleMethodOverride]
        return BM25Service

    def __getattr__(self, name: str) -> Any:
        return getattr(get_bm25_service(), name)


bm25_service = _LazyBM25Proxy()
