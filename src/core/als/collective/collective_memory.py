"""Collective Memory - Shared knowledge system for symbiotic agents.

This module enables agents to share insights, learn from each other's experiences,
and build a collective knowledge base within a tenant.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import and_, desc, select

from src.core.als.models.collective_knowledge import CollectiveKnowledge
from src.core.database.session import get_db_session

logger = logging.getLogger("CollectiveMemory")


class InsightType(str, Enum):
    """Types of insights agents can share."""

    PATTERN = "pattern"  # Code/design patterns
    ANTI_PATTERN = "anti_pattern"  # Things to avoid
    OPTIMIZATION = "optimization"  # Performance improvements
    SECURITY = "security"  # Security vulnerabilities/fixes
    WORKFLOW = "workflow"  # Process improvements
    LESSON = "lesson"  # General lessons learned


class Insight:
    """A single insight shared by an agent.

    Attributes:
        id: Unique identifier (UUID)
        agent_id: Agent that created this insight
        tenant_id: Tenant scope
        insight_type: Category of insight
        context: When is this insight relevant (stored in metadata)
        content: The actual insight content
        confidence: How confident is the agent (0.0 - 1.0)
        success_count: Times this insight led to success (stored in metadata)
        failure_count: Times this insight failed (stored in metadata)
        created_at: When created
        last_reinforced: When last validated (stored in metadata)
        metadata: Additional data
        access_count: How many times retrieved
    """

    def __init__(
        self,
        agent_id: str,
        tenant_id: int,
        insight_type: InsightType,
        context: str,
        content: dict[str, object],
        confidence: float = 0.5,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.insight_type = insight_type
        self.context = context
        self.content = content
        self.confidence = max(0.0, min(1.0, confidence))  # Clamp 0-1
        self.success_count = 0
        self.failure_count = 0
        self.created_at = datetime.now(timezone.utc)
        self.last_reinforced = datetime.now(timezone.utc)
        self.metadata = metadata or {}
        self.access_count = 0

    @property
    def relevance_score(self) -> float:
        """Calculate current relevance based on success rate and recency."""
        total = self.success_count + self.failure_count
        if total == 0:
            success_rate = 0.5  # Neutral for new insights
        else:
            success_rate = self.success_count / total

        # Recency decay - insights lose relevance over time if not reinforced
        days_since_reinforced = (datetime.now(timezone.utc) - self.last_reinforced).days
        recency_factor = max(0.5, 1.0 - (days_since_reinforced / 30))  # Decay over 30 days

        # Access count boost - frequently accessed insights are more relevant
        access_boost = min(0.2, self.access_count / 100)  # Max 0.2 boost

        return (success_rate * recency_factor * self.confidence) + access_boost

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "insight_type": self.insight_type.value,
            "context": self.context,
            "content": self.content,
            "confidence": self.confidence,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_at": self.created_at.isoformat(),
            "last_reinforced": self.last_reinforced.isoformat(),
            "metadata": self.metadata,
            "access_count": self.access_count,
            "relevance_score": self.relevance_score,
        }


class Pattern:
    """A recurring pattern extracted from multiple insights.

    Patterns emerge when similar insights are reinforced multiple times
    across different agents or contexts.
    """

    def __init__(
        self,
        pattern_id: str,
        tenant_id: int,
        pattern_type: InsightType,
        signature: str,  # Unique pattern signature
        description: str,
        supporting_insights: list[str],
        confidence: float,
    ) -> None:
        self.pattern_id = pattern_id
        self.tenant_id = tenant_id
        self.pattern_type = pattern_type
        self.signature = signature
        self.description = description
        self.supporting_insights = supporting_insights
        self.confidence = confidence
        self.created_at = datetime.now(timezone.utc)
        self.occurrence_count = len(supporting_insights)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "pattern_id": self.pattern_id,
            "tenant_id": self.tenant_id,
            "pattern_type": self.pattern_type.value,
            "signature": self.signature,
            "description": self.description,
            "supporting_insights": self.supporting_insights,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "occurrence_count": self.occurrence_count,
        }


class CollectiveMemory:
    """Shared knowledge system for symbiotic agents.

    Enables agents within a tenant to:
    - Share insights from their experiences
    - Query relevant knowledge for their current task
    - Reinforce or deprecate insights based on outcomes
    - Discover patterns across multiple agents

    Example:
        memory = CollectiveMemory(tenant_id=123)

        # Store an insight
        insight = await memory.store_insight(
            agent_id="code_agent_1",
            insight_type=InsightType.PATTERN,
            context="refactoring_legacy_code",
            content={
                "pattern": "extract_method",
                "applies_when": ["long_methods", "duplicate_code"],
                "steps": ["identify_duplication", "extract_to_method", "update_calls"]
            },
            confidence=0.8
        )

        # Query relevant insights
        insights = await memory.query_relevant(
            task_type="refactoring",
            context={"has_duplicate_code": True},
            limit=5
        )
    """

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self._cache: dict[str, Insight] = {}  # In-memory cache
        logger.info(f"CollectiveMemory initialized for tenant {tenant_id}")

    def _generate_content_hash(self, content: dict[str, object], context: str) -> str:
        """Generate hash for deduplication."""
        content_str = f"{context}:{json.dumps(content, sort_keys=True)}"
        return hashlib.sha256(content_str.encode()).hexdigest()

    async def store_insight(
        self,
        agent_id: str,
        insight_type: InsightType,
        context: str,
        content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Insight:
        """Store a new insight in collective memory.

        Args:
            agent_id: Agent sharing the insight
            insight_type: Category of insight
            context: When is this insight relevant
            content: The actual insight content
            confidence: Agent's confidence (0.0 - 1.0)
            metadata: Additional metadata

        Returns:
            The stored Insight object

        Raises:
            ValueError: If insight content is empty or invalid
        """
        if not content:
            raise ValueError("Insight content cannot be empty")

        if not isinstance(insight_type, InsightType):
            raise ValueError(f"Invalid insight type: {insight_type}")

        insight = Insight(
            agent_id=agent_id,
            tenant_id=self.tenant_id,
            insight_type=insight_type,
            context=context,
            content=content,
            confidence=confidence,
            metadata=metadata,
        )

        content_hash = self._generate_content_hash(content, context)

        # Check if similar insight already exists
        existing = await self._find_by_content_hash(content_hash)
        if existing:
            # Merge with existing insight
            logger.info(f"Merging insight with existing {existing.id}")
            await self._merge_insights(existing, insight)
            return existing

        # Prepare metadata with tracking fields
        full_metadata = metadata or {}
        full_metadata.update(
            {
                "context": context,
                "success_count": 0,
                "failure_count": 0,
                "last_reinforced": datetime.now(timezone.utc).isoformat(),
                "original_agent": agent_id,
            }
        )

        # Store in database
        #
        # De tenant wordt expliciet AANGENOMEN (ADR-036 OP-155). `get_db_session()` opent een
        # EIGEN sessie, buiten elk verzoek, dus zonder tenantcontext. `collective_knowledge`
        # heeft sinds `20260915_rls_resterende_tabellen.py` een RLS-policy, en die policy
        # geldt zonder aparte `WITH CHECK` ook voor INSERT. Zonder deze regel werpt deze
        # schrijf na de omschakeling naar `sanskritisetu_app` `new row violates row-level
        # security policy` -- luid, want het is een INSERT, maar hij breekt wel.
        #
        # `self.tenant_id` komt van de aanroeper die deze collectieve-geheugeninstantie
        # heeft gemaakt, nooit uit invoer.
        from src.core.database.bypass_session import adopt_tenant

        async with get_db_session() as session, adopt_tenant(session, self.tenant_id):
            db_id = uuid.UUID(str(insight.id))
            db_knowledge = CollectiveKnowledge(
                id=db_id,
                tenant_id=self.tenant_id,
                knowledge_type=insight_type.value,
                content_hash=content_hash,
                content=content,
                source_agent=agent_id,
                confidence=confidence,
                access_count=0,
                embedding=None,  # Would be generated in production
                embedding_model="all-MiniLM-L6-v2",
                metadata=full_metadata,
            )
            session.add(db_knowledge)
            await session.commit()

        # Cache locally
        self._cache[insight.id] = insight

        logger.info(
            f"Insight stored: {insight.id} by {agent_id}",
            extra={
                "insight_id": insight.id,
                "agent_id": agent_id,
                "insight_type": insight_type.value,
                "tenant_id": self.tenant_id,
            },
        )

        return insight

    async def query_relevant(
        self,
        task_type: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        insight_types: list[InsightType] | None = None,
        min_confidence: float = 0.3,
        limit: int = 10,
    ) -> list[Insight]:
        """Query relevant insights for current task.

        Args:
            task_type: Type of task being performed
            context: Current context for relevance matching
            insight_types: Filter by specific types
            min_confidence: Minimum confidence threshold
            limit: Maximum number of insights to return

        Returns: List[Any] of relevant insights sorted by relevance score  # TODO(TYPE): replace Any with concrete type
        """
        context = context or {}

        async with get_db_session() as session:
            query = select(CollectiveKnowledge).where(
                and_(
                    CollectiveKnowledge.tenant_id == self.tenant_id,
                    CollectiveKnowledge.confidence >= min_confidence,
                )
            )

            # Filter by insight types if specified
            if insight_types:
                type_values = [t.value for t in insight_types]
                query = query.where(CollectiveKnowledge.knowledge_type.in_(type_values))

            # Order by confidence and recency
            query = query.order_by(
                desc(CollectiveKnowledge.confidence),
                desc(CollectiveKnowledge.created_at),
            ).limit(limit * 2)  # Get extra for filtering

            result = await session.execute(query)
            db_insights = result.scalars().all()

        # Convert to Insight objects and calculate relevance
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for db_knowledge in db_insights:
            insight = self._db_to_insight(db_knowledge)

            # Context matching - simple keyword overlap
            if self._context_matches(insight, task_type, context):
                insights.append(insight)

                # Update access count
                await self._increment_access_count(db_knowledge.id)

        # Sort by relevance score
        insights.sort(key=lambda i: i.relevance_score, reverse=True)

        logger.debug(
            f"Queried {len(insights)} relevant insights for task '{task_type}'",
            extra={"task_type": task_type, "tenant_id": self.tenant_id},
        )

        return insights[:limit]

    async def reinforce_success(self, insight_id: str) -> None:
        """Reinforce an insight that led to success.

        Args:
            insight_id: ID of the insight to reinforce

        Raises:
            ValueError: If insight not found
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    and_(
                        CollectiveKnowledge.id == uuid.UUID(insight_id),
                        CollectiveKnowledge.tenant_id == self.tenant_id,
                    )
                )
            )
            db_knowledge = result.scalar_one_or_none()

            if not db_knowledge:
                raise ValueError(f"Insight not found: {insight_id}")

            # Update metadata
            metadata = db_knowledge.metadata or {}
            metadata["success_count"] = metadata.get("success_count", 0) + 1
            metadata["last_reinforced"] = datetime.now(timezone.utc).isoformat()
            db_knowledge.metadata = metadata

            # Increase confidence
            current_confidence = db_knowledge.confidence or 0.0
            db_knowledge.confidence = min(1.0, current_confidence + 0.05)

            await session.commit()

        # Update cache
        if insight_id in self._cache:
            self._cache[insight_id].success_count += 1
            self._cache[insight_id].last_reinforced = datetime.now(timezone.utc)

        logger.debug(f"Insight reinforced: {insight_id}")

    async def report_failure(self, insight_id: str) -> None:
        """Report that an insight led to failure.

        Args:
            insight_id: ID of the insight that failed

        Raises:
            ValueError: If insight not found
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    and_(
                        CollectiveKnowledge.id == uuid.UUID(insight_id),
                        CollectiveKnowledge.tenant_id == self.tenant_id,
                    )
                )
            )
            db_knowledge = result.scalar_one_or_none()

            if not db_knowledge:
                raise ValueError(f"Insight not found: {insight_id}")

            # Update metadata
            metadata = db_knowledge.metadata or {}
            metadata["failure_count"] = metadata.get("failure_count", 0) + 1
            db_knowledge.metadata = metadata

            # Decrease confidence
            current_confidence = db_knowledge.confidence or 0.0
            db_knowledge.confidence = max(0.0, current_confidence - 0.1)

            await session.commit()

        # Update cache
        if insight_id in self._cache:
            self._cache[insight_id].failure_count += 1

        logger.debug(f"Insight marked as failed: {insight_id}")

    async def get_top_insights(
        self, insight_type: InsightType | None = None, limit: int = 10
    ) -> list[Insight]:
        """Get top insights by relevance score.

        Args:
            insight_type: Filter by type
            limit: Maximum number of insights

        Returns: List[Any] of top insights  # TODO(TYPE): replace Any with concrete type
        """
        async with get_db_session() as session:
            query = select(CollectiveKnowledge).where(
                CollectiveKnowledge.tenant_id == self.tenant_id
            )

            if insight_type:
                query = query.where(CollectiveKnowledge.knowledge_type == insight_type.value)

            query = query.order_by(
                desc(CollectiveKnowledge.confidence),
                desc(CollectiveKnowledge.access_count),
            ).limit(limit)

            result = await session.execute(query)
            db_insights = result.scalars().all()

        return [self._db_to_insight(db_k) for db_k in db_insights]

    async def discover_patterns(self) -> list[Pattern]:
        """Discover patterns from multiple related insights.

        Analyzes insights to find recurring themes across agents.

        Returns: List[Any] of discovered patterns  # TODO(TYPE): replace Any with concrete type
        """
        patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        async with get_db_session() as session:
            # Get all insights for this tenant
            result = await session.execute(
                select(CollectiveKnowledge).where(CollectiveKnowledge.tenant_id == self.tenant_id)
            )
            all_insights = result.scalars().all()

        # Group by type and find similar contexts
        insights_by_type: dict[InsightType, list[CollectiveKnowledge]] = {}
        for db_k in all_insights:
            try:
                i_type = InsightType(db_k.knowledge_type)
                insights_by_type.setdefault(i_type, []).append(db_k)
            except ValueError:
                continue  # Skip unknown types

        for insight_type, type_insights in insights_by_type.items():
            if len(type_insights) < 3:  # Need at least 3 for a pattern
                continue

            # Group by context from metadata
            context_groups = self._group_by_context(type_insights)

            for context, insights in context_groups.items():
                if len(insights) >= 3:
                    # Calculate average confidence
                    avg_confidence = sum((i.confidence or 0.0) for i in insights) / len(insights)

                    # Only create pattern if confidence is high enough
                    if avg_confidence >= 0.6:
                        pattern = Pattern(
                            pattern_id=self._generate_pattern_id(context, insight_type),
                            tenant_id=self.tenant_id,
                            pattern_type=insight_type,
                            signature=self._extract_signature(insights),
                            description=f"Pattern in {context}: {len(insights)} similar insights",
                            supporting_insights=[str(i.id) for i in insights],
                            confidence=avg_confidence,
                        )
                        patterns.append(pattern)

        logger.info(f"Discovered {len(patterns)} patterns for tenant {self.tenant_id}")
        return patterns

    # Private helper methods

    async def _find_by_content_hash(self, content_hash: str) -> Insight | None:
        """Check if insight with same content hash exists."""
        async with get_db_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    and_(
                        CollectiveKnowledge.tenant_id == self.tenant_id,
                        CollectiveKnowledge.content_hash == content_hash,
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                return self._db_to_insight(existing)
            return None

    async def _merge_insights(self, existing: Insight, new: Insight) -> None:
        """Merge a new insight with an existing similar one."""
        # Average the confidence
        existing.confidence = (existing.confidence + new.confidence) / 2
        existing.last_reinforced = datetime.now(timezone.utc)

        # Update in database
        async with get_db_session() as session:
            existing_id = uuid.UUID(str(existing.id))
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    CollectiveKnowledge.id == existing_id,
                    CollectiveKnowledge.tenant_id == self.tenant_id,
                )
            )
            db_knowledge = result.scalar_one_or_none()
            if db_knowledge is None:
                return
            db_knowledge.confidence = existing.confidence

            # Update metadata
            metadata = db_knowledge.metadata or {}
            metadata["last_reinforced"] = existing.last_reinforced.isoformat()
            db_knowledge.metadata = metadata

            await session.commit()

    async def _increment_access_count(self, knowledge_id: uuid.UUID) -> None:
        """Increment access count for an insight."""
        async with get_db_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    CollectiveKnowledge.id == knowledge_id,
                    CollectiveKnowledge.tenant_id == self.tenant_id,
                )
            )
            db_knowledge = result.scalar_one_or_none()
            if db_knowledge is None:
                return
            access_count = db_knowledge.access_count or 0
            db_knowledge.access_count = access_count + 1
            db_knowledge.last_accessed = datetime.now(timezone.utc)
            await session.commit()

    def _context_matches(
        self, insight: Insight, task_type: str, context: dict[str, object]
    ) -> bool:
        """Check if insight context matches current task context."""
        # Simple keyword matching - can be enhanced with embeddings
        task_keywords = set(task_type.lower().split("_"))
        context_keywords = {str(v).lower() for v in context.values() if isinstance(v, str)}
        insight_context_keywords = set(insight.context.lower().split("_"))

        all_task_keywords = task_keywords | context_keywords
        overlap = all_task_keywords & insight_context_keywords

        # Consider it a match if there's any overlap or if insight is general
        return len(overlap) > 0 or insight.context == "general"

    def _db_to_insight(self, db_knowledge: CollectiveKnowledge) -> Insight:
        """Convert database model to Insight object."""
        metadata = db_knowledge.metadata or {}

        insight = Insight(
            agent_id=db_knowledge.source_agent or "unknown",
            tenant_id=db_knowledge.tenant_id,
            insight_type=InsightType(db_knowledge.knowledge_type),
            context=metadata.get("context", "general"),
            content=db_knowledge.content,  # type: ignore[arg-type]
            confidence=db_knowledge.confidence or 0.5,
            metadata={
                k: v
                for k, v in metadata.items()
                if k not in ["context", "success_count", "failure_count", "last_reinforced"]
            },
        )
        insight.id = str(db_knowledge.id)
        insight.success_count = metadata.get("success_count", 0)
        insight.failure_count = metadata.get("failure_count", 0)

        # Handle cases where created_at might be None (test fixtures)
        if db_knowledge.created_at:
            insight.created_at = db_knowledge.created_at

        # Handle last_reinforced with fallback
        last_reinforced_str = metadata.get("last_reinforced")
        if last_reinforced_str:
            insight.last_reinforced = datetime.fromisoformat(last_reinforced_str)
        elif db_knowledge.created_at:
            insight.last_reinforced = db_knowledge.created_at

        insight.access_count = db_knowledge.access_count or 0
        return insight

    def _group_by_context(
        self, insights: list[CollectiveKnowledge]
    ) -> dict[str, list[CollectiveKnowledge]]:
        """Group insights by context from metadata."""
        groups: dict[str, list[CollectiveKnowledge]] = {}

        for insight in insights:
            metadata = insight.metadata or {}
            context = metadata.get("context", "general")
            context_key = context.split("_")[0]  # Use first word as key
            groups.setdefault(context_key, []).append(insight)

        return groups

    def _extract_signature(self, insights: list[CollectiveKnowledge]) -> str:
        """Extract a signature from a group of similar insights."""
        if not insights:
            return ""

        # Use first insight's content keys as signature
        first_content = insights[0].content
        if isinstance(first_content, dict):
            return "|".join(sorted(first_content.keys()))
        return str(first_content)[:50]

    def _generate_pattern_id(self, context: str, insight_type: InsightType) -> str:
        """Generate unique pattern ID."""
        content = f"{self.tenant_id}:{context}:{insight_type.value}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
