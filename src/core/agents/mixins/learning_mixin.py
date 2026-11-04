"""Learning support mixin for tenant-scoped agents."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, cast

from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.shared.config import get_feature_flag
from src.core.shared.interfaces import ExecutionResult, TaskData

# Closed Loop imports (Phase 2) -- try/except handles both production and test environments
try:
    from src.core.learning.cross_agent_service import CrossAgentLearningService  # pyright: ignore
    from src.core.learning.services.adaptation_service import AdaptationService  # pyright: ignore
    from src.core.learning.services.observation_service import ObservationService  # pyright: ignore
except ImportError:

    class AdaptationService:  # type: ignore[no-redef]
        """Fallback stub -- learning services unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...

    class CrossAgentLearningService:  # type: ignore[no-redef]
        """Fallback stub -- learning services unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...

    class ObservationService:  # type: ignore[no-redef]
        """Fallback stub -- learning services unavailable. Never instantiated at runtime."""

        def __init__(self, *args: object, **kwargs: object) -> None: ...


logger = logging.getLogger(__name__)


class LearningMixin:
    """Provides opt-in observation recording for agent executions."""

    def __init_learning__(self, tenant_id: int) -> None:
        self._learning_flag_names = self._get_learning_flag_names()
        self._learning_enabled = self._is_learning_enabled(tenant_id)
        self._learning_tenant_id = tenant_id if self._learning_enabled else 0
        self._observation_service_instance: object | None = None
        self._adaptation_service_instance: AdaptationService | None = None
        self._cross_agent_service_instance: CrossAgentLearningService | None = None

    @staticmethod
    def _normalize_learning_flag_part(value: object) -> str:
        """Normalize dynamic identifiers into stable feature-flag suffixes."""
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "unknown").lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized or "unknown"

    def _get_learning_group_names(self) -> tuple[str, ...]:
        """Infer rollout groups from agent module and type information."""
        module_name = getattr(self.__class__, "__module__", "")
        agent_type = self._normalize_learning_flag_part(
            getattr(getattr(self, "agent_type", None), "value", getattr(self, "agent_type", ""))
        )

        groups: list[str] = []
        if ".generated." in module_name:
            groups.extend(["generated", "technical"])
        if ".als." in module_name:
            groups.append("als")
        if "special" in agent_type:
            groups.append("specialist")
        if not groups:
            groups.append("core")

        return tuple(dict.fromkeys(groups))

    def _get_learning_flag_names(self) -> tuple[str, ...]:
        """Build the ordered feature-flag checks used for rollout control."""
        agent_id = self._normalize_learning_flag_part(getattr(self, "agent_id", None))
        agent_type = self._normalize_learning_flag_part(
            getattr(getattr(self, "agent_type", None), "value", getattr(self, "agent_type", None))
        )
        flag_names = ["learning_enabled"]
        flag_names.extend(
            f"learning_group_{group_name}" for group_name in self._get_learning_group_names()
        )
        flag_names.append(f"learning_agent_type_{agent_type}")
        flag_names.append(f"learning_agent_{agent_id}")
        return tuple(flag_names)

    def _is_learning_enabled(self, tenant_id: int) -> bool:
        """Enable learning only for valid tenants and active rollout flags."""
        if not tenant_id or tenant_id <= 0:
            return False

        for flag_name in self._learning_flag_names:
            try:
                if get_feature_flag(flag_name):
                    return True
            except Exception as exc:
                logger.warning("Learning feature flag lookup failed for %s: %s", flag_name, exc)
        return False

    @property
    def observation_service(self) -> ObservationService | None:
        """Lazily construct the observation service when learning is enabled."""
        if not self._learning_enabled:
            return None

        if self._observation_service_instance is None:
            from src.core.learning.services.observation_service import ObservationService

            self._observation_service_instance = ObservationService(
                tenant_id=self._learning_tenant_id
            )
        return self._observation_service_instance  # type: ignore[return-value]

    @property
    def adaptation_service(self) -> "AdaptationService | None":
        """Lazily construct the adaptation service when learning is enabled."""
        if not self._learning_enabled or AdaptationService is None:
            return None

        if self._adaptation_service_instance is None:
            self._adaptation_service_instance = AdaptationService(
                tenant_id=self._learning_tenant_id
            )
        return self._adaptation_service_instance

    @property
    def cross_agent_service(self) -> "CrossAgentLearningService | None":
        """Lazily construct the cross-agent learning service when learning is enabled."""
        if not self._learning_enabled or CrossAgentLearningService is None:
            return None

        if self._cross_agent_service_instance is None:
            self._cross_agent_service_instance = CrossAgentLearningService(
                tenant_id=self._learning_tenant_id
            )
        return self._cross_agent_service_instance

    def _build_learning_context(
        self,
        task: TaskData,
        result: ExecutionResult | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build a stable learning context for a task execution."""
        return {
            "agent_id": getattr(self, "agent_id", None),
            "agent_type": getattr(getattr(self, "agent_type", None), "value", None)
            or str(getattr(self, "agent_type", "unknown")),
            "tenant_id": self._learning_tenant_id,
            "task_id": task.id,
            "task_title": task.title,
            "task_type": task.metadata.get("type", "general"),
            "assigned_to": task.assigned_to,
            "result_success": result.success if result else None,
        }

    def _build_outcome_metrics(
        self,
        task: TaskData,
        result: ExecutionResult,
    ) -> dict[str, float]:
        """Build numeric outcome metrics compatible with observation persistence."""
        return {
            "execution_time": float(result.execution_time),
            "success": 1.0 if result.success else 0.0,
            "error_count": 0.0 if result.success else 1.0,
            "task_metadata_count": float(len(task.metadata)),
        }

    async def _record_task_observation(
        self,
        task: TaskData,
        result: ExecutionResult,
    ) -> str | None:
        """Persist a task execution observation without affecting task execution."""
        if not self._learning_enabled:
            return None

        service = self.observation_service
        if service is None:
            return None

        try:
            context = self._build_learning_context(task, result)
            outcome_metrics = self._build_outcome_metrics(task, result)
            observation_data = {
                "task_title": task.title,
                "task_description": task.description,
                "result_data": result.result_data or {},
                "error_message": result.error_message,
            }
            return cast(
                Optional[str],
                await cast(Any, service).record(  # TODO(TYPE): replace Any with concrete type
                    source=LearningSource.TASK_EXECUTION,
                    learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
                    context=context,
                    observation_data=observation_data,
                    outcome_metrics=outcome_metrics,
                ),
            )
        except Exception as exc:
            logger.warning(
                "Learning recording failed for agent %s: %s",
                getattr(self, "agent_id", "unknown"),
                exc,
            )
            return None

    async def _record_method_observation(
        self,
        method_name: str,
        args_snapshot: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        result_snapshot: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        duration_seconds: float,
        learning_type: LearningType = LearningType.PERFORMANCE_OPTIMIZATION,
    ) -> str | None:
        """Persist a generic method execution observation without affecting runtime flow."""
        if not self._learning_enabled:
            return None

        service = self.observation_service
        if service is None:
            return None

        try:
            return cast(
                Optional[str],
                await cast(Any, service).record(  # TODO(TYPE): replace Any with concrete type
                    source=LearningSource.TASK_EXECUTION,
                    learning_type=learning_type,
                    context={
                        "agent_id": getattr(self, "agent_id", None),
                        "agent_type": getattr(getattr(self, "agent_type", None), "value", None)
                        or str(getattr(self, "agent_type", "unknown")),
                        "tenant_id": self._learning_tenant_id,
                        "task_type": method_name,
                    },
                    observation_data={
                        "method_name": method_name,
                        "args": args_snapshot,
                        "result": result_snapshot,
                    },
                    outcome_metrics={
                        "execution_time": duration_seconds,
                        "success": 1.0 if result_snapshot.get("success", True) else 0.0,
                        "error_count": 0.0 if result_snapshot.get("success", True) else 1.0,
                    },
                ),
            )
        except Exception as exc:
            logger.warning(
                "Method learning recording failed for agent %s method %s: %s",
                getattr(self, "agent_id", "unknown"),
                method_name,
                exc,
            )
            return None

    # =======================================================================
    # PHASE 2: Closed Learning Loop - Adaptation Consumption (Decision 6)
    # =======================================================================

    async def get_active_adaptations(
        self,
        task_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get active adaptation rules relevant to current task. Non-blocking.

        This is part of the Closed Learning Loop (Decision 6): agents consume
        learned patterns and adaptation rules during their Orient-fase by
        enriching the LLM system prompt with active adaptations.

        Args:
            task_context: Optional context dict with task_type, etc.

        Returns:
            List of active adaptations as dicts with rule_id, behavior, confidence
        """
        if not self._learning_enabled:
            return []

        service = self.adaptation_service
        if service is None:
            return []

        try:
            # Load rules from DB if not loaded yet
            if hasattr(service, "load_from_db") and callable(
                getattr(service, "load_from_db", None)
            ):
                await cast(
                    # TODO(TYPE): replace Any with concrete type
                    Any,
                    service,  # TODO(TYPE): replace Any with concrete type
                ).load_from_db()  # TODO(TYPE): replace Any with concrete type

            rules = cast(
                Any,  # TODO(TYPE): replace Any with concrete type
                service,  # TODO(TYPE): replace Any with concrete type
            ).get_active_rules()  # TODO(TYPE): replace Any with concrete type
            if task_context:
                # Filter rules by context matching
                rules = [r for r in rules if r.matches_context(task_context)]

            return [
                {
                    "rule_id": r.id,
                    "behavior": r.action if isinstance(r.action, str) else str(r.action),
                    "confidence": getattr(r, "success_rate", 0.5),
                    "name": r.name,
                }
                for r in rules
            ]
        except Exception as exc:
            logger.debug(f"Adaptation fetch failed (non-blocking): {exc}")
            return []

    def format_adaptations_for_prompt(
        self,
        adaptations: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format adaptation rules as context for LLM system prompt.

        Args:
            adaptations: List of adaptation dicts from get_active_adaptations()

        Returns:
            Formatted string for LLM prompt, or empty string if no adaptations
        """
        if not adaptations:
            return ""

        lines = ["Learned optimizations from previous executions:"]
        for a in adaptations[:5]:  # Max 5 to limit prompt size
            behavior = a.get("behavior", "")
            confidence = a.get("confidence", 0.0)
            name = a.get("name", "")
            lines.append(f"- {name}: {behavior} (confidence: {confidence:.0%})")

        return "\n".join(lines)

    async def get_learning_context_for_orient(
        self,
        task_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get full learning context: own adaptations + cross-agent patterns. Non-blocking.

        This extends Phase 2 single-agent adaptation consumption with Phase 5
        cross-agent pattern sharing.

        Args:
            task_context: Optional context dict with task_type, etc.

        Returns:
            Dict with "own_adaptations" and "cross_agent_patterns" lists
        """
        context: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "own_adaptations": [],
            "cross_agent_patterns": [],
        }  # TODO(TYPE): replace Any with concrete type

        if not self._learning_enabled:
            return context

        try:
            # Own adaptations (from Phase 2)
            context["own_adaptations"] = await self.get_active_adaptations(task_context)

            # Cross-agent patterns (Phase 5 extension)
            cross_service = self.cross_agent_service
            if cross_service is not None:
                agent_type = getattr(self, "agent_type", None)
                if agent_type is not None:
                    agent_type_str = getattr(agent_type, "value", None) or str(agent_type)
                    patterns = await cast(
                        # TODO(TYPE): replace Any with concrete type
                        Any,
                        cross_service,  # TODO(TYPE): replace Any with concrete type
                    ).get_related_patterns(  # TODO(TYPE): replace Any with concrete type
                        agent_type=agent_type_str, min_confidence=0.7
                    )
                    context["cross_agent_patterns"] = [
                        {
                            "source_type": p.trigger_conditions.get("source_agent_type"),
                            "behavior": p.learned_behavior,
                            "confidence": p.confidence_score,
                        }
                        for p in patterns[:3]  # Max 3 cross-agent patterns
                    ]
        except Exception as exc:
            logger.debug(f"Learning context fetch failed (non-blocking): {exc}")

        return context

    def format_learning_context_for_prompt(
        self,
        learning_ctx: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format own adaptations + cross-agent patterns for LLM system prompt.

        Args:
            learning_ctx: Dict from get_learning_context_for_orient()

        Returns:
            Formatted string for LLM prompt
        """
        parts: list[str] = []

        # Own adaptations
        own = learning_ctx.get("own_adaptations", [])
        if own:
            parts.append("Learned optimizations from your previous executions:")
            for a in own[:5]:
                confidence = a.get("confidence", 0.0)
                parts.append(f"- {a['behavior']} (confidence: {confidence:.0%})")

        # Cross-agent patterns
        cross = learning_ctx.get("cross_agent_patterns", [])
        if cross:
            parts.append("Insights from related specialist agents:")
            for p in cross[:3]:
                source = p.get("source_type", "unknown")
                confidence = p.get("confidence", 0.0)
                parts.append(f"- From {source}: {p['behavior']} ({confidence:.0%})")

        return "\n".join(parts) if parts else ""
