"""
Ollama Embedding Provider - Local, free, privacy-preserving.

Uses nomic-embed-text or similar models via Ollama API.
Built on RobustOllamaClient for production-grade reliability.
"""

import logging
import os
from typing import Any, List, Optional, Union

import numpy as np

from src.core.llm.ollama_client import RobustOllamaClient

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """
    Production-grade local embedding generation via Ollama.

    Benefits:
    - No API costs
    - Full privacy (data stays local)
    - Fast for common phrases (after warmup)
    - No rate limits
    - Automatic retries and fallback (via RobustOllamaClient)
    - Health monitoring and graceful degradation
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str | None = None,
        batch_size: int = 32,
        timeout_secs: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self._dimension = 768  # nomic-embed-text dimension

        # Use RobustOllamaClient for production reliability
        self._client = RobustOllamaClient(
            base_url=base_url,
            timeout_secs=timeout_secs,
            max_retries=max_retries,
            preferred_models=[model],
        )

        logger.info(f"OllamaEmbedder initialized: {model} @ {self._client.base_url}")

    async def embed(
        self, text: str
    ) -> np.ndarray[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate embedding for single text with automatic retry/fallback.

        Args:
            text: Input text to embed

        Returns:
            numpy array of shape (768,) for nomic-embed-text, or zero vector if error
        """
        if not text or not text.strip():
            return np.zeros(self._dimension)

        result = await self._client.embed(text, model=self.model)

        if result.get("success"):
            embedding = result.get("embedding", [])
            return np.array(embedding, dtype=np.float32) if embedding else np.zeros(self._dimension)
        else:
            # Graceful degradation: log error but return zero vector
            logger.warning(f"Embedding failed: {result.get('error', 'unknown error')}")
            return np.zeros(self._dimension)

    async def embed_batch(
        self, texts: list[str]
    ) -> np.ndarray[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate embeddings for batch of texts with concurrent processing.

        Args:
            texts: List[Any] of input texts  # TODO(TYPE): replace Any with concrete type

        Returns:
            numpy array of shape (len(texts), 768)
        """
        if not texts:
            return np.zeros((0, self._dimension))

        import asyncio

        # Process in batches concurrently
        all_embeddings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]

            batch_embeddings = await asyncio.gather(
                *[self.embed(text) for text in batch], return_exceptions=False
            )

            # Errors already handled in embed() with graceful degradation
            all_embeddings.extend(batch_embeddings)

        return np.vstack(all_embeddings) if all_embeddings else np.zeros((0, self._dimension))

    async def close(self) -> None:
        """Close HTTP session."""
        await self._client.close()

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension

    async def health_check(self) -> bool:
        """Check if Ollama is available and model is loaded."""
        health = await self._client.health_check()
        return bool(health.get("healthy", False))
