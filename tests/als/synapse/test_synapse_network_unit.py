"""Synapse Network Unit Tests - 100% Happy & Unhappy Paths."""

from datetime import datetime

import pytest

from src.core.als.synapse.synapse_network import (
    CollaborationHistory,
    Synapse,
    SynapseNetwork,
    SynapseStrength,
)

# =============================================================================
# CollaborationHistory Happy Path Tests
# =============================================================================


class TestCollaborationHistoryHappyPaths:
    """Happy path tests for CollaborationHistory."""

    def test_collaboration_creation(self):
        """HAPPY: Create collaboration record."""
        collab = CollaborationHistory(
            agent_a_id="agent_1",
            agent_b_id="agent_2",
            tenant_id=10001,
            task_type="refactoring",
            success=True,
            execution_time=2.5,
            quality_score=0.9,
        )

        assert collab.agent_a_id == "agent_1"
        assert collab.agent_b_id == "agent_2"
        assert collab.success is True
        assert collab.quality_score == 0.9
        assert collab.id is not None

    def test_collaboration_creation_reversed_order(self):
        """HAPPY: Agent order is normalized."""
        collab1 = CollaborationHistory(
            agent_a_id="agent_b",
            agent_b_id="agent_a",
            tenant_id=10001,
            task_type="test",
            success=True,
        )

        collab2 = CollaborationHistory(
            agent_a_id="agent_a",
            agent_b_id="agent_b",
            tenant_id=10001,
            task_type="test",
            success=True,
        )

        # Both should have same ordering
        assert collab1.agent_a_id == collab2.agent_a_id
        assert collab1.agent_b_id == collab2.agent_b_id

    def test_collaboration_quality_clamping(self):
        """HAPPY: Quality score is clamped to 0-1."""
        collab_high = CollaborationHistory(
            agent_a_id="a",
            agent_b_id="b",
            tenant_id=10001,
            task_type="test",
            success=True,
            quality_score=1.5,
        )
        assert collab_high.quality_score == 1.0

        collab_low = CollaborationHistory(
            agent_a_id="a",
            agent_b_id="b",
            tenant_id=10001,
            task_type="test",
            success=True,
            quality_score=-0.5,
        )
        assert collab_low.quality_score == 0.0

    def test_collaboration_to_dict(self):
        """HAPPY: Convert to dictionary."""
        collab = CollaborationHistory(
            agent_a_id="agent_1",
            agent_b_id="agent_2",
            tenant_id=10001,
            task_type="refactoring",
            success=True,
            execution_time=2.5,
            quality_score=0.9,
        )

        data = collab.to_dict()

        assert data["agent_a_id"] == "agent_1"
        assert data["success"] is True
        assert "timestamp" in data


# =============================================================================
# Synapse Happy Path Tests
# =============================================================================


class TestSynapseHappyPaths:
    """Happy path tests for Synapse."""

    def test_synapse_creation(self):
        """HAPPY: Create synapse between agents."""
        synapse = Synapse(agent_a_id="agent_1", agent_b_id="agent_2", tenant_id=10001)

        assert synapse.agent_a_id == "agent_1"
        assert synapse.agent_b_id == "agent_2"
        assert synapse.total_collaborations == 0
        assert synapse.strength == SynapseStrength.WEAK

    def test_synapse_agent_ordering(self):
        """HAPPY: Agents are ordered consistently."""
        synapse1 = Synapse("b", "a", 10001)
        synapse2 = Synapse("a", "b", 10001)

        assert synapse1.agent_a_id == synapse2.agent_a_id
        assert synapse1.agent_b_id == synapse2.agent_b_id

    def test_synapse_record_collaboration_success(self):
        """HAPPY: Record successful collaboration."""
        synapse = Synapse("agent_1", "agent_2", 10001)

        collab = CollaborationHistory(
            "agent_1",
            "agent_2",
            10001,
            "refactoring",
            True,
            execution_time=2.0,
            quality_score=0.9,
        )

        synapse.record_collaboration(collab)

        assert synapse.total_collaborations == 1
        assert synapse.successful_collaborations == 1
        assert synapse.success_rate == 1.0
        assert "refactoring" in synapse.task_types

    def test_synapse_record_multiple_collaborations(self):
        """HAPPY: Record multiple collaborations."""
        synapse = Synapse("agent_1", "agent_2", 10001)

        # Record successful collaborations
        for i in range(5):
            collab = CollaborationHistory(
                "agent_1",
                "agent_2",
                10001,
                "refactoring",
                True,
                execution_time=2.0,
                quality_score=0.8,
            )
            synapse.record_collaboration(collab)

        assert synapse.total_collaborations == 5
        assert synapse.successful_collaborations == 5
        assert synapse.strength == SynapseStrength.EXCELLENT

    def test_synapse_strength_progression(self):
        """HAPPY: Synapse strength increases with success."""
        synapse = Synapse("agent_1", "agent_2", 10001)

        # Start weak
        assert synapse.strength == SynapseStrength.WEAK

        # Build up - should progress through strength levels
        for i in range(10):
            collab = CollaborationHistory(
                "agent_1",
                "agent_2",
                10001,
                "test",
                True,
                execution_time=2.0,
                quality_score=0.95,
            )
            synapse.record_collaboration(collab)

        # Should reach at least MODERATE with good performance
        assert synapse.strength in [
            SynapseStrength.MODERATE,
            SynapseStrength.STRONG,
            SynapseStrength.EXCELLENT,
        ]

    def test_synapse_collaboration_score(self):
        """HAPPY: Calculate collaboration score."""
        synapse = Synapse("agent_1", "agent_2", 10001)

        # Add successful collaboration
        collab = CollaborationHistory(
            "agent_1",
            "agent_2",
            10001,
            "test",
            True,
            execution_time=2.0,
            quality_score=0.9,
        )
        synapse.record_collaboration(collab)

        score = synapse.collaboration_score
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be good with success

    def test_synapse_to_dict(self):
        """HAPPY: Convert synapse to dict."""
        synapse = Synapse("agent_1", "agent_2", 10001)

        data = synapse.to_dict()

        assert data["agent_a_id"] == "agent_1"
        assert data["strength"] == "weak"
        assert "collaboration_score" in data


# =============================================================================
# SynapseNetwork Happy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSynapseNetworkHappyPaths:
    """Happy path tests for SynapseNetwork."""

    @pytest.fixture
    def network(self):
        """Create SynapseNetwork instance."""
        return SynapseNetwork(tenant_id=10001)

    async def test_record_collaboration(self, network):
        """HAPPY: Record collaboration between agents."""
        collab = await network.record_collaboration(
            agent_a_id="agent_1",
            agent_b_id="agent_2",
            task_type="refactoring",
            success=True,
            execution_time=2.5,
            quality_score=0.9,
        )

        assert collab.success is True
        assert collab.task_type == "refactoring"

        # Verify synapse was created
        synapse_info = await network.get_synapse_info("agent_1", "agent_2")
        assert synapse_info is not None
        assert synapse_info["total_collaborations"] == 1

    async def test_find_best_partner(self, network):
        """HAPPY: Find best collaboration partner."""
        # Create collaboration history
        await network.record_collaboration(
            "agent_1", "agent_2", "refactoring", True, quality_score=0.9
        )
        await network.record_collaboration(
            "agent_1", "agent_3", "refactoring", True, quality_score=0.6
        )

        # Find best partner
        best = await network.find_best_partner("agent_1")

        assert best == "agent_2"  # Higher quality score

    async def test_find_partner_with_task_filter(self, network):
        """HAPPY: Filter partners by task type."""
        await network.record_collaboration(
            "agent_1", "agent_2", "refactoring", True, quality_score=0.9
        )
        await network.record_collaboration(
            "agent_1", "agent_3", "security", True, quality_score=0.9
        )

        # Find partner for refactoring
        partner = await network.find_best_partner("agent_1", task_type="refactoring")

        assert partner == "agent_2"

    async def test_get_partner_rankings(self, network):
        """HAPPY: Get ranked list of partners."""
        # Create multiple collaborations
        for i in range(3):
            await network.record_collaboration(
                "agent_1", f"agent_{i+2}", "test", True, quality_score=0.5 + (i * 0.2)
            )

        rankings = await network.get_partner_rankings("agent_1")

        assert len(rankings) == 3
        # Should be sorted by score
        assert rankings[0]["collaboration_score"] >= rankings[1]["collaboration_score"]

    async def test_discover_collaboration_clusters(self, network):
        """HAPPY: Discover agent clusters."""
        # Create a cluster of agents that work well together
        agents = ["agent_a", "agent_b", "agent_c"]
        for i, a1 in enumerate(agents):
            for a2 in agents[i + 1 :]:
                for _ in range(5):  # Multiple collaborations
                    await network.record_collaboration(a1, a2, "design", True, quality_score=0.9)

        clusters = await network.discover_collaboration_clusters()

        assert isinstance(clusters, list)
        if clusters:
            assert clusters[0]["size"] >= 3

    async def test_get_network_stats(self, network):
        """HAPPY: Get network statistics."""
        # Create some collaborations
        await network.record_collaboration("a", "b", "test", True, quality_score=0.8)
        await network.record_collaboration("b", "c", "test", True, quality_score=0.7)

        stats = await network.get_network_stats()

        assert stats["total_synapses"] == 2
        assert stats["total_agents"] == 3
        assert stats["average_success_rate"] == 1.0


# =============================================================================
# SynapseNetwork Unhappy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSynapseNetworkUnhappyPaths:
    """Unhappy path tests for SynapseNetwork."""

    @pytest.fixture
    def network(self):
        """Create SynapseNetwork instance."""
        return SynapseNetwork(tenant_id=10001)

    async def test_record_self_collaboration(self, network):
        """UNHAPPY: Cannot record collaboration with self."""
        with pytest.raises(ValueError, match="Cannot record collaboration with self"):
            await network.record_collaboration(
                agent_a_id="agent_1",
                agent_b_id="agent_1",
                task_type="test",
                success=True,
            )

    async def test_find_partner_no_history(self, network):
        """UNHAPPY: No partner found without history."""
        partner = await network.find_best_partner("lonely_agent")

        assert partner is None

    async def test_find_partner_excluded(self, network):
        """UNHAPPY: Excluded agents not returned."""
        await network.record_collaboration("agent_1", "agent_2", "test", True)

        partner = await network.find_best_partner("agent_1", exclude_agents=["agent_2"])

        assert partner is None

    async def test_get_synapse_info_no_history(self, network):
        """UNHAPPY: Returns None for unknown synapse."""
        info = await network.get_synapse_info("unknown_a", "unknown_b")

        assert info is None

    async def test_find_partner_min_strength_filter(self, network):
        """UNHAPPY: Minimum strength filtering works."""
        # Single collaboration = WEAK strength
        await network.record_collaboration("agent_1", "agent_2", "test", True)

        # Require STRONG strength
        partner = await network.find_best_partner("agent_1", min_strength=SynapseStrength.STRONG)

        assert partner is None  # Too weak


# =============================================================================
# Synapse Strength Tests
# =============================================================================


class TestSynapseStrengthLevels:
    """Tests for synapse strength levels."""

    def test_strength_enum_values(self):
        """HAPPY: Strength enum has correct values."""
        assert SynapseStrength.WEAK.value == "weak"
        assert SynapseStrength.MODERATE.value == "moderate"
        assert SynapseStrength.STRONG.value == "strong"
        assert SynapseStrength.EXCELLENT.value == "excellent"

    def test_strength_progression_logic(self):
        """HAPPY: Strength progresses correctly."""
        synapse = Synapse("a", "b", 10001)

        # Add collaborations to progress strength
        for i in range(10):
            collab = CollaborationHistory(
                "a", "b", 10001, "test", True, execution_time=2.0, quality_score=0.95
            )
            synapse.record_collaboration(collab)

        assert synapse.strength == SynapseStrength.EXCELLENT

    def test_weak_synapses_with_failures(self):
        """HAPPY: Failures keep synapse weak."""
        synapse = Synapse("a", "b", 10001)

        # Add failed collaborations
        for i in range(5):
            collab = CollaborationHistory("a", "b", 10001, "test", False, quality_score=0.3)
            synapse.record_collaboration(collab)

        assert synapse.strength == SynapseStrength.WEAK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
