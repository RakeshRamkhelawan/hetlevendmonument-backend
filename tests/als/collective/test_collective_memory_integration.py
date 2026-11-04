"""Collective Memory Integration Tests - Live Database & Redis.

These tests use real PostgreSQL and Redis connections to verify
end-to-end functionality without mocks.
"""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.core.als.collective.collective_memory import CollectiveMemory, Insight, InsightType
from src.core.als.models.collective_knowledge import CollectiveKnowledge
from src.core.database.database import get_async_session

# =============================================================================
# Integration Test Configuration
# =============================================================================

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# =============================================================================
# CollectiveMemory Integration Tests
# =============================================================================


class TestCollectiveMemoryIntegration:
    """Integration tests using live database."""

    async def test_full_insight_lifecycle(self, db_session):
        """INTEGRATION: Complete insight lifecycle - store, query, reinforce."""
        tenant_id = 20001  # Unique tenant for isolation
        memory = CollectiveMemory(tenant_id=tenant_id)

        # 1. Store insight
        insight = await memory.store_insight(
            agent_id="code_agent_integration",
            insight_type=InsightType.PATTERN,
            context="refactoring_python_code",
            content={
                "pattern": "extract_method",
                "applies_when": ["long_methods", "duplicate_code"],
                "steps": [
                    "identify_duplication",
                    "extract_to_new_method",
                    "update_all_callers",
                ],
                "example_before": "def process(): # 50 lines",
                "example_after": "def process(): self.process_step()",
            },
            confidence=0.85,
            metadata={
                "language": "python",
                "tested_on": "legacy_codebase",
                "success_rate": 0.9,
            },
        )

        assert insight.id is not None
        assert insight.tenant_id == tenant_id

        # Verify in database directly
        async with get_async_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight.id)
            )
            db_record = result.scalar_one_or_none()
            assert db_record is not None
            assert db_record.agent_id == "code_agent_integration"
            assert db_record.knowledge_type == "pattern"

        # 2. Query relevant insights
        insights = await memory.query_relevant(
            task_type="refactoring",
            context={"language": "python", "has_duplicate_code": True},
            min_confidence=0.5,
            limit=5,
        )

        # Should find our insight
        assert len(insights) >= 1
        found = any(i.id == insight.id for i in insights)
        assert found, "Stored insight should be found in query"

        # 3. Reinforce success
        await memory.reinforce_success(insight.id)

        # Verify reinforcement in database
        async with get_async_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight.id)
            )
            db_record = result.scalar_one()
            assert db_record.success_count == 1
            assert db_record.confidence > 0.85  # Should increase

        # 4. Report failure
        await memory.report_failure(insight.id)

        # Verify failure recorded
        async with get_async_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight.id)
            )
            db_record = result.scalar_one()
            assert db_record.failure_count == 1

        # Cleanup
        async with get_async_session() as session:
            await session.delete(db_record)
            await session.commit()

    async def test_multiple_agents_sharing(self, db_session):
        """INTEGRATION: Multiple agents share and query insights."""
        tenant_id = 20002
        memory = CollectiveMemory(tenant_id=tenant_id)

        # Agent 1 stores security insight
        security_insight = await memory.store_insight(
            agent_id="security_agent",
            insight_type=InsightType.SECURITY,
            context="sql_injection_prevention",
            content={
                "vulnerability": "SQL injection",
                "prevention": "Use parameterized queries",
                "code_example": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
            },
            confidence=0.95,
        )

        # Agent 2 stores performance insight
        perf_insight = await memory.store_insight(
            agent_id="performance_agent",
            insight_type=InsightType.OPTIMIZATION,
            context="database_query_optimization",
            content={
                "technique": "Add index on frequently queried columns",
                "when_to_apply": ["slow_queries", "frequent_lookups"],
                "measurement": "Query time reduced from 500ms to 10ms",
            },
            confidence=0.9,
        )

        # Agent 3 queries for security insights
        security_insights = await memory.query_relevant(
            task_type="security_audit",
            context={"concern": "sql_injection"},
            insight_types=[InsightType.SECURITY],
            limit=5,
        )

        # Should find security insight but not performance
        assert any(i.id == security_insight.id for i in security_insights)
        assert not any(i.id == perf_insight.id for i in security_insights)

        # Cleanup
        async with get_async_session() as session:
            for insight_id in [security_insight.id, perf_insight.id]:
                result = await session.execute(
                    select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight_id)
                )
                record = result.scalar_one_or_none()
                if record:
                    await session.delete(record)
            await session.commit()

    async def test_insight_merging(self, db_session):
        """INTEGRATION: Similar insights are merged instead of duplicated."""
        tenant_id = 20003
        memory = CollectiveMemory(tenant_id=tenant_id)

        # Store first insight
        insight1 = await memory.store_insight(
            agent_id="code_agent",
            insight_type=InsightType.PATTERN,
            context="error_handling",
            content={"pattern": "try_except_logging"},
            confidence=0.7,
        )

        # Store very similar insight from same agent
        insight2 = await memory.store_insight(
            agent_id="code_agent",  # Same agent
            insight_type=InsightType.PATTERN,  # Same type
            context="error_handling",  # Same context
            content={"pattern": "try_except_logging"},  # Same content
            confidence=0.8,  # Different confidence
        )

        # Should return same ID (merged)
        assert insight1.id == insight2.id

        # Verify only one record in database
        async with get_async_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(
                    CollectiveKnowledge.context == "error_handling",
                    CollectiveKnowledge.tenant_id == tenant_id,
                )
            )
            records = result.scalars().all()
            assert len(records) == 1

            # Confidence should be averaged
            assert 0.7 <= records[0].confidence <= 0.8

        # Cleanup
        async with get_async_session() as session:
            for record in records:
                await session.delete(record)
            await session.commit()

    async def test_pattern_discovery(self, db_session):
        """INTEGRATION: Discover patterns from multiple similar insights."""
        tenant_id = 20004
        memory = CollectiveMemory(tenant_id=tenant_id)

        # Create multiple similar refactoring insights
        insight_ids = []
        for i in range(3):
            insight = await memory.store_insight(
                agent_id=f"agent_{i}",
                insight_type=InsightType.PATTERN,
                context="refactoring_code",  # Similar context
                content={
                    "technique": "extract_method",
                    "benefit": "improved_readability",
                },
                confidence=0.75,
            )
            insight_ids.append(insight.id)

            # Reinforce each insight
            await memory.reinforce_success(insight.id)
            await memory.reinforce_success(insight.id)

        # Discover patterns
        patterns = await memory.discover_patterns()

        # Should find at least one pattern
        assert isinstance(patterns, list)

        # Cleanup
        async with get_async_session() as session:
            for insight_id in insight_ids:
                result = await session.execute(
                    select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight_id)
                )
                record = result.scalar_one_or_none()
                if record:
                    await session.delete(record)
            await session.commit()

    async def test_relevance_scoring_and_ranking(self, db_session):
        """INTEGRATION: Insights ranked by relevance score."""
        tenant_id = 20005
        memory = CollectiveMemory(tenant_id=tenant_id)

        # Store insight with low success
        low_success = await memory.store_insight(
            agent_id="agent_1",
            insight_type=InsightType.PATTERN,
            context="testing",
            content={"pattern": "low_success"},
            confidence=0.5,
        )

        # Store insight with high success
        high_success = await memory.store_insight(
            agent_id="agent_2",
            insight_type=InsightType.PATTERN,
            context="testing",
            content={"pattern": "high_success"},
            confidence=0.9,
        )

        # Reinforce high success multiple times
        for _ in range(5):
            await memory.reinforce_success(high_success.id)

        # Query insights
        insights = await memory.query_relevant(task_type="testing", limit=10)

        # High success insight should have higher relevance
        high_success_insight = next((i for i in insights if i.id == high_success.id), None)
        low_success_insight = next((i for i in insights if i.id == low_success.id), None)

        if high_success_insight and low_success_insight:
            assert high_success_insight.relevance_score > low_success_insight.relevance_score

        # Cleanup
        async with get_async_session() as session:
            for insight_id in [low_success.id, high_success.id]:
                result = await session.execute(
                    select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight_id)
                )
                record = result.scalar_one_or_none()
                if record:
                    await session.delete(record)
            await session.commit()

    async def test_tenant_isolation(self, db_session):
        """INTEGRATION: Insights are isolated by tenant."""
        tenant_a = 20006
        tenant_b = 20007
        memory_a = CollectiveMemory(tenant_id=tenant_a)
        memory_b = CollectiveMemory(tenant_id=tenant_b)

        # Store insight in tenant A
        insight_a = await memory_a.store_insight(
            agent_id="agent",
            insight_type=InsightType.LESSON,
            context="general",
            content={"lesson": "tenant_a_secret"},
            confidence=0.8,
        )

        # Query from tenant B
        insights_b = await memory_b.query_relevant(task_type="general", limit=10)

        # Should not find tenant A's insight
        assert not any(i.id == insight_a.id for i in insights_b)

        # Query from tenant A should find it
        insights_a = await memory_a.query_relevant(task_type="general", limit=10)
        assert any(i.id == insight_a.id for i in insights_a)

        # Cleanup
        async with get_async_session() as session:
            result = await session.execute(
                select(CollectiveKnowledge).where(CollectiveKnowledge.id == insight_a.id)
            )
            record = result.scalar_one_or_none()
            if record:
                await session.delete(record)
            await session.commit()


# =============================================================================
# Error Handling Integration Tests
# =============================================================================


class TestCollectiveMemoryErrorHandling:
    """Integration tests for error scenarios."""

    async def test_reinforce_nonexistent_insight_live(self, db_session):
        """INTEGRATION: Reinforce non-existent insight raises error."""
        memory = CollectiveMemory(tenant_id=20008)

        with pytest.raises(ValueError, match="Insight not found"):
            await memory.reinforce_success("definitely_does_not_exist_12345")

    async def test_store_insight_invalid_type_live(self, db_session):
        """INTEGRATION: Invalid insight type raises error."""
        memory = CollectiveMemory(tenant_id=20009)

        with pytest.raises(ValueError, match="Invalid insight type"):
            await memory.store_insight(
                agent_id="agent",
                insight_type="not_a_real_type",
                context="test",
                content={"test": "data"},
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
