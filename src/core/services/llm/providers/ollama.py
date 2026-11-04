"""
Ollama Provider - Local LLM via Ollama

Supports any Ollama model (llama2, mistral, codellama, etc.)
"""

import logging
from typing import Optional
from collections.abc import AsyncGenerator

import httpx

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider): # LLMProvider untyped without mypy plugin
    """
    Ollama provider for local LLM inference

    Configuration:
    - base_url: Ollama server URL (default: http://localhost:11434)
    - model: Model name (e.g., "llama2", "mistral")
    - timeout: Request timeout in seconds
    """

    def _validate_config(self) -> None:
        """Validate Ollama configuration"""
        if not self.config.model:
            raise ValueError("Ollama requires 'model' in config")

        # Set default base_url if not provided
        if not self.config.base_url:
            self.config.base_url = "http://localhost:11434"

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate completion using Ollama"""

        # Convert messages to Ollama format
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Build request payload
        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(f"{self.config.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()

            # Parse Ollama response
            content = data.get("message", {}).get("content", "")

            # Ollama provides token counts
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)

            return LLMResponse(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                model=self.config.model,
                finish_reason="stop",
            )

        except httpx.TimeoutException:
            raise LLMTimeoutError(f"Ollama request timed out after {self.config.timeout}s")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise LLMAuthenticationError("Ollama authentication failed")
            raise LLMServiceError(f"Ollama API error: {e}")
        except Exception as e:
            raise LLMServiceError(f"Ollama error: {e}")

    @property
    def supports_streaming(self) -> bool:
        """Ollama supports streaming"""
        return True

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream completion from Ollama"""

        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST", f"{self.config.base_url}/api/chat", json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json

                        data = json.loads(line)
                        if "message" in data:
                            yield data["message"].get("content", "")
