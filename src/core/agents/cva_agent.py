#!/usr/bin/env python3
"""
Chief Visionary Architect (CVA) Agent Implementation
(Refactored: Now delegates to modules in src/core/agents/cva/)
"""

import logging
from typing import Any, Optional, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.memory.facade import MemoryManager

from src.core.agents.cva import communication_handler as communication_handler_module
from src.core.agents.cva.agent import CVAAgent as _ModularCVAAgent
from src.core.agents.cva.models import CVAState, OrchestrationCommand
from src.core.agents.cva_state_machine import CVAMode
from src.core.communication.communication_manager import communication_manager
from src.core.communication.message_protocol import MessageFactory
from src.core.shared.config import get_feature_flag
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel, LLMClient, LLMMessage

memory_manager: "MemoryManager | None" = None
logger = logging.getLogger(__name__)


class CVAAgent(_ModularCVAAgent):
    """Compatibility wrapper around the modular CVA agent implementation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._llm_clients = self.llm_handler._llm_clients
        self._startup_operational_providers = self.llm_handler._startup_operational_providers
        self.memory_initialized = False

    @property
    def communication_initialized(self) -> bool:
        return self.communication_handler.communication_initialized

    @communication_initialized.setter
    def communication_initialized(self, value: bool) -> None:
        self.communication_handler.communication_initialized = value

    @property
    def _llm_clients(self) -> dict[str, LLMClient]:
        return self.llm_handler._llm_clients

    @_llm_clients.setter
    def _llm_clients(self, value: dict[str, LLMClient]) -> None:
        self.llm_handler._llm_clients = value

    @property
    def _startup_operational_providers(self) -> set[str]:
        return self.llm_handler._startup_operational_providers

    @_startup_operational_providers.setter
    def _startup_operational_providers(self, value: set[str]) -> None:
        self.llm_handler._startup_operational_providers = value

    @_startup_operational_providers.deleter
    def _startup_operational_providers(self) -> None:
        if hasattr(self.llm_handler, "_startup_operational_providers"):
            delattr(self.llm_handler, "_startup_operational_providers")

    def get_current_mode(self) -> CVAMode:
        return self.state_manager.cva_state.mode

    async def initialize_communication_system(
        self,
    ) -> None:
        communication_handler_module.communication_manager = communication_manager
        await super().initialize_communication_system()

    async def send_strategic_command(
        self, *args: Any, **kwargs: Any
    ) -> (
        # TODO(TYPE): replace Any with concrete type
        Any
    ):  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        communication_handler_module.communication_manager = communication_manager
        setattr(communication_handler_module, "MessageFactory", MessageFactory)
        return await super().send_strategic_command(*args, **kwargs)

    async def _get_llm_client_for_provider(self, provider: str) -> ChatTaalmodel | None:
        """Het taalmodel van de TENANT van deze agent, ongeacht de gevraagde `provider`.

        Hier stond `create_llm_client(provider)`: een eigen client per leverancier (Google, Anthropic, ...), buiten
        de keuze van de klant om (brief 2026-10-20, ADR-041 B14).
        """
        if not get_feature_flag("real_llm_integration"):
            return None
        return TenantTaalmodel(self.tenant_id)

    async def _validate_provider_health(self, provider: str) -> bool:
        try:
            if provider in getattr(self, "_startup_operational_providers", set()):
                return True
            client = await self._get_llm_client_for_provider(provider)
            return client is not None
        except Exception as exc:
            logger.error("Provider health check failed for %s: %s", provider, exc)
            return False

    async def _log_successful_provider_usage(self, provider: str, request_type: str) -> None:
        logger.info("LLM provider success: %s for %s", provider, request_type)
        detector = globals().get("mock_usage_detector")
        record = getattr(detector, "record_successful_request", None)
        if record is not None:
            try:
                await record(provider=provider, request_type=request_type)
            except Exception:
                logger.debug("mock_usage_detector record_successful_request failed")

    async def _alert_critical_llm_failure(self, query: str, request_type: str) -> None:
        logger.critical("Critical LLM failure for %s request", request_type)

    async def _enhanced_mock_response_with_retry_option(
        self,
        query: str,
        conversation_history: list[dict[str, object]],
        request_type: str,
    ) -> dict[str, object]:
        if request_type == "strategic":
            payload: dict[str, object] = {
                "text": "Mock strategic guidance generated.",
                "strategy_type": "fallback",
                "recommendation": "Retry with a live provider.",
            }
        elif request_type == "decomposition":
            payload = {
                "text": "Mock task decomposition generated.",
                "subtasks": ["Analyze", "Plan", "Execute"],
                "timeline": "Short-term",
            }
        elif request_type == "vision":
            payload = {
                "text": "Mock vision synthesis generated.",
                "vision_statement": "Deliver reliable strategic outcomes.",
                "objectives": ["Stability", "Clarity", "Execution"],
            }
        else:
            payload = {"text": "Mock general consultation response."}

        payload.update(
            {
                "success": True,
                "is_mock": True,
                "provider_used": "mock_fallback",
                "error_message": "Live LLM unavailable",
                "mock_reason": "all_providers_unavailable",
                "retry_available": True,
                "retry_suggestion": "Retry the request once a live provider is available.",
            }
        )
        return payload

    async def _enhanced_mock_response(
        self,
        query: str,
        conversation_history: list[dict[str, object]],
        request_type: str,
    ) -> dict[str, object]:
        return await self._enhanced_mock_response_with_retry_option(
            query, conversation_history, request_type
        )

    async def _execute_llm_request(
        self,
        llm_client: ChatTaalmodel,
        query: str,
        conversation_history: list[dict[str, object]],
        request_type: str,
        model_override: str | None = None,
    ) -> dict[str, object]:
        try:
            prompt_request_type = {
                "strategic": "strategic_analysis",
                "decomposition": "task_decomposition",
                "vision": "vision_synthesis",
            }.get(request_type, request_type)
            system_prompt, user_prompt = self.cva_prompts.format_prompt(
                prompt_request_type,
                {
                    "query": query,
                    "context": conversation_history,
                    "conversation_history": conversation_history,
                },
            )
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ]

            kwargs: dict[str, str] = {}
            if model_override is not None:
                kwargs["model"] = model_override
            elif hasattr(self, "ai_router") and self.ai_router is not None:
                try:
                    complexity = self.ai_router.analyze_complexity(query)
                    selected_model = self.ai_router.route_to_model(complexity)
                    if selected_model is not None:
                        kwargs["model"] = selected_model
                except Exception:
                    logger.debug("AI router model selection failed", exc_info=True)

            response = await llm_client.chat_completion(messages, **kwargs)
            if response is None:
                return {"success": False, "error": "LLM returned no response"}
            if not getattr(response, "success", False):
                return {
                    "success": False,
                    "error": getattr(response, "error_message", "LLM request failed"),
                }

            return {
                "success": True,
                "content": getattr(response, "content", "") or "",
                "provider_used": getattr(response, "provider", "unknown"),
                "model": getattr(response, "model", None),
                "response_time": getattr(response, "response_time", 0.0),
                "usage": getattr(response, "usage", {}),
                "confidence": 0.9,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def request_llm_reasoning(
        self,
        query: str,
        conversation_history: list[dict[str, object]],
        request_type: str,
        model_override: str | None = None,
    ) -> dict[str, object]:
        providers = ["anthropic", "google", "ollama"]
        if model_override and "gemini" in model_override.lower():
            providers = ["google", "anthropic", "ollama"]

        if hasattr(self, "ai_router") and self.ai_router is not None:
            try:
                complexity = self.ai_router.analyze_complexity(query)
                routed_model = self.ai_router.route_to_model(complexity)
                if model_override is None and routed_model is not None:
                    model_override = routed_model
            except Exception:
                logger.debug("AI router analysis failed", exc_info=True)

        for provider in providers:
            try:
                healthy = await self._validate_provider_health(provider)
                if not healthy:
                    continue
                client = await self._get_llm_client_for_provider(provider)
                if client is None:
                    continue
                result = await self._execute_llm_request(
                    client,
                    query,
                    conversation_history,
                    request_type,
                    model_override=model_override,
                )
                if result.get("success"):
                    await self._log_successful_provider_usage(provider, request_type)
                    result.setdefault("provider_used", provider)
                    return result
            except Exception as exc:
                logger.error("Provider %s failed during reasoning request: %s", provider, exc)
                logger.exception(exc)

        await self._alert_critical_llm_failure(query, request_type)
        return await self._enhanced_mock_response_with_retry_option(
            query, conversation_history, request_type
        )


__all__ = ["CVAAgent", "CVAState", "OrchestrationCommand"]
