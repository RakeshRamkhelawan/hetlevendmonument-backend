import json
import logging
from typing import Any

from .llm_client import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class MockProvider:
    """
    Mock LLM Provider for testing and fallback.
    Returns deterministic responses based on prompt keywords.
    """

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        self.provider = LLMProvider.MOCK
        self.model_names = ["mock-intelligent"]
        self.initialized = True
        self._should_fail: bool = False
        self._json_response: dict[str, str | float] = {
            "result": "mock_json_response",
            "status": "ok",
        }

    async def initialize(self) -> bool:
        return True

    async def validate_connection(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {"available": True, "latency_ms": 1}

    async def generate_response(
        self,
        prompt: str,
        model: str | None = None,
        tools: list[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        automatic_function_calling: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate mock response based on keywords."""

        # Check messages if prompt is empty (common in chat history context)
        messages = kwargs.get("messages", [])
        if not prompt and messages:
            # Extract last user message
            for m in reversed(messages):
                if m.get("role") == "user":
                    prompt = m.get("content", "")
                    break

        logger.info(f"MockProvider processing request. Prompt[:100]: {prompt[:100]}...")

        prompt_lower = prompt.lower()

        # Default response structure (JSON for CVA Agent)
        response_payload: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "message": "I am operating in Mock Mode. I processed your request.",
            "action": None,
            "confidence": 1.0,
            "thought_process": "Mock output generated based on keywords.",
        }

        # Keyword Logic
        if "analyze this user command" in prompt_lower:
            # NLP Handler Response
            response_payload = {
                "intent": "direct_question",
                "confidence": 0.9,
                "parameters": {},
                "suggested_clarification": None,
            }
            if "workflow" in prompt_lower:
                response_payload["intent"] = "creation"
            elif "status" in prompt_lower:
                response_payload["intent"] = "system_status"

        elif "workflow" in prompt_lower or "signup" in prompt_lower or "vibe" in prompt_lower:
            response_payload["message"] = "I can help you create that workflow in Vibe Studio."
            response_payload["action"] = "navigate_to_vibe"
            response_payload["action_params"] = {
                "intent": "create_workflow",
                "description": prompt,
            }
            response_payload["plan"] = ["Navigate to Vibe", "Pre-populate workflow"]

        elif "dashboard" in prompt_lower or "revenue" in prompt_lower:
            response_payload["message"] = (
                "I see the Total Revenue is irrelevant in Mock Mode, but I acknowledge the context."
            )

        elif "context" in prompt_lower or "page" in prompt_lower:
            response_payload["message"] = "I am aware of the page context provided."

        elif "number" in prompt_lower:
            response_payload["message"] = (
                "You showed me the number 50,000 from the revenue context."
            )

        else:
            logger.info(f"MockProvider: No keyword match for prompt: {prompt[:50]}...")

        # Return format matching LLMService expectation
        return {
            "content": json.dumps(response_payload),
            "success": True,
            "provider": self.provider.value,
            "model": "mock-intelligent",
        }

    async def complete_json(
        self,
        messages: list["LLMMessage"],
        schema: type[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> LLMResponse:
        """Return configurable mock JSON response. Raises RuntimeError if _should_fail=True."""
        if self._should_fail:
            raise RuntimeError("MockProvider configured to fail")
        return LLMResponse(
            content=json.dumps(self._json_response),
            model="mock-intelligent",
            provider=self.provider.value,
            success=True,
        )
