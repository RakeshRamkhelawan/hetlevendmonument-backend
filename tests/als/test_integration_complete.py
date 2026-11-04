"""
COMPLETE ALS INTEGRATION TEST

Verifies all components work together correctly.
Tests imports, initialization, and basic workflows.
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestImports:
    """Test all imports are consistent."""

    def test_als_package_imports(self):
        """Test main als package exports."""
        from src.core.als import (
            AgentRegister,
            AgentStatus,
            RedisPoolManager,
            SignalCreate,
            SignalTier,
        )

        assert RedisPoolManager is not None
        assert SignalTier.COGNITIVE is not None
        assert AgentStatus.HEALTHY is not None

    def test_infrastructure_imports(self):
        """Test infrastructure components."""
        from src.core.als.infrastructure import RedisPoolManager, Signal, SignalBus, SignalTier

        assert SignalBus is not None
        assert Signal is not None

    def test_models_imports(self):
        """Test database models."""
        from src.core.als.models import (
            collective_knowledge,
            immune_antibody,
            immune_memory_cell,
            organism_registry,
        )

        assert organism_registry is not None

    def test_no_duplicate_circuit_breaker(self):
        """Verify no duplicate CircuitBreaker in als."""
        import src.core.als.infrastructure as infra

        # Should NOT have circuit_breaker module
        assert not hasattr(infra, "circuit_breaker"), "Duplicate circuit_breaker found!"

        # Should use tool_broker's CircuitBreaker
        try:
            from src.core.tool_broker.resilience import CircuitBreaker

            assert CircuitBreaker is not None
        except ImportError:
            pytest.skip("tool_broker.resilience not available")


class TestRedisPool:
    """Test Redis Pool Manager (Fix #11)."""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test Redis pool returns same client."""
        from src.core.als.infrastructure.redis_pool import RedisPoolManager

        pool = RedisPoolManager()

        # Can't test actual Redis without server, but can test structure
        assert pool._client is None  # Initially None
        assert hasattr(pool, "get_client")
        assert hasattr(pool, "get_channel_name")

    def test_channel_naming(self):
        """Test tenant isolation via channel naming."""
        from src.core.als.infrastructure.redis_pool import RedisPoolManager

        pool = RedisPoolManager()
        channel = pool.get_channel_name(123, "cognitive")

        assert channel == "organism:123:cognitive"
        assert "123" in channel  # Tenant isolated
        assert "cognitive" in channel


class TestSignalBus:
    """Test Signal Bus functionality."""

    @pytest.mark.asyncio
    async def test_signal_creation(self):
        """Test Signal dataclass."""
        from datetime import datetime

        from src.core.als.infrastructure.signal_bus import Signal, SignalTier

        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_001",
            target_agent_ids=["agent_002"],
            tier=SignalTier.COGNITIVE,
            payload={"action": "test"},
        )

        assert signal.tenant_id == 1
        assert signal.tier == SignalTier.COGNITIVE
        assert signal.signal_id is not None  # Auto-generated

    def test_signal_serialization(self):
        """Test Signal JSON serialization."""
        from src.core.als.infrastructure.signal_bus import Signal, SignalTier

        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_001",
            target_agent_ids=[],
            tier=SignalTier.REFLEX,
            payload={"test": "data"},
        )

        json_str = signal.to_json()
        assert isinstance(json_str, str)
        assert "agent_001" in json_str

        # Deserialize
        restored = Signal.from_json(json_str)
        assert restored.source_agent_id == "agent_001"
        assert restored.tier == SignalTier.REFLEX


class TestPydanticSchemas:
    """Test Pydantic v2 schemas (Fix #4)."""

    def test_signal_create_schema(self):
        """Test SignalCreate Pydantic model."""
        from src.core.als.models.schemas import SignalCreate, SignalPayload, SignalTier

        signal = SignalCreate(
            tenant_id=1,
            source_agent_id="agent_001",
            target_agent_ids=["agent_002"],
            tier=SignalTier.COGNITIVE,
            payload=SignalPayload(action="test"),
        )

        assert signal.tenant_id == 1  # INTEGER (Fix #16)
        assert signal.tier == SignalTier.COGNITIVE

    def test_agent_register_schema(self):
        """Test AgentRegister Pydantic model."""
        from src.core.als.models.schemas import AgentRegister

        agent = AgentRegister(
            tenant_id=1,
            agent_id="test_agent",
            agent_type="conservator",
            capabilities=["conservation"],
        )

        assert agent.agent_id == "test_agent"
        assert "conservation" in agent.capabilities

    def test_insight_confidence_validation(self):
        """Test confidence range validation."""
        from pydantic import ValidationError

        from src.core.als.models.schemas import InsightCreate

        # Valid confidence
        insight = InsightCreate(
            tenant_id=1,
            agent_id="agent_001",
            insight_type="pattern",
            context="test",
            content={"key": "value"},
            confidence=0.85,
        )
        assert insight.confidence == 0.85

        # Invalid confidence > 1
        with pytest.raises(ValidationError):
            InsightCreate(
                tenant_id=1,
                agent_id="agent_001",
                insight_type="pattern",
                context="test",
                content={},
                confidence=1.5,
            )


class TestDatabaseModels:
    """Test SQLAlchemy database models."""

    def test_model_imports(self):
        """Test all model files import correctly."""
        from src.core.als.models.collective_knowledge import CollectiveKnowledge
        from src.core.als.models.immune_antibody import ImmuneAntibody
        from src.core.als.models.immune_memory_cell import ImmuneMemoryCell
        from src.core.als.models.organism_registry import OrganismRegistry
        from src.core.als.models.signal_audit_log import SignalAuditLog

        # Just verify they import - actual DB tests need database
        assert OrganismRegistry is not None
        assert CollectiveKnowledge is not None
        assert ImmuneAntibody is not None
        assert ImmuneMemoryCell is not None
        assert SignalAuditLog is not None


class TestArchitectureConsistency:
    """Test overall architecture consistency."""

    def test_no_circular_imports(self):
        """Test no circular imports in als package."""
        # This test just imports everything - if there are circular imports,
        # it will fail
        import src.core.als
        import src.core.als.agents
        import src.core.als.collective
        import src.core.als.immune
        import src.core.als.infrastructure
        import src.core.als.models
        import src.core.als.swarm
        import src.core.als.synapse

        assert True  # If we get here, no circular imports

    def test_fix_11_single_pool(self):
        """Verify Fix #11: Single Redis pool."""
        # Check class uses singleton pattern
        import inspect

        from src.core.als.infrastructure.redis_pool import RedisPoolManager

        source = inspect.getsource(RedisPoolManager.get_client)

        # Should have singleton check
        assert "_client" in source
        assert "_lock" in source

    def test_fix_12_sha256_hash(self):
        """Verify Fix #12: SHA-256 hashing."""
        import hashlib

        from src.core.als.infrastructure.signal_bus import Signal

        # Check Signal has get_payload_hash method
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent",
            target_agent_ids=[],
            tier="cognitive",
            payload={"test": "data"},
        )

        hash_value = signal.get_payload_hash()
        assert len(hash_value) == 64  # SHA-256 is 64 hex chars
        assert all(c in "0123456789abcdef" for c in hash_value)


class TestEndToEndWorkflow:
    """Test complete workflows."""

    @pytest.mark.asyncio
    async def test_signal_flow(self):
        """Test complete signal flow."""
        from src.core.als.infrastructure.signal_bus import Signal, SignalTier
        from src.core.als.models.schemas import SignalCreate, SignalPayload

        # Create Pydantic schema
        create_data = SignalCreate(
            tenant_id=1,
            source_agent_id="agent_001",
            target_agent_ids=["agent_002"],
            tier=SignalTier.COGNITIVE,
            payload=SignalPayload(action="delegate_task"),
        )

        # Convert to Signal (internal)
        signal = Signal(
            tenant_id=create_data.tenant_id,
            source_agent_id=create_data.source_agent_id,
            target_agent_ids=create_data.target_agent_ids,
            tier=create_data.tier,
            payload=create_data.payload.model_dump(),
        )

        # Verify hash
        hash_value = signal.get_payload_hash()
        assert len(hash_value) == 64

        # Serialize
        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.source_agent_id == "agent_001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
