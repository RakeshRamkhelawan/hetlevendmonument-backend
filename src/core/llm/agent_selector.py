"""
Agent Selector Service - Intelligent agent selection using LLM with fallbacks.

Combines:
- LLM-based selection with fallback chain
- Optimized prompt templates
- Caching for common selections
- Cost-aware model selection
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.core.llm.fallback_chain import (
    FallbackResult,
    LLMFallbackChain,
    ModelConfig,
    ModelTier,
    get_fallback_chain,
)
from src.core.llm.prompt_templates import optimizer, templates

logger = logging.getLogger(__name__)


@dataclass
class AgentSelection:
    """Result of agent selection process."""

    agent_id: str
    confidence: float
    reasoning: str
    fallback_agents: list[str]
    method: str  # "llm", "cache", "heuristic", "fallback"
    latency_ms: float
    cost_usd: float
    model_used: str


class AgentSelector:
    """
    Intelligent agent selector with multi-tier fallback.

    Selection flow:
    1. Check cache for identical/similar tasks
    2. Try LLM-based selection with fallback models
    3. Fall back to heuristic matching
    4. Return default agent if all else fails
    """

    def __init__(
        self,
        fallback_chain: LLMFallbackChain | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.fallback_chain = fallback_chain or get_fallback_chain()
        self._cache: dict[str, AgentSelection] = {}
        self._cache_ttl = cache_ttl_seconds
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "llm_calls": 0,
            "heuristic_fallbacks": 0,
        }

    def _get_cache_key(
        self,
        task_title: str,
        task_description: str,
        capabilities: list[str] | None,
    ) -> str:
        """Generate cache key from task."""
        import hashlib

        key_data = f"{task_title}|{task_description}|{','.join(sorted(capabilities or []))}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def select_agent(
        self,
        task_title: str,
        task_description: str,
        available_agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        required_capabilities: list[str] | None = None,
        use_cache: bool = True,
        preferred_tier: ModelTier | None = None,
    ) -> AgentSelection:
        """
        Select best agent for the task.

        Args:
            task_title: Short task name
            task_description: Detailed task description
            available_agents: List[Any] of candidate agents with capabilities  # TODO(TYPE): replace Any with concrete type
            required_capabilities: Required agent capabilities
            use_cache: Whether to check/use cache
            preferred_tier: Preferred LLM tier (for cost control)

        Returns:
            AgentSelection with selected agent and metadata
        """
        import time

        start_time: float = time.time()

        # Step 1: Check cache
        if use_cache:
            cache_key = self._get_cache_key(task_title, task_description, required_capabilities)
            if cache_key in self._cache:
                self._stats["cache_hits"] += 1
                cached = self._cache[cache_key]
                cached.latency_ms = (time.time() - start_time) * 1000  # Update latency
                logger.debug(f"Cache hit for agent selection: {cached.agent_id}")
                return cached

            self._stats["cache_misses"] += 1

        # Step 2: Try LLM-based selection with fallback chain
        self._stats["llm_calls"] += 1

        prompt = optimizer.build_routing_prompt(
            task_title=task_title,
            task_description=task_description,
            agents=available_agents,
            capabilities=required_capabilities,
            use_few_shot=len(available_agents) < 15,
        )

        system_prompt = """You are an expert task router. Analyze tasks and select the best agent.
Respond only with valid JSON matching the requested format."""

        result = await self.fallback_chain.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            preferred_tier=preferred_tier or ModelTier.PRIMARY,
            fallback=True,
            temperature=0.3,  # Lower temperature for consistent routing
        )

        # Parse LLM response
        selection = self._parse_llm_result(
            result, available_agents, (time.time() - start_time) * 1000
        )

        # Cache successful selections
        if use_cache and selection.confidence > 0.7:
            cache_key = self._get_cache_key(task_title, task_description, required_capabilities)
            self._cache[cache_key] = selection

        return selection

    def _parse_llm_result(
        self,
        result: FallbackResult,
        available_agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        latency_ms: float,
    ) -> AgentSelection:
        """Parse LLM response into AgentSelection."""

        agent_ids = {a["id"] for a in available_agents}

        if result.success and result.content:
            try:
                # Extract JSON from response
                content = result.content

                # Handle markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                data = json.loads(content.strip())

                selected = data.get("selected_agent", "")
                confidence = float(data.get("confidence", 0.5))
                reasoning = data.get("reasoning", "No reasoning provided")
                fallbacks = data.get("fallback_agents", [])

                # Validate selected agent exists
                if selected in agent_ids:
                    return AgentSelection(
                        agent_id=selected,
                        confidence=confidence,
                        reasoning=reasoning,
                        fallback_agents=[a for a in fallbacks if a in agent_ids][:2],
                        method="llm",
                        latency_ms=latency_ms,
                        cost_usd=result.estimated_cost_usd,
                        model_used=result.model_used,
                    )

                logger.warning(f"LLM selected unknown agent: {selected}")

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response: {e}")
            except Exception as e:
                logger.warning(f"Error parsing selection: {e}")

        # Fall back to heuristic
        self._stats["heuristic_fallbacks"] += 1
        return self._heuristic_selection(available_agents, latency_ms)

    def _heuristic_selection(
        self,
        available_agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        latency_ms: float,
    ) -> AgentSelection:
        """Fallback heuristic selection when LLM fails."""

        if not available_agents:
            # Ultimate fallback
            return AgentSelection(
                agent_id="executor_agent_001",
                confidence=0.3,
                reasoning="No agents available, using default executor",
                fallback_agents=[],
                method="default",
                latency_ms=latency_ms,
                cost_usd=0.0,
                model_used="none",
            )

        # Select first agent with highest capability count
        best_agent = max(
            available_agents,
            key=lambda a: len(a.get("capabilities", [])),
        )

        return AgentSelection(
            agent_id=best_agent["id"],
            confidence=0.5,
            reasoning="Heuristic: agent with most capabilities",
            fallback_agents=[a["id"] for a in available_agents if a["id"] != best_agent["id"]][:2],
            method="heuristic",
            latency_ms=latency_ms,
            cost_usd=0.0,
            model_used="none",
        )

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get selector statistics."""
        total = self._stats["cache_hits"] + self._stats["cache_misses"]
        return {
            **self._stats,
            "cache_hit_rate": self._stats["cache_hits"] / total if total > 0 else 0.0,
            "cache_size": len(self._cache),
        }

    def clear_cache(self) -> None:
        """Clear selection cache."""
        self._cache.clear()
        logger.info("Agent selection cache cleared")


# Convenience function for direct usage
async def select_agent(
    task_title: str,
    task_description: str,
    available_agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    **kwargs: Any,
) -> AgentSelection:
    """Quick agent selection without managing selector instance."""
    selector = AgentSelector()
    return await selector.select_agent(
        task_title=task_title,
        task_description=task_description,
        available_agents=available_agents,
        **kwargs,
    )
