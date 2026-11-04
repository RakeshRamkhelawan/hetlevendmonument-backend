"""
LLM Client Interface and Implementations
Provides abstraction for Google Gemini LLM provider
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from src.core.shared.model_deur import bewaak_modelmethoden, bewaakt_model_aanroep
from src.core.shared.tenant_llm_keuze import namaak_toegestaan

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers"""

    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LOCAL = "local"
    MOCK = "mock"


class LLMModel(Enum):
    """Supported LLM models"""

    # Google Gemini Models (2026)
    GEMINI_3_PRO = "gemini-3-pro"  # Latest flagship model
    GEMINI_3_FLASH = "gemini-3-flash"  # Fast frontier model
    GEMINI_3_DEEP_THINK = "gemini-3-deep-think"  # Complex reasoning
    GEMINI_2_5_PRO = "gemini-2.5-pro"  # Stable production model
    GEMINI_2_5_FLASH = "gemini-2.5-flash"  # Price-performance optimized
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"  # Cost-efficient
    GEMINI_2_0_FLASH = "gemini-2.0-flash"  # Legacy (deprecating March 2026)
    # Legacy (deprecated)
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    GEMINI_PRO = "gemini-pro"

    # DeepSeek Models
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_REASONER = "deepseek-reasoner"
    DEEPSEEK_CODER = "deepseek-coder"

    # Anthropic Models
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet"

    # Ollama/Local Models (from user's setup)
    LLAMA_3_2_3B = "llama3.2:3b"
    LLAMA_3_1_8B = "llama3.1:8b"
    LLAMA_3 = "llama3:latest"
    QWEN_3 = "qwen3:latest"
    QWEN_2_5_CODER = "qwen2.5-coder:1.5b-base"
    PHI_3_MINI = "phi3:mini"
    CODELLAMA_13B = "codellama:13b"

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


class ChatAntwoord(Protocol):
    """Wat een agent van een antwoord leest; `LLMResponse` en het antwoord van de tenantdeur voldoen allebei."""

    @property
    def content(self) -> str: ...

    @property
    def success(self) -> bool: ...

    @property
    def error_message(self) -> str | None: ...


class ChatTaalmodel(Protocol):
    """Wat een agent van zijn taalmodel nodig heeft: een `LLMClient` OF het model van de tenant."""

    async def chat_completion(
        self, messages: list[LLMMessage], **kwargs: object
    ) -> ChatAntwoord: ...

    async def text_completion(self, prompt: str, **kwargs: object) -> ChatAntwoord: ...


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
                "generate_response",
            ),
        )

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self._request_count = 0
        self._total_response_time = 0.0
        self._error_count = 0

    @abstractmethod
    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Get chat completion from LLM"""

    @abstractmethod
    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Get text completion from LLM"""

    @bewaakt_model_aanroep
    async def generate_response(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Alias for text_completion, used by some agent implementations."""
        return await self.text_completion(prompt, **kwargs)

    async def validate_connection(self) -> bool:
        """Validate connection to LLM provider"""
        try:
            test_response = await self.text_completion(
                "Test connection. Respond with 'OK'.", max_tokens=10
            )
            return test_response.success
        except Exception as e:
            logger.error(f"LLM connection validation failed: {e}")
            return False

    def get_metrics(self) -> dict[str, str | int | float]:
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
            "workflow_generation": [
                json.dumps(
                    {
                        "name": "automated_customer_support",
                        "description": "A workflow to handle customer support tickets using AI and human agents.",
                        "nodes": [
                            {
                                "id": "node_1",
                                "agent_name": "schedule_agent",
                                "label": "Check Inbox",
                                "config": {"interval": "5m"},
                                "position": {"x": 100, "y": 100},
                            },
                            {
                                "id": "node_2",
                                "agent_name": "llm_summarizer",
                                "label": "Analyze Sentiment",
                                "config": {"model": "gemini-pro"},
                                "position": {"x": 250, "y": 100},
                            },
                            {
                                "id": "node_3",
                                "agent_name": "slack_agent",
                                "label": "Notify Team",
                                "config": {"channel": "#support"},
                                "position": {"x": 400, "y": 100},
                            },
                            {
                                "id": "node_4",
                                "agent_name": "email_agent",
                                "label": "Reply to Customer",
                                "config": {"template": "support_reply"},
                                "position": {"x": 400, "y": 250},
                            },
                        ],
                        "edges": [
                            {"id": "edge_1", "source": "node_1", "target": "node_2"},
                            {
                                "id": "edge_2",
                                "source": "node_2",
                                "target": "node_3",
                                "condition": "sentiment == 'negative'",
                            },
                            {
                                "id": "edge_3",
                                "source": "node_2",
                                "target": "node_4",
                                "condition": "sentiment == 'positive'",
                            },
                        ],
                        "metadata": {"version": "1.0", "author": "VIBE Mock"},
                    }
                ),
                json.dumps(
                    {
                        "name": "content_approval_pipeline",
                        "description": "Workflow for generating and approving marketing content.",
                        "nodes": [
                            {
                                "id": "node_1",
                                "agent_name": "schedule_agent",
                                "label": "Weekly Trigger",
                                "config": {"cron": "0 9 * * 1"},
                                "position": {"x": 100, "y": 100},
                            },
                            {
                                "id": "node_2",
                                "agent_name": "llm_summarizer",
                                "label": "Generate Draft",
                                "config": {"topic": "Heritage Curation"},
                                "position": {"x": 250, "y": 100},
                            },
                            {
                                "id": "node_3",
                                "agent_name": "notification_agent",
                                "label": "Review Required",
                                "config": {"user": "admin"},
                                "position": {"x": 400, "y": 100},
                            },
                            {
                                "id": "node_4",
                                "agent_name": "http_request",
                                "label": "Publish to Web",
                                "config": {"url": "https://api.sanskritisetu.org/publish"},
                                "position": {"x": 550, "y": 100},
                            },
                        ],
                        "edges": [
                            {"id": "edge_1", "source": "node_1", "target": "node_2"},
                            {"id": "edge_2", "source": "node_2", "target": "node_3"},
                            {"id": "edge_3", "source": "node_3", "target": "node_4"},
                        ],
                        "metadata": {"version": "1.1", "author": "VIBE Mock"},
                    }
                ),
            ],
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

        if any(word in text_lower for word in ["workflow", "node", "edge", "json only"]):
            return "workflow_generation"
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

            # Determine model to use (support override)
            model_name = kwargs.get("model", self.model.value)

            # Build generation config (new SDK)
            config = self.types.GenerateContentConfig(
                max_output_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
            )

            # Generate response using client API
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=model_name, contents=conversation_text, config=config
                ),
            )

            response_time = time.time() - start_time
            self._update_metrics(response_time, True)

            # Handle blocked content from Google safety filters
            try:
                content: str | None = response.text
            except Exception as text_error:
                # Check if content was blocked by safety filters
                candidates = getattr(response, "candidates", None)
                if candidates is not None and len(candidates) > 0:
                    candidate = candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        if candidate.finish_reason == 2:  # SAFETY filter block
                            return LLMResponse(
                                content="Content blocked by safety filters",
                                model=model_name,
                                provider=self.provider.value,
                                response_time=response_time,
                                success=False,
                                error_message=f"Content blocked by Google safety filters (finish_reason={candidate.finish_reason})",
                            )
                # Other text access errors
                return LLMResponse(
                    content="Response text not accessible",
                    model=model_name,
                    provider=self.provider.value,
                    response_time=response_time,
                    success=False,
                    error_message=f"Could not access response text: {str(text_error)}",
                )

            # Ensure content is not None before passing to LLMResponse
            if content is None:
                return LLMResponse(
                    content="Response text is empty",
                    model=model_name,
                    provider=self.provider.value,
                    response_time=response_time,
                    success=False,
                    error_message="Google API returned empty response",
                )

            return LLMResponse(
                content=content,
                model=model_name,
                provider=self.provider.value,
                usage={
                    "input_tokens": len(conversation_text.split()),
                    "output_tokens": len(content.split()) if content else 0,
                    "total_tokens": len(conversation_text.split())
                    + (len(content.split()) if content else 0),
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


class DeepSeekClient(LLMClient):
    """DeepSeek LLM client implementation (OpenAI-compatible)"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            import httpx

            self.httpx = httpx
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
                error_message="DeepSeek client (httpx) not initialized",
            )

        start_time = time.time()

        try:
            # Convert messages to OpenAI format
            openai_messages: list[dict[str, str]] = []
            for msg in messages:
                openai_messages.append({"role": msg.role, "content": msg.content})

            # Determine model
            model_name = kwargs.get("model", self.model.value)

            # Build payload
            payload = {
                "model": model_name,
                "messages": openai_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "stream": False,
            }

            # Make request
            async with self.httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise Exception(f"DeepSeek API error: {response.text}")

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                response_time = time.time() - start_time
                self._update_metrics(response_time, True)

                return LLMResponse(
                    content=content,
                    model=model_name,
                    provider=self.provider.value,
                    usage=usage,
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

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """DeepSeek text completion"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)


class LocalClient(LLMClient):
    """Local LLM client implementation (OpenAI-compatible)"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            import httpx

            self.httpx = httpx
            self.api_key = config.api_key
            # Use configured URL or default
            from src.core.shared.config import get_settings

            settings = get_settings()
            self.base_url = getattr(settings, "LOCAL_LLM_URL", "http://localhost:11434/v1")
            self._available = True
        except ImportError:
            logger.warning("httpx package not available. Install with: pip install httpx")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Local client: {e}")
            self._available = False

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """Local chat completion. A failure is an error: there is no fallback to a rented model."""
        if not self._available:
            return LLMResponse(
                content="Local client not available",
                model=self.model.value,
                provider=self.provider.value,
                success=False,
                error_message="Local client (httpx) not initialized",
            )

        start_time = time.time()

        try:
            # Convert messages to OpenAI format
            openai_messages: list[dict[str, str]] = []
            for msg in messages:
                openai_messages.append({"role": msg.role, "content": msg.content})

            # Determine model
            model_name = kwargs.get("model", self.model.value)

            # Build payload
            payload = {
                "model": model_name,
                "messages": openai_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "stream": False,
            }

            # Make request
            async with self.httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise Exception(f"Local API error ({response.status_code}): {response.text}")

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

                response_time = time.time() - start_time
                self._update_metrics(response_time, True)

                return LLMResponse(
                    content=content,
                    model=model_name,
                    provider=self.provider.value,
                    usage=usage,
                    response_time=response_time,
                    success=True,
                )

        except Exception as e:
            response_time = time.time() - start_time
            self._update_metrics(response_time, False)

            # GEEN terugval op een gehuurd model (ADR-041 B14, brief 2026-10-19). Hier stond een keten
            # lokaal -> DeepSeek -> Gemini, en bij het mislukken van alles `success=True` met een foutmelding
            # als antwoord. Een klant die het lokale model koos (ollama), of wiens taak lokaal draait, mag bij
            # een storing niet stil bij DeepSeek (China) of Google uitkomen, en een mislukking is geen succes.
            logger.error(
                "Local LLM unavailable (%s): geen terugval op een gehuurd model", type(e).__name__
            )
            return LLMResponse(
                content="",
                model=self.model.value,
                provider=self.provider.value,
                response_time=response_time,
                success=False,
                error_message=f"Lokaal taalmodel niet beschikbaar: {e}",
            )

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Local text completion"""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat_completion(messages, **kwargs)


def get_default_llm_config() -> LLMConfig:
    """Get default LLM configuration based on available API keys"""
    from src.core.shared.config import get_settings

    settings = get_settings()

    # Check explicit preference
    provider_pref = getattr(settings, "LLM_PROVIDER", "local").lower()

    if provider_pref == "local":
        return LLMConfig(
            provider=LLMProvider.LOCAL,
            model=LLMModel.LLAMA_3,  # Default to llama3:latest (available in Ollama)
            api_key="local",
            max_tokens=2000,
            temperature=0.7,
        )

    # Use Google Gemini or fallback to local
    if settings.google_api_key:
        return LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_2_5_FLASH,  # Current stable model
            api_key=settings.google_api_key,
            max_tokens=2000,
            temperature=0.7,
        )
    else:
        # Fallback to local Ollama if no API keys
        return LLMConfig(
            provider=LLMProvider.LOCAL,
            model=LLMModel.LLAMA_3,
            api_key="local",
            max_tokens=2000,
        )


# Convenience function for backward compatibility
def create_llm_client(provider_name: str) -> LLMClient:
    """Create LLM client from provider name string.

    Wie om model X vraagt krijgt model X of een FOUT (ADR-041 B14, brief 2026-10-20). Hier stond een keten:
    een ontbrekende Google-sleutel viel door naar Google/Local/mock, `anthropic` gaf een Google-client, een
    onbekende naam een namaakclient. Een tenantverzoek hoort via `TenantTaalmodel`; deze fabriek is voor
    systeemtaken en voor de paden op de lijst van `tests/architecture/test_klantpaden_volgen_de_modelkeuze.py`.
    """
    from src.core.shared.config import get_settings

    settings = get_settings()
    naam = provider_name.strip().lower()

    if naam == "local":
        config = LLMConfig(
            provider=LLMProvider.LOCAL,
            model=LLMModel.LLAMA_3,
            api_key="local",
            max_tokens=2000,
        )
    elif naam == "google":
        google_sleutel = getattr(settings, "google_api_key", None)
        if not google_sleutel:
            raise ValueError(
                "google: er is geen GOOGLE_API_KEY; er wordt niet op een ander model teruggevallen"
            )
        config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_1_5_FLASH,
            api_key=google_sleutel,
            max_tokens=2000,
            temperature=0.7,
        )
    elif naam == "anthropic":
        raise ValueError(
            "anthropic: er is geen Anthropic-client; er wordt niet stil een Google-client voor in de plaats gezet"
        )
    elif naam == "mock":
        if not namaak_toegestaan():
            raise ValueError("mock: een namaakmodel is alleen in tests toegestaan")
        config = LLMConfig(
            provider=LLMProvider.MOCK,
            model=LLMModel.MOCK_MODEL,
            api_key="mock",
            max_tokens=2000,
            temperature=0.7,
        )
    else:
        raise ValueError(f"onbekend taalmodel '{provider_name}'")
    return create_llm_client_from_config(config)


# Clean factory function for supported providers
def create_llm_client_from_config(config: LLMConfig) -> LLMClient:
    """Factory function to create appropriate LLM client from config"""
    if config.provider == LLMProvider.GOOGLE:
        return GoogleClient(config)
    elif config.provider == LLMProvider.DEEPSEEK:
        # Geen client voor DeepSeek: mag niet met klantgegevens (ADR-041 B14, brief 2026-10-19).
        raise ValueError("DeepSeek (China, geen verwerkersovereenkomst) wordt niet gebouwd")
    elif config.provider == LLMProvider.LOCAL or config.provider == LLMProvider.OLLAMA:
        return LocalClient(config)
    elif config.provider == LLMProvider.ANTHROPIC:
        # Er is geen Anthropic-client. Hier stond "fallback to Google": een verzoek om Claude ging stil naar
        # Gemini (brief 2026-10-20).
        raise ValueError("anthropic: er is geen Anthropic-client")
    elif config.provider == LLMProvider.MOCK:
        if not namaak_toegestaan():
            raise ValueError("mock: een namaakmodel is alleen in tests toegestaan")
        return MockLLMClient(config)
    else:
        raise ValueError(f"Provider {config.provider} niet ondersteund")
