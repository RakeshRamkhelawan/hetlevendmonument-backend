"""
DeepSeek Provider Implementation
OpenAI-compatible LLM integration for DeepSeek API with streaming support
"""

import json
import logging
import os
import time
from typing import Any
from collections.abc import AsyncIterator

import httpx

from .llm_client import LLMClient, LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class DeepSeekProvider(LLMClient):
    """DeepSeek API provider with streaming support"""

    api_key: str | None

    def __init__(self, config: LLMConfig | str | None = None, api_key: str | None = None) -> None:
        # Handle case where a string (API key) is passed as config instead of LLMConfig
        if isinstance(config, str):
            self.api_key = config
            config = None
        elif api_key:
            # Factory passes api_key as kwarg
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("DEEPSEEK_API_KEY")

        # Create a proper LLMConfig if not provided
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.DEEPSEEK,
                model=LLMModel.DEEPSEEK_CHAT,
                api_key=self.api_key or "",
                temperature=0.7,
                max_tokens=2000,
            )
        else:
            # Ensure api_key is set from environment if not in config
            if not config.api_key and self.api_key:
                config.api_key = self.api_key

        # Call parent constructor
        super().__init__(config)

        self.base_url = "https://api.deepseek.com"
        self._available = bool(self.api_key)
        self._initialized = False

        if not self._available:
            logger.warning("DeepSeek API key not configured - provider will be unavailable")
        else:
            logger.info(f"Initialized DeepSeek provider with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the provider (validate connection)"""
        if not self._available:
            return False

        try:
            # Test connection with a simple request (optional)
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"DeepSeek initialization failed: {e}")
            return False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def model_names(self) -> list[str]:
        return ["deepseek-chat", "deepseek-reasoner"]

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """
        Chat completion - required by LLMClient ABC.
        Wraps the chat() method with proper response format.
        """
        if not self._available:
            model_value = self.model.value if hasattr(self.model, "value") else str(self.model)
            provider_value = (
                self.provider.value if hasattr(self.provider, "value") else str(self.provider)
            )
            return LLMResponse(
                content="DeepSeek client not available",
                model=model_value,
                provider=provider_value,
                success=False,
                error_message="DeepSeek API key not configured",
            )

        start_time = time.time()
        response_time = 0.0

        try:
            # Build request payload
            payload = {
                "model": self.model.value,
                "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "stream": False,
            }

            # Support for JSON Mode
            if kwargs.get("response_format"):
                payload["response_format"] = kwargs.get("response_format")

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error("DeepSeek Error: %s", response.text)
                    response.raise_for_status()

                data = response.json()

            # Extract response
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            response_time = time.time() - start_time

            self._update_metrics(response_time, True)

            return LLMResponse(
                content=content,
                model=self.model.value,
                provider=self.provider.value,
                usage=usage,
                response_time=response_time,
                success=True,
            )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)
            logger.error(f"DeepSeek chat completion failed: {e}")
            model_value = self.model.value if hasattr(self.model, "value") else str(self.model)
            provider_value = (
                self.provider.value if hasattr(self.provider, "value") else str(self.provider)
            )
            return LLMResponse(
                content="",
                model=model_value,
                provider=provider_value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Text completion - wraps chat_completion with a user message"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type,  # base type -- subclasses pass Pydantic model classes at runtime
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via DeepSeek's native response_format."""
        kwargs.setdefault("response_format", {"type": "json_object"})
        return await self.chat_completion(messages, **kwargs)

    async def chat(
        self,
        messages: list[LLMMessage],
        model: LLMModel | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send chat request to DeepSeek API

        Args:
            messages: List of LLMMessage conversation messages
            model: Optional model override
            **kwargs: Additional parameters

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()
        processing_time = 0.0
        model = model or self.config.model

        # Build request payload
        payload = {
            "model": model.value,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code != 200:
                    logger.error("DeepSeek Error: %s", response.text)
                    response.raise_for_status()

                data = response.json()

            # Extract response
            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0]["finish_reason"]
            usage = data.get("usage", {})

            processing_time = time.time() - start_time

            return LLMResponse(
                content=content,
                model=model.value if hasattr(model, "value") else str(model),
                provider=self.provider.value,
                usage=usage,
                response_time=processing_time,
                metadata={"provider": "deepseek", "finish_reason": finish_reason},
            )

        except httpx.HTTPStatusError as e:
            logger.error("DeepSeek API error: %s - %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.exception(f"DeepSeek request failed: {e}")
            raise

    async def stream_response(
        self,
        messages: list[LLMMessage],
        model: LLMModel | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream chat response from DeepSeek API

        Args:
            messages: List of LLMMessage conversation messages
            model: Optional model override
            **kwargs: Additional parameters

        Yields:
            Content chunks as they arrive
        """
        model = model or self.config.model

        # Build request payload
        payload = {
            "model": model.value,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,  # Enable streaming
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line or line.strip() == "":
                            continue

                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix

                            if data.strip() == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)

                                # Extract content delta
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    content = delta.get("content")

                                    if content:
                                        yield content

                            except json.JSONDecodeError:
                                logger.warning("Failed to parse SSE data: %s", data)
                                continue

        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek streaming error: {e.response.status_code}")
            raise
        except Exception as e:
            logger.exception(f"DeepSeek streaming failed: {e}")
            raise

    def get_available_models(self) -> list[LLMModel]:
        """Return list of available DeepSeek models"""
        return [
            LLMModel.DEEPSEEK_CHAT,
            LLMModel.DEEPSEEK_REASONER,
        ]

    async def generate_response(
        self, prompt: str, model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate a response from the LLM (Non-streaming).
        Required by LLMProviderProtocol.

        FIX: If prompt is empty but messages are provided in kwargs,
        use chat_completion directly with those messages instead of text_completion.
        """
        try:
            # Check if messages are provided in kwargs (from generate_with_tools)
            messages_raw = kwargs.pop("messages", None)

            if messages_raw and (not prompt or prompt.strip() == ""):
                # Convert dict messages to LLMMessage objects if needed
                if messages_raw and isinstance(messages_raw[0], dict):
                    messages = [
                        LLMMessage(role=msg.get("role", "user"), content=msg.get("content", ""))
                        for msg in messages_raw
                    ]
                else:
                    messages = messages_raw

                # Use chat_completion directly with provided messages
                response = await self.chat_completion(messages, **kwargs)
            else:
                # Use standard text_completion flow for simple prompts
                response = await self.text_completion(prompt, **kwargs)

            if response.success:
                return {
                    "success": True,
                    "content": response.content,
                    "model": response.model,
                    "provider": response.provider,
                    "usage": response.usage,
                    "metadata": response.metadata,
                }
            else:
                return {"success": False, "error": response.error_message}
        except Exception as e:
            logger.error(f"DeepSeek generate_response failed: {e}")
            return {"success": False, "error": str(e)}
