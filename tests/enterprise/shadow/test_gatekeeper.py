"""
Tests for Gatekeeper - Deterministic Policy Enforcement

Sprint C Completion: Gatekeeper with HITL and policy enforcement
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.gatekeeper import (
    GateDecision,
    GateDecisionRecord,
    Gatekeeper,
    HITLRequest,
    PolicyRule,
    RiskCategory,
)
from src.core.als.enterprise.shadow.shadow_ceo import RiskLevel, VetoDecision
from src.core.shared.interfaces import TaskData


def make_task(task_id: str, task_title: str, **kwargs) -> TaskData:
    """Helper to create TaskData with required fields."""
    defaults = {
        "id": task_id,
        "title": task_title,
        "description": f"Description for task {task_id}",
        "payload": {},
        "priority": 1,
    }
    defaults.update(kwargs)
    return TaskData(**defaults)


@pytest.fixture
def gatekeeper():
    """Create a Gatekeeper instance for testing."""
    return Gatekeeper(tenant_id=1)


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return make_task("task-001", "simple_task")


@pytest.fixture
def critical_veto():
    """Create a CRITICAL veto decision."""
    return VetoDecision(
        decision_id="veto-001",
        original_task_id="task-001",
        veto_reason="Critical cascade risk",
        risk_level=RiskLevel.CRITICAL,
        risk_factors=["cascade_risk: 0.9"],
        override_possible=False,
    )


@pytest.fixture
def high_veto_overridable():
    """Create a HIGH veto that can be overridden."""
    return VetoDecision(
        decision_id="veto-002",
        original_task_id="task-002",
        veto_reason="High complexity",
        risk_level=RiskLevel.HIGH,
        risk_factors=["complexity: 0.85"],
        override_possible=True,
        override_requirements=["manual_approval", "risk_acknowledgment"],
    )


class TestGatekeeperInitialization:
    """Test Gatekeeper initialization."""

    def test_initialization(self):
        """Test that Gatekeeper initializes correctly."""
        gk = Gatekeeper(tenant_id=123)

        assert gk.tenant_id == 123
        assert len(gk._decision_log) == 0
        assert len(gk._hitl_requests) == 0
        assert len(gk._policy_rules) > 0  # Default policies initialized

    def test_default_policies_loaded(self, gatekeeper):
        """Test that default policies are loaded."""
        assert "PII_ACCESS" in gatekeeper._policy_rules
        assert "FINANCIAL_OPS" in gatekeeper._policy_rules
        assert "VETO_CRITICAL" in gatekeeper._policy_rules
        assert "CROSS_DEPT" in gatekeeper._policy_rules


class TestRiskCategorization:
    """Test risk categorization."""

    def test_low_risk_task(self, gatekeeper):
        """Test categorization of low-risk tasks."""
        task = make_task("task-001", "simple_query")

        category = gatekeeper._categorize_risk(task, Department.HR)
        assert category == RiskCategory.LOW

    def test_medium_risk_sensitive_department(self, gatekeeper):
        """Test categorization for sensitive departments."""
        task = make_task("task-002", "report_generation")

        category = gatekeeper._categorize_risk(task, Department.FINANCE)
        assert category == RiskCategory.MEDIUM

    def test_high_risk_financial_task(self, gatekeeper):
        """Test categorization of financial tasks."""
        task = make_task("task-003", "process payment")

        category = gatekeeper._categorize_risk(task, Department.FINANCE)
        assert category == RiskCategory.HIGH

    def test_critical_risk_system_task(self, gatekeeper):
        """Test categorization of system-level tasks."""
        task = make_task("task-004", "deploy to production")

        category = gatekeeper._categorize_risk(task, Department.IT_SECURITY)
        assert category == RiskCategory.CRITICAL


class TestShadowCEOVetoProcessing:
    """Test ShadowCEO veto processing."""

    def test_critical_veto_blocks(self, gatekeeper, critical_veto):
        """Test that CRITICAL vetoes always block."""
        decision = gatekeeper._process_shadow_ceo_veto(critical_veto)
        assert decision == GateDecision.BLOCK

    def test_high_veto_requires_hitl(self, gatekeeper, high_veto_overridable):
        """Test that HIGH overridable vetoes require HITL."""
        decision = gatekeeper._process_shadow_ceo_veto(high_veto_overridable)
        assert decision == GateDecision.REQUIRE_HITL

    def test_high_veto_non_overridable_blocks(self, gatekeeper):
        """Test that HIGH non-overridable vetoes block."""
        veto = VetoDecision(
            decision_id="veto-003",
            original_task_id="task-003",
            veto_reason="High risk",
            risk_level=RiskLevel.HIGH,
            risk_factors=["risk"],
            override_possible=False,
        )

        decision = gatekeeper._process_shadow_ceo_veto(veto)
        assert decision == GateDecision.BLOCK

    def test_medium_veto_allows(self, gatekeeper):
        """Test that MEDIUM vetoes don't block."""
        veto = VetoDecision(
            decision_id="veto-004",
            original_task_id="task-004",
            veto_reason="Medium risk",
            risk_level=RiskLevel.MEDIUM,
            risk_factors=["risk"],
        )

        decision = gatekeeper._process_shadow_ceo_veto(veto)
        assert decision == GateDecision.ALLOW


class TestTaskEvaluation:
    """Test task evaluation with Gatekeeper."""

    @pytest.mark.asyncio
    async def test_low_risk_task_allowed(self, gatekeeper):
        """Test that low-risk tasks are allowed."""
        task = make_task("task-001", "simple_query")

        result = await gatekeeper.evaluate_task(task=task, proposed_department=Department.HR)

        assert result.decision == GateDecision.ALLOW
        assert result.risk_category == RiskCategory.LOW
        assert result.task_id == "task-001"
        assert result.tenant_id == 1

    @pytest.mark.asyncio
    async def test_critical_veto_blocks_task(self, gatekeeper, critical_veto):
        """Test that CRITICAL veto blocks task execution."""
        task = make_task("task-veto", "test_task")
        result = await gatekeeper.evaluate_task(
            task=task, proposed_department=Department.HR, shadow_ceo_veto=critical_veto
        )

        assert result.decision == GateDecision.BLOCK
        assert result.shadow_ceo_veto == critical_veto
        assert "VETO_CRITICAL" in result.policy_rules_checked

    @pytest.mark.asyncio
    async def test_high_risk_task_requires_hitl(self, gatekeeper):
        """Test that high-risk tasks require HITL."""
        task = make_task("task-002", "process payment")

        result = await gatekeeper.evaluate_task(
            task=task, proposed_department=Department.FINANCE, context={"amount": 50000}
        )

        assert result.decision == GateDecision.REQUIRE_HITL
        assert result.hitl_required is True
        assert result.hitl_ticket_ref is not None

    @pytest.mark.asyncio
    async def test_pii_access_requires_hitl(self, gatekeeper):
        """Test that PII access requires HITL."""
        task = make_task("task-003", "access pii data")

        result = await gatekeeper.evaluate_task(task=task, proposed_department=Department.HR)

        assert result.decision == GateDecision.REQUIRE_HITL
        assert result.hitl_required is True

    @pytest.mark.asyncio
    async def test_decision_recorded_in_log(self, gatekeeper):
        """Test that decisions are recorded in the log."""
        task = make_task("task-log", "test_task")
        initial_count = len(gatekeeper._decision_log)

        await gatekeeper.evaluate_task(task=task, proposed_department=Department.HR)

        assert len(gatekeeper._decision_log) == initial_count + 1


class TestHITLWorkflow:
    """Test Human-in-the-Loop workflow."""

    @pytest.mark.asyncio
    async def test_hitl_request_created(self, gatekeeper):
        """Test that HITL request is created for high-risk tasks."""
        task = make_task("task-hitl", "process payment")

        result = await gatekeeper.evaluate_task(task=task, proposed_department=Department.FINANCE)

        assert result.hitl_required is True
        assert result.hitl_ticket_ref is not None

        # Verify HITL request was stored
        hitl_requests = gatekeeper.get_hitl_requests_by_task("task-hitl")
        assert len(hitl_requests) > 0
        assert hitl_requests[0].status == "pending"

    def test_approve_hitl_request(self, gatekeeper):
        """Test approving a HITL request."""
        # Create a HITL request
        request = gatekeeper._create_hitl_request(
            task_id="task-001", reason="Test", risk_factors=["test"]
        )
        gatekeeper._hitl_requests[request.request_id] = request

        # Approve it
        result = gatekeeper.approve_hitl_request(
            request_id=request.request_id,
            approved_by="admin_user",
            notes="Approved after review",
        )

        assert result is True
        assert request.status == "approved"
        assert request.approved_by == "admin_user"
        assert request.approved_at is not None

    def test_reject_hitl_request(self, gatekeeper):
        """Test rejecting a HITL request."""
        # Create a HITL request
        request = gatekeeper._create_hitl_request(
            task_id="task-002", reason="Test", risk_factors=["test"]
        )
        gatekeeper._hitl_requests[request.request_id] = request

        # Reject it
        result = gatekeeper.reject_hitl_request(
            request_id=request.request_id,
            rejected_by="admin_user",
            reason="Insufficient justification",
        )

        assert result is True
        assert request.status == "rejected"
        assert request.rejection_reason == "Insufficient justification"

    def test_approve_nonexistent_request_fails(self, gatekeeper):
        """Test that approving non-existent request fails."""
        result = gatekeeper.approve_hitl_request(request_id="nonexistent", approved_by="admin")
        assert result is False

    def test_double_approve_fails(self, gatekeeper):
        """Test that double approval fails."""
        request = gatekeeper._create_hitl_request(
            task_id="task-003", reason="Test", risk_factors=["test"]
        )
        gatekeeper._hitl_requests[request.request_id] = request

        # First approval
        gatekeeper.approve_hitl_request(request.request_id, "admin1")

        # Second approval should fail
        result = gatekeeper.approve_hitl_request(request.request_id, "admin2")
        assert result is False


class TestDecisionLog:
    """Test decision logging."""

    @pytest.mark.asyncio
    async def test_get_decision_log_by_task(self, gatekeeper):
        """Test filtering decision log by task ID."""
        task = make_task("task-log-001", "test")

        await gatekeeper.evaluate_task(task, Department.HR)

        decisions = gatekeeper.get_decision_log(task_id="task-log-001")
        assert len(decisions) == 1
        assert decisions[0].task_id == "task-log-001"

    @pytest.mark.asyncio
    async def test_get_decision_log_by_type(self, gatekeeper):
        """Test filtering decision log by decision type."""
        # Create an allowed decision
        task1 = make_task("task-type-001", "simple")
        await gatekeeper.evaluate_task(task1, Department.HR)

        # Create a blocked decision
        veto = VetoDecision(
            decision_id="veto-001",
            original_task_id="task-type-002",
            veto_reason="Critical",
            risk_level=RiskLevel.CRITICAL,
            risk_factors=["risk"],
            override_possible=False,
        )
        task2 = make_task("task-type-002", "test")
        await gatekeeper.evaluate_task(task2, Department.HR, shadow_ceo_veto=veto)

        allowed_decisions = gatekeeper.get_decision_log(decision_type=GateDecision.ALLOW)
        blocked_decisions = gatekeeper.get_decision_log(decision_type=GateDecision.BLOCK)

        assert len(allowed_decisions) >= 1
        assert len(blocked_decisions) >= 1

    @pytest.mark.asyncio
    async def test_get_decision_log_by_time(self, gatekeeper):
        """Test filtering decision log by time range."""
        task = make_task("task-time-001", "test")
        await gatekeeper.evaluate_task(task, Department.HR)

        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        decisions = gatekeeper.get_decision_log(since=since)

        assert len(decisions) >= 1


class TestDecisionHash:
    """Test tamper-evident decision hashes."""

    def test_decision_hash_computed(self):
        """Test that decision hash is computed correctly."""
        record = GateDecisionRecord(
            decision_id="test-001",
            timestamp=datetime.now(timezone.utc),
            task_id="task-001",
            tenant_id=1,
            decision=GateDecision.ALLOW,
            risk_category=RiskCategory.LOW,
            risk_level=RiskLevel.LOW,
            shadow_ceo_veto=None,
            policy_rules_checked=[],
            policy_rules_failed=[],
            hitl_required=False,
            hitl_ticket_ref=None,
            override_used=False,
            decision_hash="",
        )

        # Compute hash
        record.decision_hash = record.compute_hash()

        assert record.decision_hash is not None
        assert len(record.decision_hash) == 64  # full SHA-256 hexdigest

    def test_decision_hash_deterministic(self):
        """Test that same inputs produce same hash."""
        timestamp = datetime.now(timezone.utc)

        record1 = GateDecisionRecord(
            decision_id="test-001",
            timestamp=timestamp,
            task_id="task-001",
            tenant_id=1,
            decision=GateDecision.ALLOW,
            risk_category=RiskCategory.LOW,
            risk_level=RiskLevel.LOW,
            shadow_ceo_veto=None,
            policy_rules_checked=[],
            policy_rules_failed=[],
            hitl_required=False,
            hitl_ticket_ref=None,
            override_used=False,
            decision_hash="",
        )

        record2 = GateDecisionRecord(
            decision_id="test-001",
            timestamp=timestamp,
            task_id="task-001",
            tenant_id=1,
            decision=GateDecision.ALLOW,
            risk_category=RiskCategory.LOW,
            risk_level=RiskLevel.LOW,
            shadow_ceo_veto=None,
            policy_rules_checked=[],
            policy_rules_failed=[],
            hitl_required=False,
            hitl_ticket_ref=None,
            override_used=False,
            decision_hash="",
        )

        assert record1.compute_hash() == record2.compute_hash()


class TestStatistics:
    """Test statistics collection."""

    @pytest.mark.asyncio
    async def test_statistics_calculation(self, gatekeeper):
        """Test that statistics are calculated correctly."""
        # Create some decisions
        task1 = make_task("task-stats-001", "simple")
        await gatekeeper.evaluate_task(task1, Department.HR)

        veto = VetoDecision(
            decision_id="veto-stats",
            original_task_id="task-stats-002",
            veto_reason="Critical",
            risk_level=RiskLevel.CRITICAL,
            risk_factors=["risk"],
            override_possible=False,
        )
        task2 = make_task("task-stats-002", "test")
        await gatekeeper.evaluate_task(task2, Department.HR, shadow_ceo_veto=veto)

        stats = gatekeeper.get_statistics()

        assert stats["tenant_id"] == 1
        assert stats["total_decisions"] >= 2
        assert stats["allowed"] >= 1
        assert stats["blocked"] >= 1
        assert "policy_rules_active" in stats


class TestPolicyRules:
    """Test policy rule evaluation."""

    def test_policy_rule_enabled(self, gatekeeper):
        """Test that enabled rules are evaluated."""
        rule = gatekeeper._policy_rules["PII_ACCESS"]
        assert rule.enabled is True

    def test_policy_rule_conditions(self, gatekeeper):
        """Test policy rule condition evaluation."""
        rule = PolicyRule(
            rule_id="TEST-001",
            name="Test Rule",
            description="Test",
            risk_categories={RiskCategory.HIGH},
            required_approvals=["manual_approval"],
            conditions={"amount_threshold": 1000},
        )

        task = make_task("task-001", "payment")

        # Below threshold - condition not met
        context_low = {"amount": 500}
        result_low = gatekeeper._evaluate_rule_conditions(rule, task, context_low)
        assert result_low is False

        # Above threshold - condition met
        context_high = {"amount": 1500}
        result_high = gatekeeper._evaluate_rule_conditions(rule, task, context_high)
        assert result_high is True
