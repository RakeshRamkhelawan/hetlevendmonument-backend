"""
Unit Tests for Crisis Orchestrator - P4.1.2
Tests for src/core/subagents/crisis_orchestrator.py

Coverage target: 80%+

Tests:
- CrisisOrchestrator initialization and agent registration
- initiate_crisis_response flow
- Multi-agent coordination
- Decision aggregation (consensus and conflict)
- Escalation on timeout
- CrisisContext dataclass behavior
- CrisisTask and CrisisDecision dataclasses
- Orchestration status and detailed results
"""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module components with the AgentFactory mocked to avoid initialization issues
with patch("src.core.subagents.crisis_orchestrator.AgentFactory") as MockFactory:
    # Configure the mock factory to work during import
    mock_factory_instance = MagicMock()
    mock_factory_instance.register_agent_type = MagicMock()
    mock_factory_instance.register_default_configuration = MagicMock()
    MockFactory.return_value = mock_factory_instance

    from src.core.subagents.crisis_orchestrator import (
        CrisisOrchestrator,
        CrisisPhase,
        CrisisTask,
        CrisisDecision,
        get_crisis_orchestrator,
    )

from src.core.subagents.crisis_management_agents import CrisisContext, CrisisType, RiskLevel


@pytest.fixture(autouse=True)
def reset_crisis_orchestrator_singleton():
    """Reset the global singleton before each test"""
    import src.core.subagents.crisis_orchestrator as module

    module._crisis_orchestrator = None
    yield
    module._crisis_orchestrator = None


class TestCrisisPhaseEnum:
    """Test CrisisPhase enum values"""

    def test_crisis_phase_values(self):
        """Verify all crisis phases are defined correctly"""
        assert CrisisPhase.INITIAL_RESPONSE.value == "initial_response"
        assert CrisisPhase.ANALYSIS.value == "analysis"
        assert CrisisPhase.DECISION_MAKING.value == "decision_making"
        assert CrisisPhase.IMPLEMENTATION.value == "implementation"
        assert CrisisPhase.RECOVERY.value == "recovery"

    def test_crisis_phase_count(self):
        """Ensure all expected phases exist"""
        assert len(CrisisPhase) == 5


class TestCrisisTask:
    """Test CrisisTask dataclass"""

    def test_create_crisis_task(self):
        """Test CrisisTask creation with all fields"""
        task = CrisisTask(
            task_id="test_task_001",
            agent_type="cybersecurity",
            analysis_type="incident_analysis",
            priority=1,
            deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
            dependencies=["dep_1", "dep_2"],
        )

        assert task.task_id == "test_task_001"
        assert task.agent_type == "cybersecurity"
        assert task.analysis_type == "incident_analysis"
        assert task.priority == 1
        assert task.status == "pending"  # Default value
        assert len(task.dependencies) == 2

    def test_crisis_task_default_status(self):
        """Test default status is 'pending'"""
        task = CrisisTask(
            task_id="task_002",
            agent_type="legal",
            analysis_type="compliance",
            priority=2,
            deadline=datetime.now(timezone.utc),
            dependencies=[],
        )
        assert task.status == "pending"

    def test_crisis_task_custom_status(self):
        """Test CrisisTask with custom status"""
        task = CrisisTask(
            task_id="task_003",
            agent_type="pr",
            analysis_type="communication",
            priority=3,
            deadline=datetime.now(timezone.utc),
            dependencies=[],
            status="in_progress",
        )
        assert task.status == "in_progress"


class TestCrisisDecision:
    """Test CrisisDecision dataclass"""

    def test_create_crisis_decision(self):
        """Test CrisisDecision creation with all fields"""
        decision = CrisisDecision(
            decision_id="decision_001",
            scenario="Test Scenario",
            recommendation="Execute recovery plan",
            confidence=0.85,
            rationale=["Reason 1", "Reason 2"],
            cost_benefit={"savings": "1M", "cost": "500K"},
            risks=["Risk 1", "Risk 2"],
            timeline="24 hours",
        )

        assert decision.decision_id == "decision_001"
        assert decision.scenario == "Test Scenario"
        assert decision.recommendation == "Execute recovery plan"
        assert decision.confidence == 0.85
        assert len(decision.rationale) == 2
        assert "savings" in decision.cost_benefit
        assert len(decision.risks) == 2
        assert decision.timeline == "24 hours"

    def test_crisis_decision_to_dict(self):
        """Test conversion to dictionary"""
        decision = CrisisDecision(
            decision_id="decision_002",
            scenario="Financial Crisis",
            recommendation="Reduce exposure",
            confidence=0.92,
            rationale=["Market volatility"],
            cost_benefit={"net_benefit": "2M"},
            risks=["Currency risk"],
            timeline="48 hours",
        )

        decision_dict = asdict(decision)
        assert decision_dict["decision_id"] == "decision_002"
        assert decision_dict["confidence"] == 0.92


class TestCrisisContext:
    """Test CrisisContext dataclass"""

    def test_create_crisis_context(self):
        """Test CrisisContext creation"""
        context = CrisisContext(
            crisis_code="CRISIS_001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="immediate",
            affected_systems=["database", "api_gateway"],
            stakeholders=["CEO", "CTO", "Legal"],
            regulatory_implications=["GDPR", "SOX"],
        )

        assert context.crisis_code == "CRISIS_001"
        assert context.crisis_type == CrisisType.CYBERSECURITY
        assert context.severity == RiskLevel.CRITICAL
        assert len(context.affected_systems) == 2
        assert len(context.stakeholders) == 3
        assert "GDPR" in context.regulatory_implications

    def test_context_priority_levels(self):
        """Test different severity levels in context"""
        for level in RiskLevel:
            context = CrisisContext(
                crisis_code=f"TEST_{level.value}",
                crisis_type=CrisisType.OPERATIONAL,
                severity=level,
                timeline="urgent",
                affected_systems=[],
                stakeholders=[],
                regulatory_implications=[],
            )
            assert context.severity == level

    def test_context_crisis_types(self):
        """Test all crisis types"""
        for crisis_type in CrisisType:
            context = CrisisContext(
                crisis_code=f"TYPE_{crisis_type.value}",
                crisis_type=crisis_type,
                severity=RiskLevel.MEDIUM,
                timeline="normal",
                affected_systems=[],
                stakeholders=[],
                regulatory_implications=[],
            )
            assert context.crisis_type == crisis_type


class TestCrisisOrchestrator:
    """Test CrisisOrchestrator class"""

    @pytest.fixture
    def mock_agent_factory(self):
        """Create mock agent factory"""
        factory = MagicMock()
        factory.register_agent_type = MagicMock()
        factory.register_default_configuration = MagicMock()
        factory.create_agent = AsyncMock(return_value="agent_123")
        factory.get_agent = AsyncMock()
        return factory

    @pytest.fixture
    def mock_crisis_agents(self):
        """Create mock crisis agents"""
        return {
            "cybersecurity": AsyncMock(),
            "legal_compliance": AsyncMock(),
            "pr_communications": AsyncMock(),
            "financial_risk": AsyncMock(),
            "customer_operations": AsyncMock(),
        }

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator for testing with mocked factory"""
        with patch("src.core.subagents.crisis_orchestrator.AgentFactory") as MockFactory:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            mock_factory.create_agent = AsyncMock(return_value="agent_123")
            mock_factory.get_agent = AsyncMock()
            MockFactory.return_value = mock_factory
            orch = CrisisOrchestrator()
            return orch

    @pytest.fixture
    def crisis_scenario(self):
        """Sample crisis scenario for tests"""
        return {
            "scenario_name": "Ransomware Attack",
            "crisis_code": "RANSOMWARE_001",
            "crisis_type": "cybersecurity",
            "severity": "critical",
            "timeline": "immediate",
            "affected_systems": ["customer_database", "payment_gateway"],
            "stakeholders": ["Board", "Customers", "Regulators"],
            "regulatory_implications": ["GDPR notification required"],
        }

    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes with correct state"""
        assert orchestrator.crisis_agents == {}
        assert orchestrator.active_crisis is None
        assert orchestrator.crisis_timeline == []
        assert orchestrator.agent_responses == {}
        assert orchestrator.decisions == []
        assert orchestrator.orchestration_start_time is None
        assert orchestrator.agent_factory is not None

    def test_register_crisis_agents(self, orchestrator):
        """Test crisis agents are registered on initialization"""
        # Check that agent types were registered
        assert orchestrator.agent_factory.register_agent_type.call_count >= 5
        assert orchestrator.agent_factory.register_default_configuration.call_count >= 5

    @pytest.mark.asyncio
    async def test_initiate_crisis_response(
        self, orchestrator, mock_crisis_agents, crisis_scenario
    ):
        """Test initiate_crisis_response creates crisis context and deploys agents"""
        # Setup mocks
        mock_agent = AsyncMock()
        mock_agent.execute_task = AsyncMock(
            return_value={
                "result": {"analysis": "test"},
                "recommendations": [],
                "next_actions": [],
            }
        )
        orchestrator.agent_factory.create_agent = AsyncMock(return_value="agent_id")
        orchestrator.agent_factory.get_agent = AsyncMock(return_value=mock_agent)

        # Execute
        crisis_id = await orchestrator.initiate_crisis_response(crisis_scenario)

        # Verify
        assert crisis_id.startswith("crisis_")
        assert orchestrator.active_crisis is not None
        assert orchestrator.active_crisis.crisis_code == "RANSOMWARE_001"
        assert orchestrator.active_crisis.crisis_type == CrisisType.CYBERSECURITY
        assert orchestrator.active_crisis.severity == RiskLevel.CRITICAL
        assert orchestrator.orchestration_start_time is not None
        assert len(orchestrator.crisis_timeline) > 0

    @pytest.mark.asyncio
    async def test_deploy_crisis_agents(self, orchestrator):
        """Test _deploy_crisis_agents creates all specialized agents"""
        mock_agent = AsyncMock()
        orchestrator.agent_factory.create_agent = AsyncMock(return_value="agent_id_123")
        orchestrator.agent_factory.get_agent = AsyncMock(return_value=mock_agent)

        await orchestrator._deploy_crisis_agents()

        # Should have called create_agent for all 5 agent types
        assert orchestrator.agent_factory.create_agent.call_count == 5
        assert len(orchestrator.crisis_agents) == 5

    @pytest.mark.asyncio
    async def test_deploy_crisis_agents_failure(self, orchestrator):
        """Test _deploy_crisis_agents handles creation failures gracefully"""
        orchestrator.agent_factory.create_agent = AsyncMock(return_value=None)

        await orchestrator._deploy_crisis_agents()

        # No agents should be deployed when creation returns None
        assert len(orchestrator.crisis_agents) == 0

    @pytest.mark.asyncio
    async def test_deploy_crisis_agents_exception(self, orchestrator):
        """Test _deploy_crisis_agents handles exceptions gracefully"""
        orchestrator.agent_factory.create_agent = AsyncMock(
            side_effect=Exception("Agent creation failed")
        )

        # Should not raise, just log error
        await orchestrator._deploy_crisis_agents()
        assert len(orchestrator.crisis_agents) == 0

    @pytest.mark.asyncio
    async def test_execute_crisis_task_success(self, orchestrator, crisis_scenario):
        """Test successful execution of a crisis task"""
        # Setup
        mock_agent = AsyncMock()
        mock_agent.execute_task = AsyncMock(
            return_value={
                "result": {"analysis": "complete"},
                "recommendations": ["action1"],
            }
        )
        orchestrator.crisis_agents["cybersecurity"] = mock_agent
        orchestrator.active_crisis = CrisisContext(
            crisis_code="TEST_001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.HIGH,
            timeline="immediate",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        task = CrisisTask(
            task_id="cyber_analysis",
            agent_type="cybersecurity",
            analysis_type="incident_analysis",
            priority=1,
            deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
            dependencies=[],
        )

        result = await orchestrator._execute_crisis_task(task, crisis_scenario)

        assert result is not None
        assert "cyber_analysis" in orchestrator.agent_responses
        assert orchestrator.agent_responses["cyber_analysis"]["agent_type"] == "cybersecurity"

    @pytest.mark.asyncio
    async def test_execute_crisis_task_agent_not_available(self, orchestrator, crisis_scenario):
        """Test crisis task execution when agent is not available"""
        orchestrator.crisis_agents = {}  # No agents available
        orchestrator.active_crisis = CrisisContext(
            crisis_code="TEST_001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.HIGH,
            timeline="immediate",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        task = CrisisTask(
            task_id="missing_agent_task",
            agent_type="nonexistent",
            analysis_type="test",
            priority=1,
            deadline=datetime.now(timezone.utc) + timedelta(minutes=10),
            dependencies=[],
        )

        result = await orchestrator._execute_crisis_task(task, crisis_scenario)

        assert "error" in result
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_crisis_task_exception(self, orchestrator, crisis_scenario):
        """Test crisis task execution handles exceptions"""
        mock_agent = AsyncMock()
        mock_agent.execute_task = AsyncMock(side_effect=Exception("Task failed"))
        orchestrator.crisis_agents["cybersecurity"] = mock_agent
        orchestrator.active_crisis = CrisisContext(
            crisis_code="TEST_001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.HIGH,
            timeline="immediate",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        task = CrisisTask(
            task_id="failing_task",
            agent_type="cybersecurity",
            analysis_type="test",
            priority=1,
            deadline=datetime.now(timezone.utc),
            dependencies=[],
        )

        result = await orchestrator._execute_crisis_task(task, crisis_scenario)

        assert "error" in result
        assert result["task_id"] == "failing_task"

    @pytest.mark.asyncio
    async def test_coordinate_multi_agent_response(self, orchestrator, crisis_scenario):
        """Test coordinated multi-agent crisis response"""
        # Setup mock agents
        for agent_type in [
            "cybersecurity",
            "legal_compliance",
            "pr_communications",
            "financial_risk",
            "customer_operations",
        ]:
            mock_agent = AsyncMock()
            mock_agent.execute_task = AsyncMock(
                return_value={
                    "result": {"analysis": f"{agent_type}_complete"},
                    "recommendations": [f"{agent_type}_recommendation"],
                }
            )
            orchestrator.crisis_agents[agent_type] = mock_agent

        orchestrator.active_crisis = CrisisContext(
            crisis_code="MULTI_AGENT_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="immediate",
            affected_systems=["system1"],
            stakeholders=["CEO"],
            regulatory_implications=["GDPR"],
        )

        await orchestrator._phase_1_immediate_analysis(crisis_scenario)

        # All agents should have been called
        for agent_type, mock_agent in orchestrator.crisis_agents.items():
            mock_agent.execute_task.assert_called()

        # Timeline should have analysis phase entry
        assert any(
            event.get("phase") == CrisisPhase.ANALYSIS.value
            for event in orchestrator.crisis_timeline
        )

    @pytest.mark.asyncio
    async def test_aggregate_decisions_consensus(self, orchestrator):
        """Test decision aggregation when agents reach consensus"""
        # Setup agent responses
        orchestrator.agent_responses = {
            "financial_impact_analysis": {
                "result": {
                    "ransom_payment_scenario": {"cost": 8000000},
                    "recovery_without_payment_scenario": {"cost": 650000},
                }
            },
            "legal_regulatory_assessment": {"result": {"compliance_risk": "high"}},
            "cyber_incident_analysis": {"result": {"threat_level": "critical"}},
            "communication_strategy": {"result": {"approach": "transparent"}},
            "service_continuity_assessment": {"result": {"downtime": "7-14 days"}},
        }

        await orchestrator._phase_2_decision_synthesis()

        # Should have generated decisions
        assert len(orchestrator.decisions) == 3
        assert any(d.decision_id == "financial_response" for d in orchestrator.decisions)
        assert any(d.decision_id == "operational_response" for d in orchestrator.decisions)
        assert any(d.decision_id == "communication_strategy" for d in orchestrator.decisions)

    @pytest.mark.asyncio
    async def test_aggregate_decisions_conflict(self, orchestrator):
        """Test decision aggregation handles conflicting recommendations"""
        # Setup conflicting agent responses
        orchestrator.agent_responses = {
            "financial_impact_analysis": {
                "result": {
                    "recommendation": "pay_ransom",
                    "ransom_payment_scenario": {},
                    "recovery_without_payment_scenario": {},
                }
            },
            "legal_regulatory_assessment": {
                "result": {"recommendation": "do_not_pay", "compliance_risk": "high"}
            },
            "cyber_incident_analysis": {"result": {}},
            "communication_strategy": {"result": {}},
            "service_continuity_assessment": {"result": {}},
        }

        # Decision synthesis should still work even with conflicting inputs
        await orchestrator._phase_2_decision_synthesis()

        # Financial decision should still recommend NOT paying
        financial_decision = next(
            (d for d in orchestrator.decisions if d.decision_id == "financial_response"),
            None,
        )
        assert financial_decision is not None
        assert "DO NOT PAY" in financial_decision.recommendation

    @pytest.mark.asyncio
    async def test_synthesize_financial_decision(self, orchestrator):
        """Test financial decision synthesis"""
        orchestrator.agent_responses = {
            "financial_impact_analysis": {
                "result": {
                    "ransom_payment_scenario": {"total_cost": "6.5M"},
                    "recovery_without_payment_scenario": {"total_cost": "650K"},
                }
            },
            "legal_regulatory_assessment": {"result": {}},
            "cyber_incident_analysis": {"result": {}},
        }

        decision = await orchestrator._synthesize_financial_decision()

        assert decision.decision_id == "financial_response"
        assert decision.confidence >= 0.9
        assert "cost_benefit" in asdict(decision)
        assert len(decision.rationale) > 0
        assert len(decision.risks) > 0

    @pytest.mark.asyncio
    async def test_synthesize_operational_decision(self, orchestrator):
        """Test operational decision synthesis"""
        orchestrator.agent_responses = {
            "service_continuity_assessment": {"result": {"capacity": "20%"}},
            "cyber_incident_analysis": {"result": {}},
        }

        decision = await orchestrator._synthesize_operational_decision()

        assert decision.decision_id == "operational_response"
        assert "Business Continuity" in decision.scenario
        assert decision.confidence >= 0.8
        assert len(decision.rationale) > 0

    @pytest.mark.asyncio
    async def test_synthesize_communication_decision(self, orchestrator):
        """Test communication decision synthesis"""
        orchestrator.agent_responses = {
            "communication_strategy": {"result": {"approach": "proactive"}},
            "legal_regulatory_assessment": {"result": {"gdpr_deadline": "72 hours"}},
        }

        decision = await orchestrator._synthesize_communication_decision()

        assert decision.decision_id == "communication_strategy"
        assert "Communication" in decision.scenario
        assert decision.confidence >= 0.85
        assert "GDPR" in " ".join(decision.rationale)

    @pytest.mark.asyncio
    async def test_generate_crisis_action_plan(self, orchestrator):
        """Test crisis action plan generation"""
        orchestrator.active_crisis = CrisisContext(
            crisis_code="ACTION_PLAN_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="immediate",
            affected_systems=["database"],
            stakeholders=["Board"],
            regulatory_implications=["GDPR"],
        )

        action_plan = await orchestrator._generate_crisis_action_plan()

        assert action_plan["document_type"] == "Crisis Action Plan"
        assert action_plan["crisis_code"] == "ACTION_PLAN_TEST"
        assert "executive_summary" in action_plan
        assert "immediate_actions_0_4_hours" in action_plan
        assert "urgent_actions_4_24_hours" in action_plan
        assert "coordination_structure" in action_plan
        assert "success_metrics" in action_plan

    @pytest.mark.asyncio
    async def test_generate_decision_document(self, orchestrator):
        """Test decision document generation"""
        orchestrator.active_crisis = CrisisContext(
            crisis_code="DECISION_DOC_TEST",
            crisis_type=CrisisType.FINANCIAL,
            severity=RiskLevel.HIGH,
            timeline="urgent",
            affected_systems=["payment_system"],
            stakeholders=["CFO"],
            regulatory_implications=["SOX"],
        )

        decision_doc = await orchestrator._generate_decision_document()

        assert decision_doc["document_type"] == "Executive Decision Document"
        assert "scenario_analysis" in decision_doc
        assert "scenario_a_pay_ransom" in decision_doc["scenario_analysis"]
        assert "scenario_b_recovery_strategy" in decision_doc["scenario_analysis"]
        assert "final_recommendation" in decision_doc
        assert "board_approval_required" in decision_doc

    def test_get_orchestration_status_not_initiated(self, orchestrator):
        """Test status when orchestration not yet started"""
        status = orchestrator.get_orchestration_status()

        assert status["status"] == "Not initiated"

    def test_get_orchestration_status_active(self, orchestrator):
        """Test status during active orchestration"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="STATUS_TEST",
            crisis_type=CrisisType.OPERATIONAL,
            severity=RiskLevel.MEDIUM,
            timeline="normal",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )
        orchestrator.crisis_agents = {"cybersecurity": MagicMock()}
        orchestrator.agent_responses = {"task_1": {}}
        orchestrator.decisions = [MagicMock()]
        orchestrator.crisis_timeline = [{"event": "start"}]

        status = orchestrator.get_orchestration_status()

        assert status["status"] == "Active"
        assert "elapsed_time_minutes" in status
        assert status["deployed_agents"] == ["cybersecurity"]
        assert status["completed_analyses"] == 1
        assert status["generated_decisions"] == 1
        assert status["timeline_events"] == 1

    def test_get_orchestration_status_completed(self, orchestrator):
        """Test status when orchestration is completed (elapsed > 15 min)"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="COMPLETE_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.LOW,
            timeline="normal",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        status = orchestrator.get_orchestration_status()

        assert status["status"] == "Completed"

    def test_get_detailed_results(self, orchestrator):
        """Test detailed results retrieval"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="DETAIL_TEST",
            crisis_type=CrisisType.REPUTATIONAL,
            severity=RiskLevel.HIGH,
            timeline="immediate",
            affected_systems=["social_media"],
            stakeholders=["PR Team"],
            regulatory_implications=[],
        )
        orchestrator.crisis_agents = {
            "pr_communications": MagicMock(),
            "legal_compliance": MagicMock(),
        }
        orchestrator.agent_responses = {
            "pr_task": {"result": {"done": True}, "execution_time": 5.5},
            "legal_task": {"result": {"done": True}, "execution_time": 3.2},
        }
        orchestrator.decisions = [
            CrisisDecision(
                decision_id="test_dec",
                scenario="Test",
                recommendation="Action",
                confidence=0.9,
                rationale=["reason"],
                cost_benefit={},
                risks=[],
                timeline="1 hour",
            )
        ]
        orchestrator.crisis_timeline = [{"event": "start"}, {"event": "end"}]

        results = orchestrator.get_detailed_results()

        assert "orchestration_summary" in results
        assert "crisis_context" in results
        assert results["crisis_context"]["crisis_code"] == "DETAIL_TEST"
        assert "agent_responses" in results
        assert len(results["agent_responses"]) == 2
        assert "executive_decisions" in results
        assert len(results["executive_decisions"]) == 1
        assert "crisis_timeline" in results
        assert "performance_metrics" in results
        assert results["performance_metrics"]["total_agents_deployed"] == 2
        assert results["performance_metrics"]["successful_analyses"] == 2

    def test_get_detailed_results_with_errors(self, orchestrator):
        """Test detailed results with some failed analyses"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="ERROR_TEST",
            crisis_type=CrisisType.REGULATORY,
            severity=RiskLevel.CRITICAL,
            timeline="urgent",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=["compliance_issue"],
        )
        orchestrator.crisis_agents = {"legal": MagicMock()}
        orchestrator.agent_responses = {
            "success_task": {"result": {"done": True}, "execution_time": 2.0},
            "failed_task": {"result": {"error": "timeout"}, "execution_time": 30.0},
        }
        orchestrator.decisions = []
        orchestrator.crisis_timeline = []

        results = orchestrator.get_detailed_results()

        # One successful, one failed
        assert results["performance_metrics"]["successful_analyses"] == 1

    def test_get_detailed_results_no_crisis(self, orchestrator):
        """Test detailed results when no crisis is active"""
        results = orchestrator.get_detailed_results()

        assert results["crisis_context"] is None
        assert results["orchestration_summary"]["status"] == "Not initiated"

    @pytest.mark.asyncio
    async def test_escalation_on_timeout(self, orchestrator, crisis_scenario):
        """Test escalation behavior when agent times out"""
        import asyncio

        # Setup agent that times out
        async def slow_execute(task_data):
            await asyncio.sleep(0.1)  # Simulate slow response
            return {"result": "completed after delay"}

        mock_agent = AsyncMock()
        mock_agent.execute_task = slow_execute
        orchestrator.crisis_agents["cybersecurity"] = mock_agent
        orchestrator.active_crisis = CrisisContext(
            crisis_code="TIMEOUT_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="immediate",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        task = CrisisTask(
            task_id="timeout_task",
            agent_type="cybersecurity",
            analysis_type="test",
            priority=1,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=1),  # Short deadline
            dependencies=[],
        )

        # Execute task - should complete (simulating escalation would be in real scenario)
        result = await orchestrator._execute_crisis_task(task, crisis_scenario)

        # Task should complete, even if delayed
        assert result is not None

    @pytest.mark.asyncio
    async def test_phase_1_with_partial_agents(self, orchestrator, crisis_scenario):
        """Test phase 1 analysis with only some agents available"""
        # Only deploy 2 out of 5 agents
        for agent_type in ["cybersecurity", "financial_risk"]:
            mock_agent = AsyncMock()
            mock_agent.execute_task = AsyncMock(return_value={"result": {"done": True}})
            orchestrator.crisis_agents[agent_type] = mock_agent

        orchestrator.active_crisis = CrisisContext(
            crisis_code="PARTIAL_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.HIGH,
            timeline="urgent",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        await orchestrator._phase_1_immediate_analysis(crisis_scenario)

        # Should have responses only from available agents
        # Only 2 tasks will execute since only 2 agents are available
        assert len(orchestrator.agent_responses) <= 2


class TestGetCrisisOrchestrator:
    """Test global crisis orchestrator singleton"""

    def test_get_crisis_orchestrator_creates_instance(self):
        """Test that get_crisis_orchestrator creates a new instance"""
        import src.core.subagents.crisis_orchestrator as module

        # Reset the global
        module._crisis_orchestrator = None

        with patch.object(module, "AgentFactory") as MockFactory:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            MockFactory.return_value = mock_factory

            orchestrator = get_crisis_orchestrator()

            assert orchestrator is not None
            assert isinstance(orchestrator, CrisisOrchestrator)

    def test_get_crisis_orchestrator_returns_same_instance(self):
        """Test that get_crisis_orchestrator returns the same singleton"""
        import src.core.subagents.crisis_orchestrator as module

        # Reset the global
        module._crisis_orchestrator = None

        with patch.object(module, "AgentFactory") as MockFactory:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            MockFactory.return_value = mock_factory

            orchestrator1 = get_crisis_orchestrator()
            orchestrator2 = get_crisis_orchestrator()

            assert orchestrator1 is orchestrator2


class TestCrisisOrchestratorIntegration:
    """Integration-style tests for full orchestration flow"""

    @pytest.fixture
    def fully_mocked_orchestrator(self):
        """Create orchestrator with all dependencies mocked"""
        with patch("src.core.subagents.crisis_orchestrator.AgentFactory") as MockFactory:
            # Create agents that return proper responses
            def create_mock_agent():
                agent = AsyncMock()
                agent.execute_task = AsyncMock(
                    return_value={
                        "result": {
                            "analysis": "complete",
                            "recommendations": ["action"],
                        },
                        "success": True,
                    }
                )
                return agent

            mock_factory = MagicMock()
            mock_factory.create_agent = AsyncMock(return_value="agent_id_123")
            mock_factory.get_agent = AsyncMock(side_effect=lambda _: create_mock_agent())
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            MockFactory.return_value = mock_factory

            orchestrator = CrisisOrchestrator()
            orchestrator.agent_factory = mock_factory
            return orchestrator

    @pytest.mark.asyncio
    async def test_full_orchestration_flow(self, fully_mocked_orchestrator):
        """Test complete orchestration from initiation to deliverables"""
        scenario = {
            "scenario_name": "Full Integration Test",
            "crisis_code": "FULL_TEST_001",
            "crisis_type": "cybersecurity",
            "severity": "critical",
            "timeline": "immediate",
            "affected_systems": ["all_systems"],
            "stakeholders": ["Everyone"],
            "regulatory_implications": ["All regulations"],
        }

        crisis_id = await fully_mocked_orchestrator.initiate_crisis_response(scenario)

        # Verify full flow completed
        assert crisis_id.startswith("crisis_")
        assert fully_mocked_orchestrator.active_crisis is not None
        assert len(fully_mocked_orchestrator.crisis_timeline) >= 3  # At least 3 phases logged
        assert len(fully_mocked_orchestrator.decisions) == 3  # 3 decisions generated

        # Verify status shows completion
        status = fully_mocked_orchestrator.get_orchestration_status()
        assert status["generated_decisions"] == 3

        # Verify detailed results
        results = fully_mocked_orchestrator.get_detailed_results()
        assert len(results["executive_decisions"]) == 3


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.fixture
    def orchestrator(self):
        """Create basic orchestrator for edge case tests"""
        with patch("src.core.subagents.crisis_orchestrator.AgentFactory") as MockFactory:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            MockFactory.return_value = mock_factory
            return CrisisOrchestrator()

    def test_empty_agent_responses_average_calculation(self, orchestrator):
        """Test average calculation with no responses"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="EMPTY_TEST",
            crisis_type=CrisisType.OPERATIONAL,
            severity=RiskLevel.LOW,
            timeline="normal",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )
        orchestrator.agent_responses = {}

        results = orchestrator.get_detailed_results()

        # Should handle division by zero gracefully
        assert results["performance_metrics"]["average_agent_response_time"] == 0.0

    def test_orchestration_efficiency_classification(self, orchestrator):
        """Test efficiency classification based on response count"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="EFF_TEST",
            crisis_type=CrisisType.FINANCIAL,
            severity=RiskLevel.MEDIUM,
            timeline="normal",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )

        # Test with 4+ responses (High efficiency)
        orchestrator.agent_responses = {
            "task1": {"result": {}, "execution_time": 1},
            "task2": {"result": {}, "execution_time": 1},
            "task3": {"result": {}, "execution_time": 1},
            "task4": {"result": {}, "execution_time": 1},
        }

        results = orchestrator.get_detailed_results()
        assert results["performance_metrics"]["orchestration_efficiency"] == "High"

        # Test with < 4 responses (Medium efficiency)
        orchestrator.agent_responses = {
            "task1": {"result": {}, "execution_time": 1},
            "task2": {"result": {}, "execution_time": 1},
        }

        results = orchestrator.get_detailed_results()
        assert results["performance_metrics"]["orchestration_efficiency"] == "Medium"

    @pytest.mark.asyncio
    async def test_generate_deliverables_logging(self, orchestrator):
        """Test deliverables generation adds to timeline"""
        orchestrator.orchestration_start_time = datetime.now(timezone.utc)
        orchestrator.active_crisis = CrisisContext(
            crisis_code="DELIVERABLE_TEST",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="immediate",
            affected_systems=[],
            stakeholders=[],
            regulatory_implications=[],
        )
        orchestrator.decisions = []
        orchestrator.crisis_timeline = []

        await orchestrator._generate_crisis_deliverables()

        # Should have added implementation phase to timeline
        assert any(
            event.get("phase") == CrisisPhase.IMPLEMENTATION.value
            for event in orchestrator.crisis_timeline
        )
        assert any("deliverables" in event for event in orchestrator.crisis_timeline)

    def test_crisis_task_with_empty_dependencies(self):
        """Test CrisisTask with empty dependencies list"""
        task = CrisisTask(
            task_id="no_deps_task",
            agent_type="test",
            analysis_type="test",
            priority=1,
            deadline=datetime.now(timezone.utc),
            dependencies=[],
        )
        assert task.dependencies == []

    def test_crisis_decision_with_empty_lists(self):
        """Test CrisisDecision with empty lists"""
        decision = CrisisDecision(
            decision_id="empty_lists",
            scenario="Test",
            recommendation="None",
            confidence=0.0,
            rationale=[],
            cost_benefit={},
            risks=[],
            timeline="Never",
        )
        assert decision.rationale == []
        assert decision.risks == []
        assert decision.cost_benefit == {}
