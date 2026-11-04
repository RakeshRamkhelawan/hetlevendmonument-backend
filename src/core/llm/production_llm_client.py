"""
Production LLM Client with Gemini Flash/Pro routing, caching, and rate limiting
For P0-3: MOCK-003 - Mock LLM Client Fallback

Features:
- 80% queries -> Gemini Flash (cost optimized)
- 20% queries -> Gemini Pro (complex queries)
- Redis caching (50% hit rate target)
- Rate limiting per user (100 requests/day)
- Retry logic with exponential backoff
- No mock fallback (fail fast)
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from enum import Enum
from typing import Any

from google import genai
from google.genai import types

from src.core.shared.llm_client import (
    LLMClient,
    LLMConfig,
    LLMMessage,
    LLMModel,
    LLMProvider,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity levels for routing"""

    SIMPLE = "simple"  # Use Flash
    MEDIUM = "medium"  # Use Flash
    COMPLEX = "complex"  # Use Pro


class ProductionLLMClient(LLMClient):
    """
    Production-ready LLM client with intelligent routing and caching.

    NO MOCK FALLBACK - Fails fast if API key missing or errors occur.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        """
        Initialize production LLM client.

        Args:
            config: LLM configuration (optional, reads from env if None)

        Raises:
            EnvironmentError: If GOOGLE_API_KEY not set in production
        """
        if config is None:
            config = self._create_config_from_env()

        super().__init__(config)

        # Initialize Gemini API with Client pattern (new SDK)
        self.client = genai.Client(api_key=self.config.api_key)

        # Store model names for routing
        self.flash_model_name = "gemini-2.5-flash"
        self.pro_model_name = "gemini-2.5-pro"

        # Initialize Redis cache (optional)
        self.cache = self._init_cache()

        # Initialize rate limiter
        self.rate_limiter = RateLimiter()

        # Query routing stats
        self.flash_count = 0
        self.pro_count = 0

        logger.info("Production LLM Client initialized with Flash and Pro models")

    @staticmethod
    def _create_config_from_env() -> LLMConfig:
        """Create LLM config from environment variables"""
        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise OSError(
                "GOOGLE_API_KEY must be set in production environment. No mock fallback available."
            )

        return LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_2_5_FLASH,  # Default to Flash
            api_key=api_key,
            max_tokens=2000,
            temperature=0.7,
            timeout=30.0,
            max_retries=3,
            retry_delay=1.0,
        )

    def _init_cache(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Initialize Redis cache for LLM responses"""
        try:
            from src.core.typing import create_sync_redis_client

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            cache = create_sync_redis_client(redis_url, decode_responses=True, socket_timeout=5)
            # Test connection
            if cache is not None:
                getattr(cache, "ping", lambda: None)()
            logger.info("Redis cache initialized for LLM responses")
            return cache
        except Exception as e:
            logger.warning(f"Redis cache unavailable: {e}. Proceeding without cache.")
            return None

    async def chat_completion(
        self, messages: list[LLMMessage], user_id: str | None = None, **kwargs: Any
    ) -> LLMResponse:
        """
        Get chat completion with intelligent routing and caching.

        Args:
            messages: List[Any] of chat messages  # TODO(TYPE): replace Any with concrete type
            user_id: User ID for rate limiting (optional)
            **kwargs: Additional parameters

        Returns:
            LLMResponse with completion

        Raises:
            Exception: If API call fails after retries
        """
        start_time = time.time()

        # Check rate limit
        if user_id and not self.rate_limiter.check_limit(user_id):
            raise Exception(f"Rate limit exceeded for user {user_id}")

        # Generate cache key
        cache_key = self._generate_cache_key(messages)

        # Check cache
        if self.cache is not None:
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                logger.info("Cache hit for LLM request")
                return cached_response

        # Determine query complexity and route to appropriate model
        complexity = self._analyze_complexity(messages)
        model = self._route_query(complexity)

        # Generate completion with retry logic
        response = await self._generate_with_retry(model, messages, **kwargs)

        # Update metrics
        response_time = time.time() - start_time
        self._update_metrics(response_time, response.success)

        # Cache response
        if self.cache is not None and response.success:
            self._cache_response(cache_key, response)

        return response

    async def text_completion(
        self, prompt: str, user_id: str | None = None, **kwargs: Any
    ) -> LLMResponse:
        """
        Get text completion with intelligent routing and caching.

        Args:
            prompt: Text prompt
            user_id: User ID for rate limiting (optional)
            **kwargs: Additional parameters

        Returns:
            LLMResponse with completion
        """
        # Convert to chat format
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, user_id=user_id, **kwargs)

    def _analyze_complexity(self, messages: list[LLMMessage]) -> QueryComplexity:
        """
        Analyze query complexity to determine which model to use.

        Strategy: 80% Flash, 20% Pro
        - Flash: Simple queries, < 500 chars, no code generation
        - Pro: Complex analysis, > 500 chars, code generation, strategic planning
        """
        if not messages:
            return QueryComplexity.SIMPLE

        last_message = messages[-1].content.lower()
        char_count = len(last_message)

        # Complex indicators
        complex_keywords = [
            "analyze",
            "strategic",
            "architecture",
            "design",
            "complex",
            "detailed",
            "comprehensive",
            "code",
            "implementation",
            "algorithm",
            "optimize",
        ]

        # Check for complex indicators
        has_complex_keywords = any(kw in last_message for kw in complex_keywords)
        is_long_query = char_count > 500

        if has_complex_keywords or is_long_query:
            return QueryComplexity.COMPLEX
        elif char_count > 200:
            return QueryComplexity.MEDIUM
        else:
            return QueryComplexity.SIMPLE

    def _route_query(self, complexity: QueryComplexity) -> str:
        """
        Route query to Flash or Pro based on complexity.

        Target: 80% Flash, 20% Pro

        Returns:
            Model name string for use with client.models.generate_content()
        """
        if complexity == QueryComplexity.COMPLEX:
            self.pro_count += 1
            logger.info("Routing to Gemini Pro (complex query)")
            return self.pro_model_name
        else:
            self.flash_count += 1
            logger.info("Routing to Gemini Flash (simple/medium query)")
            return self.flash_model_name

    async def _generate_with_retry(
        self, model_name: str, messages: list[LLMMessage], **kwargs: Any
    ) -> LLMResponse:
        """
        Generate completion with retry logic and exponential backoff.
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                # Convert messages to Gemini format
                prompt = self._messages_to_prompt(messages)

                # Build generation config (new SDK types)
                config = types.GenerateContentConfig(
                    max_output_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                )

                # Generate response using client API
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=config,
                )

                # Extract content - handle both attribute and method access patterns
                content: str | None = None
                if hasattr(response, "text"):
                    content = response.text
                elif hasattr(response, "candidates"):
                    candidates = getattr(response, "candidates", None)
                    if candidates and len(candidates) > 0:
                        candidate = candidates[0]
                        cand_content = getattr(candidate, "content", None)
                        if cand_content is not None:
                            parts = getattr(cand_content, "parts", None)
                            if parts and len(parts) > 0:
                                content = getattr(parts[0], "text", None)
                            else:
                                content = None
                        else:
                            content = None

                # Handle None content - treat as error
                if content is None:
                    return LLMResponse(
                        content="",
                        model=model_name,
                        provider="google",
                        success=False,
                        error_message="LLM returned empty response",
                    )

                usage_metadata = None
                if hasattr(response, "usage_metadata"):
                    usage_metadata = response.usage_metadata

                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0
                if usage_metadata is not None:
                    prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
                    completion_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0
                    total_tokens = getattr(usage_metadata, "total_token_count", 0) or 0

                return LLMResponse(
                    content=content,
                    model=model_name,
                    provider="google",
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    success=True,
                )

            except Exception as e:
                last_exception = e

                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2**attempt)
                    logger.warning(
                        f"LLM request failed (attempt {attempt + 1}/{self.config.max_retries}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM request failed after {self.config.max_retries} retries: {e}")

        # All retries failed
        return LLMResponse(
            content="",
            model="error",
            provider="google",
            success=False,
            error_message=str(last_exception),
        )

    def _messages_to_prompt(self, messages: list[LLMMessage]) -> str:
        """Convert LLMMessage list to Gemini prompt format"""
        prompt_parts: list[str] = []
        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"System: {msg.content}")
            elif msg.role == "user":
                prompt_parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}")

        return "\n\n".join(prompt_parts)

    def _generate_cache_key(self, messages: list[LLMMessage]) -> str:
        """Generate cache key from messages"""
        content = json.dumps(
            [{"role": m.role, "content": m.content} for m in messages], sort_keys=True
        )

        return f"llm:cache:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    def _get_cached_response(self, cache_key: str) -> LLMResponse | None:
        """Get cached response from Redis"""
        if self.cache is None:
            return None
        try:
            cached = self.cache.get(cache_key)
            if cached:
                data = json.loads(cached)
                return LLMResponse(**data)
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")

        return None

    def _cache_response(self, cache_key: str, response: LLMResponse) -> None:
        """Cache response in Redis with 1 hour TTL"""
        if self.cache is None:
            return
        try:
            data = {
                "content": response.content,
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage,
                "success": response.success,
            }
            self.cache.setex(cache_key, 3600, json.dumps(data))  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")

    def get_routing_stats(self) -> dict[str, float | int]:
        """Get query routing statistics"""
        total = self.flash_count + self.pro_count

        return {
            "flash_count": self.flash_count,
            "pro_count": self.pro_count,
            "total_queries": total,
            "flash_percentage": (self.flash_count / max(total, 1)) * 100,
            "pro_percentage": (self.pro_count / max(total, 1)) * 100,
            "target_flash_percentage": 80.0,
            "target_pro_percentage": 20.0,
        }


class RateLimiter:
    """
    Rate limiter for LLM requests per user.
    Limit: 100 requests per day per user
    """

    def __init__(self) -> None:
        self.redis = self._init_redis()
        self.daily_limit = int(os.getenv("LLM_RATE_LIMIT_DAILY", "100"))

    def _init_redis(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Initialize Redis for rate limiting"""
        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            from src.core.typing import create_sync_redis_client

            client = create_sync_redis_client(redis_url, decode_responses=True)
            # Test connection
            if client is not None:
                getattr(client, "ping", lambda: None)()
            return client
        except Exception as e:
            logger.warning(f"Redis unavailable for rate limiting: {e}")
            return None

    def check_limit(self, user_id: str) -> bool:
        """
        Check if user is within rate limit.

        Returns:
            True if within limit, False if exceeded
        """
        if not self.redis:
            # No Redis, allow request (fail open)
            return True

        try:
            key = f"ratelimit:llm:{user_id}"

            # Get current count
            current = self.redis.get(key)

            if current is None:
                # First request today
                self.redis.setex(key, 86400, 1)  # 24 hours
                return True

            current_count = int(current)

            if current_count >= self.daily_limit:
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: {current_count}/{self.daily_limit}"
                )
                return False

            # Increment counter
            self.redis.incr(key)
            return True

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Fail open on errors
            return True


# Factory function
def get_production_llm_client() -> ProductionLLMClient:
    """
    Get production LLM client instance.

    Raises:
        EnvironmentError: If GOOGLE_API_KEY not set
    """
    return ProductionLLMClient()


if __name__ == "__main__":
    # Test the production client
    import asyncio

    async def test() -> None:
        client = get_production_llm_client()

        # Test simple query (should use Flash)
        response = await client.text_completion("What is 2+2?")
        print(f"Simple query: {response.model} - {response.content[:100]}")

        # Test complex query (should use Pro)
        response = await client.text_completion(
            "Provide a detailed architectural analysis of microservices vs monolithic design patterns"
        )
        print(f"Complex query: {response.model} - {response.content[:100]}")

        # Show routing stats
        print("\nRouting stats:", client.get_routing_stats())

    asyncio.run(test())
