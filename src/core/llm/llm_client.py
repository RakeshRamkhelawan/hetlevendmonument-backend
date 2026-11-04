"""
LLM Client Interface and Implementations
Provides abstraction for Google Gemini LLM provider
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, Optional, cast

from src.core.shared.model_deur import bewaak_modelmethoden, bewaakt_model_aanroep
from src.core.governance.gdpr_enforcer import GDPREnforcer
from src.core.shared.tenant_llm_keuze import namaak_toegestaan

logger = logging.getLogger(__name__)

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """
    Protocol (interface) that all LLM providers must implement.
    Using Protocol allows duck-typing while maintaining type safety.
    """

    async def generate_response(
        self, prompt: str, model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate a response from the LLM."""
        ...

    async def validate_connection(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate the connection to the LLM provider."""
        ...

    async def complete_json(
        self, messages: list["LLMMessage"], schema: type[Any], **kwargs: Any
    ) -> "LLMResponse":
        """Generate a JSON-mode response matching the given schema."""
        ...

    @property
    def initialized(self) -> bool:
        """Whether the provider is initialized."""
        ...

    @property
    def model_names(self) -> list[str]:
        """List of available model names."""
        ...


# ============================================
# EXCEPTION HIERARCHY (Phase 1 Enhancement)
# ============================================


class LLMServiceError(Exception):
    """Base exception for LLM service errors"""

    pass


class LLMTimeoutError(LLMServiceError):
    """LLM request timed out"""

    pass


class LLMRateLimitError(LLMServiceError):
    """LLM rate limit exceeded"""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMAuthenticationError(LLMServiceError):
    """LLM authentication failed"""

    pass


class LLMContentFilterError(LLMServiceError):
    """Content blocked by safety filter"""

    pass


class TokenBudgetExceededError(LLMServiceError):
    """Token budget exceeded"""

    pass


class LLMProvider(Enum):
    """Supported LLM providers"""

    GOOGLE = "google"
    MOCK = "mock"
    DEEPSEEK = "deepseek"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class LLMModel(Enum):
    """Supported LLM models"""

    # OpenAI Models
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_3_5_TURBO = "gpt-3.5-turbo"

    # Anthropic Models
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet"
    CLAUDE_3_OPUS = "claude-3-opus"
    CLAUDE_3_SONNET = "claude-3-sonnet"
    CLAUDE_3_HAIKU = "claude-3-haiku"

    # Local/Ollama Models
    LLAMA_3 = "llama3:latest"
    LLAMA_3_1_8B = "llama3.1:8b"
    LLAMA_3_2_3B = "llama3.2:3b"

    # Google Models
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_PRO = "gemini-pro"

    # Mistral Models (EU, ADR-041 B14)
    MISTRAL_SMALL = "mistral-small-latest"
    MISTRAL_LARGE = "mistral-large-latest"

    # DeepSeek Models
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_REASONER = "deepseek-reasoner"

    # Ollama Models
    DEEPSEEK_R1_32B = "deepseek-r1:32b"
    GPT_OSS_20B = "gpt-oss:20b"
    GPT_OSS_LATEST = "gpt-oss:latest"
    LLAMA3_LATEST = "llama3:latest"

    # Mock Model
    MOCK_MODEL = "mock-model"


@dataclass
class LLMMessage:
    """Standard message format for LLM interactions"""

    role: str  # system, user, assistant
    content: str
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


@dataclass
class LLMResponse:
    """Standard response format from LLM"""

    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    response_time: float = 0.0
    success: bool = True
    error_message: str | None = None


@dataclass
class LLMConfig:
    """Configuration for LLM client"""

    provider: LLMProvider
    model: LLMModel
    api_key: str
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class ModelInfo:
    """Rich metadata for an LLM model"""

    id: str  # Unique identifier (e.g. 'gemini-1.5-flash')
    name: str  # Display name (e.g. 'Gemini 1.5 Flash')
    provider: str  # Provider ID (e.g. 'google')
    capabilities: list[str]  # e.g. ['multimodal', 'fast', 'reasoning']
    description: str  # User-friendly description
    context_window: int = 0
    max_output_tokens: int = 0


class LLMClient(ABC):
    """Abstract base class for LLM clients"""

    def __init_subclass__(cls) -> None:
        # Noodstop (ronde 3): elke subklasse bewaakt zijn modelaanroepen, ook een nieuwe.
        super().__init_subclass__()
        bewaak_modelmethoden(
            cls,
            (
                "chat_completion",
                "text_completion",
                "complete_json",
                "generate_response",
                "chat",
                "stream_response",
            ),
        )

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self._request_count = 0
        self._total_response_time = 0.0
        self._error_count = 0
        self._gdpr_enforcer = GDPREnforcer()

    @abstractmethod
    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Get chat completion from LLM"""

    @abstractmethod
    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Get text completion from LLM"""

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode chat completion.

        Override in providers with native JSON support.
        Default raises NotImplementedError so callers get a clear error.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement complete_json. "
            f"Use a provider with native JSON-mode (DeepSeek, Gemini, Anthropic)."
        )

    async def validate_connection(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate connection to LLM provider"""
        try:
            test_response = await self.text_completion(
                "Test connection. Respond with 'OK'.", max_tokens=10
            )
            return {
                "available": test_response.success,
                "error": test_response.error_message if not test_response.success else None,
            }
        except Exception as e:
            logger.error(f"LLM connection validation failed: {e}")
            return {"available": False, "error": str(e)}

    @bewaakt_model_aanroep
    async def generate_response(
        self, prompt: str, model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate a response from the LLM (Non-streaming).
        Base implementation that wraps text_completion or chat_completion.
        """
        try:
            # Check if messages provided (Chat Mode)
            messages = kwargs.get("messages")
            if messages:
                # Convert dict messages to LLMMessage if needed
                formatted_messages: list[LLMMessage] = []
                for m in messages:
                    if isinstance(m, dict):
                        formatted_messages.append(
                            LLMMessage(role=m.get("role", "user"), content=m.get("content", ""))
                        )
                    elif isinstance(m, LLMMessage):
                        formatted_messages.append(m)
                    # Skip invalid formats

                sanitized_messages, token_map = self._sanitize_messages(formatted_messages)
                response = await self.chat_completion(sanitized_messages, **kwargs)
                if token_map:
                    response.content = self._gdpr_enforcer.detokenize(response.content, token_map)
                    if response.error_message:
                        response.error_message = self._gdpr_enforcer.detokenize(
                            response.error_message, token_map
                        )
            else:
                # Text Mode fallback
                masked_prompt, token_map = self._gdpr_enforcer.redact_pii(prompt)
                response = await self.text_completion(masked_prompt, **kwargs)
                if token_map:
                    response.content = self._gdpr_enforcer.detokenize(response.content, token_map)
                    if response.error_message:
                        response.error_message = self._gdpr_enforcer.detokenize(
                            response.error_message, token_map
                        )

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
            logger.error(f"LLMClient generate_response failed: {e}")
            return {"success": False, "error": str(e)}

    def _sanitize_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[list[LLMMessage], dict[str, str]]:
        """Mask PII in 'user' role messages before sending to an external provider.

        'system' and 'assistant' messages are skipped -- they are application-
        generated and do not contain raw end-user input.

        Returns (sanitized_messages, combined_token_map).
        """
        combined_map: dict[str, str] = {}
        sanitized: list[LLMMessage] = []
        offset = 0
        for msg in messages:
            if msg.role == "user":
                clean_content, token_map = self._gdpr_enforcer.redact_pii(msg.content)
                for old_key, value in token_map.items():
                    idx = int(old_key[len("[TOKEN_PII_") : -1])
                    new_key = f"[TOKEN_PII_{idx + offset}]"
                    clean_content = clean_content.replace(old_key, new_key)
                    combined_map[new_key] = value
                offset += len(token_map)
                sanitized.append(
                    LLMMessage(role=msg.role, content=clean_content, metadata=msg.metadata)
                )
            else:
                sanitized.append(msg)
        return sanitized, combined_map

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get client metrics"""
        avg_response_time = self._total_response_time / max(self._request_count, 1)

        return {
            "provider": self.provider.value,
            "model": self.model.value,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "average_response_time": avg_response_time,
            "error_rate": self._error_count / max(self._request_count, 1),
        }

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update internal metrics"""
        self._request_count += 1
        self._total_response_time += response_time
        if not success:
            self._error_count += 1


class MockLLMClient(LLMClient):
    """
    Mock LLM client for TESTING AND DEVELOPMENT ONLY

    [WARN] WARNING: Not for production use!
    This class returns hardcoded responses and does NOT call real LLM APIs.
    Use only in development and test environments.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.MOCK,
                model=LLMModel.MOCK_MODEL,
                api_key="mock-key-development-only",  # gitleaks:allow
                max_tokens=2000,
            )
        super().__init__(config)

        # Mock responses for different types of requests
        self.mock_responses = {
            "strategic_analysis": [
                "Based on strategic analysis, I recommend focusing on user-centric design and scalable architecture.",
                "The key strategic priorities should be: 1) Market validation, 2) Technical foundation, 3) User experience optimization.",
                "Strategic assessment indicates high potential for growth through systematic execution of core features.",
            ],
            "task_decomposition": [
                "This complex task can be broken down into the following components: Research phase, Design phase, Implementation phase, Testing phase.",
                "Task decomposition suggests: 1) Requirements analysis (2 hours), 2) Solution design (4 hours), 3) Implementation (8 hours), 4) Validation (2 hours).",
                "Breaking down this task: Core logic implementation, User interface design, Data integration, Performance optimization.",
            ],
            "vision_synthesis": [
                "Vision synthesis: Create an innovative, user-focused solution that balances technical excellence with practical usability.",
                "Strategic vision: Build a scalable, maintainable platform that delivers measurable value to users while maintaining high quality standards.",
                "Synthesized vision: Develop a robust system that prioritizes user experience, technical reliability, and sustainable growth.",
            ],
            "general": [
                "I understand your request. Let me provide a thoughtful analysis of the situation and recommendations for moving forward.",
                "Based on the context provided, I can offer strategic insights and practical next steps to address your needs.",
                "Thank you for your question. I'll analyze this from multiple perspectives and provide actionable recommendations.",
            ],
        }

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Mock chat completion"""
        start_time = time.time()

        # Simulate processing time
        await asyncio.sleep(0.5)

        # Analyze messages to determine response type
        last_message = messages[-1] if messages else None
        response_type = self._determine_response_type(last_message.content if last_message else "")

        # Get mock response
        responses = self.mock_responses.get(response_type, self.mock_responses["general"])
        response_content = responses[hash(str(messages)) % len(responses)]

        response_time = time.time() - start_time
        self._update_metrics(response_time, True)

        return LLMResponse(
            content=response_content,
            model=self.model.value,
            provider=self.provider.value,
            usage={"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
            response_time=response_time,
            success=True,
        )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Mock text completion"""
        start_time = time.time()

        # Simulate processing time
        await asyncio.sleep(0.3)

        # Determine response type from prompt
        response_type = self._determine_response_type(prompt)

        # Get mock response
        responses = self.mock_responses.get(response_type, self.mock_responses["general"])
        response_content = responses[hash(prompt) % len(responses)]

        response_time = time.time() - start_time
        self._update_metrics(response_time, True)

        return LLMResponse(
            content=response_content,
            model=self.model.value,
            provider=self.provider.value,
            usage={
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response_content.split()),
                "total_tokens": len(prompt.split()) + len(response_content.split()),
            },
            response_time=response_time,
            success=True,
        )

    def _determine_response_type(self, text: str) -> str:
        """Determine the type of response needed based on input text"""
        text_lower = text.lower()

        if any(word in text_lower for word in ["strategy", "strategic", "planning", "plan"]):
            return "strategic_analysis"
        elif any(
            word in text_lower for word in ["decompose", "breakdown", "subtask", "break down"]
        ):
            return "task_decomposition"
        elif any(word in text_lower for word in ["vision", "synthesize", "synthesis", "roadmap"]):
            return "vision_synthesis"
        else:
            return "general"


class OpenAIClient(LLMClient):
    """OpenAI LLM client implementation"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            import openai

            self.client = openai.AsyncOpenAI(api_key=config.api_key)
            self._available = True
        except ImportError:
            logger.warning("OpenAI package not available. Install with: pip install openai")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self._available = False

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """OpenAI chat completion"""
        if not self._available:
            return LLMResponse(
                content="OpenAI client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="OpenAI client not initialized",
            )

        start_time = time.time()

        try:
            # Convert to OpenAI format
            openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

            response = await self.client.chat.completions.create(
                model=self.model.value,
                messages=openai_messages,  # type: ignore[arg-type]
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                timeout=self.config.timeout,
            )

            response_time = time.time() - start_time
            self._update_metrics(response_time, True)

            message_content = response.choices[0].message.content or ""
            usage = response.usage

            return LLMResponse(
                content=message_content,
                model=response.model or self.model.value,
                provider=self.provider.value,
                usage={
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
                response_time=response_time,
                success=True,
            )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)

            logger.error(f"OpenAI chat completion failed: {e}")
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """OpenAI text completion using chat format"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)


class AnthropicClient(LLMClient):
    """Anthropic LLM client implementation"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)

        # Skip Anthropic if no API key provided
        if not config.api_key:
            logger.info("Anthropic API key not provided - skipping Anthropic client initialization")
            self._available = False
            return

        try:
            import anthropic

            self.client = anthropic.AsyncAnthropic(api_key=config.api_key)
            self._available = True
        except ImportError:
            logger.warning("Anthropic package not available. Install with: pip install anthropic")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            self._available = False

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Anthropic chat completion"""
        if not self._available:
            return LLMResponse(
                content="Anthropic client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="Anthropic client not initialized",
            )

        start_time = time.time()

        try:
            # Convert messages to Anthropic format
            system_message = ""
            user_messages: list[dict[str, str]] = []
            for msg in messages:
                if msg.role == "system":
                    system_message += msg.content + "\n"
                else:
                    user_messages.append({"role": msg.role, "content": msg.content})

            create_params = {
                "model": self.model.value,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "messages": user_messages,
            }

            # Only add system parameter if we have a system message
            if system_message and system_message.strip():
                create_params["system"] = system_message.strip()

            response = await self.client.messages.create(**create_params)

            response_time = time.time() - start_time
            self._update_metrics(response_time, True)

            return LLMResponse(
                content=response.content[0].text,
                model=response.model,
                provider=self.provider.value,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                },
                response_time=response_time,
                success=True,
            )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)

            logger.error(f"Anthropic chat completion failed: {e}")
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    def _inject_system_instruction(
        self,
        messages: list[LLMMessage],
        instruction: str,
    ) -> list[LLMMessage]:
        """Append a JSON instruction to the first system message, or add a new one."""
        if messages and messages[0].role == "system":
            patched_content = messages[0].content + instruction
            return [
                LLMMessage(role="system", content=patched_content),
                *messages[1:],
            ]
        return [
            LLMMessage(role="system", content=instruction),
            *messages,
        ]

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        json_instruction = (
            " Output strictly valid JSON matching the supplied schema. "
            "Do not include any text outside the JSON object."
        )
        patched = self._inject_system_instruction(messages, json_instruction)
        return await self.chat_completion(patched, **kwargs)

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Anthropic text completion using messages format"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)


class GoogleClient(LLMClient):
    """Google Gemini LLM client implementation"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            from google import genai
            from google.genai import types

            self.genai = genai
            self.types = types
            self.client = genai.Client(api_key=config.api_key)
            self._available = True
        except ImportError:
            logger.warning(
                "Google genai package not available. Install with: pip install google-genai"
            )
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Google client: {e}")
            self._available = False

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Google Gemini chat completion"""
        if not self._available:
            return LLMResponse(
                content="Google client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="Google client not initialized",
            )

        start_time = time.time()

        try:
            # Convert messages to Google format
            conversation_text = ""
            for msg in messages:
                if msg.role == "system":
                    conversation_text += f"System: {msg.content}\n\n"
                elif msg.role == "user":
                    conversation_text += f"User: {msg.content}\n\n"
                elif msg.role == "assistant":
                    conversation_text += f"Assistant: {msg.content}\n\n"

            # Remove the last "User:" and use it as the prompt
            conversation_text = conversation_text.strip()

            # Build generation config (new SDK)
            config = self.types.GenerateContentConfig(
                max_output_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
            )

            # Generate response using client API
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=self.model.value, contents=conversation_text, config=config
                ),
            )

            response_time = time.time() - start_time
            self._update_metrics(response_time, True)

            # Handle blocked content from Google safety filters
            try:
                content = response.text
            except Exception as text_error:
                # Check if content was blocked by safety filters
                candidates = response.candidates
                if candidates and len(candidates) > 0:
                    candidate = candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        if int(candidate.finish_reason or 0) == 2:  # SAFETY filter block
                            return LLMResponse(
                                content="Content blocked by safety filters",
                                model=self.model.value,
                                provider=self.provider.value,
                                response_time=response_time,
                                success=False,
                                error_message=f"Content blocked by Google safety filters (finish_reason={candidate.finish_reason})",
                            )
                # Other text access errors
                return LLMResponse(
                    content="Response text not accessible",
                    model=self.model.value,
                    provider=self.provider.value,
                    response_time=response_time,
                    success=False,
                    error_message=f"Could not access response text: {str(text_error)}",
                )

            content_str = content or ""
            return LLMResponse(
                content=content_str,
                model=self.model.value,
                provider=self.provider.value,
                usage={
                    "input_tokens": len(conversation_text.split()),
                    "output_tokens": len(content_str.split()),
                    "total_tokens": len(conversation_text.split()) + len(content_str.split()),
                },
                response_time=response_time,
                success=True,
            )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)

            logger.error(f"Google chat completion failed: {e}")
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Google text completion"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via system instruction injection."""
        json_instruction = (
            " Output strictly valid JSON. Do not include any text outside the JSON object."
        )
        if messages and messages[0].role == "system":
            patched: list[LLMMessage] = [
                LLMMessage(
                    role="system",
                    content=messages[0].content + json_instruction,
                ),
                *messages[1:],
            ]
        else:
            patched = [
                LLMMessage(role="system", content=json_instruction),
                *messages,
            ]
        return await self.chat_completion(patched, **kwargs)


class OllamaClient(LLMClient):
    """Ollama local LLM client implementation"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            self.base_url = (
                config.api_key or "http://localhost:11434"
            )  # Use api_key field for base URL
            self.session: Any = None
            self._available = True
        except ImportError:
            logger.warning("aiohttp package not available. Install with: pip install aiohttp")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            self._available = False

    async def _get_session(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get or create aiohttp session"""
        if self.session is None:
            import aiohttp

            self.session = aiohttp.ClientSession()
        return self.session

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Ollama chat completion"""
        if not self._available:
            return LLMResponse(
                content="Ollama client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="Ollama client not initialized",
            )

        start_time = time.time()

        try:
            session = await self._get_session()

            # Convert messages to Ollama format
            prompt_parts: list[str] = []
            for msg in messages:
                if msg.role == "system":
                    prompt_parts.append(f"System: {msg.content}")
                elif msg.role == "user":
                    prompt_parts.append(f"User: {msg.content}")
                elif msg.role == "assistant":
                    prompt_parts.append(f"Assistant: {msg.content}")

            prompt = "\n\n".join(prompt_parts) + "\n\nAssistant:"

            # Ollama API call
            payload = {
                "model": self.model.value,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                },
            }
            if kwargs.get("format"):
                payload["format"] = kwargs["format"]

            import aiohttp

            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as response:
                if response.status == 200:
                    result = cast(
                        dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                        await response.json(),  # TODO(TYPE): replace Any with concrete type
                    )  # TODO(TYPE): replace Any with concrete type
                    response_time = time.time() - start_time

                    return LLMResponse(
                        content=result.get("response", "").strip(),
                        model=self.model.value,
                        provider=self.provider.value,
                        response_time=response_time,
                        success=True,
                        metadata={
                            "total_duration": result.get("total_duration", 0),
                            "load_duration": result.get("load_duration", 0),
                            "prompt_eval_count": result.get("prompt_eval_count", 0),
                            "eval_count": result.get("eval_count", 0),
                        },
                    )
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Ollama chat completion failed: {e}")
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Ollama text completion"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via Ollama format=json parameter.

        NOTE: OllamaProvider should be preferred for production JSON mode
        as it uses the /api/chat endpoint with native message semantics.
        """
        kwargs.setdefault("format", "json")
        return await self.chat_completion(messages, **kwargs)

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session:
            await self.session.close()


class DeepSeekClient(LLMClient):
    """DeepSeek LLM client implementation"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            import httpx

            self.api_key = config.api_key
            self.base_url = "https://api.deepseek.com"
            self._available = True
        except ImportError:
            logger.warning("httpx package not available. Install with: pip install httpx")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek client: {e}")
            self._available = False

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """DeepSeek chat completion"""
        if not self._available:
            return LLMResponse(
                content="DeepSeek client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="DeepSeek client not initialized",
            )

        start_time = time.time()

        try:
            import httpx

            # Convert messages to OpenAI format
            openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model.value,
                "messages": openai_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "stream": False,
            }
            if kwargs.get("response_format"):
                payload["response_format"] = kwargs["response_format"]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout,
                )

                if response.status_code != 200:
                    response_time = time.time() - start_time
                    self._update_metrics(response_time, False)
                    return LLMResponse(
                        content="",
                        model=self.model.value,
                        provider=self.provider.value,
                        response_time=response_time,
                        success=False,
                        error_message=f"HTTP {response.status_code}: {response.text}",
                    )

                data = cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    response.json(),  # TODO(TYPE): replace Any with concrete type
                )  # TODO(TYPE): replace Any with concrete type
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                response_time = time.time() - start_time
                self._update_metrics(response_time, True)

                return LLMResponse(
                    content=content,
                    model=self.model.value,
                    provider=self.provider.value,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    response_time=response_time,
                    success=True,
                )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)
            logger.error(f"DeepSeek chat completion failed: {e}")
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=str(e),
            )

    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """JSON-mode completion via DeepSeek OpenAI-compatible response_format."""
        kwargs.setdefault("response_format", {"type": "json_object"})
        return await self.chat_completion(messages, **kwargs)

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """DeepSeek text completion"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)


def get_default_llm_config() -> LLMConfig:
    """Get default LLM configuration based on available API keys"""
    from src.core.shared.config import get_settings

    settings = get_settings()

    # Ollama > Google > Mock. DeepSeek staat hier NIET meer, ook niet bij een gezette sleutel: deze
    # standaard draait over klantgegevens (ADR-041 B14, brief 2026-10-19).
    if hasattr(settings, "ollama_base_url") and settings.ollama_base_url:
        return LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA3_LATEST,
            api_key=settings.ollama_base_url,
            max_tokens=2000,
            temperature=0.7,
        )
    elif settings.google_api_key:
        return LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_1_5_FLASH,
            api_key=settings.google_api_key,
            max_tokens=2000,
            temperature=0.7,
        )
    elif namaak_toegestaan():
        # Alleen in tests, en dan met een zichtbare melding. Hier stond ook een tak die bij ALLEEN een
        # OpenAI-sleutel stil een namaakmodel gaf (brief 2026-10-20, ADR-041 B14).
        logger.warning("[MOCK] geen taalmodel geconfigureerd: namaakmodel gebruikt (alleen tests)")
        return LLMConfig(provider=LLMProvider.MOCK, model=LLMModel.MOCK_MODEL, api_key="mock-key")
    else:
        raise ValueError(
            "geen taalmodel geconfigureerd (OLLAMA_BASE_URL of GOOGLE_API_KEY); er wordt niet "
            "teruggevallen op een namaakmodel"
        )


# Convenience function for backward compatibility
def create_llm_client(provider_name: str) -> LLMClient:
    """Create LLM client from provider name string - CLEAN VERSION (only Google Gemini, Ollama, DeepSeek)"""
    from src.core.shared.config import get_settings

    settings = get_settings()

    provider_lower = provider_name.lower()

    if provider_lower == "google":
        google_key = getattr(settings, "google_api_key", "") or ""
        config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_1_5_FLASH,
            api_key=google_key,
            max_tokens=2000,
            temperature=0.7,
        )
    elif provider_lower == "ollama":
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA3_LATEST,
            api_key=getattr(settings, "ollama_base_url", "http://localhost:11434"),
            max_tokens=2000,
            temperature=0.7,
        )
    else:
        raise ValueError(
            f"Only Google Gemini and Ollama providers are supported. Got: {provider_name}. "
            "DeepSeek mag niet met klantgegevens (ADR-041 B14)."
        )

    return create_llm_client_from_config(config)


# Clean factory function for supported providers only
def create_llm_client_from_config(config: LLMConfig) -> LLMClient:
    """Factory function to create appropriate LLM client from config - CLEAN VERSION"""
    if config.provider == LLMProvider.GOOGLE:
        return GoogleClient(config)
    elif config.provider == LLMProvider.OLLAMA:
        return OllamaClient(config)
    elif config.provider == LLMProvider.MOCK:
        return MockLLMClient(config)
    else:
        # Ook DEEPSEEK: een client voor DeepSeek wordt nergens meer gebouwd (ADR-041 B14).
        raise ValueError(f"Provider {config.provider} not supported")
