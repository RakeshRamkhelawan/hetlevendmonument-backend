"""Cross-agent learning services for sharing patterns between related agents."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from src.core.agents.learning_loop import LearningPattern
from src.core.als.synapse.synapse_network import SynapseNetwork
from src.core.shared.learning_audit import log_learning_audit_event
from src.core.learning.metrics import record_learning_cross_agent_share
from src.core.learning.services.pattern_service import PatternService
from src.core.shared.config import get_feature_flag

logger = logging.getLogger(__name__)

_TENANT_SYNAPSE_NETWORKS: dict[int, SynapseNetwork] = {}


def get_tenant_synapse_network(tenant_id: int) -> SynapseNetwork:
    """Return a process-local synapse network shared per tenant."""
    if tenant_id not in _TENANT_SYNAPSE_NETWORKS:
        _TENANT_SYNAPSE_NETWORKS[tenant_id] = SynapseNetwork(tenant_id=tenant_id)
    return _TENANT_SYNAPSE_NETWORKS[tenant_id]


DEFAULT_AGENT_RELATIONS: dict[str, set[str]] = {
    "python_pro": {"ai_engineer", "data_scientist", "ml_engineer"},
    "ai_engineer": {"python_pro", "data_scientist", "ml_engineer"},
    "data_scientist": {"python_pro", "ai_engineer", "ml_engineer"},
    "ml_engineer": {"python_pro", "ai_engineer", "data_scientist"},
    "javascript_pro": {"typescript_pro", "fastapi_pro"},
    "typescript_pro": {"javascript_pro", "fastapi_pro"},
    "fastapi_pro": {"javascript_pro", "typescript_pro"},
    "cloud_architect": {"kubernetes_architect", "terraform_specialist"},
    "kubernetes_architect": {"cloud_architect", "terraform_specialist"},
    "terraform_specialist": {"cloud_architect", "kubernetes_architect"},
    "hr_pro": {"legal_advisor", "finance_pro"},
    "legal_advisor": {"hr_pro", "finance_pro"},
    "finance_pro": {"hr_pro", "legal_advisor"},
}


class CrossAgentLearningService:
    """Shares high-confidence patterns across related agents within a tenant."""

    def __init__(
        self,
        tenant_id: int,
        pattern_service: PatternService | None = None,
        synapse_network: SynapseNetwork | None = None,
        min_confidence: float = 0.7,
        relations_map: dict[str, set[str]] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.pattern_service = pattern_service or PatternService(tenant_id=tenant_id)
        self.synapse_network = synapse_network or get_tenant_synapse_network(tenant_id)
        self.min_confidence = min_confidence
        self._relations_map = relations_map or DEFAULT_AGENT_RELATIONS
        self._db_loaded = False

    @staticmethod
    def _normalize_agent_type(agent_type: str | None) -> str:
        return (agent_type or "").strip().lower()

    def get_related_agent_types(self, agent_type: str | None) -> list[str]:
        """Return related agent types using the Phase 5 bidirectional map."""
        normalized = self._normalize_agent_type(agent_type)
        if not normalized:
            return []

        direct = set(self._relations_map.get(normalized, set()))
        reverse = {
            source for source, targets in self._relations_map.items() if normalized in targets
        }
        return sorted(direct | reverse)

    async def _get_dynamic_related_agent_types(
        self,
        agent_type: str | None,
        task_type: str | None = None,
    ) -> list[str]:
        """Return related agent types learned dynamically from ALS synapses."""
        normalized = self._normalize_agent_type(agent_type)
        if not normalized or self.synapse_network is None:
            return []

        try:
            rankings = await self.synapse_network.get_partner_rankings(
                normalized, task_type=task_type
            )
        except Exception as exc:
            logger.warning("Failed to get dynamic synapse partners for %s: %s", normalized, exc)
            return []

        dynamic = {
            self._normalize_agent_type(item.get("agent_id"))
            for item in rankings
            if item.get("agent_id")
        }
        dynamic.discard("")
        dynamic.discard(normalized)
        return sorted(dynamic)

    async def share_pattern(
        self,
        pattern: LearningPattern,
        source_agent_type: str | None,
    ) -> list[LearningPattern]:
        """Share a high-confidence pattern with related agent types."""
        if not get_feature_flag("learning_enabled"):
            return []

        if pattern.confidence_score < self.min_confidence:
            return []

        normalized_source = self._normalize_agent_type(source_agent_type)
        related_types = sorted(
            set(self.get_related_agent_types(normalized_source))
            | set(
                await self._get_dynamic_related_agent_types(
                    normalized_source,
                    task_type=pattern.trigger_conditions.get("task_type"),
                )
            )
        )
        if not related_types:
            return []

        shared_patterns: list[LearningPattern] = []
        for related_type in related_types:
            try:
                trigger_conditions = dict(pattern.trigger_conditions)
                trigger_conditions["agent_type"] = related_type
                trigger_conditions["shared_from_agent_type"] = normalized_source
                trigger_conditions["shared_pattern"] = True

                learned_behavior = dict(pattern.learned_behavior)
                learned_behavior["shared_from_agent_type"] = normalized_source
                learned_behavior["shared_for_agent_type"] = related_type
                learned_behavior["shared_pattern"] = True

                shared = await self.pattern_service.register(
                    pattern_type=pattern.pattern_type,
                    trigger_conditions=trigger_conditions,
                    learned_behavior=learned_behavior,
                    observation_count=pattern.observation_count,
                    success_rate=pattern.success_rate,
                    confidence_score=pattern.confidence_score,
                )
                shared_patterns.append(shared)
                record_learning_cross_agent_share(self.tenant_id, normalized_source, related_type)
                await log_learning_audit_event(
                    action="learning.cross_agent_shared",
                    tenant_id=self.tenant_id,
                    resource=f"pattern:{pattern.id}",
                    details={
                        "source_agent_type": normalized_source,
                        "target_agent_type": related_type,
                    },
                )

                if self.synapse_network is not None and normalized_source:
                    await self.synapse_network.record_collaboration(
                        agent_a_id=normalized_source,
                        agent_b_id=related_type,
                        task_type=trigger_conditions.get("task_type") or "cross_agent_learning",
                        success=pattern.success_rate >= 0.5,
                        quality_score=pattern.confidence_score,
                        metadata={"pattern_id": pattern.id, "shared": True},
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to share pattern %s from %s to %s: %s",
                    pattern.id,
                    normalized_source,
                    related_type,
                    exc,
                )

        return shared_patterns

    async def get_related_patterns(
        self,
        agent_type: str | None,
        task_type: str | None = None,
        min_confidence: float | None = None,
    ) -> list[LearningPattern]:
        """Return high-confidence patterns relevant to related agent types."""
        if self.pattern_service._repository is not None and not self._db_loaded:
            await self.pattern_service.load_from_db()
            self._db_loaded = True

        threshold = min_confidence if min_confidence is not None else self.min_confidence
        normalized_agent_type = self._normalize_agent_type(agent_type)
        related_types = set(self.get_related_agent_types(agent_type))
        related_types.update(await self._get_dynamic_related_agent_types(agent_type, task_type))
        if normalized_agent_type:
            related_types.add(normalized_agent_type)
        if not related_types:
            return []

        patterns = self.pattern_service.get_patterns_by_agent_type(None)
        relevant: list[LearningPattern] = []
        for pattern in patterns:
            pattern_agent_type = self._normalize_agent_type(
                pattern.trigger_conditions.get("agent_type")
            )
            if pattern_agent_type not in related_types:
                continue
            if pattern.confidence_score < threshold:
                continue
            if task_type and pattern.trigger_conditions.get("task_type") not in {None, task_type}:
                continue
            relevant.append(pattern)

        relevant.sort(key=lambda item: item.confidence_score, reverse=True)
        return relevant
