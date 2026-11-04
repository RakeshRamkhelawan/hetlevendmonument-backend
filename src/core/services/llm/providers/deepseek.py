"""
DeepSeek Provider - DeepSeek API

Supports DeepSeek models via their API
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class DeepSeekProvider(LLMProvider):  # LLMProvider untyped without mypy plugin
    """
    DeepSeek provider for API-based inference

    Configuration:
    - api_key: DeepSeek API key (required)
    - model: Model name (e.g., "deepseek-chat")
    - base_url: API endpoint (default: https://api.deepseek.com/v1)
    """

    def _validate_config(self) -> None:
        """Validate DeepSeek configuration"""
        if not self.config.api_key:
            raise ValueError("DeepSeek requires 'api_key' in config")

        if not self.config.model:
            self.config.model = "deepseek-chat"

        if not self.config.base_url:
            self.config.base_url = "https://api.deepseek.com/v1"

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate completion using DeepSeek API"""

        # Convert to OpenAI-compatible format (DeepSeek uses same format)
        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        payload = {
            "model": self.config.model,
            "messages": api_messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            # Parse DeepSeek response (OpenAI-compatible)
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "stop")

            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=data.get("model", self.config.model),
                finish_reason=finish_reason,
            )

        except httpx.TimeoutException:
            raise LLMTimeoutError(f"DeepSeek request timed out after {self.config.timeout}s")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise LLMAuthenticationError("Invalid DeepSeek API key")
            elif e.response.status_code == 429:
                raise LLMRateLimitError("DeepSeek rate limit exceeded")
            raise LLMServiceError(f"DeepSeek API error: {e}")
        except Exception as e:
            raise LLMServiceError(f"DeepSeek error: {e}")

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream completion using DeepSeek API (OpenAI-compatible SSE)."""
        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        payload = {
            "model": self.config.model,
            "messages": api_messages,
            "stream": True,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                return
                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except (json.JSONDecodeError, KeyError):
                                continue
        except httpx.TimeoutException:
            raise LLMTimeoutError(f"DeepSeek streaming timed out after {self.config.timeout}s")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise LLMAuthenticationError("Invalid DeepSeek API key")
            elif e.response.status_code == 429:
                raise LLMRateLimitError("DeepSeek rate limit exceeded")
            raise LLMServiceError("DeepSeek streaming API error")
        except Exception as e:
            raise LLMServiceError(f"DeepSeek streaming error: {e}")

    @property
    def supports_streaming(self) -> bool:
        """DeepSeek supports streaming"""
        return True
