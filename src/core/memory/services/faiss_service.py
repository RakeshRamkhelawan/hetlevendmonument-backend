"""FAISS Service for vector similarity search."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy imports
_numpy: Any = None
_faiss: Any = None


class _FallbackIndexFlatIP:
    """Minimal FAISS-compatible inner-product index used when faiss is unavailable."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.ntotal = 0
        self._vectors: Any = None

    def add(self, vectors: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        np = _get_numpy()
        array: Any = np.array(vectors, dtype=np.float32)  # TODO(TYPE): replace Any with concrete type
        if array.ndim == 1:
            array = array.reshape(1, -1)

        if self._vectors is None:
            self._vectors = array
        else:
            self._vectors = np.vstack([self._vectors, array])

        if self._vectors is None:
            return
        self.ntotal = len(self._vectors)

    def search(self, query_vector: Any, k: int) -> tuple[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        np = _get_numpy()
        query = np.array(query_vector, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)

        if self._vectors is None or self.ntotal == 0:
            scores = np.full((len(query), k), -np.inf, dtype=np.float32)
            indices = np.full((len(query), k), -1, dtype=np.int64)
            return scores, indices

        similarities = query @ self._vectors.T
        k = min(k, self.ntotal)
        top_indices = np.argsort(-similarities, axis=1)[:, :k]
        top_scores = np.take_along_axis(similarities, top_indices, axis=1)

        if k < similarities.shape[1] or top_scores.shape[1] < k:
            pad_size = max(0, k - top_scores.shape[1])
            if pad_size:
                top_scores = np.pad(
                    top_scores,
                    ((0, 0), (0, pad_size)),
                    constant_values=-np.inf,
                )
                top_indices = np.pad(
                    top_indices,
                    ((0, 0), (0, pad_size)),
                    constant_values=-1,
                )

        return top_scores.astype(np.float32), top_indices.astype(np.int64)


class _FallbackFaissModule:
    IndexFlatIP = _FallbackIndexFlatIP


def _get_numpy() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy-load numpy library"""
    global _numpy
    if _numpy is None:
        import numpy as np_lib

        _numpy = np_lib
    return _numpy


def _get_faiss() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy-load faiss library"""
    global _faiss
    if _faiss is None:
        try:
            import faiss as faiss_lib

            _faiss = faiss_lib
        except ImportError:
            logger.warning("faiss library not installed, using in-process fallback index")
            _faiss = _FallbackFaissModule()
    return _faiss


class FAISSService:
    """Service for FAISS vector index operations."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self._indices: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    def create_index(self, name: str) -> bool:
        """Create a new FAISS index."""
        try:
            faiss = _get_faiss()
            self._indices[name] = faiss.IndexFlatIP(self.dimension)
            logger.debug("Created FAISS index: %s", name)
            return True
        except Exception as exc:
            logger.error("Failed to create FAISS index %s: %s", name, exc)
            return False

    def get_index(self, name: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get an existing index."""
        return self._indices.get(name)

    def has_index(self, name: str) -> bool:
        """Check if an index exists."""
        return name in self._indices

    def add_vectors(self, index_name: str, vectors: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Add vectors to an index."""
        index = self._indices.get(index_name)
        if index is None:
            logger.warning("Index %s does not exist", index_name)
            return False

        try:
            np = _get_numpy()
            if not isinstance(vectors, np.ndarray):
                vectors = np.array(vectors)
            index.add(vectors)
            return True
        except Exception as exc:
            logger.error("Failed to add vectors to %s: %s", index_name, exc)
            return False

    def search(
        self, index_name: str, query_vector: Any, k: int = 5  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[Any | None, Any | None]:  # TODO(TYPE): replace Any with concrete type
        """Search for similar vectors.

        Returns: Tuple[Any, ...] of (scores, indices) or (None, None) on error  # TODO(TYPE): replace Any with concrete type
        """
        index = self._indices.get(index_name)
        if index is None:
            logger.warning("Index %s does not exist", index_name)
            return None, None

        try:
            np = _get_numpy()
            if not isinstance(query_vector, np.ndarray):
                query_vector = np.array([query_vector])
            elif len(query_vector.shape) == 1:
                query_vector = np.array([query_vector])

            scores, indices = index.search(query_vector, k)
            return scores[0], indices[0]
        except Exception as exc:
            logger.error("Failed to search index %s: %s", index_name, exc)
            return None, None

    def reset_index(self, name: str) -> bool:
        """Reset an index (remove all vectors)."""
        return self.create_index(name)

    def remove_index(self, name: str) -> bool:
        """Remove an index."""
        if name in self._indices:
            del self._indices[name]
            return True
        return False

    def get_stats(self, name: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics for an index."""
        index = self._indices.get(name)
        if index is None:
            return {"exists": False, "ntotal": 0}
        return {"exists": True, "ntotal": index.ntotal}

    def rebuild_from_vectors(self, name: str, vectors: list[Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Rebuild an index from a list of vectors."""
        if not self.create_index(name):
            return False

        if not vectors:
            return True

        try:
            np = _get_numpy()
            valid_vectors = [v for v in vectors if v is not None]
            if not valid_vectors:
                return True

            embeddings = np.array(valid_vectors)
            return self.add_vectors(name, embeddings)
        except Exception as exc:
            logger.error("Failed to rebuild index %s: %s", name, exc)
            return False
