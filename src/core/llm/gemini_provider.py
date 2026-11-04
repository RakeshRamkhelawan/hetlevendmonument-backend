"""
Google Gemini Provider Implementation
ASCII-only compliant LLM integration for Sanskriti Setu
"""

import logging
import os
import time
from typing import Any, cast
from collections.abc import AsyncIterator, Callable

try:
    from google import genai
    from google.genai import types

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

from .llm_client import LLMClient, LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMClient):
    """Google Gemini LLM Provider with fallback handling"""

    def __init__(self, config: LLMConfig | str | None = None, api_key: str | None = None) -> None:
        # Handle case where a string (API key) is passed as config instead of LLMConfig
        if isinstance(config, str):
            api_key = config
            config = None

        # Create default config if not provided
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.GOOGLE,
                model=LLMModel.GEMINI_2_5_FLASH,
                api_key=cast(str, api_key or os.getenv("GOOGLE_API_KEY", "")),
                max_tokens=1000,
                temperature=0.7,
            )
        super().__init__(config)

        self.api_key = config.api_key
        self.available_models: list[str] = []
        self.model_names: list[str] = []
        self.initialized = False
        self.client: Any = None

    async def initialize(self) -> bool:
        """Initialize Google Gemini client and discover available models asynchronously"""
        try:
            if not GOOGLE_AVAILABLE:
                logger.error("Google GenerativeAI library not installed")
                return False

            if not self.api_key:
                logger.error("GOOGLE_API_KEY not provided")
                return False

            # Create client with API key
            # genai.Client might do some setup, but usually safe.
            # If strictly needed, we could wrap this too, but usually it's just config.
            if genai is None:
                logger.error("Google GenerativeAI library not available")
                return False
            self.client = genai.Client(api_key=self.api_key)

            # Dynamically discover available models asynchronously
            await self._discover_available_models()

            self.initialized = True
            logger.info(
                f"Google Gemini provider initialized successfully with {len(self.model_names)} models"
            )
            return True

        except Exception as e:
            logger.error("Failed to initialize Gemini provider: %s", e)
            return False

    async def _discover_available_models(self) -> None:
        """Dynamically discover useable Gemini models without blocking the event loop"""
        import asyncio

        try:
            if self.client is None:
                logger.error("Client not initialized, cannot discover models")
                self._set_fallback_models()
                return
            # Run the blocking network call in a separate thread
            loop = asyncio.get_running_loop()
            available_models = await loop.run_in_executor(None, self.client.models.list)

            gemini_models: list[str] = []
            for model in available_models:
                # The model object from client.models.list() has a .name attribute
                if model.name is None:
                    continue
                model_name = model.name.replace("models/", "")
                if "gemini" in model_name.lower():
                    gemini_models.append(model_name)
                    logger.debug(f"Discovered Gemini model: {model_name}")

            self.model_names = sorted(gemini_models)

            if not self.model_names:
                logger.warning("No models discovered via API, using fallback list")
                self._set_fallback_models()

            logger.info(f"Available Gemini models: {', '.join(self.model_names)}")

        except Exception as e:
            logger.error("Model discovery failed: %s, using fallback models", e)
            self._set_fallback_models()

    def _set_fallback_models(self) -> None:
        """Set fallback models if discovery fails"""
        self.model_names = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]

    async def generate_response(
        self,
        prompt: str,
        model: str | None = None,
        tools: list[Callable[..., Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
        automatic_function_calling: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate response using Google Gemini

        FIX: If prompt is empty but messages are provided in kwargs,
        convert messages to Gemini contents format.
        """

        # Select model dynamically
        if model is None:
            model = self.model_names[0] if self.model_names else "gemini-2.0-flash"
        elif model not in self.model_names:
            logger.warning(
                f"Requested model {model} not available, using {self.model_names[0] if self.model_names else 'gemini-2.0-flash'}"
            )
            model = self.model_names[0] if self.model_names else "gemini-2.0-flash"

        if not self.initialized:
            return {
                "content": "LLM service temporarily unavailable - configuration issue",
                "model": model,
                "provider": self.provider.value,
                "success": False,
                "error": "Provider not initialized",
            }

        if self.client is None or types is None:
            return {
                "content": "LLM service not available - missing dependencies",
                "model": model,
                "provider": self.provider.value,
                "success": False,
                "error": "Client or types not available",
            }

        try:
            start_time = time.time()
            client = self.client

            # FIX: Check if messages are provided in kwargs (from generate_with_tools)
            messages_raw = kwargs.pop("messages", None)

            # Determine what to send as contents
            if messages_raw and (not prompt or prompt.strip() == ""):
                contents: Any = []  # TODO(TYPE): replace Any with concrete type
                for msg in messages_raw:
                    role = msg.get("role", "user")
                    content = msg.get("content", "") or ""
                    # Gemini uses 'user' and 'model' roles
                    gemini_role = "model" if role == "assistant" else "user"
                    contents.append(
                        types.Content(
                            role=gemini_role,
                            parts=[types.Part(text=cast(str, content))],
                        )
                    )
            else:
                contents = prompt

            # Build generation config using types module (new SDK)
            config_params = {
                "temperature": kwargs.get("temperature", 0.7),
                "max_output_tokens": kwargs.get("max_tokens", 1000),
                "top_p": kwargs.get("top_p", 0.8),
                "top_k": kwargs.get("top_k", 40),
            }

            # CRITICAL FIX: Pass tools to config if provided
            if tools:
                config_params["tools"] = tools

            # JSON-mode support via response_mime_type
            if kwargs.get("response_mime_type"):
                config_params["response_mime_type"] = kwargs["response_mime_type"]

            gen_config = types.GenerateContentConfig(**config_params)

            # Use new client API for generation in a separate thread to avoid blocking
            import asyncio

            loop = asyncio.get_running_loop()

            def _blocking_generate() -> Any:  # TODO(TYPE): replace Any with concrete type
                return client.models.generate_content(
                    model=model, contents=contents, config=gen_config
                )

            response = await loop.run_in_executor(None, _blocking_generate)

            response_time = time.time() - start_time

            # ENHANCEMENT 1: Check for function calls in response
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if (
                    candidate.content is not None
                    and hasattr(candidate.content, "parts")
                    and candidate.content.parts is not None
                ):
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            # Function call detected - return structured response
                            function_calls: list[dict[str, object]] = []
                            for p in candidate.content.parts:
                                if hasattr(p, "function_call") and p.function_call:
                                    args = p.function_call.args
                                    function_calls.append(
                                        {
                                            "name": p.function_call.name,
                                            "args": dict(args) if args else {},
                                        }
                                    )

                            logger.info(f"LLM requested {len(function_calls)} function call(s)")
                            return {
                                "content": "",
                                "model": model,
                                "provider": self.provider.value,
                                "success": True,
                                "response_time": response_time,
                                "requires_function_execution": True,
                                "function_calls": function_calls,
                                "usage": {
                                    "prompt_tokens": (
                                        getattr(
                                            response.usage_metadata,
                                            "prompt_token_count",
                                            0,
                                        )
                                        if hasattr(response, "usage_metadata")
                                        else 0
                                    ),
                                    "completion_tokens": (
                                        getattr(
                                            response.usage_metadata,
                                            "candidates_token_count",
                                            0,
                                        )
                                        if hasattr(response, "usage_metadata")
                                        else 0
                                    ),
                                    "total_tokens": (
                                        getattr(
                                            response.usage_metadata,
                                            "total_token_count",
                                            0,
                                        )
                                        if hasattr(response, "usage_metadata")
                                        else 0
                                    ),
                                },
                            }

            # Process response and ensure ASCII compliance
            content = response.text if response.text else "No response generated"

            # ASCII-only compliance - replace non-ASCII characters
            ascii_content = content.encode("ascii", errors="replace").decode("ascii")

            return {
                "content": ascii_content,
                "model": model,
                "provider": self.provider.value,
                "success": True,
                "response_time": response_time,
                "usage": {
                    "prompt_tokens": (
                        getattr(response.usage_metadata, "prompt_token_count", 0)
                        if hasattr(response, "usage_metadata")
                        else 0
                    ),
                    "completion_tokens": (
                        getattr(response.usage_metadata, "candidates_token_count", 0)
                        if hasattr(response, "usage_metadata")
                        else 0
                    ),
                    "total_tokens": (
                        getattr(response.usage_metadata, "total_token_count", 0)
                        if hasattr(response, "usage_metadata")
                        else 0
                    ),
                },
            }

        except Exception as e:
            logger.error("Gemini generation error: %s", e)
            return {
                "content": f"Generation failed: {str(e)}",
                "model": model,
                "provider": self.provider.value,
                "success": False,
                "error": str(e),
            }

    async def stream_response(
        self, prompt: str, model: str | None = None, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Streaming response generator using Google Gemini"""
        # Select model dynamically
        if model is None:
            model = self.model_names[0] if self.model_names else "gemini-1.5-flash"

        if not self.initialized:
            yield {"error": "Provider not initialized"}
            return

        if self.client is None or types is None:
            yield {"error": "Client or types not available"}
            return

        try:
            # Build generation config
            config = types.GenerateContentConfig(
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=kwargs.get("max_tokens", 1000),
                top_p=kwargs.get("top_p", 0.8),
                top_k=kwargs.get("top_k", 40),
            )

            # Use streaming API
            # Note: The client is synchronous, so this will block thread during iteration
            # In a real async/high-perf scenario, this should be run in a threadpool or use AsyncClient
            chunks = self.client.models.generate_content_stream(
                model=model, contents=prompt, config=config
            )

            for chunk in chunks:
                if chunk.text:
                    # ASCII compliance
                    ascii_text = chunk.text.encode("ascii", errors="replace").decode("ascii")
                    yield {"text": ascii_text}

        except Exception as e:
            logger.error("Gemini streaming error: %s", e)
            yield {"error": str(e)}

    async def get_available_models(self) -> list[str]:
        """Get list of available Gemini models"""
        if not self.initialized:
            return []

        return self.model_names

    async def validate_connection(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Test connection to Google Gemini API"""
        if not self.initialized:
            return {
                "status": "failed",
                "error": "Provider not initialized",
                "available": False,
            }

        try:
            # Test with simple prompt using first available model
            test_model = self.model_names[0] if self.model_names else "gemini-2.0-flash"
            test_response = await self.generate_response(
                "Say 'Connection test successful' in exactly those words.",
                model=test_model,
            )

            return {
                "status": "connected" if test_response["success"] else "failed",
                "provider": self.provider.value,
                "available": test_response["success"],
                "models": await self.get_available_models(),
                "test_response": test_response["success"],
            }

        except Exception as e:
            return {"status": "failed", "error": str(e), "available": False}

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Chat completion using conversation format"""
        # Convert messages to single prompt for now
        prompt = "\n".join([f"{msg.role}: {msg.content}" for msg in messages])
        response_dict = await self.generate_response(prompt, **kwargs)

        return LLMResponse(
            content=response_dict.get("content", ""),
            model=response_dict.get("model", ""),
            provider=response_dict.get("provider", ""),
            usage=response_dict.get("usage"),
            response_time=response_dict.get("response_time", 0.0),
            success=response_dict.get("success", False),
            error_message=response_dict.get("error"),
        )

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via Gemini's response_mime_type."""
        kwargs["response_mime_type"] = "application/json"
        return await self.chat_completion(messages, **kwargs)

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Text completion using single prompt"""
        response_dict = await self.generate_response(prompt, **kwargs)

        return LLMResponse(
            content=response_dict.get("content", ""),
            model=response_dict.get("model", ""),
            provider=response_dict.get("provider", ""),
            usage=response_dict.get("usage"),
            response_time=response_dict.get("response_time", 0.0),
            success=response_dict.get("success", False),
            error_message=response_dict.get("error"),
        )
