"""
Ollama Provider Implementation
Production-grade local LLM integration for Sanskriti Setu
"""

import logging
import os
import time
from typing import Any, cast

import aiohttp

from .llm_client import LLMClient, LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


def _strip_code_fences(content: str) -> str:
    """Strip markdown code fences that Ollama models sometimes wrap around JSON."""
    content = content.strip()
    if not content.startswith("```"):
        return content
    lines = content.split("\n")
    # Drop the opening fence line (e.g. "```json" or "```")
    lines = lines[1:]
    # Drop the closing fence if present
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class OllamaProvider(LLMClient):
    """
    Ollama LLM Provider with Tool Calling Support.
    Uses /api/chat endpoint for clean conversation history and tool usage.
    """

    def __init__(
        self, base_url: str | None = None, api_key: str | None = None, **kwargs: Any
    ) -> None:
        # Default config
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.DEEPSEEK_R1_32B,  # Prefer powerful local model
            api_key="ollama",  # Not used but required by config
            max_tokens=2000,
            temperature=0.7,
        )
        super().__init__(config)

        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.session: aiohttp.ClientSession | None = None
        self.available_models: list[str] = []
        self.initialized = False

    async def initialize(self) -> bool:
        """Initialize Ollama client and check connectivity"""
        try:
            self.session = aiohttp.ClientSession()

            # Check connectivity and discover models
            # Use host.docker.internal if configured, otherwise fallback to provided url
            logger.info("Connecting to Ollama at %s...", self.base_url)

            async with self.session.get(
                f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=1)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.available_models = [m["name"] for m in data.get("models", [])]
                    self.initialized = True
                    logger.info(
                        "Ollama provider initialized. Available models: %s",
                        len(self.available_models),
                    )
                    return True
                else:
                    logger.error("Ollama connection check failed: %s", response.status)
                    return False

        except Exception as e:
            logger.error("Failed to initialize Ollama provider: %s", e)
            # Ensure we don't leak a session if init failed
            if self.session:
                await self.session.close()
                self.session = None
            return False

    async def generate_response(
        self,
        prompt: str = "",
        model: str | None = None,
        tools: list[dict[str, object]] | None = None,
        automatic_function_calling: bool = False,
        messages: list[dict[str, str]] | None = None,  # Added support for chat history
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate response using Ollama /api/chat.
        Supports native tool calling if model supports it (like llama3.1, mistral-nemo).
        """
        if not self.initialized or self.session is None:
            return {"success": False, "error": "Ollama not initialized"}

        model = model or self.available_models[0] if self.available_models else "llama3.1:latest"

        # Prepare messages
        # If messages list is provided (rich chat), use it. Otherwise wrap prompt.
        if messages:
            final_messages = messages
        else:
            final_messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": model,
            "messages": final_messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_predict": kwargs.get("max_tokens", 2000),
            },
        }

        # Handle Tools
        # Ollama expects tools in a specific format similar to OpenAI
        if tools:
            payload["tools"] = self._format_tools_for_ollama(tools)

        start_time = time.time()

        try:
            async with self.session.post(f"{self.base_url}/api/chat", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception("Ollama API Error %s: %s" % (response.status, error_text))

                result = await response.json()
                msg = result.get("message", {})
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                response_time = time.time() - start_time

                # Parse Tool Calls
                parsed_function_calls: list[dict[str, object]] = []
                if tool_calls:
                    for tc in tool_calls:
                        if "function" in tc:
                            fn = tc["function"]
                            parsed_function_calls.append(
                                {
                                    "name": fn.get("name"),
                                    "args": fn.get("arguments", {}),
                                }
                            )

                return {
                    "success": True,
                    "content": content,
                    "model": result.get("model", model),
                    "provider": LLMProvider.OLLAMA.value,
                    "response_time": response_time,
                    "function_calls": parsed_function_calls if parsed_function_calls else None,
                    "requires_function_execution": bool(parsed_function_calls),
                    "usage": {
                        "prompt_tokens": result.get("prompt_eval_count", 0),
                        "completion_tokens": result.get("eval_count", 0),
                        "total_tokens": result.get("prompt_eval_count", 0)
                        + result.get("eval_count", 0),
                    },
                }

        except Exception as e:
            logger.error("Ollama generation failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "provider": LLMProvider.OLLAMA.value,
            }

    def _format_tools_for_ollama(
        self,
        tools: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """
        Convert internal tool definitions (often OpenAI/Gemini style) to Ollama format.
        Assuming 'tools' passed are already JSON/Dict compatible.
        """
        formatted: list[dict[str, object]] = []
        for tool in tools:
            # If tool is a Pydantic model dump or dict
            # Ensure it is wrapped in {"type": "function", "function": {...}}

            # Check if it's referenced as a bare function schema
            if "parameters" in tool and "name" in tool:
                formatted.append({"type": "function", "function": tool})
            elif "type" in tool and tool["type"] == "function":
                formatted.append(tool)
            else:
                # Fallback or complex handling
                formatted.append({"type": "function", "function": tool})
        return formatted

    # Implement abstract methods from LLMClient
    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        # Re-use generate_response logic but strictly for chat
        # Since generate_response is tailored for Service Layer, we map back here
        prompt = messages[-1].content  # Simplification
        res = await self.generate_response(prompt, **kwargs)

        return LLMResponse(
            content=cast(str, res.get("content", "")),
            model=cast(str, res.get("model", "")),
            provider=cast(str, res.get("provider", "")),
            success=cast(bool, res.get("success", False)),
            response_time=cast(float, res.get("response_time", 0)),
        )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return await self.chat_completion([LLMMessage(role="user", content=prompt)], **kwargs)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[object],
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via Ollama's format=json parameter.

        Adds format='json' to the request payload so the model returns valid JSON.
        Strips markdown code fences from the response content if present.
        """
        if not self.initialized or self.session is None:
            return LLMResponse(
                content="{}",
                model=self.config.model.value,
                provider=LLMProvider.OLLAMA.value,
                success=False,
                error_message="Ollama not initialized",
            )

        model_name = self.available_models[0] if self.available_models else self.config.model.value
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        payload = {
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            },
        }

        start_time = time.time()
        try:
            async with self.session.post(f"{self.base_url}/api/chat", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception("Ollama API Error %s: %s" % (response.status, error_text))

                result = await response.json()
                content = result.get("message", {}).get("content", "")
                response_time = time.time() - start_time

                content = _strip_code_fences(content)

                return LLMResponse(
                    content=content,
                    model=result.get("model", model_name),
                    provider=LLMProvider.OLLAMA.value,
                    response_time=response_time,
                    success=True,
                    usage={
                        "prompt_tokens": result.get("prompt_eval_count", 0),
                        "completion_tokens": result.get("eval_count", 0),
                        "total_tokens": (
                            result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                        ),
                    },
                )

        except Exception as e:
            response_time = time.time() - start_time
            logger.error("OllamaProvider.complete_json failed: %s", e, exc_info=True)
            return LLMResponse(
                content="{}",
                model=model_name,
                provider=LLMProvider.OLLAMA.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def validate_connection(
        self,
    ) -> dict[str, object]:
        """Validate Ollama connection and return status."""
        try:
            if not self.session:
                return {
                    "status": "error",
                    "error": "Session not initialized",
                    "available": False,
                }

            async with self.session.get(
                f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=1)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    model_count = len(data.get("models", []))
                    return {
                        "status": "healthy",
                        "available": True,
                        "model_count": model_count,
                        "base_url": self.base_url,
                    }
                else:
                    return {
                        "status": "error",
                        "error": "HTTP %s" % response.status,
                        "available": False,
                    }
        except Exception as e:
            return {"status": "error", "error": str(e), "available": False}

    @property
    def model_names(self) -> list[str]:
        """Return list of available model names."""
        return self.available_models
