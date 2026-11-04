"""
Embedding Service - Generate vector embeddings for text content
Supports multiple embedding models with fallback mechanisms
"""

import asyncio
import hashlib
from enum import Enum
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np
import numpy.typing as npt

from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.caching import cache_system

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from sentence_transformers import SentenceTransformer


class _HubTensor(Protocol):
    def numpy(self) -> npt.NDArray[np.float32]: ...


class _HubEncoder(Protocol):
    def __call__(self, texts: list[str]) -> _HubTensor: ...


from src.core.caching.cache_layer import cached
from src.core.middleware.tenant_context import get_tenant_id
from src.core.shared.config import get_settings
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class EmbeddingModel(Enum):
    """Available embedding models"""

    SENTENCE_TRANSFORMER = "sentence_transformer"
    OPENAI_ADA = "openai_ada"
    GOOGLE_UNIVERSAL = "google_universal"
    MOCK_EMBEDDING = "mock_embedding"


class EmbeddingService:
    """
    Service for generating text embeddings
    Provides caching and fallback mechanisms
    """

    def __init__(self, model: EmbeddingModel = EmbeddingModel.MOCK_EMBEDDING) -> None:
        self.model = model
        self.model_instance: object | None = None
        self._openai_client: AsyncOpenAI | None = None
        self.dimension = 384  # Default dimension
        self._initialized = False
        self._stats: dict[str, int] = {
            "embeddings_generated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
        }

    async def initialize(self) -> bool:
        """Initialize embedding model"""
        try:
            logger.info(f"Initializing embedding service with model: {self.model.value}")

            if self.model == EmbeddingModel.SENTENCE_TRANSFORMER:
                success = await self._initialize_sentence_transformer()
            elif self.model == EmbeddingModel.OPENAI_ADA:
                success = await self._initialize_openai()
            elif self.model == EmbeddingModel.GOOGLE_UNIVERSAL:
                success = await self._initialize_google()
            else:
                # Mock embedding for testing
                success = await self._initialize_mock()

            if success:
                self._initialized = True
                logger.info(
                    f"Embedding service initialized successfully (dimension: {self.dimension})"
                )
            else:
                logger.error("Embedding service initialization failed")

            return success

        except Exception as e:
            logger.error(f"Embedding service initialization error: {e}")
            return False

    async def _initialize_sentence_transformer(self) -> bool:
        """Initialize SentenceTransformer model"""
        try:
            # Try to import SentenceTransformer
            from sentence_transformers import SentenceTransformer

            # Use a lightweight model for production
            model_name = "all-MiniLM-L6-v2"
            # Keep the concrete model in a local: self.model_instance is typed
            # `object | None` because it also holds a tfhub model (see line 148).
            model = SentenceTransformer(model_name)
            self.model_instance = model
            dim = model.get_sentence_embedding_dimension()
            self.dimension = dim if dim is not None else 768

            return True

        except ImportError:
            logger.warning("SentenceTransformer not available, falling back to mock")
            return await self._initialize_mock()
        except Exception as e:
            logger.error(f"Failed to initialize SentenceTransformer: {e}")
            return await self._initialize_mock()

    async def _initialize_openai(self) -> bool:
        """Initialize OpenAI embedding model"""
        try:
            from openai import AsyncOpenAI

            settings = get_settings()
            if not hasattr(settings, "openai_api_key") or not settings.openai_api_key:
                logger.warning("OpenAI API key not configured, falling back to mock")
                return await self._initialize_mock()

            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.dimension = 1536  # Ada-002 dimension

            # Test the connection
            await self._openai_client.embeddings.create(
                model="text-embedding-ada-002", input="test"
            )

            return True

        except ImportError:
            logger.warning("OpenAI library not available, falling back to mock")
            return await self._initialize_mock()
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI embeddings: {e}")
            return await self._initialize_mock()

    async def _initialize_google(self) -> bool:
        """Initialize Google Universal Sentence Encoder"""
        try:
            import tensorflow_hub as hub

            # Load Google Universal Sentence Encoder
            self.model_instance = hub.load("https://tfhub.dev/google/universal-sentence-encoder/4")
            self.dimension = 512  # USE dimension

            return True

        except ImportError:
            logger.warning("TensorFlow Hub not available, falling back to mock")
            return await self._initialize_mock()
        except Exception as e:
            logger.error(f"Failed to initialize Google USE: {e}")
            return await self._initialize_mock()

    async def _initialize_mock(self) -> bool:
        """Initialize mock embedding for testing"""
        self.model = EmbeddingModel.MOCK_EMBEDDING
        self.dimension = 384
        logger.info("Using mock embedding service for testing")
        return True

    @cached(ttl=3600, key_prefix="embedding")
    @bewaakt_model_aanroep
    async def generate_embedding(self, text: str) -> npt.NDArray[np.float32] | None:
        """
        Generate embedding for text content

        Args:
            text: Input text (ASCII-only)

        Returns:
            Numpy array embedding or None if failed
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Ensure ASCII compliance
            ascii_text = text.encode("ascii", errors="ignore").decode("ascii")

            if not ascii_text.strip():
                return None

            # Generate cache key -- prefixed with tenant_id to prevent cross-tenant cache leaks
            text_hash = hashlib.md5(ascii_text.encode("ascii"), usedforsecurity=False).hexdigest()
            _tid = get_tenant_id() or 0
            # NOTE: t0 = system namespace; never a real tenant (tenant_id > 0 per ADR-005)
            cache_key = f"t{_tid}:embedding_{self.model.value}_{text_hash}"

            # Try cache first
            cached_embedding = await cache_system.get(cache_key)
            if cached_embedding is not None:
                self._stats["cache_hits"] += 1
                return cast(
                    npt.NDArray[np.float32],
                    np.array(cached_embedding),
                )

            self._stats["cache_misses"] += 1

            # Generate embedding based on model
            if self.model == EmbeddingModel.SENTENCE_TRANSFORMER:
                embedding = await self._generate_sentence_transformer_embedding(ascii_text)
            elif self.model == EmbeddingModel.OPENAI_ADA:
                embedding = await self._generate_openai_embedding(ascii_text)
            elif self.model == EmbeddingModel.GOOGLE_UNIVERSAL:
                embedding = await self._generate_google_embedding(ascii_text)
            else:
                embedding = await self._generate_mock_embedding(ascii_text)

            if embedding is not None:
                # Cache the result
                await cache_system.set(cache_key, embedding.tolist())
                self._stats["embeddings_generated"] += 1
                return embedding
            else:
                self._stats["errors"] += 1
                return None

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            self._stats["errors"] += 1
            return None

    async def _generate_sentence_transformer_embedding(
        self, text: str
    ) -> npt.NDArray[np.float32] | None:
        """Generate embedding using SentenceTransformer"""
        try:
            if not self.model_instance:
                return None

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            st_model = cast("SentenceTransformer", self.model_instance)
            embedding = await loop.run_in_executor(None, st_model.encode, text)

            return cast(
                npt.NDArray[np.float32],
                np.array(embedding),
            )

        except Exception as e:
            logger.error(f"SentenceTransformer embedding error: {e}")
            return None

    async def _generate_openai_embedding(self, text: str) -> npt.NDArray[np.float32] | None:
        """Generate embedding using OpenAI API"""
        try:
            if self._openai_client is None:
                return None
            response = await self._openai_client.embeddings.create(
                model="text-embedding-ada-002", input=text
            )

            embedding = response.data[0].embedding
            return cast(
                npt.NDArray[np.float32],
                np.array(embedding),
            )

        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            return None

    async def _generate_google_embedding(self, text: str) -> npt.NDArray[np.float32] | None:
        """Generate embedding using Google Universal Sentence Encoder"""
        try:
            if not self.model_instance:
                return None

            # Run in thread pool
            loop = asyncio.get_event_loop()
            model = cast(_HubEncoder, self.model_instance)
            embedding = await loop.run_in_executor(None, lambda: model([text]).numpy()[0])

            return cast(
                npt.NDArray[np.float32],
                embedding,
            )

        except Exception as e:
            logger.error(f"Google USE embedding error: {e}")
            return None

    async def _generate_mock_embedding(self, text: str) -> npt.NDArray[np.float32] | None:
        """Generate mock embedding for testing"""
        try:
            # Create deterministic embedding based on text hash
            text_hash = hashlib.md5(text.encode("ascii"), usedforsecurity=False).hexdigest()

            # Convert hash to seed for reproducible results
            seed = int(text_hash[:8], 16)
            np.random.seed(seed)

            # Generate normalized random vector
            embedding = np.random.normal(0, 1, self.dimension)
            embedding = embedding / np.linalg.norm(embedding)

            return cast(
                npt.NDArray[np.float32],
                embedding.astype(np.float32),
            )

        except Exception as e:
            logger.error(f"Mock embedding error: {e}")
            return None

    @bewaakt_model_aanroep
    async def generate_embeddings_batch(
        self, texts: list[str], batch_size: int = 32
    ) -> list[npt.NDArray[np.float32] | None]:
        """
        Generate embeddings for multiple texts in batches

        Args:
            texts: List[Any] of text strings
            batch_size: Number of texts to process in each batch

        Returns: List[Any] of embeddings (same order as input)
        """
        if not self._initialized:
            await self.initialize()

        results: list[npt.NDArray[np.float32] | None] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results: list[npt.NDArray[np.float32] | None] = []
            # Process batch
            for text in batch:
                embedding = await self.generate_embedding(text)
                batch_results.append(embedding)

            results.extend(batch_results)

            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.01)

        return results

    async def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity between two texts

        Args:
            text1: First text
            text2: Second text

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        try:
            embedding1 = await self.generate_embedding(text1)
            embedding2 = await self.generate_embedding(text2)

            if embedding1 is None or embedding2 is None:
                return 0.0

            # Cosine similarity
            similarity = np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )

            # Ensure result is between 0 and 1
            return max(0.0, min(1.0, float(similarity)))

        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0

    async def find_similar_texts(
        self, query_text: str, candidate_texts: list[str], threshold: float = 0.7
    ) -> list[tuple[str, float]]:
        """
        Find texts similar to query text

        Args:
            query_text: Text to find similarities for
            candidate_texts: List[Any] of candidate texts
            threshold: Minimum similarity threshold

        Returns: List[Any] of (text, similarity_score) tuples sorted by similarity
        """
        try:
            query_embedding = await self.generate_embedding(query_text)
            if query_embedding is None:
                return []

            candidate_embeddings = await self.generate_embeddings_batch(candidate_texts)

            similarities: list[tuple[str, float]] = []
            for i, candidate_embedding in enumerate(candidate_embeddings):
                if candidate_embedding is not None:
                    similarity = np.dot(query_embedding, candidate_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(candidate_embedding)
                    )

                    if similarity >= threshold:
                        similarities.append((candidate_texts[i], float(similarity)))

            # Sort by similarity descending
            similarities.sort(key=lambda x: x[1], reverse=True)
            return similarities

        except Exception as e:
            logger.error(f"Failed to find similar texts: {e}")
            return []

    def get_model_info(self) -> dict[str, object]:
        """Get information about the current model"""
        return {
            "model": self.model.value,
            "dimension": self.dimension,
            "initialized": self._initialized,
        }

    def get_stats(self) -> dict[str, object]:
        """Get embedding service statistics"""
        total_requests = self._stats["cache_hits"] + self._stats["cache_misses"]
        cache_hit_rate = (
            (self._stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "model": self.model.value,
            "dimension": self.dimension,
            "embeddings_generated": self._stats["embeddings_generated"],
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "errors": self._stats["errors"],
            "initialized": self._initialized,
        }

    async def benchmark_model(self, test_texts: list[str] | None = None) -> dict[str, object]:
        """Benchmark embedding model performance"""
        if test_texts is None:
            test_texts = [
                "This is a test sentence for embedding.",
                "Another example text for performance testing.",
                "How fast can we generate embeddings for this text?",
                "Machine learning and artificial intelligence are fascinating topics.",
                "Knowledge management systems help organize information effectively.",
            ]

        try:
            import time

            start_time = time.time()
            embeddings = await self.generate_embeddings_batch(test_texts)
            end_time = time.time()

            successful_embeddings = [e for e in embeddings if e is not None]

            return {
                "model": self.model.value,
                "test_texts_count": len(test_texts),
                "successful_embeddings": len(successful_embeddings),
                "total_time_seconds": round(end_time - start_time, 3),
                "average_time_per_embedding": round((end_time - start_time) / len(test_texts), 4),
                "dimension": self.dimension,
                "embeddings_per_second": round(len(test_texts) / (end_time - start_time), 2),
            }

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            return {"error": str(e)}


# Default embedding service instance
default_embedding_service = EmbeddingService()
