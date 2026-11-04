"""Partner Recommender - Intelligent agent partner recommendations.

Analyzes collaboration history and current task context to recommend
optimal collaboration partners.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .synapse_network import SynapseNetwork

from src.core.shared.interfaces import TaskData

logger = logging.getLogger("PartnerRecommender")


class PartnerRecommender:
    """Recommends collaboration partners based on task context.

    Uses collaboration history, agent capabilities, and task requirements
    to suggest optimal partners.

    Example:
        recommender = PartnerRecommender(synapse_network)

        recommendation = await recommender.recommend_partner(
            agent_id="code_agent",
            task=task_data,
            available_agents=["architect_agent", "test_agent"]
        )
    """

    def __init__(self, synapse_network: "SynapseNetwork") -> None:
        """Initialize with SynapseNetwork instance."""
        self.network = synapse_network

        # Scoring weights
        self.weights = {
            "historical_success": 0.35,
            "task_relevance": 0.30,
            "availability": 0.20,
            "workload": 0.15,
        }

    async def recommend_partner(
        self,
        agent_id: str,
        task: TaskData,
        available_agents: list[str],
        agent_loads: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Recommend best partner for a task.

        Args:
            agent_id: Agent seeking partner
            task: Task to collaborate on
            available_agents: List[Any] of available agent IDs  # TODO(TYPE): replace Any with concrete type
            agent_loads: Current load of each agent (0.0 - 1.0)

        Returns:
            Recommendation dict with partner_id and score
        """
        agent_loads = agent_loads or {}

        # Get task type from task
        task_type = self._extract_task_type(task)

        # Score each available agent
        scores: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for candidate_id in available_agents:
            if candidate_id == agent_id:
                continue

            score = await self._score_candidate(
                agent_id=agent_id,
                candidate_id=candidate_id,
                task_type=task_type,
                load=agent_loads.get(candidate_id, 0.5),
            )

            scores.append(
                {
                    "agent_id": candidate_id,
                    "score": score,
                    "reasoning": self._generate_reasoning(agent_id, candidate_id, score),
                }
            )

        if not scores:
            return None

        # Sort by score
        scores.sort(key=lambda x: float(x["score"]), reverse=True)

        best = scores[0]
        logger.info(
            f"Recommended partner for {agent_id}: {best['agent_id']} "
            f"(score={best['score']:.2f})"
        )

        return best

    async def recommend_partners_for_swarm(
        self,
        task: TaskData,
        required_capabilities: list[str],
        available_agents: list[str],
        swarm_size: int = 3,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Recommend multiple agents to form a swarm.

        Args:
            task: Mission task
            required_capabilities: Capabilities needed
            available_agents: Pool of available agents
            swarm_size: Desired swarm size

        Returns: List[Any] of recommended agents with roles  # TODO(TYPE): replace Any with concrete type
        """
        task_type = self._extract_task_type(task)

        # Score all candidates
        candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id in available_agents:
            # Get agent's collaboration scores with others
            rankings = await self.network.get_partner_rankings(agent_id, task_type)
            avg_score = (
                sum(r["collaboration_score"] for r in rankings) / len(rankings) if rankings else 0.5
            )

            candidates.append(
                {
                    "agent_id": agent_id,
                    "score": avg_score,
                    "collaborations": len(rankings),
                }
            )

        # Sort by score
        candidates.sort(key=lambda x: float(x["score"]), reverse=True)

        # Select top N with diversity
        selected: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for candidate in candidates[:swarm_size]:
            selected.append(
                {
                    "agent_id": candidate["agent_id"],
                    "role": self._suggest_role(candidate["agent_id"], required_capabilities),
                    "collaboration_score": candidate["score"],
                }
            )

        return selected

    async def analyze_collaboration_health(self, agent_ids: list[str]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze health of collaboration between agents.

        Args:
            agent_ids: List[Any] of agents to analyze  # TODO(TYPE): replace Any with concrete type

        Returns:
            Health analysis dict
        """
        analysis: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "overall_health": "good",
            "agent_pairs": [],
            "recommendations": [],
        }

        weak_synapses = 0
        strong_synapses = 0

        # Analyze each pair
        for i, agent_a in enumerate(agent_ids):
            for agent_b in agent_ids[i + 1 :]:
                synapse_info = await self.network.get_synapse_info(agent_a, agent_b)

                if synapse_info:
                    pair_analysis = {
                        "agents": [agent_a, agent_b],
                        "strength": synapse_info["strength"],
                        "success_rate": synapse_info["success_rate"],
                        "total_collaborations": synapse_info["total_collaborations"],
                    }

                    if synapse_info["strength"] in ["weak", "moderate"]:
                        weak_synapses += 1
                        pair_analysis["recommendation"] = (
                            "Consider more collaborations to strengthen"
                        )
                    else:
                        strong_synapses += 1

                    analysis["agent_pairs"].append(pair_analysis)
                else:
                    weak_synapses += 1
                    analysis["agent_pairs"].append(
                        {
                            "agents": [agent_a, agent_b],
                            "strength": "none",
                            "recommendation": "No collaboration history - start with small tasks",
                        }
                    )

        # Overall health
        total_pairs = len(analysis["agent_pairs"])
        if total_pairs > 0:
            strong_ratio = strong_synapses / total_pairs
            if strong_ratio >= 0.7:
                analysis["overall_health"] = "excellent"
            elif strong_ratio >= 0.4:
                analysis["overall_health"] = "good"
            else:
                analysis["overall_health"] = "needs_improvement"
                analysis["recommendations"].append(
                    "Team needs more collaboration practice. Schedule joint tasks."
                )

        return analysis

    async def _score_candidate(
        self, agent_id: str, candidate_id: str, task_type: str, load: float
    ) -> float:
        """Score a candidate partner."""
        scores: dict[str, float] = {}

        # Historical success score
        synapse_info = await self.network.get_synapse_info(agent_id, candidate_id)
        if synapse_info:
            scores["historical_success"] = synapse_info["collaboration_score"]
        else:
            scores["historical_success"] = 0.3  # Neutral for unknown

        # Task relevance score
        if synapse_info and task_type in synapse_info.get("task_types", []):
            scores["task_relevance"] = 1.0
        else:
            scores["task_relevance"] = 0.5

        # Availability score (inverse of load)
        scores["availability"] = 1.0 - load

        # Workload score (prefer agents with lower load)
        scores["workload"] = 1.0 - (load * 0.5)  # Partial weight

        # Calculate weighted total
        total = sum(scores[category] * self.weights[category] for category in self.weights.keys())

        return float(total)

    def _extract_task_type(self, task: TaskData) -> str:
        """Extract task type from TaskData."""
        if hasattr(task, "title"):
            title_lower = task.title.lower()

            # Simple keyword matching
            if any(kw in title_lower for kw in ["refactor", "clean", "restructure"]):
                return "refactoring"
            elif any(kw in title_lower for kw in ["security", "vulnerability", "patch"]):
                return "security"
            elif any(kw in title_lower for kw in ["performance", "optimize", "speed"]):
                return "performance"
            elif any(kw in title_lower for kw in ["test", "testing", "spec"]):
                return "testing"
            elif any(kw in title_lower for kw in ["design", "architect"]):
                return "design"

        return "general"

    def _generate_reasoning(self, agent_id: str, candidate_id: str, score: float) -> str:
        """Generate human-readable reasoning for recommendation."""
        if score >= 0.8:
            return "Excellent historical collaboration with high success rate"
        elif score >= 0.6:
            return f"Good collaboration history with {candidate_id}"
        elif score >= 0.4:
            return "Moderate collaboration experience, consider for task suitability"
        else:
            return "Limited collaboration history, monitor closely"

    def _suggest_role(self, agent_id: str, capabilities: list[str]) -> str:
        """Suggest a role for an agent in a swarm."""
        # Simple role assignment based on agent name patterns
        agent_lower = agent_id.lower()

        if "architect" in agent_lower or "design" in agent_lower:
            return "lead_designer"
        elif "code" in agent_lower or "dev" in agent_lower:
            return "implementer"
        elif "test" in agent_lower or "qa" in agent_lower:
            return "tester"
        elif "security" in agent_lower:
            return "security_reviewer"
        elif "performance" in agent_lower:
            return "optimizer"
        else:
            return "contributor"
