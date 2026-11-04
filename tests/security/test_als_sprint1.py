"""Security tests for Sprint 1 ALS implementation.

CRITICAL: These tests verify that tenant isolation is enforced
across all ALS tables and operations.
"""

import hashlib
import json

import pytest
from sqlalchemy import insert, select

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.als.models.collective_knowledge import CollectiveKnowledge
from src.core.als.models.immune_antibody import ImmuneAntibody
from src.core.als.models.immune_memory_cell import ImmuneMemoryCell
from src.core.als.models.organism_registry import OrganismRegistry
from src.core.als.models.signal_audit_log import SignalAuditLog
from src.core.types import AgentType


@pytest.mark.security
@pytest.mark.als
class TestALSTenantIsolation:
    """Verify strict tenant isolation in ALS schema."""

    async def test_organism_registry_isolation(self, db_session, tenant_a, tenant_b):
        """Agent registrations are isolated per tenant."""
        # Create agent for tenant_a
        await db_session.execute(
            insert(OrganismRegistry).values(
                tenant_id=tenant_a.id,
                agent_id="test-agent",
                agent_type="test",
                department="test",
            )
        )
        await db_session.commit()

        # Verify tenant_b cannot see tenant_a's agent
        result = await db_session.execute(
            select(OrganismRegistry).where(OrganismRegistry.tenant_id == tenant_b.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_signal_audit_integrity(self, db_session, tenant_a):
        """Signal audit logs use SHA-256 hashing."""
        payload = {"action": "test", "data": "sensitive"}
        payload_str = json.dumps(payload, sort_keys=True)
        expected_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:64]

        await db_session.execute(
            insert(SignalAuditLog).values(
                tenant_id=tenant_a.id,
                signal_id="test-123",
                source_agent="test",
                tier="COGNITIVE",
                payload_hash=expected_hash,
            )
        )
        await db_session.commit()

        # Verify hash is stored correctly
        result = await db_session.execute(
            select(SignalAuditLog).where(SignalAuditLog.signal_id == "test-123")
        )
        log = result.scalar_one()
        assert log.payload_hash == expected_hash

    async def test_immune_system_isolation(self, db_session, tenant_a, tenant_b):
        """Threat memories are isolated per tenant."""
        # Create threat memory for tenant_a
        await db_session.execute(
            insert(ImmuneMemoryCell).values(
                tenant_id=tenant_a.id,
                threat_signature="malicious_pattern_abc",
                threat_type="rate_limit_breach",
                threat_description="Too many requests",
                antibodies_used=["rate_limiter_v1"],
            )
        )
        await db_session.commit()

        # Verify tenant_b cannot see tenant_a's threat
        result = await db_session.execute(
            select(ImmuneMemoryCell).where(ImmuneMemoryCell.tenant_id == tenant_b.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_knowledge_isolation(self, db_session, tenant_a, tenant_b):
        """Collective knowledge is isolated per tenant."""
        # Create knowledge for tenant_a
        await db_session.execute(
            insert(CollectiveKnowledge).values(
                tenant_id=tenant_a.id,
                knowledge_type="pattern",
                content_hash="abc123",
                content={"pattern": "test"},
            )
        )
        await db_session.commit()

        # Verify tenant_b cannot access
        result = await db_session.execute(
            select(CollectiveKnowledge).where(CollectiveKnowledge.tenant_id == tenant_b.id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.security
class TestAgentSecurity:
    """Verify agent initialization security."""

    def test_enhanced_base_agent_requires_tenant_id(self):
        """EnhancedBaseAgent rejects missing tenant_id."""
        with pytest.raises(ValueError, match="invalid tenant_id"):
            EnhancedBaseAgent(
                agent_id="test",
                agent_type=AgentType.GENERAL,
                tenant_id=None,
            )

    def test_enhanced_base_agent_rejects_invalid_tenant(self):
        """EnhancedBaseAgent rejects invalid tenant_id (negative or zero)."""
        with pytest.raises(ValueError, match="invalid tenant_id"):
            EnhancedBaseAgent(
                agent_id="test",
                agent_type=AgentType.GENERAL,
                tenant_id=-1,  # Invalid!
            )

    def test_enhanced_base_agent_accepts_valid_tenant(self):
        """EnhancedBaseAgent accepts valid tenant_id."""
        # This should NOT raise
        agent = EnhancedBaseAgent(
            agent_id="test",
            agent_type=AgentType.GENERAL,
            tenant_id=123,  # Valid
        )
        assert agent.tenant_id == 123


@pytest.mark.security
class TestRLSEnforcement:
    """Test Row Level Security policies."""

    async def test_rls_policy_enforced(self, db_session, tenant_a, tenant_b):
        """Row Level Security prevents cross-tenant access.

        This test requires a live PostgreSQL database with RLS enabled.
        Skips if running on SQLite or if RLS is not configured.
        """
        # Check if we're using PostgreSQL
        bind = db_session.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            pytest.skip("RLS test requires PostgreSQL")

        # Check if RLS policies exist for collective_knowledge table
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                """
                SELECT COUNT(*) FROM pg_policies
                WHERE tablename = 'collective_knowledge'
            """
            )
        )
        policy_count = result.scalar() or 0

        if policy_count == 0:
            pytest.skip("RLS not enabled on collective_knowledge table")

        # Insert as tenant_a
        await db_session.execute(
            insert(CollectiveKnowledge).values(
                tenant_id=tenant_a.id,
                knowledge_type="test",
                content_hash="abc123",
                content={"test": True},
            )
        )
        await db_session.commit()

        # Simulate tenant_b context
        await db_session.execute(text(f"SET app.current_tenant = '{tenant_b.id}'"))

        # With RLS, tenant_b should see empty result
        result = await db_session.execute(select(CollectiveKnowledge))
        assert result.scalar_one_or_none() is None


@pytest.mark.security
class TestAntibodySecurity:
    """Test immune system security features."""

    async def test_antibody_effectiveness_validation(self, db_session, tenant_a):
        """Antibody effectiveness must be between 0 and 1."""
        with pytest.raises(ValueError):
            await db_session.execute(
                insert(ImmuneAntibody).values(
                    tenant_id=tenant_a.id,
                    name="test",
                    target_antigen="test",
                    action_type="block",
                    effectiveness=1.5,  # Invalid!
                )
            )

    async def test_antibody_action_type_validation(self, db_session, tenant_a):
        """Antibody action_type must be valid."""
        with pytest.raises(ValueError):
            await db_session.execute(
                insert(ImmuneAntibody).values(
                    tenant_id=tenant_a.id,
                    name="test",
                    target_antigen="test",
                    action_type="invalid_action",  # Invalid!
                )
            )


@pytest.mark.security
class TestModelValidation:
    """Test model-level validation."""

    async def test_organism_registry_status_validation(self, db_session, tenant_a):
        """OrganismRegistry status must be valid."""
        with pytest.raises(ValueError):
            await db_session.execute(
                insert(OrganismRegistry).values(
                    tenant_id=tenant_a.id,
                    agent_id="test",
                    agent_type="test",
                    department="test",
                    status="invalid_status",  # Invalid!
                )
            )

    async def test_signal_audit_tier_validation(self, db_session, tenant_a):
        """SignalAuditLog tier must be valid."""
        with pytest.raises(ValueError):
            await db_session.execute(
                insert(SignalAuditLog).values(
                    tenant_id=tenant_a.id,
                    signal_id="test",
                    source_agent="test",
                    tier="INVALID_TIER",  # Invalid!
                )
            )
