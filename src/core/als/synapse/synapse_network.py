"""Synapse Network - Dynamic agent collaboration network.

This module tracks collaboration success between agents and helps
find optimal collaboration partners based on historical performance.
"""

import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional



logger = logging.getLogger("SynapseNetwork")


class SynapseStrength(str, Enum):
    """Strength levels of agent synapses (connections)."""

    WEAK = "weak"  # New or unsuccessful collaborations
    MODERATE = "moderate"  # Some successful collaborations
    STRONG = "strong"  # Consistently successful
    EXCELLENT = "excellent"  # Highly successful, preferred partners


class CollaborationHistory:
    """Record of a collaboration between two agents.

    Attributes:
        id: Unique record ID
        agent_a_id: First agent
        agent_b_id: Second agent
        tenant_id: Tenant scope
        task_type: Type of task collaborated on
        success: Whether collaboration succeeded
        execution_time: How long the collaboration took
        quality_score: Quality of collaboration (0-1)
        timestamp: When collaboration occurred
        metadata: Additional collaboration data
    """

    def __init__(
        self,
        agent_a_id: str,
        agent_b_id: str,
        tenant_id: int,
        task_type: str,
        success: bool,
        execution_time: float = 0.0,
        quality_score: float = 0.5,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        # Ensure consistent ordering for ID generation
        agents = sorted([agent_a_id, agent_b_id])
        self.id = self._generate_id(agents[0], agents[1], task_type, datetime.now(timezone.utc))
        self.agent_a_id = agents[0]
        self.agent_b_id = agents[1]
        self.tenant_id = tenant_id
        self.task_type = task_type
        self.success = success
        self.execution_time = execution_time
        self.quality_score = max(0.0, min(1.0, quality_score))
        self.timestamp = datetime.now(timezone.utc)
        self.metadata = metadata or {}

    def _generate_id(self, agent_a: str, agent_b: str, task_type: str, timestamp: datetime) -> str:
        """Generate unique ID for collaboration record."""
        content = f"{agent_a}:{agent_b}:{task_type}:{timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "id": self.id,
            "agent_a_id": self.agent_a_id,
            "agent_b_id": self.agent_b_id,
            "tenant_id": self.tenant_id,
            "task_type": self.task_type,
            "success": self.success,
            "execution_time": self.execution_time,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class Synapse:
    """A connection (synapse) between two agents.

    Tracks the strength of collaboration relationship based on
    historical performance and success rates.
    """

    def __init__(self, agent_a_id: str, agent_b_id: str, tenant_id: int) -> None:
        # Consistent ordering
        agents = sorted([agent_a_id, agent_b_id])
        self.agent_a_id = agents[0]
        self.agent_b_id = agents[1]
        self.tenant_id = tenant_id

        self.total_collaborations = 0
        self.successful_collaborations = 0
        self.total_execution_time = 0.0
        self.average_quality = 0.5
        self.strength = SynapseStrength.WEAK
        self.last_collaboration: datetime | None = None
        self.task_types: set[str] = set()

        # Scoring weights
        self.success_weight = 0.4
        self.quality_weight = 0.3
        self.speed_weight = 0.2
        self.recency_weight = 0.1

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_collaborations == 0:
            return 0.5  # Neutral for new synapses
        return self.successful_collaborations / self.total_collaborations

    @property
    def collaboration_score(self) -> float:
        """Calculate overall collaboration score (0-1)."""
        # Success rate component
        success_component = self.success_rate * self.success_weight

        # Quality component
        quality_component = self.average_quality * self.quality_weight

        # Speed component (faster is better, normalize to 0-1)
        speed_score = 1.0  # Default
        if self.total_collaborations > 0 and self.total_execution_time > 0:
            avg_time = self.total_execution_time / self.total_collaborations
            # Assume 5 seconds is fast (1.0), 60 seconds is slow (0.0)
            speed_score = max(0.0, 1.0 - (avg_time / 60))
        speed_component = speed_score * self.speed_weight

        # Recency component
        recency_score = 0.5  # Default neutral
        if self.last_collaboration:
            days_since = (datetime.now(timezone.utc) - self.last_collaboration).days
            # Decay over 30 days
            recency_score = max(0.0, 1.0 - (days_since / 30))
        recency_component = recency_score * self.recency_weight

        total_score = success_component + quality_component + speed_component + recency_component
        return min(1.0, max(0.0, total_score))

    def update_strength(self) -> None:
        """Update synapse strength based on collaboration history."""
        score = self.collaboration_score

        if score >= 0.85 and self.total_collaborations >= 5:
            self.strength = SynapseStrength.EXCELLENT
        elif score >= 0.7 and self.total_collaborations >= 3:
            self.strength = SynapseStrength.STRONG
        elif score >= 0.5 and self.total_collaborations >= 2:
            self.strength = SynapseStrength.MODERATE
        else:
            self.strength = SynapseStrength.WEAK

    def record_collaboration(self, history: CollaborationHistory) -> None:
        """Record a new collaboration in this synapse."""
        self.total_collaborations += 1

        if history.success:
            self.successful_collaborations += 1

        self.total_execution_time += history.execution_time

        # Update rolling average quality
        self.average_quality = (
            self.average_quality * (self.total_collaborations - 1) + history.quality_score
        ) / self.total_collaborations

        self.last_collaboration = history.timestamp
        self.task_types.add(history.task_type)

        # Update strength
        self.update_strength()

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "agent_a_id": self.agent_a_id,
            "agent_b_id": self.agent_b_id,
            "tenant_id": self.tenant_id,
            "total_collaborations": self.total_collaborations,
            "successful_collaborations": self.successful_collaborations,
            "success_rate": self.success_rate,
            "average_quality": self.average_quality,
            "collaboration_score": self.collaboration_score,
            "strength": self.strength.value,
            "task_types": list(self.task_types),
            "last_collaboration": (
                self.last_collaboration.isoformat() if self.last_collaboration else None
            ),
        }


class SynapseNetwork:
    """Network of agent synapses for collaboration optimization.

    Tracks all collaborations between agents and provides recommendations
    for optimal collaboration partners based on historical performance.

    Example:
        network = SynapseNetwork(tenant_id=123)

        # Record collaboration
        await network.record_collaboration(
            agent_a_id="architect_agent",
            agent_b_id="code_agent",
            task_type="refactoring",
            success=True,
            quality_score=0.9
        )

        # Find best partner
        partner = await network.find_best_partner(
            agent_id="architect_agent",
            task_type="refactoring"
        )
    """

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self._synapses: dict[str, Synapse] = {}  # In-memory cache
        logger.info(f"SynapseNetwork initialized for tenant {tenant_id}")

    def _get_synapse_key(self, agent_a: str, agent_b: str) -> str:
        """Generate consistent key for synapse lookup."""
        agents = sorted([agent_a, agent_b])
        return f"{agents[0]}:{agents[1]}"

    async def record_collaboration(
        self,
        agent_a_id: str,
        agent_b_id: str,
        task_type: str,
        success: bool,
        execution_time: float = 0.0,
        quality_score: float = 0.5,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> CollaborationHistory:
        """Record a collaboration between two agents.

        Args:
            agent_a_id: First agent
            agent_b_id: Second agent
            task_type: Type of task
            success: Whether collaboration succeeded
            execution_time: Time taken
            quality_score: Quality rating (0-1)
            metadata: Additional data

        Returns:
            CollaborationHistory record
        """
        if agent_a_id == agent_b_id:
            raise ValueError("Cannot record collaboration with self")

        # Create history record
        history = CollaborationHistory(
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            tenant_id=self.tenant_id,
            task_type=task_type,
            success=success,
            execution_time=execution_time,
            quality_score=quality_score,
            metadata=metadata,
        )

        # Get or create synapse
        synapse_key = self._get_synapse_key(agent_a_id, agent_b_id)

        if synapse_key not in self._synapses:
            self._synapses[synapse_key] = Synapse(
                agent_a_id=agent_a_id, agent_b_id=agent_b_id, tenant_id=self.tenant_id
            )

        # Update synapse
        self._synapses[synapse_key].record_collaboration(history)

        logger.debug(
            f"Collaboration recorded: {agent_a_id} <-> {agent_b_id} "
            f"(success={success}, strength={self._synapses[synapse_key].strength.value})"
        )

        return history

    async def find_best_partner(
        self,
        agent_id: str,
        task_type: str | None = None,
        min_strength: SynapseStrength = SynapseStrength.WEAK,
        exclude_agents: list[str] | None = None,
    ) -> str | None:
        """Find best collaboration partner for an agent.

        Args:
            agent_id: Agent seeking partner
            task_type: Optional task type filter
            min_strength: Minimum synapse strength
            exclude_agents: Agents to exclude

        Returns:
            Best partner agent ID or None
        """
        exclude_agents = exclude_agents or []
        candidates: list[tuple[str, float, SynapseStrength]] = []
        for synapse_key, synapse in self._synapses.items():
            # Check if this synapse involves the agent
            if agent_id not in [synapse.agent_a_id, synapse.agent_b_id]:
                continue

            # Get partner ID
            partner_id = (
                synapse.agent_b_id if synapse.agent_a_id == agent_id else synapse.agent_a_id
            )

            # Skip excluded agents
            if partner_id in exclude_agents:
                continue

            # Check minimum strength
            strength_levels = {
                SynapseStrength.WEAK: 0,
                SynapseStrength.MODERATE: 1,
                SynapseStrength.STRONG: 2,
                SynapseStrength.EXCELLENT: 3,
            }

            if strength_levels[synapse.strength] < strength_levels[min_strength]:
                continue

            # Check task type compatibility if specified
            if task_type and task_type not in synapse.task_types:
                continue

            # Calculate score
            score = synapse.collaboration_score

            # Boost for task type match
            if task_type and task_type in synapse.task_types:
                score += 0.1

            candidates.append((partner_id, score, synapse.strength))

        if not candidates:
            return None

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        best_partner = candidates[0][0]
        logger.debug(
            f"Best partner for {agent_id}: {best_partner} "
            f"(score={candidates[0][1]:.2f}, strength={candidates[0][2].value})"
        )

        return best_partner

    async def get_partner_rankings(
        self, agent_id: str, task_type: str | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get ranked list of all potential partners.

        Args:
            agent_id: Agent seeking partners
            task_type: Optional task type filter

        Returns: List[Any] of partner info dicts sorted by score  # TODO(TYPE): replace Any with concrete type
        """
        partners: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for synapse_key, synapse in self._synapses.items():
            if agent_id not in [synapse.agent_a_id, synapse.agent_b_id]:
                continue

            partner_id = (
                synapse.agent_b_id if synapse.agent_a_id == agent_id else synapse.agent_a_id
            )

            # Filter by task type if specified
            if task_type and task_type not in synapse.task_types:
                continue

            partners.append(
                {
                    "agent_id": partner_id,
                    "collaboration_score": synapse.collaboration_score,
                    "success_rate": synapse.success_rate,
                    "total_collaborations": synapse.total_collaborations,
                    "synapse_strength": synapse.strength.value,
                    "task_types": list(synapse.task_types),
                    "last_collaboration": (
                        synapse.last_collaboration.isoformat()
                        if synapse.last_collaboration
                        else None
                    ),
                }
            )

        # Sort by collaboration score
        partners.sort(key=lambda x: float(x["collaboration_score"]), reverse=True)

        return partners

    async def get_synapse_info(self, agent_a_id: str, agent_b_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get synapse information between two agents.

        Args:
            agent_a_id: First agent
            agent_b_id: Second agent

        Returns:
            Synapse info dict or None if no collaboration history
        """
        synapse_key = self._get_synapse_key(agent_a_id, agent_b_id)
        synapse = self._synapses.get(synapse_key)

        if not synapse:
            return None

        return synapse.to_dict()

    async def discover_collaboration_clusters(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Discover clusters of agents that work well together.

        Returns: List[Any] of collaboration clusters  # TODO(TYPE): replace Any with concrete type
        """
        clusters: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        processed_agents: set[str] = set()

        for synapse_key, synapse in self._synapses.items():
            # Only consider strong synapses
            if synapse.strength not in [
                SynapseStrength.STRONG,
                SynapseStrength.EXCELLENT,
            ]:
                continue

            # Check if either agent already in a cluster
            if synapse.agent_a_id in processed_agents or synapse.agent_b_id in processed_agents:
                continue

            # Find all agents connected to this synapse
            cluster_agents = self._find_connected_agents(
                synapse.agent_a_id, min_strength=SynapseStrength.STRONG
            )

            if len(cluster_agents) >= 3:
                clusters.append(
                    {
                        "agents": list(cluster_agents),
                        "size": len(cluster_agents),
                        "common_task_types": list(synapse.task_types),
                        "average_score": synapse.collaboration_score,
                    }
                )
                processed_agents.update(cluster_agents)

        return clusters

    def _find_connected_agents(
        self, start_agent: str, min_strength: SynapseStrength = SynapseStrength.MODERATE
    ) -> set[str]:
        """Find all agents connected to start_agent via strong synapses."""
        connected = {start_agent}
        to_process = {start_agent}
        processed = set()

        strength_levels = {
            SynapseStrength.WEAK: 0,
            SynapseStrength.MODERATE: 1,
            SynapseStrength.STRONG: 2,
            SynapseStrength.EXCELLENT: 3,
        }
        min_level = strength_levels[min_strength]

        while to_process:
            current = to_process.pop()
            if current in processed:
                continue
            processed.add(current)

            # Find all agents connected to current
            for synapse in self._synapses.values():
                if current not in [synapse.agent_a_id, synapse.agent_b_id]:
                    continue

                if strength_levels[synapse.strength] < min_level:
                    continue

                partner = (
                    synapse.agent_b_id if synapse.agent_a_id == current else synapse.agent_a_id
                )
                if partner not in processed:
                    connected.add(partner)
                    to_process.add(partner)

        return connected

    async def get_network_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get statistics about the collaboration network.

        Returns:
            Network statistics dict
        """
        if not self._synapses:
            return {
                "total_synapses": 0,
                "total_agents": 0,
                "average_success_rate": 0.0,
                "synapse_strength_distribution": {},
            }

        total_collaborations = sum(s.total_collaborations for s in self._synapses.values())
        total_successes = sum(s.successful_collaborations for s in self._synapses.values())

        # Count agents
        all_agents: set[str] = set()
        for synapse in self._synapses.values():
            all_agents.add(synapse.agent_a_id)
            all_agents.add(synapse.agent_b_id)

        # Strength distribution
        strength_counts = {
            SynapseStrength.WEAK.value: 0,
            SynapseStrength.MODERATE.value: 0,
            SynapseStrength.STRONG.value: 0,
            SynapseStrength.EXCELLENT.value: 0,
        }
        for synapse in self._synapses.values():
            strength_counts[synapse.strength.value] += 1

        return {
            "total_synapses": len(self._synapses),
            "total_agents": len(all_agents),
            "total_collaborations": total_collaborations,
            "average_success_rate": (
                total_successes / total_collaborations if total_collaborations > 0 else 0.0
            ),
            "synapse_strength_distribution": strength_counts,
        }
