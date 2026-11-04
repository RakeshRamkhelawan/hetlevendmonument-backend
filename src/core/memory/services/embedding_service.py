"""Embedding Service for generating vector embeddings."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded model
_embedding_model: Any = None


class _FallbackSentenceTransformer:
    """Minimal sentence transformer fallback for test and degraded runtime paths."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def _encode_one(self, text: str) -> object:
        import numpy as np

        vector = np.zeros(384, dtype=np.float32)
        if not text:
            return vector

        for index, char in enumerate(text.encode("utf-8")[:384]):
            vector[index] = char / 255.0
        return vector

    def encode(self, text: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        if isinstance(text, list):
            return [self._encode_one(str(item)) for item in text]
        return self._encode_one(str(text))


def _get_embedding_model() -> object:
    """Lazy-load SentenceTransformer model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded SentenceTransformer model: all-MiniLM-L6-v2")
        except ImportError:
            logger.warning(
                "sentence_transformers library not installed, using fallback embedding model"
            )
            _embedding_model = _FallbackSentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


class EmbeddingService:
    """Service for generating text embeddings using SentenceTransformer."""

    DIMENSION = 384  # all-MiniLM-L6-v2 dimension

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or "all-MiniLM-L6-v2"
        self._model: Any = None

    async def initialize(self) -> None:
        """Initialize the embedding model (lazy-load)."""
        if self._model is None:
            self._model = _get_embedding_model()

    def _ensure_initialized(self) -> None:
        """Ensure model is loaded."""
        if self._model is None:
            self._model = _get_embedding_model()

    def encode(self, text: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Generate embedding for a single text."""
        self._ensure_initialized()
        model = self._model
        if model is None:
            raise RuntimeError("Embedding model is not initialized")
        return model.encode(text)

    def encode_batch(self, texts: list[str]) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Generate embeddings for multiple texts."""
        self._ensure_initialized()
        model = self._model
        if model is None:
            raise RuntimeError("Embedding model is not initialized")
        return model.encode(texts)

    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        return self.DIMENSION

    def get_model_name(self) -> str:
        """Get the name of the embedding model."""
        return self._model_name
