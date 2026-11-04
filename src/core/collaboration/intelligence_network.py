#!/usr/bin/env python3
"""
Intelligence Network - M-MDP Distributed Learning and Knowledge Sharing
Advanced distributed intelligence and collective learning system
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    """Types of knowledge in the network"""

    FACTUAL = "factual"
    PROCEDURAL = "procedural"
    EXPERIENTIAL = "experiential"
    STRATEGIC = "strategic"
    PATTERN = "pattern"
    HEURISTIC = "heuristic"


class LearningMode(Enum):
    """Learning modes for intelligence network"""

    SUPERVISED = "supervised"
    UNSUPERVISED = "unsupervised"
    REINFORCEMENT = "reinforcement"
    COLLABORATIVE = "collaborative"
    IMITATION = "imitation"
    DISCOVERY = "discovery"


@dataclass
class KnowledgeNode:
    """Knowledge representation in the network"""

    id: str
    type: KnowledgeType
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence: float
    source_agent: str
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    validation_score: float = 0.0
    tags: set[str] = field(default_factory=set)
    relationships: set[str] = field(default_factory=set)


@dataclass
class LearningExperience:
    """Captured learning experience"""

    id: str
    agent_id: str
    task_context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    actions_taken: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    outcome: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_score: float
    timestamp: datetime
    lessons_learned: list[str] = field(default_factory=list)
    applicable_scenarios: list[str] = field(default_factory=list)


@dataclass
class IntelligencePattern:
    """Discovered intelligence pattern"""

    id: str
    pattern_type: str
    description: str
    triggers: list[str]
    actions: list[str]
    success_rate: float
    confidence: float
    discovered_by: str
    discovered_at: datetime
    usage_count: int = 0


class IntelligenceNetwork:
    """Distributed Intelligence and Learning Network"""

    def __init__(self) -> None:
        self.knowledge_base: dict[str, KnowledgeNode] = {}
        self.learning_experiences: dict[str, LearningExperience] = {}
        self.intelligence_patterns: dict[str, IntelligencePattern] = {}
        self.agent_profiles: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.learning_metrics: dict[str, float] = {}
        self.running = False
        self.learning_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

    async def start_network(self) -> None:
        """Start the intelligence network"""
        if self.running:
            logger.warning("Intelligence network already running")
            return

        self.running = True
        logger.info("Starting M-MDP Intelligence Network")

        # Initialize base knowledge
        await self._initialize_base_knowledge()

        # Start learning processes
        self.learning_task = asyncio.create_task(self._continuous_learning())

        logger.info("Intelligence network started successfully")

    async def stop_network(self) -> None:
        """Stop the intelligence network"""
        self.running = False
        if self.learning_task:
            self.learning_task.cancel()
        logger.info("Intelligence network stopped")

    async def _initialize_base_knowledge(self) -> None:
        """Initialize base knowledge and patterns"""
        # Core system knowledge
        base_knowledge = [
            {
                "id": "system_architecture",
                "type": KnowledgeType.FACTUAL,
                "content": {
                    "description": "M-MDP system architecture principles",
                    "components": [
                        "agent_mesh",
                        "collaboration_engine",
                        "intelligence_network",
                    ],
                    "patterns": [
                        "multi_agent",
                        "distributed_learning",
                        "collaborative_intelligence",
                    ],
                },
                "confidence": 0.95,
                "source_agent": "system_initializer",
                "tags": {"architecture", "system", "core"},
            },
            {
                "id": "collaboration_strategies",
                "type": KnowledgeType.PROCEDURAL,
                "content": {
                    "strategies": {
                        "sequential": "One agent after another",
                        "parallel": "Multiple agents simultaneously",
                        "hierarchical": "Leader-follower structure",
                        "consensus": "Agreement-based collaboration",
                    },
                    "selection_criteria": [
                        "task_complexity",
                        "agent_availability",
                        "time_constraints",
                    ],
                },
                "confidence": 0.89,
                "source_agent": "collaboration_expert",
                "tags": {"collaboration", "strategy", "coordination"},
            },
            {
                "id": "performance_optimization",
                "type": KnowledgeType.HEURISTIC,
                "content": {
                    "optimization_rules": [
                        "Distribute load based on agent capabilities",
                        "Cache frequently accessed data",
                        "Use parallel processing for independent tasks",
                        "Implement fallback strategies for failures",
                    ],
                    "performance_indicators": [
                        "response_time",
                        "throughput",
                        "resource_usage",
                        "error_rate",
                    ],
                },
                "confidence": 0.92,
                "source_agent": "performance_optimizer",
                "tags": {"performance", "optimization", "efficiency"},
            },
        ]

        for knowledge_data in base_knowledge:
            _kd: dict[str, Any] = knowledge_data  # TODO(TYPE): replace Any with concrete type
            knowledge_node = KnowledgeNode(
                id=str(_kd["id"]),
                type=KnowledgeType(_kd["type"]),
                content=dict(_kd["content"]),
                confidence=float(_kd["confidence"]),
                source_agent=str(_kd["source_agent"]),
                created_at=datetime.now(timezone.utc),
                last_accessed=datetime.now(timezone.utc),
                tags=set(_kd["tags"]),
            )
            self.knowledge_base[knowledge_node.id] = knowledge_node

        logger.info(f"Initialized {len(base_knowledge)} base knowledge nodes")

    async def add_knowledge(self, knowledge_data: dict[str, Any], source_agent: str) -> str:  # TODO(TYPE): replace Any with concrete type
        """Add new knowledge to the network"""
        try:
            knowledge_id = str(uuid.uuid4())

            knowledge_node = KnowledgeNode(
                id=knowledge_id,
                type=KnowledgeType(knowledge_data.get("type", "factual")),
                content=knowledge_data.get("content", {}),
                confidence=knowledge_data.get("confidence", 0.5),
                source_agent=source_agent,
                created_at=datetime.now(timezone.utc),
                last_accessed=datetime.now(timezone.utc),
                tags=set(knowledge_data.get("tags", [])),
            )

            self.knowledge_base[knowledge_id] = knowledge_node

            # Link to related knowledge
            await self._link_related_knowledge(knowledge_node)

            logger.info(f"Added knowledge node {knowledge_id} from {source_agent}")
            return knowledge_id

        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            raise

    async def query_knowledge(
        self, query: dict[str, Any], requesting_agent: str  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Query knowledge base"""
        try:
            results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            query_terms = set(query.get("terms", []))
            knowledge_type = query.get("type")
            min_confidence = query.get("min_confidence", 0.0)

            for knowledge_id, knowledge_node in self.knowledge_base.items():
                # Type filter
                if knowledge_type and knowledge_node.type.value != knowledge_type:
                    continue

                # Confidence filter
                if knowledge_node.confidence < min_confidence:
                    continue

                # Term matching
                if query_terms:
                    node_terms = knowledge_node.tags.union(
                        set(str(knowledge_node.content).lower().split())
                    )
                    if not query_terms.intersection(node_terms):
                        continue

                # Update access metrics
                knowledge_node.last_accessed = datetime.now(timezone.utc)
                knowledge_node.access_count += 1

                results.append(
                    {
                        "id": knowledge_node.id,
                        "type": knowledge_node.type.value,
                        "content": knowledge_node.content,
                        "confidence": knowledge_node.confidence,
                        "source": knowledge_node.source_agent,
                        "relevance_score": self._calculate_relevance_score(knowledge_node, query),
                    }
                )

            # Sort by relevance
            results.sort(key=lambda x: x["relevance_score"], reverse=True)

            logger.debug(f"Knowledge query returned {len(results)} results for {requesting_agent}")
            return results

        except Exception as e:
            logger.error(f"Knowledge query failed: {e}")
            return []

    def _calculate_relevance_score(
        self, knowledge_node: KnowledgeNode, query: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate relevance score for knowledge node"""
        score = knowledge_node.confidence * 0.4

        # Tag matching bonus
        query_terms = set(query.get("terms", []))
        if query_terms:
            tag_matches = len(query_terms.intersection(knowledge_node.tags))
            score += (tag_matches / len(query_terms)) * 0.3

        # Recency bonus
        age_days = (datetime.now(timezone.utc) - knowledge_node.created_at).days
        recency_score = max(0, 1 - (age_days / 365))  # Decay over a year
        score += recency_score * 0.2

        # Usage popularity bonus
        usage_score = min(1.0, knowledge_node.access_count / 100)
        score += usage_score * 0.1

        return min(1.0, score)

    async def capture_learning_experience(self, experience_data: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Capture learning experience from agent"""
        try:
            experience_id = str(uuid.uuid4())

            experience = LearningExperience(
                id=experience_id,
                agent_id=experience_data["agent_id"],
                task_context=experience_data.get("task_context", {}),
                actions_taken=experience_data.get("actions_taken", []),
                outcome=experience_data.get("outcome", {}),
                success_score=experience_data.get("success_score", 0.5),
                timestamp=datetime.now(timezone.utc),
                lessons_learned=experience_data.get("lessons_learned", []),
                applicable_scenarios=experience_data.get("applicable_scenarios", []),
            )

            self.learning_experiences[experience_id] = experience

            # Extract patterns from experience
            await self._extract_patterns_from_experience(experience)

            # Update agent profile
            await self._update_agent_profile(experience.agent_id, experience)

            logger.info(f"Captured learning experience {experience_id} from {experience.agent_id}")
            return experience_id

        except Exception as e:
            logger.error(f"Failed to capture learning experience: {e}")
            raise

    async def _extract_patterns_from_experience(self, experience: LearningExperience) -> None:
        """Extract reusable patterns from learning experience"""
        try:
            # Pattern extraction based on successful experiences
            if experience.success_score > 0.7:
                pattern_id = f"pattern_{experience.agent_id}_{int(time.time())}"

                # Extract trigger patterns
                triggers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                context = experience.task_context
                if context.get("task_type"):
                    triggers.append(f"task_type:{context['task_type']}")
                if context.get("complexity"):
                    triggers.append(f"complexity:{context['complexity']}")

                # Extract action patterns
                actions = [action.get("type", "unknown") for action in experience.actions_taken]

                pattern = IntelligencePattern(
                    id=pattern_id,
                    pattern_type="success_pattern",
                    description=f"Successful approach for {context.get('task_type', 'unknown')} tasks",
                    triggers=triggers,
                    actions=actions,
                    success_rate=experience.success_score,
                    confidence=0.6,  # Initial confidence
                    discovered_by=experience.agent_id,
                    discovered_at=datetime.now(timezone.utc),
                )

                self.intelligence_patterns[pattern_id] = pattern
                logger.debug(f"Extracted pattern {pattern_id} from experience")

        except Exception as e:
            logger.error(f"Pattern extraction failed: {e}")

    async def _update_agent_profile(self, agent_id: str, experience: LearningExperience) -> None:
        """Update agent learning profile"""
        if agent_id not in self.agent_profiles:
            self.agent_profiles[agent_id] = {
                "total_experiences": 0,
                "average_success": 0.0,
                "specializations": {},
                "learning_trajectory": [],
                "last_updated": datetime.now(timezone.utc),
            }

        profile = self.agent_profiles[agent_id]

        # Update experience count
        profile["total_experiences"] += 1

        # Update average success
        current_avg = profile["average_success"]
        total_exp = profile["total_experiences"]
        new_avg = ((current_avg * (total_exp - 1)) + experience.success_score) / total_exp
        profile["average_success"] = new_avg

        # Update specializations
        task_type = experience.task_context.get("task_type", "general")
        if task_type not in profile["specializations"]:
            profile["specializations"][task_type] = {"count": 0, "avg_success": 0.0}

        spec = profile["specializations"][task_type]
        spec["count"] += 1
        spec_avg = spec["avg_success"]
        spec_count = spec["count"]
        spec["avg_success"] = (
            (spec_avg * (spec_count - 1)) + experience.success_score
        ) / spec_count

        # Add to learning trajectory
        profile["learning_trajectory"].append(
            {
                "timestamp": experience.timestamp.isoformat(),
                "success_score": experience.success_score,
                "task_type": task_type,
            }
        )

        # Keep only last 100 entries
        if len(profile["learning_trajectory"]) > 100:
            profile["learning_trajectory"] = profile["learning_trajectory"][-100:]

        profile["last_updated"] = datetime.now(timezone.utc)

    async def get_learning_recommendations(self, agent_id: str) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get learning recommendations for specific agent"""
        try:
            recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if agent_id not in self.agent_profiles:
                return [
                    {
                        "type": "exploration",
                        "description": "Explore various task types to build experience",
                        "priority": "high",
                    }
                ]

            profile = self.agent_profiles[agent_id]
            avg_success = profile["average_success"]

            # Recommend improvement areas
            if avg_success < 0.7:
                recommendations.append(
                    {
                        "type": "skill_improvement",
                        "description": "Focus on improving success rate in current specializations",
                        "priority": "high",
                        "target_areas": list(profile["specializations"].keys()),
                    }
                )

            # Recommend new specializations
            all_specializations = set()
            for other_profile in self.agent_profiles.values():
                all_specializations.update(other_profile["specializations"].keys())

            agent_specializations = set(profile["specializations"].keys())
            new_areas = all_specializations - agent_specializations

            if new_areas:
                recommendations.append(
                    {
                        "type": "diversification",
                        "description": "Explore new task types to broaden capabilities",
                        "priority": "medium",
                        "suggested_areas": list(new_areas)[:3],
                    }
                )

            # Recommend collaboration
            high_performers = [
                aid
                for aid, prof in self.agent_profiles.items()
                if prof["average_success"] > 0.8 and aid != agent_id
            ]

            if high_performers:
                recommendations.append(
                    {
                        "type": "collaboration",
                        "description": "Collaborate with high-performing agents",
                        "priority": "medium",
                        "suggested_partners": high_performers[:3],
                    }
                )

            return recommendations

        except Exception as e:
            logger.error(f"Failed to generate learning recommendations: {e}")
            return []

    async def _link_related_knowledge(self, knowledge_node: KnowledgeNode) -> None:
        """Link knowledge node to related nodes"""
        try:
            for existing_id, existing_node in self.knowledge_base.items():
                if existing_id == knowledge_node.id:
                    continue

                # Check for tag overlap
                tag_overlap = len(knowledge_node.tags.intersection(existing_node.tags))
                if tag_overlap > 0:
                    knowledge_node.relationships.add(existing_id)
                    existing_node.relationships.add(knowledge_node.id)

                # Check for content similarity (simplified)
                content_similarity = self._calculate_content_similarity(
                    knowledge_node.content, existing_node.content
                )
                if content_similarity > 0.5:
                    knowledge_node.relationships.add(existing_id)
                    existing_node.relationships.add(knowledge_node.id)

        except Exception as e:
            logger.error(f"Failed to link related knowledge: {e}")

    def _calculate_content_similarity(
        self, content1: dict[str, Any], content2: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate similarity between content objects"""
        try:
            # Simple keyword-based similarity
            text1 = str(content1).lower()
            text2 = str(content2).lower()

            words1 = set(text1.split())
            words2 = set(text2.split())

            if not words1 or not words2:
                return 0.0

            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))

            return intersection / union if union > 0 else 0.0

        except Exception:
            return 0.0

    async def _continuous_learning(self) -> None:
        """Continuous learning and optimization process"""
        while self.running:
            try:
                # Update learning metrics
                await self._update_learning_metrics()

                # Optimize knowledge base
                await self._optimize_knowledge_base()

                # Discover new patterns
                await self._discover_patterns()

                await asyncio.sleep(300)  # Every 5 minutes

            except Exception as e:
                logger.error(f"Continuous learning error: {e}")
                await asyncio.sleep(600)

    async def _update_learning_metrics(self) -> None:
        """Update learning performance metrics"""
        self.learning_metrics = {
            "total_knowledge_nodes": len(self.knowledge_base),
            "total_experiences": len(self.learning_experiences),
            "total_patterns": len(self.intelligence_patterns),
            "active_agents": len(self.agent_profiles),
            "average_knowledge_confidence": (
                sum(node.confidence for node in self.knowledge_base.values())
                / len(self.knowledge_base)
                if self.knowledge_base
                else 0.0
            ),
            "overall_learning_rate": (
                sum(profile["average_success"] for profile in self.agent_profiles.values())
                / len(self.agent_profiles)
                if self.agent_profiles
                else 0.0
            ),
        }

    async def _optimize_knowledge_base(self) -> None:
        """Optimize knowledge base by removing low-value knowledge"""
        current_time = datetime.now(timezone.utc)
        to_remove: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for knowledge_id, knowledge_node in self.knowledge_base.items():
            # Remove low-confidence, unused knowledge older than 30 days
            age_days = (current_time - knowledge_node.created_at).days
            if (
                age_days > 30
                and knowledge_node.confidence < 0.3
                and knowledge_node.access_count < 2
            ):
                to_remove.append(knowledge_id)

        for knowledge_id in to_remove:
            del self.knowledge_base[knowledge_id]

        if to_remove:
            logger.info(f"Optimized knowledge base: removed {len(to_remove)} low-value nodes")

    async def _discover_patterns(self) -> None:
        """Discover new patterns from accumulated experiences"""
        # Group experiences by task type
        task_experiences: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for experience in self.learning_experiences.values():
            task_type = experience.task_context.get("task_type", "unknown")
            if task_type not in task_experiences:
                task_experiences[task_type] = []
            task_experiences[task_type].append(experience)

        # Look for patterns in successful experiences
        for task_type, experiences in task_experiences.items():
            successful_experiences = [exp for exp in experiences if exp.success_score > 0.8]

            if len(successful_experiences) >= 3:  # Need minimum examples
                await self._analyze_success_patterns(task_type, successful_experiences)

    async def _analyze_success_patterns(
        self, task_type: str, experiences: list[LearningExperience]
    ) -> None:
        """Analyze patterns in successful experiences"""
        try:
            # Find common action sequences
            action_sequences: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for experience in experiences:
                sequence = [action.get("type", "unknown") for action in experience.actions_taken]
                action_sequences.append(sequence)

            # Find most common sequence
            from collections import Counter

            sequence_counts = Counter(tuple(seq) for seq in action_sequences)

            if sequence_counts:
                most_common_sequence = sequence_counts.most_common(1)[0]
                if most_common_sequence[1] >= 2:  # Appears at least twice
                    pattern_id = f"success_pattern_{task_type}_{int(time.time())}"

                    pattern = IntelligencePattern(
                        id=pattern_id,
                        pattern_type="success_sequence",
                        description=f"Successful action sequence for {task_type}",
                        triggers=[f"task_type:{task_type}"],
                        actions=list(most_common_sequence[0]),
                        success_rate=sum(exp.success_score for exp in experiences)
                        / len(experiences),
                        confidence=0.7,
                        discovered_by="intelligence_network",
                        discovered_at=datetime.now(timezone.utc),
                    )

                    self.intelligence_patterns[pattern_id] = pattern
                    logger.info(f"Discovered new success pattern: {pattern_id}")

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")

    def get_network_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get intelligence network status"""
        return {
            "network_active": self.running,
            "learning_metrics": self.learning_metrics,
            "knowledge_base_size": len(self.knowledge_base),
            "experience_count": len(self.learning_experiences),
            "pattern_count": len(self.intelligence_patterns),
            "agent_profiles": len(self.agent_profiles),
            "top_patterns": [
                {
                    "id": pattern.id,
                    "type": pattern.pattern_type,
                    "success_rate": pattern.success_rate,
                    "usage_count": pattern.usage_count,
                }
                for pattern in sorted(
                    self.intelligence_patterns.values(),
                    key=lambda p: p.success_rate,
                    reverse=True,
                )[:5]
            ],
        }


# Global intelligence network instance
_intelligence_network: IntelligenceNetwork | None = None


def create_intelligence_network() -> IntelligenceNetwork:
    """Create or get global intelligence network instance"""
    global _intelligence_network
    if _intelligence_network is None:
        _intelligence_network = IntelligenceNetwork()
    return _intelligence_network


def get_intelligence_network() -> IntelligenceNetwork | None:
    """Get global intelligence network instance"""
    return _intelligence_network
