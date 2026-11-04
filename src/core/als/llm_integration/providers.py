"""LLM Providers for ALS integration.

Supports DeepSeek and Gemini (Google) APIs.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, NotRequired, Optional, Set, Tuple, TypedDict, cast

import requests
from src.core.shared.model_deur import bewaak_modelmethoden

logger = logging.getLogger("LLMProvider")


class _Message(TypedDict):
    content: str | None


class _Choice(TypedDict):
    message: _Message


class _DeepSeekResponse(TypedDict):
    choices: list[_Choice]
    model: NotRequired[str]
    usage: NotRequired[dict[str, object]]


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init_subclass__(cls) -> None:
        # Noodstop (ronde 3): elke subklasse bewaakt zijn modelaanroepen, ook een nieuwe.
        super().__init_subclass__()
        bewaak_modelmethoden(
            cls,
            (
                "generate",
            ),
        )

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instructions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns: Dict[str, Any] with 'content', 'success', and 'error' keys  # TODO(TYPE): replace Any with concrete type
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


class DeepSeekProvider(LLMProvider):
    """DeepSeek API provider."""

    def __init__(self, api_key: str | None = None, model: str = "deepseek-chat") -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.base_url = "https://api.deepseek.com/v1"

        if not self.api_key:
            raise ValueError("DeepSeek API key not provided")

    @property
    def name(self) -> str:
        return f"deepseek-{self.model}"

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate using DeepSeek API."""
        messages: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = cast(_DeepSeekResponse, response.json())

            return {
                "success": True,
                "content": data["choices"][0]["message"]["content"],
                "model": data.get("model", self.model),
                "usage": data.get("usage", {}),
                "error": None,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API error: {e}")
            return {"success": False, "content": None, "error": str(e), "usage": {}}


class GeminiProvider(LLMProvider):
    """Google Gemini API provider with automatic model selection.

    Automatically tries the latest models first, with fallback to older models.
    """

    # Ordered list: newest first (will try in order)
    AVAILABLE_MODELS = [
        "gemini-2.0-flash-exp",  # Latest experimental (fastest)
        "gemini-2.0-flash",  # Latest stable
        "gemini-1.5-pro",  # High quality
        "gemini-1.5-flash",  # Fast & cheap
        "gemini-1.5-pro-latest",  # Fallback
        "gemini-1.0-pro",  # Legacy fallback
    ]

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")

        if not self.api_key:
            raise ValueError("Google API key not provided")

        # Try new google.genai first (recommended), fallback to old
        self._use_new_genai = False
        try:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
            self._use_new_genai = True
            logger.info("Using new google.genai package")

            # For new API, just store model name, client handles the rest
            self.model = model or self.AVAILABLE_MODELS[0]

        except ImportError:
            # Fallback to deprecated google.generativeai
            try:
                import google.generativeai as legacy_genai  # pyright: ignore[reportMissingImports]

                legacy_genai.configure(  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateImportUsage]
                    api_key=self.api_key
                )
                self.genai = legacy_genai

                # Try to use specified model, or auto-select latest available
                if model:
                    self.model = model
                    self._model = legacy_genai.GenerativeModel(  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateImportUsage]
                        model
                    )
                else:
                    self.model, self._model = self._auto_select_model(legacy_genai)

                logger.info("Using deprecated google.generativeai package")

            except ImportError:
                raise ImportError(
                    "No Gemini SDK installed. Run: pip install google-genai "
                    "(or google-generativeai for legacy support)"
                )

    def _auto_select_model(
        self,
        genai: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Automatically select the best available model.

        Returns:
            tuple: (model_name, model_instance)
        """
        for model_name in self.AVAILABLE_MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                # Test the model with a simple request
                logger.info(f"Trying Gemini model: {model_name}...")
                # Just create the model - actual test happens on first use
                logger.info(f"[OK] Selected Gemini model: {model_name}")
                return model_name, model
            except Exception as e:
                logger.warning(f"Model {model_name} not available: {e}")
                continue

        # If none work, fall back to default and let it fail later
        logger.error("No Gemini models available - using fallback")
        return "gemini-1.5-flash", genai.GenerativeModel("gemini-1.5-flash")

    @property
    def name(self) -> str:
        return f"gemini-{self.model}"

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate using Gemini API with fallback support."""

        # Use new google.genai if available
        if self._use_new_genai:
            return await self._generate_new_genai(prompt, system_prompt, temperature, max_tokens)
        else:
            return await self._generate_legacy(prompt, system_prompt, temperature, max_tokens)

    async def _generate_new_genai(
        self, prompt: str, system_prompt: str | None, temperature: float, max_tokens: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate using new google.genai package."""
        from google.genai import types

        try:
            # Try models in order
            models_to_try = [self.model] + [m for m in self.AVAILABLE_MODELS if m != self.model]

            for model_name in models_to_try:
                try:
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        ),
                    )
                    return {
                        "success": True,
                        "content": response.text,
                        "model": model_name,
                        "usage": {},
                        "error": None,
                    }
                except Exception as e:
                    logger.warning(f"Model {model_name} failed: {e}")
                    continue

            return {
                "success": False,
                "content": None,
                "error": "All Gemini models failed",
                "usage": {},
            }

        except Exception as e:
            return {"success": False, "content": None, "error": str(e), "usage": {}}

    async def _generate_legacy(
        self, prompt: str, system_prompt: str | None, temperature: float, max_tokens: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate using legacy google.generativeai package."""

        # Prepare content based on model capabilities
        contents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if system_prompt:
            contents = [f"{system_prompt}\n\n{prompt}"]
        else:
            contents = [prompt]

        # Try primary model first
        try:
            response = self._model.generate_content(
                contents,
                generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
            )

            return {
                "success": True,
                "content": response.text,
                "model": self.model,
                "usage": {},
                "error": None,
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Gemini API error with {self.model}: {error_msg}")

            # Try fallback models if primary fails
            if "not found" in error_msg.lower() or "permission" in error_msg.lower():
                return await self._try_fallback_models(contents, temperature, max_tokens)

            return {"success": False, "content": None, "error": error_msg, "usage": {}}

    async def _try_fallback_models(
        self,
        contents: list[Any],  # TODO(TYPE): replace Any with concrete type
        temperature: float,
        max_tokens: int,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Try fallback models if primary model fails."""
        # Skip current model, try others
        fallback_models = [m for m in self.AVAILABLE_MODELS if m != self.model]

        for model_name in fallback_models:
            try:
                logger.info(f"Trying fallback model: {model_name}")
                fallback = self.genai.GenerativeModel(  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateImportUsage]
                    model_name
                )
                response = fallback.generate_content(
                    contents,
                    generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                )
                logger.info(f"[OK] Fallback model {model_name} succeeded")
                return {
                    "success": True,
                    "content": response.text,
                    "model": model_name,
                    "usage": {},
                    "error": None,
                }
            except Exception as e:
                logger.warning(f"Fallback model {model_name} failed: {e}")
                continue

        return {"success": False, "content": None, "error": "All Gemini models failed", "usage": {}}


def get_provider(provider_name: str = "gemini", **kwargs: Any) -> LLMProvider:
    """Factory function to get the appropriate provider.

    Args:
        provider_name: 'gemini'. 'deepseek' wordt geweigerd: DeepSeek mag niet met klantgegevens
            (ADR-041 B14, brief 2026-10-19); de standaard was 'deepseek'.
        **kwargs: Additional provider-specific arguments
            - For Gemini: model=None for auto-selection, or specific model name

    Returns:
        LLMProvider instance
    """
    provider_name = provider_name.lower()

    if provider_name == "deepseek":
        raise ValueError(
            "DeepSeek (China, geen verwerkersovereenkomst) mag niet met klantgegevens (ADR-041 B14)"
        )
    elif provider_name in ("gemini", "google"):
        # If no model specified, GeminiProvider will auto-select latest
        return GeminiProvider(**kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def list_available_gemini_models() -> list[str]:
    """List all available Gemini model names (newest first).

    Returns: List[Any] of model names in priority order  # TODO(TYPE): replace Any with concrete type
    """
    return GeminiProvider.AVAILABLE_MODELS.copy()
