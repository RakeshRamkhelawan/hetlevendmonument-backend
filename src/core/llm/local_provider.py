"""
Local LLM Provider Implementation

This module provides integration with local LLM servers (e.g., Ollama, LM Studio, LocalAI)
that provide an OpenAI-compatible API.

Created: 2026-01-16
"""

import logging
import os
from typing import Any


from .llm_client import LLMProviderProtocol
from src.core.shared.model_deur import bewaakt_model_aanroep

# from openai import AsyncOpenAI # Moved to __init__


logger = logging.getLogger(__name__)


class LocalLLMProvider(LLMProviderProtocol):
    """
    Provider for Local LLM servers (Ollama, etc.).
    Assumes an OpenAI-compatible API structure.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str = "lm-studio",
        model: str = "local-model",
        **kwargs: Any,
    ) -> None:
        """
        Initialize the Local LLM provider.
        """
        self.base_url = base_url or os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        self.api_key = api_key
        self.default_model = model
        self._initialized = False
        self.client: Any = (  # TODO(TYPE): replace Any with concrete type
            None  # AsyncOpenAI | None -- deferred import avoids ImportError when openai is absent
        )

        try:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            logger.info(f"Initialized LocalLLMProvider at {base_url}")
        except ImportError:
            logger.warning("openai package not found. LocalLLMProvider disabled.")
            self.client = None
        except Exception as e:
            logger.error(f"Failed to init LocalLLMProvider: {e}")
            self.client = None

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def model_names(self) -> list[str]:
        """Return available models (could fetch from API in future)"""
        return [self.default_model, "llama3", "mistral", "gemma"]

    async def validate_connection(
        self,
    ) -> dict[str, str | bool]:
        """
        Validate connection to the local server.
        """
        if self.client is None:
            return {"success": False, "error": "Local LLM client not initialized"}
        try:
            # Simple check - list models
            await self.client.models.list()
            self._initialized = True
            return {"success": True, "message": "Connected to Local LLM"}
        except Exception as e:
            logger.error(f"Failed to connect to Local LLM: {e}")
            return {"success": False, "error": str(e)}

    @bewaakt_model_aanroep
    async def generate_response(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        prompt: str,
        model: str | None = None,
        system_instruction: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate a response using the local LLM.
        Falls back to Gemini if local LLM is unavailable.
        """
        if self.client is None:
            return {
                "content": "",
                "success": False,
                "error": "Local LLM client not initialized",
            }
        try:
            target_model = model or self.default_model

            # dict shape required by openai chat completions API (role + content fields)
            messages: list[dict[str, str]] = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})

            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1024),
            )

            content = response.choices[0].message.content
            return {
                "content": content,
                "success": True,
                "model": target_model,
                "usage": (
                    {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                    if response.usage
                    else {}
                ),
            }

        except Exception as e:
            logger.warning(f"Local LLM unavailable ({e}), attempting Gemini fallback...")

            # Automatic fallback to Gemini
            try:
                import os

                from .gemini_provider import GeminiProvider

                api_key = os.getenv("GOOGLE_API_KEY", "")
                if api_key:
                    gemini = GeminiProvider(api_key=api_key)
                    result = await gemini.generate_response(
                        prompt=prompt, system_instruction=system_instruction, **kwargs
                    )
                    if result.get("success"):
                        result["fallback"] = True
                        result["original_error"] = f"Local LLM at {self.base_url} unavailable"
                        logger.info("Successfully used Gemini fallback")
                        return result

                # No API key, return helpful message
                return {
                    "success": False,
                    "error": str(e),
                    "content": f"Error connecting to Local LLM at {self.base_url}. Is it running? (Tip: Start Ollama or set GOOGLE_API_KEY for fallback)",
                }

            except Exception as fallback_error:
                logger.error(f"Gemini fallback also failed: {fallback_error}")
                return {
                    "success": False,
                    "error": str(e),
                    "content": f"Error connecting to Local LLM at {self.base_url}. Is it running?",
                }
