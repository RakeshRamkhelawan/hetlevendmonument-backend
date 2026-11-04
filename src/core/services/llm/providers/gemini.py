"""
Gemini Provider - Google Gemini API

Supports Google's Gemini models
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):  # LLMProvider untyped without mypy plugin
    """
    Google Gemini provider

    Configuration:
    - api_key: Google API key (required)
    - model: Model name (e.g., "gemini-pro", "gemini-1.5-pro")
    - base_url: API endpoint (default: https://generativelanguage.googleapis.com/v1beta)
    """

    def _validate_config(self) -> None:
        """Validate Gemini configuration"""
        if not self.config.api_key:
            raise ValueError("Gemini requires 'api_key' in config")

        if not self.config.model:
            self.config.model = "gemini-pro"

        if not self.config.base_url:
            # gemini-2.x and newer models are only available on v1beta
            self.config.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate completion using Gemini API"""

        # Convert messages to Gemini format
        # Gemini uses "contents" (user/model only) + separate "system_instruction"
        system_parts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        gemini_contents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for msg in messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            else:
                # Gemini uses "user" and "model" roles (not "assistant")
                role = "model" if msg.role == "assistant" else "user"
                gemini_contents.append({"role": role, "parts": [{"text": msg.content}]})

        payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": temperature if temperature is not None else self.config.temperature,
                "maxOutputTokens": max_tokens or self.config.max_tokens,
            },
        }
        if system_parts:
            payload["system_instruction"] = {"parts": system_parts}

        logger.debug(
            "Gemini payload keys: %s, contents_count=%d, system_parts_count=%d",
            list(payload.keys()),
            len(gemini_contents),
            len(system_parts),
        )

        api_key: str = self.config.api_key or ""  # _validate_config ensures non-empty
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.base_url}/models/{self.config.model}:generateContent",
                    headers={
                        "x-goog-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if not response.is_success:
                    logger.warning("Gemini HTTP error: status=%s", response.status_code)
                response.raise_for_status()
                data = response.json()

            # Parse Gemini response
            if "candidates" not in data or not data["candidates"]:
                # Check for safety filters
                if "promptFeedback" in data:
                    feedback = data["promptFeedback"]
                    if feedback.get("blockReason"):
                        raise LLMContentFilterError(f"Content blocked: {feedback['blockReason']}")
                raise LLMServiceError("No response from Gemini")

            candidate = data["candidates"][0]
            content = candidate["content"]["parts"][0]["text"]
            finish_reason = candidate.get("finishReason", "STOP")

            # Gemini provides token counts in usageMetadata
            usage = data.get("usageMetadata", {})

            return LLMResponse(
                content=content,
                prompt_tokens=usage.get("promptTokenCount", 0),
                completion_tokens=usage.get("candidatesTokenCount", 0),
                total_tokens=usage.get("totalTokenCount", 0),
                model=self.config.model,
                finish_reason=finish_reason,
            )

        except httpx.TimeoutException:
            raise LLMTimeoutError(f"Gemini request timed out after {self.config.timeout}s")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise LLMAuthenticationError("Invalid Gemini API key")
            elif e.response.status_code == 429:
                raise LLMRateLimitError("Gemini rate limit exceeded")
            raise LLMServiceError("Gemini API error")
        except Exception as e:
            raise LLMServiceError(f"Gemini error: {e}")

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream completion using Gemini API (Server-Sent Events)."""
        system_parts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        gemini_contents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for msg in messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            else:
                role = "model" if msg.role == "assistant" else "user"
                gemini_contents.append({"role": role, "parts": [{"text": msg.content}]})
        payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": temperature if temperature is not None else self.config.temperature,
                "maxOutputTokens": max_tokens or self.config.max_tokens,
            },
        }
        if system_parts:
            payload["system_instruction"] = {"parts": system_parts}

        stream_api_key: str = self.config.api_key or ""  # _validate_config ensures non-empty
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.base_url}/models/{self.config.model}:streamGenerateContent",
                    params={"alt": "sse"},
                    headers={
                        "x-goog-api-key": stream_api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                chunk = json.loads(line[6:])
                                text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                                if text:
                                    yield text
                            except (json.JSONDecodeError, KeyError):
                                logger.debug("Gemini stream: skipping unparseable chunk")
                                continue
        except httpx.TimeoutException:
            raise LLMTimeoutError(f"Gemini streaming timed out after {self.config.timeout}s")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise LLMAuthenticationError("Invalid Gemini API key")
            elif e.response.status_code == 429:
                raise LLMRateLimitError("Gemini rate limit exceeded")
            raise LLMServiceError("Gemini streaming API error")
        except Exception as e:
            raise LLMServiceError(f"Gemini streaming error: {e}")

    @property
    def supports_streaming(self) -> bool:
        """Gemini supports streaming"""
        return True
