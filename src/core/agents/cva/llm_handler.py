import logging
from typing import Any, Optional, cast

from src.core.agents.cva_prompts import get_cva_prompts
from src.core.shared.config import get_feature_flag
from src.core.shared.llm_client import (
    LLMClient,
    LLMMessage,
    create_llm_client,
    get_default_llm_config,
)
from src.core.shared.response_cache import cached_llm_response

logger = logging.getLogger(__name__)


class LLMHandler:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._llm_clients: dict[str, LLMClient] = {}
        self._startup_operational_providers: set[str] = {"google"}
        self.cva_prompts = get_cva_prompts()
        self._llm_initialized = False
        self.llm_client: LLMClient | None = None

        try:
            llm_config = get_default_llm_config()
            self.llm_client = create_llm_client(llm_config.provider.value)
            self._llm_initialized = True
            logger.info(f"CVA LLM Handler initialized with {llm_config.provider.value}")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
            self.llm_client = None

    async def _get_llm_client_for_provider(self, provider: str) -> LLMClient | None:
        """Get or create LLM client for specific provider"""
        if not get_feature_flag("real_llm_integration"):
            return None

        if provider in self._llm_clients:
            return self._llm_clients[provider]

        try:
            llm_client = create_llm_client(provider)
            if llm_client:
                self._llm_clients[provider] = llm_client
                return llm_client
        except Exception as e:
            logger.error(f"Error creating client for {provider}: {e}")
        return None

    @cached_llm_response("vision_synthesis")
    async def _call_llm_for_vision_synthesis(
        self, requirements: list[Any], constraints: list[Any], description: str  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Call real LLM for vision synthesis"""
        # Logic extracted from cva_agent.py
        variables = {
            "stakeholder_requirements": str(requirements),
            "business_constraints": "Budget and timeline constraints",
            "technical_constraints": str(constraints),
            "market_context": "Competitive AI/ML market",
            "success_criteria": "User satisfaction, system reliability",
            "timeline": "Quarterly milestones",
        }

        system_prompt, user_prompt = self.cva_prompts.format_prompt("vision_synthesis", variables)
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        if self.llm_client:
            response = await self.llm_client.chat_completion(messages)
            if response.success:
                try:
                    import json

                    return cast(dict[str, Any], json.loads(response.content))  # TODO(TYPE): replace Any with concrete type
                except:
                    pass
        return {"error": "LLM call failed"}

    async def consult_ceo(
        self,
        user_query: str,
        context: str = "",
        current_situation: str = "",
        desired_outcome: str = "",
        client_context: Any = "N/A",  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """
        Consult the CEO/CVA with strategic context and dynamic capabilities awareness.
        """
        from src.core.awareness.capabilities import get_capabilities_context

        # 1. Get dynamic capabilities context
        capabilities_context = await get_capabilities_context()

        # 2. Prepare variables
        variables = {
            "user_query": user_query,
            "context": context,
            "current_situation": current_situation,
            "desired_outcome": desired_outcome,
            "capabilities_context": capabilities_context,
        }

        # Handle client_context unpacking for new prompts
        if isinstance(client_context, dict):
            variables["client_context_route"] = client_context.get("route", "Unknown")
            variables["client_context_active_selection"] = client_context.get(
                "active_selection", "None"
            )
            # Keep original for backward compat if needed?
            # Or just use the string representation for other prompts
            variables["client_context"] = str(client_context)
        else:
            variables["client_context"] = str(client_context)
            variables["client_context_route"] = "Unknown"
            variables["client_context_active_selection"] = "None"

        # 3. Format prompt
        system_prompt, user_prompt = self.cva_prompts.format_prompt(
            "general_consultation", variables
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        # 4. Call LLM
        # Determine client to use
        target_client = self.llm_client

        # Check for preferred model in client_context
        if isinstance(client_context, dict) and client_context.get("preferred_model"):
            pref = client_context.get("preferred_model")
            # Map frontend model names to provider types
            provider_map = {
                "local": "local",
                "gemini": "gemini",
                "openai": "openai",
                "gpt-4": "openai",
            }
            if pref in provider_map:
                provider_type = provider_map[pref]
                # Dynamic switch
                dynamic_client = await self._get_llm_client_for_provider(provider_type)
                if dynamic_client:
                    target_client = dynamic_client
                    logger.info(f"Switched to {provider_type} provider for this request")

        if target_client:
            response = await target_client.chat_completion(messages)
            if response.success:
                return response.content
            return f"Strategic analysis unavailable: {response.error_message}"

        return "Strategic analysis unavailable: LLM client not initialized"
