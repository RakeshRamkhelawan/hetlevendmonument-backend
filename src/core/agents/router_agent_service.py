import logging
import os
from enum import Enum
from typing import Any, Optional, cast

from pydantic import BaseModel, Field

from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.llm.provider_factory import LLMProviderFactory
from src.core.shared.config import get_settings

instructor: Any | None = None  # TODO(TYPE): replace Any with concrete type
try:
    import instructor as _instructor  # Optional dependency for structured LLM outputs

    instructor = _instructor
except ImportError:  # pragma: no cover - optional dependency in local/test envs
    pass

logger = logging.getLogger(__name__)


class TaskCategory(str, Enum):
    SIMPLE_CHAT = "simple_chat"
    COMPLEX_REASONING = "complex_reasoning"
    TOOL_USE = "tool_use"
    DATA_ANALYSIS = "data_analysis"


class RoutingDecision(BaseModel):
    category: TaskCategory = Field(..., description="The category of the task")
    priority: int = Field(..., description="Priority level 1-10 (10 being highest)")
    suggested_model: str = Field(..., description="Model to use e.g. llama3.1:8b, gemini-pro")
    reasoning: str = Field(..., description="Why this route was chosen")


class RouterAgentService:
    """
    Router Agent Service (Feature 0)
    Uses a small, fast local LLM (llama3.1:8b via Ollama) to classify
    and route user queries to the appropriate specialized agent or model.
    """

    def __init__(
        self, client: Any | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        settings = get_settings()
        # Default to localhost for now, allowing override via env
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
        self.api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        self.model = os.getenv("ROUTER_MODEL", "llama3.1:8b")
        self._raw_client: Any = None

        if client:
            self.client = client
        else:
            try:
                from openai import AsyncOpenAI

                self._raw_client = AsyncOpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                )

                if instructor is not None:
                    self.client = instructor.from_openai(
                        self._raw_client,
                        mode=instructor.Mode.JSON,
                    )
                else:
                    self.client = None
                    logger.warning(
                        "RouterAgentService initialized without instructor; using fallback routing"
                    )
                logger.info(
                    "RouterAgentService initialized with model %s at %s",
                    self.model,
                    self.base_url,
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize RouterAgentService: %s: %s",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                raise e

    @bewaakt_model_aanroep
    async def route_request(self, query: str) -> RoutingDecision:
        """
        Classifies the user query and determines the best routing strategy.
        """
        if self.client is None:
            return self._fallback_route(query, "instructor dependency unavailable")

        try:
            decision = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an intelligent router for an AI platform. "
                            "Analyze the user's query and classify it into one of the following categories:\n"
                            "- simple_chat: Basic greetings, simple questions, concise answers.\n"
                            "- complex_reasoning: detailed explanations, creative writing, multi-step logic.\n"
                            "- tool_use: requests needing external data, calculations, or specific actions.\n"
                            "- data_analysis: requests involving large text processing or structured data analysis.\n\n"
                            "Assign a priority (1-10) and suggest a model (e.g., 'llama3.1:8b' for simple/local, 'gemini-pro' for complex/cloud)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
                response_model=RoutingDecision,
            )
            return cast(RoutingDecision, decision)
        except Exception as e:
            logger.error("Error routing request: %s: %s", type(e).__name__, e, exc_info=True)
            return self._fallback_route(query, str(e))

    @bewaakt_model_aanroep
    async def execute_request(
        self, query: str, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Executes the route decision by calling the appropriate provider.
        """
        decision = await self.route_request(query)
        result = None
        executed_by = ""

        try:
            if "gemini" in decision.suggested_model.lower():
                try:
                    # GEEN tenant meer (BE-LLM-004). Die parameter werd hier meegegeven en
                    # verderop genegeerd: de fabriek keek in een woordenboek dat nergens werd
                    # gevuld, dus dit pad draaide altijd al op de platformsleutel. De melding
                    # hieronder zei "for tenant" en suggereerde daarmee een inrichting per
                    # klant die niet bestond. Wie hier wel de provider van de KLANT wil, gaat
                    # via `LLMService.for_tenant()` -- dat is een eigen wijziging, want dit is
                    # een Gemini-specifiek pad dat in fase 4 sowieso verdwijnt.
                    provider = LLMProviderFactory.get_provider(provider_type="gemini")
                    if not getattr(provider, "api_key", None):
                        raise ValueError("No Gemini API key configured for the platform")

                    response = await provider.text_completion(query)
                    if response.success:
                        result = response.content
                        executed_by = "gemini_provider"
                    else:
                        raise Exception(f"Gemini provider error: {response.error_message}")
                except Exception as e:
                    logger.warning(
                        "Gemini execution failed: %s: %s -- falling back to Ollama",
                        type(e).__name__,
                        e,
                        exc_info=True,
                    )
                    result = await self._call_ollama(query, self.model)
                    executed_by = "ollama_fallback"
            else:
                # Default to Ollama (local)
                # Use the suggested model if it is likely local, else fallback to self.model
                model_to_use = (
                    decision.suggested_model
                    if "llama" in decision.suggested_model.lower()
                    or "mistral" in decision.suggested_model.lower()
                    else self.model
                )
                result = await self._call_ollama(query, model_to_use)
                executed_by = "ollama_local"
        except Exception as e:
            logger.error("Execution failed: %s: %s", type(e).__name__, e, exc_info=True)
            result = f"Error processing request: {str(e)}"
            executed_by = "error_handler"

        return {
            "query": query,
            "decision": decision.model_dump(),  # pydantic v2 uses model_dump
            "result": result,
            "executed_by": executed_by,
            "tenant_id": tenant_id,
        }

    async def _call_ollama(self, query: str, model: str) -> str:
        """Helper to call local Ollama model for simple text generation."""
        try:
            if self.client is not None:
                return cast(
                    str,
                    await self.client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": query}],
                        response_model=str,
                    ),
                )

            if self._raw_client is None:
                raise RuntimeError("No Ollama client available")

            response = await self._raw_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": query}],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(
                "Ollama call failed for %s: %s: %s", model, type(e).__name__, e, exc_info=True
            )
            # Try fallback to validated model
            if model != self.model:
                if self.client is not None:
                    return cast(
                        str,
                        await self.client.chat.completions.create(
                            model=self.model,
                            messages=[{"role": "user", "content": query}],
                            response_model=str,
                        ),
                    )
                if self._raw_client is not None:
                    retry = await self._raw_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": query}],
                    )
                    return retry.choices[0].message.content or ""
            raise e

    def _fallback_route(self, query: str, reason: str) -> RoutingDecision:
        """Return a deterministic local routing decision when structured routing is unavailable."""
        lowered = query.lower()
        category = TaskCategory.SIMPLE_CHAT
        if any(token in lowered for token in ["analyze", "dataset", "csv", "json", "table"]):
            category = TaskCategory.DATA_ANALYSIS
        elif any(token in lowered for token in ["tool", "search", "fetch", "call", "run"]):
            category = TaskCategory.TOOL_USE
        elif any(token in lowered for token in ["explain", "plan", "reason", "compare"]):
            category = TaskCategory.COMPLEX_REASONING

        return RoutingDecision(
            category=category,
            priority=5,
            suggested_model=self.model,
            reasoning=f"Fallback routing used: {reason}",
        )
