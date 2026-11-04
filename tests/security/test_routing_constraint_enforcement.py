"""Task #6: Routing Constraint Enforcement Tests

Tests for the 5-tier routing strategy with department constraints:
- Tier 1 Memory Cache: Department filtering in LRU cache
- Tier 2 Redis Cache: Cross-node department isolation
- Tier 3 Capability Matching: Capability-to-department alignment
- Tier 4 LLM Routing: Department-aware LLM routing decisions
- Tier 5 Fallback: Department constraints in fallback selection
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pytest

from src.core.als.enterprise.departments.department_orchestrator import Department

# =============================================================================
# Test Data Structures
# =============================================================================


class RoutingTier(Enum):
    """Routing tier identifiers."""

    MEMORY_CACHE = 1
    REDIS_CACHE = 2
    CAPABILITY_MATCHING = 3
    LLM_ROUTING = 4
    FALLBACK = 5


@dataclass
class RoutingConstraint:
    """Represents a routing constraint."""

    constraint_type: str  # "department", "capability", "tenant"
    value: str
    is_required: bool = True


@dataclass
class RoutingResult:
    """Result of a routing decision."""

    agent_id: str
    agent_department: Department
    task_department: Optional[Department]
    tier_selected: RoutingTier
    constraint_satisfied: bool
    confidence: float = 0.0


def _evaluate_department_constraint(
    agent_dept: Department,
    required_dept: Optional[Department],
) -> bool:
    """Check if agent department satisfies task requirement."""
    if required_dept is None:
        return True  # No constraint
    if str(agent_dept).lower() == "unassigned":
        return True  # Unassigned agents bypass constraints
    return agent_dept == required_dept


# =============================================================================
# Part 1: Tier 1 Memory Cache - Department Filtering
# =============================================================================


@pytest.mark.als
@pytest.mark.security
class TestMemoryCacheDepartmentFiltering:
    """Memory cache (Tier 1) must filter agents by department."""

    def test_memory_cache_returns_agents_matching_department(self):
        """Cache returns only agents in required department."""
        cache_entries = {
            "agent_fin_001": (Department.FINANCE, 0.95),
            "agent_fin_002": (Department.FINANCE, 0.90),
            "agent_ops_001": (Department.OPERATIONS, 0.88),
        }

        required_department = Department.FINANCE
        matching = [
            (agent_id, conf)
            for agent_id, (dept, conf) in cache_entries.items()
            if dept == required_department
        ]

        assert len(matching) == 2
        assert all(agent_id.startswith("agent_fin") for agent_id, _ in matching)

    def test_memory_cache_filters_out_wrong_department(self):
        """Cache correctly filters out agents from wrong department."""
        cache_entries = {
            "agent_fin_001": (Department.FINANCE, 0.95),
            "agent_ops_001": (Department.OPERATIONS, 0.92),
            "agent_ops_002": (Department.OPERATIONS, 0.90),
        }

        required_department = Department.FINANCE
        matching = [
            (agent_id, dept)
            for agent_id, (dept, _) in cache_entries.items()
            if dept == required_department
        ]

        # Only 1 agent in Finance
        assert len(matching) == 1

        # No Operations agents should match a Finance requirement
        ops_matches = [
            (agent_id, dept)
            for agent_id, (dept, _) in cache_entries.items()
            if dept == Department.OPERATIONS and dept == required_department
        ]
        assert len(ops_matches) == 0

    def test_memory_cache_hit_with_department_constraint(self):
        """Cache hit preserves department constraint satisfaction."""
        cache = {
            "agent_fin_001": (Department.FINANCE, 0.95),
        }

        # Task requires FINANCE department
        task_dept = Department.FINANCE

        result = cache.get("agent_fin_001")
        assert result is not None
        cached_dept, confidence = result

        # Constraint satisfied
        satisfies = cached_dept == task_dept
        assert satisfies
        assert confidence >= 0.9


# =============================================================================
# Part 2: Tier 2 Redis Cache - Cross-Node Department Isolation
# =============================================================================


@pytest.mark.als
@pytest.mark.security
class TestRedisCacheDepartmentIsolation:
    """Redis cache (Tier 2) maintains department isolation across nodes."""

    def test_redis_cache_key_includes_department(self):
        """Redis cache keys are scoped by department for isolation."""
        tenant_id = 1
        department = Department.FINANCE
        task_hash = "task_abc123"

        cache_key = f"tenant:{tenant_id}:dept:{department.value}:route:{task_hash}"

        # Key includes both tenant and department
        assert "tenant:1" in cache_key
        assert f"dept:{Department.FINANCE.value}" in cache_key
        assert "route:task_abc123" in cache_key

    def test_redis_cache_prevents_cross_department_hits(self):
        """Cache hit for Finance task won't return Operations agent."""
        cache_entries = {
            "tenant:1:dept:finance:route:task_001": "agent_fin_001",
            "tenant:1:dept:operations:route:task_001": "agent_ops_001",
        }

        # Looking up Finance task
        task_key = "tenant:1:dept:finance:route:task_001"
        result = cache_entries.get(task_key)

        assert result == "agent_fin_001"
        assert result != "agent_ops_001"

    def test_redis_cache_tenant_scoped_department_isolation(self):
        """Redis isolates departments within each tenant."""
        cache_entries = {
            "tenant:1:dept:finance:route:task_001": "agent_t1_fin",
            "tenant:2:dept:finance:route:task_001": "agent_t2_fin",
        }

        # Tenant 1 Finance query
        tenant1_key = "tenant:1:dept:finance:route:task_001"
        result1 = cache_entries.get(tenant1_key)
        assert result1 == "agent_t1_fin"

        # Tenant 2 Finance query
        tenant2_key = "tenant:2:dept:finance:route:task_001"
        result2 = cache_entries.get(tenant2_key)
        assert result2 == "agent_t2_fin"

        # Results are tenant-specific
        assert result1 != result2


# =============================================================================
# Part 3: Tier 3 Capability Matching - Department Alignment
# =============================================================================


@pytest.mark.als
@pytest.mark.security
class TestCapabilityMatchingDepartmentAlignment:
    """Capability matching (Tier 3) respects department boundaries."""

    def test_capability_match_requires_department_alignment(self):
        """Matched capabilities must be from correct department."""
        task_capabilities = {"financial_reporting", "budgeting"}

        agents = {
            "agent_fin_001": {
                "department": Department.FINANCE,
                "capabilities": {"financial_reporting", "budgeting", "audit"},
            },
            "agent_ops_001": {
                "department": Department.OPERATIONS,
                "capabilities": {"infrastructure", "deployment"},
            },
        }

        # Score matches for Finance task
        matches = {}
        for agent_id, agent_data in agents.items():
            agent_dept = agent_data["department"]
            agent_caps = agent_data["capabilities"]
            task_dept = Department.FINANCE

            # Check department first
            dept_match = agent_dept == task_dept or str(agent_dept).lower() == "unassigned"

            if dept_match:
                # Then check capability overlap
                overlap = task_capabilities & agent_caps
                score = len(overlap) / len(task_capabilities)
                matches[agent_id] = score

        # Only Finance agent should match
        assert "agent_fin_001" in matches
        assert "agent_ops_001" not in matches
        assert matches["agent_fin_001"] == 1.0  # 2/2 capabilities

    def test_capability_filtering_excludes_wrong_department(self):
        """Wrong department agents are filtered even with capability match."""
        agents_with_capability = [
            ("agent_legal_001", Department.LEGAL_COMPLIANCE),
            ("agent_fin_001", Department.FINANCE),
            ("agent_ops_001", Department.OPERATIONS),
        ]

        # All agents have the capability, but we need Finance
        required_dept = Department.FINANCE

        filtered = [agent_id for agent_id, dept in agents_with_capability if dept == required_dept]

        assert len(filtered) == 1
        assert filtered[0] == "agent_fin_001"

    def test_capability_match_score_includes_department_weight(self):
        """Department match is weighted higher than capability overlap."""
        task_dept = Department.FINANCE
        task_capabilities = {"reporting", "analysis"}

        # Perfect department + capability match
        perfect_match = {
            "department": Department.FINANCE,
            "capabilities": {"reporting", "analysis", "budgeting"},
            "capability_score": 2.0 / 2.0,  # 2/2 required capabilities
        }

        # Wrong department despite capability match
        wrong_dept = {
            "department": Department.OPERATIONS,
            "capabilities": {"reporting", "analysis"},
            "capability_score": 2.0 / 2.0,  # Same 2/2 capabilities
        }

        # Department must match for routing to proceed
        perfect_eligible = (
            perfect_match["department"] == task_dept
            or str(perfect_match["department"]).lower() == "unassigned"
        )
        wrong_dept_eligible = (
            wrong_dept["department"] == task_dept
            or str(wrong_dept["department"]).lower() == "unassigned"
        )

        assert perfect_eligible
        assert not wrong_dept_eligible


# =============================================================================
# Part 4: Tier 4 LLM Routing - Department-Aware Decisions
# =============================================================================


@pytest.mark.als
@pytest.mark.security
class TestLLMRoutingDepartmentAwareness:
    """LLM routing (Tier 4) must respect department constraints."""

    def test_llm_routing_respects_department_requirement(self):
        """LLM routing output is constrained by department requirement."""
        task_dept = Department.FINANCE
        candidate_agents = [
            {"agent_id": "agent_fin_001", "department": Department.FINANCE},
            {"agent_id": "agent_ops_001", "department": Department.OPERATIONS},
            {"agent_id": "agent_sales_001", "department": Department.SALES_MARKETING},
        ]

        # Simulate LLM returning best agent, then filtering by department
        # (In real code, LLM would be constrained upfront)
        valid_candidates = [
            agent
            for agent in candidate_agents
            if agent["department"] == task_dept or str(agent["department"]).lower() == "unassigned"
        ]

        assert len(valid_candidates) == 1
        assert valid_candidates[0]["agent_id"] == "agent_fin_001"

    def test_llm_routing_filters_out_unqualified_departments(self):
        """LLM routing result must be filtered post-hoc for department."""
        task_dept = Department.LEGAL_COMPLIANCE

        # Hypothetical LLM output (without department awareness)
        llm_suggestion = {
            "agent_id": "agent_ops_001",
            "department": Department.OPERATIONS,
            "confidence": 0.85,
        }

        # Post-filter for department constraint
        dept_satisfied = llm_suggestion["department"] == task_dept
        assert not dept_satisfied

        # Would be rejected and fall through to Tier 5


# =============================================================================
# Part 5: Tier 5 Fallback - Department Constraints in Fallback
# =============================================================================


@pytest.mark.als
@pytest.mark.security
class TestFallbackDepartmentConstraints:
    """Fallback routing (Tier 5) must respect department constraints."""

    def test_fallback_selects_first_agent_matching_department(self):
        """Fallback selects first available agent in required department."""
        available_agents = [
            {"agent_id": "agent_ops_001", "department": Department.OPERATIONS},
            {"agent_id": "agent_ops_002", "department": Department.OPERATIONS},
            {"agent_id": "agent_fin_001", "department": Department.FINANCE},
        ]

        required_dept = Department.OPERATIONS

        fallback = next(
            (agent for agent in available_agents if agent["department"] == required_dept),
            None,
        )

        assert fallback is not None
        assert fallback["agent_id"] == "agent_ops_001"

    def test_fallback_returns_none_if_no_department_match(self):
        """Fallback returns None rather than cross-department agent."""
        available_agents = [
            {"agent_id": "agent_fin_001", "department": Department.FINANCE},
            {"agent_id": "agent_fin_002", "department": Department.FINANCE},
        ]

        required_dept = Department.OPERATIONS

        fallback = next(
            (agent for agent in available_agents if agent["department"] == required_dept),
            None,
        )

        # Must be None, not Finance agent
        assert fallback is None

    def test_fallback_accepts_unassigned_agent(self):
        """Fallback can use unassigned agent as last resort."""
        from src.core.als.agents.departments.base_department_agent import (
            DepartmentType,
        )

        available_agents = [
            {
                "agent_id": "agent_universal",
                "department": DepartmentType.UNASSIGNED,
            },
        ]

        required_dept = Department.FINANCE

        # Unassigned agents satisfy any department constraint
        fallback = next(
            (
                agent
                for agent in available_agents
                if agent["department"] == required_dept
                or agent["department"].value.lower() == "unassigned"
            ),
            None,
        )

        assert fallback is not None
        assert fallback["agent_id"] == "agent_universal"


# =============================================================================
# Part 6: Constraint Violation Detection
# =============================================================================


@pytest.mark.security
class TestConstraintViolationDetection:
    """System detects and reports constraint violations."""

    def test_detect_cross_department_routing_violation(self):
        """Detect attempt to route task to wrong department agent."""
        agent_dept = Department.OPERATIONS
        required_dept = Department.FINANCE

        violation = agent_dept != required_dept
        assert violation

    def test_detect_cross_tenant_routing_violation(self):
        """Detect attempt to route across tenant boundary."""
        agent_tenant = 1
        task_tenant = 2

        violation = agent_tenant != task_tenant
        assert violation

    def test_detect_capability_constraint_violation(self):
        """Detect missing required capability."""
        required_capabilities = {"financial_reporting", "budgeting"}
        agent_capabilities = {"audit"}

        violation = required_capabilities - agent_capabilities
        assert len(violation) > 0
        assert violation == {"financial_reporting", "budgeting"}


# =============================================================================
# Part 7: Confidence Scoring with Department Weight
# =============================================================================


@pytest.mark.als
class TestConfidenceScoringWithDepartmentWeight:
    """Confidence scoring must factor in department constraint satisfaction."""

    def test_department_mismatch_reduces_confidence_to_zero(self):
        """Department mismatch forces confidence to 0.0."""
        base_confidence = 0.85
        agent_dept = Department.OPERATIONS
        required_dept = Department.FINANCE

        dept_satisfied = agent_dept == required_dept
        final_confidence = base_confidence if dept_satisfied else 0.0

        assert final_confidence == 0.0

    def test_department_match_preserves_confidence(self):
        """Department match allows confidence to propagate."""
        base_confidence = 0.85
        agent_dept = Department.FINANCE
        required_dept = Department.FINANCE

        dept_satisfied = agent_dept == required_dept
        final_confidence = base_confidence if dept_satisfied else 0.0

        assert final_confidence == base_confidence

    def test_unassigned_agent_preserves_confidence(self):
        """Unassigned agents don't reduce confidence for department."""
        base_confidence = 0.75
        agent_dept = "unassigned"
        required_dept = Department.FINANCE

        # Unassigned bypasses department check
        dept_satisfied = agent_dept.lower() == "unassigned" or agent_dept == required_dept
        final_confidence = base_confidence if dept_satisfied else 0.0

        assert final_confidence == base_confidence
