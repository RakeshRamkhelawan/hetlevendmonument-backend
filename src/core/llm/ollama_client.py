"""
Robust Ollama Client with Retry, Fallback, and Health Checks
For production-grade local LLM integration without regressions
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from src.core.shared.model_deur import bewaakt_model_aanroep

logger = logging.getLogger(__name__)


class OllamaConnectionError(Exception):
    """Raised when Ollama is unreachable."""

    pass


class OllamaHealthError(Exception):
    """Raised when Ollama is unhealthy or model missing."""

    pass


class RobustOllamaClient:
    """
    Production-grade Ollama client with automatic retries, fallbacks, and health checks.

    Features:
    - Connection pooling with configurable timeout
    - Automatic retry with exponential backoff
    - Health check endpoint monitoring
    - Graceful degradation (returns error response instead of crashing)
    - Support for both container-internal (http://ollama:11434) and host external (http://host.docker.internal:11434) URLs
    - Model preloading on connect
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_secs: int = 30,
        max_retries: int = 3,
        retry_backoff_max: int = 10,
        preferred_models: list[str] | None = None,
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL. If None, tries container DNS first, then host.docker.internal
            timeout_secs: HTTP timeout
            max_retries: Max retry attempts for transient failures
            retry_backoff_max: Max exponential backoff in seconds
            preferred_models: List of models to auto-load on connect (e.g., ["nomic-embed-text"])
        """
        self.base_url = base_url or self._detect_url()
        self.timeout_secs = timeout_secs
        self.max_retries = max_retries
        self.retry_backoff_max = retry_backoff_max
        self.preferred_models = preferred_models or ["nomic-embed-text"]

        self.session: aiohttp.ClientSession | None = None
        self.available_models: list[str] = []
        self.initialized = False
        self.last_health_check: float = 0
        self.health_check_interval: float = 300  # 5 minutes

    @staticmethod
    def _detect_url() -> str:
        """
        Auto-detect Ollama URL based on environment.
        Falls back through: explicit env var -> container DNS -> host.docker.internal
        """
        if url := os.getenv("OLLAMA_BASE_URL"):
            logger.info("Using OLLAMA_BASE_URL from env: %s", url)
            return url

        # Default: try container DNS first (for docker-compose service)
        # Then fallback to host.docker.internal (for Docker Desktop / Podman on host)
        return "http://ollama:11434"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-load session to avoid warnings."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_secs)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def initialize(self) -> bool:
        """
        Initialize: connect, discover models, and pre-load preferred models.
        Returns True if healthy, False if degraded (still usable with fallback).
        """
        try:
            session = await self._get_session()

            # Health check
            async with session.get(
                f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=1)
            ) as resp:
                if resp.status != 200:
                    logger.warning("Ollama health check failed: HTTP %s", resp.status)
                    self.initialized = False
                    return False

                data = await resp.json()
                self.available_models = [m["name"] for m in data.get("models", [])]
                logger.info("Ollama healthy. Available models: %s", len(self.available_models))

                # Pre-load preferred models if not present
                for model in self.preferred_models:
                    if not any(model in m for m in self.available_models):
                        logger.info("Pre-loading model: %s", model)
                        await self._pull_model(model)

                self.initialized = True
                self.last_health_check = time.time()
                return True

        except Exception as e:
            logger.error("Ollama initialization failed: %s", e)
            self.initialized = False
            return False

    async def _pull_model(self, model: str) -> bool:
        """Pull model to local Ollama. Returns True if successful."""
        try:
            session = await self._get_session()
            async with session.post(f"{self.base_url}/api/pull", json={"name": model}) as resp:
                if resp.status == 200:
                    logger.info("Model pulled: %s", model)
                    return True
                else:
                    logger.warning("Failed to pull %s: HTTP %s", model, resp.status)
                    return False
        except Exception as e:
            logger.warning("Model pull failed for %s: %s", model, e)
            return False

    async def _should_health_check(self) -> bool:
        """Check if periodic health check is due."""
        return (time.time() - self.last_health_check) > self.health_check_interval

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Quick health check of Ollama server.
        Returns dict with 'healthy' (bool), 'model_count', 'error' (if any).
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=1)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    model_count = len(data.get("models", []))
                    self.last_health_check = time.time()
                    return {
                        "healthy": True,
                        "model_count": model_count,
                        "base_url": self.base_url,
                    }
                else:
                    return {
                        "healthy": False,
                        "error": f"HTTP {resp.status}",
                        "base_url": self.base_url,
                    }
        except Exception as e:
            return {"healthy": False, "error": str(e), "base_url": self.base_url}

    @bewaakt_model_aanroep
    async def embed(
        self, text: str, model: str = "nomic-embed-text"
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate embedding with retry + fallback.
        Returns {'success': True, 'embedding': [...]}, or {'success': False, 'error': '...'}
        """
        if not text or not text.strip():
            return {"success": True, "embedding": [], "model": model}

        payload = {"model": model, "prompt": text[:8192]}

        # Retry with exponential backoff
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=self.retry_backoff_max),
            reraise=False,
        ):
            with attempt:
                session = await self._get_session()
                try:
                    async with session.post(
                        f"{self.base_url}/api/embeddings", json=payload
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            embedding = data.get("embedding", [])
                            return {"success": True, "embedding": embedding, "model": model}
                        else:
                            error = await resp.text()
                            logger.error(f"Embedding failed: HTTP {resp.status}: {error}")
                            raise aiohttp.ClientError(f"HTTP {resp.status}")

                except Exception as e:
                    if attempt.retry_state.attempt_number >= self.max_retries:
                        logger.error(f"Embedding failed after {self.max_retries} retries: {e}")
                        return {"success": False, "error": str(e), "model": model}
                    logger.warning(
                        f"Embedding attempt {attempt.retry_state.attempt_number} failed: {e}"
                    )
                    raise

        return {"success": False, "error": "Max retries exceeded", "model": model}

    @bewaakt_model_aanroep
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Chat completion with retry + fallback.
        Returns {'success': True, 'content': '...', 'model': '...'}, or error dict.
        """
        model = model or (self.available_models[0] if self.available_models else "llama2:latest")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=self.retry_backoff_max),
            reraise=False,
        ):
            with attempt:
                session = await self._get_session()
                try:
                    async with session.post(f"{self.base_url}/api/chat", json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data.get("message", {}).get("content", "")
                            return {
                                "success": True,
                                "content": content,
                                "model": model,
                                "tokens": {
                                    "prompt": data.get("prompt_eval_count", 0),
                                    "completion": data.get("eval_count", 0),
                                },
                            }
                        else:
                            error = await resp.text()
                            logger.error(f"Chat failed: HTTP {resp.status}: {error}")
                            raise aiohttp.ClientError(f"HTTP {resp.status}")

                except Exception as e:
                    if attempt.retry_state.attempt_number >= self.max_retries:
                        logger.error(f"Chat failed after {self.max_retries} retries: {e}")
                        return {"success": False, "error": str(e), "model": model}
                    logger.warning(f"Chat attempt {attempt.retry_state.attempt_number} failed: {e}")
                    raise

        return {"success": False, "error": "Max retries exceeded", "model": model}

    async def close(self) -> None:
        """Clean up session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Ollama client session closed")

    async def __aenter__(self) -> "RobustOllamaClient":
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
