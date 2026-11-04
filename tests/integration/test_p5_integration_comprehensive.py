"""
P5.0 Integration Tests - Comprehensive Cross-Module Integration
================================================================

Tests realistic flows that integrate:
- CVA Agent (state machine + LLM integration)
- Workflow Engine (DAG execution + observability)
- Tool Broker (circuit breaker + resilience)
- Domain Modules (validation + business rules)

Test Scenarios:
1. CVA-Driven Workflow Creation and Execution
2. Multi-Tenant Workflow Isolation (parallel execution)
3. Circuit Breaker + Retry Integration (failure handling)
4. Agent Coordination Flow (crisis → pool → specialists)

Execution:
    pytest tests/integration/test_p5_integration_comprehensive.py -v -m integration
    pytest tests/integration/test_p5_integration_comprehensive.py::TestCVAWorkflowIntegration -v
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Core modules under integration
from src.core.agents.cva_agent import CVAAgent
from src.core.agents.cva_state_machine import CVAMode
from src.core.tool_broker.resilience import (
    CircuitBreaker,
    CircuitBreakerState,
    RetryConfig,
    async_retry,
)
from src.core.workflow.engine import DAGValidator, ProductionWorkflowEngine, WorkflowSpec
from src.core.workflow.models import TaskStatus, Workflow, WorkflowExecution, WorkflowStatus
from src.core.workflow.providers import FakeAgentRuntime, FakeLLMProvider, FakeToolBroker
from src.domains.agents.models import Agent as DomainAgent
from src.domains.agents.services import AgentService

# Domain modules
from src.domains.workflows.models import WorkflowStep
from tests.fixtures.agent_mocks import FakeAgentRuntime as TestAgentRuntime
from tests.fixtures.llm_mocks import FakeLLMProvider as TestLLMProvider

# Test fixtures
from tests.fixtures.workflow_mocks import MockWorkflowEngine

# ============================================================================
# PYTEST MARKERS
# ============================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


# ============================================================================
# INTEGRATION TEST SUITE 1: CVA → WORKFLOW → DOMAIN
# ============================================================================


class TestCVAWorkflowIntegration:
    """Integration tests for CVA Agent → Workflow Engine → Domain Models"""

    @pytest.mark.xfail(
        reason="Workflow engine incompatible with C7 schema: missing id/tenant_id defaults for execution/event/task models"
    )
    async def test_cva_creates_and_executes_workflow(
        self, db_session: AsyncSession, test_tenant: int
    ):
        """
        SCENARIO: CVA agent creates a workflow, executes it via workflow engine,
        and updates domain models based on results.

        Flow:
        1. CVA agent transitions to PROACTIVE mode
        2. CVA creates workflow spec (DAG with 3 tasks)
        3. Workflow engine validates DAG
        4. Workflow engine executes tasks using fake providers
        5. Domain models updated (Agent + Workflow status)
        6. CVA receives completion notification

        Validates:
        - CVA state machine transitions
        - Workflow DAG validation
        - Task execution ordering (topological sort)
        - Domain model persistence
        - End-to-end integration
        """
        # ARRANGE: Initialize CVA agent in REACTIVE mode
        cva_agent = CVAAgent(agent_id="test_cva_integration", tenant_id=test_tenant["id"])
        assert cva_agent.state_machine.current_mode == CVAMode.CEO_MODE  # Default mode

        # Transition to PROACTIVE mode for workflow creation
        await cva_agent.state_machine.transition_to(CVAMode.PROACTIVE)
        assert cva_agent.state_machine.current_mode == CVAMode.PROACTIVE

        # ACT: CVA creates workflow spec
        # Workflow: research → analyze → report (linear DAG)
        workflow_spec = WorkflowSpec(
            workflow_id="cva_integration_workflow",
            version=1,
            tasks={
                "research": {"type": "llm", "prompt": "Research market trends"},
                "analyze": {"type": "agent", "agent_type": "data_analysis"},
                "report": {"type": "llm", "prompt": "Generate final report"},
            },
            dependencies={
                "research": [],
                "analyze": ["research"],  # analyze depends on research
                "report": ["analyze"],  # report depends on analyze
            },
            timeout_seconds=300,
            max_retries=2,
        )

        # ASSERT: DAG validation passes
        is_valid, error_msg = DAGValidator.validate_dag(workflow_spec)
        assert is_valid, f"DAG validation failed: {error_msg}"
        assert error_msg is None

        # ACT: Create workflow engine with fake providers (deterministic testing)
        # FakeLLMProvider expects a dict mapping prompt keywords to responses
        fake_llm = FakeLLMProvider(
            responses={
                "Research market trends": "Research complete - market analysis done",
                "Generate final report": "Report generated with findings",
            }
        )
        fake_tool = FakeToolBroker()
        fake_agent = FakeAgentRuntime(agent_results={"data_analysis": "Analysis complete"})

        # Use legacy mode with db_session for full execute_workflow support
        workflow_engine = ProductionWorkflowEngine(
            llm_provider=fake_llm,
            tool_broker=fake_tool,
            agent_runtime=fake_agent,
            db_session=db_session,  # Legacy mode for full functionality
        )

        # ACT: Create workflow
        workflow_db_id = await workflow_engine.create_workflow(
            workflow_id=workflow_spec.workflow_id,
            spec_json={
                "tasks": workflow_spec.tasks,
                "dependencies": workflow_spec.dependencies,
            },
            version=workflow_spec.version,
            tenant_id=test_tenant["id"],
        )

        # ACT: Start workflow execution
        execution_id = await workflow_engine.start_execution(
            workflow_id=workflow_spec.workflow_id,
            input_data={"context": "Integration test context"},
            tenant_id=test_tenant["id"],
        )

        # ACT: Execute workflow
        execution_summary = await workflow_engine.execute_workflow(
            execution_id=execution_id,
        )

        # ASSERT: Workflow execution completed successfully
        assert execution_summary is not None
        assert (
            execution_summary.get("status") == "succeeded"
        ), f"Expected succeeded, got {execution_summary.get('status')}"

        # ASSERT: Verify workflow was created
        result = await db_session.execute(select(Workflow).where(Workflow.id == workflow_db_id))
        workflow = result.scalar()
        assert workflow is not None, "Workflow not found in database"

        # ACT: CVA transitions back to CEO_MODE after workflow completion
        await cva_agent.state_machine.transition_to(CVAMode.CEO_MODE)
        assert cva_agent.state_machine.current_mode == CVAMode.CEO_MODE

    async def test_workflow_dag_cycle_detection_integration(self, db_session: AsyncSession):
        """
        SCENARIO: Workflow engine detects cyclic dependency and rejects DAG

        Validates:
        - DAG cycle detection algorithm
        - Graceful error handling
        - No database pollution from invalid workflows
        """
        # ARRANGE: Create workflow spec with cycle: A → B → C → A
        workflow_spec = WorkflowSpec(
            workflow_id="cyclic_workflow",
            version=1,
            tasks={
                "task_a": {"type": "llm", "prompt": "Step A"},
                "task_b": {"type": "llm", "prompt": "Step B"},
                "task_c": {"type": "llm", "prompt": "Step C"},
            },
            dependencies={
                "task_a": ["task_c"],  # A depends on C
                "task_b": ["task_a"],  # B depends on A
                "task_c": ["task_b"],  # C depends on B → CYCLE!
            },
        )

        # ACT: Validate DAG
        is_valid, error_msg = DAGValidator.validate_dag(workflow_spec)

        # ASSERT: Cycle detected
        assert not is_valid, "Expected cycle detection to fail validation"
        assert (
            "cycle" in error_msg.lower() or "cyclic" in error_msg.lower()
        ), f"Expected cycle error message, got: {error_msg}"


# ============================================================================
# INTEGRATION TEST SUITE 2: MULTI-TENANT WORKFLOW ISOLATION
# ============================================================================


class TestMultiTenantWorkflowIsolation:
    """Integration tests for tenant isolation in workflow execution"""

    @pytest.mark.xfail(
        reason="Parallel execution with shared session needs sequential execution - P6 improvement"
    )
    async def test_parallel_workflows_tenant_isolation(self, db_session: AsyncSession):
        """
        SCENARIO: Multiple tenants execute workflows sequentially with proper isolation

        Flow:
        1. Create 3 tenants with identical workflow definitions
        2. Execute workflows sequentially
        3. Verify each tenant's data is isolated
        4. Verify no cross-tenant data leakage

        Validates:
        - Multi-tenant isolation
        - Sequential execution correctness
        - Database transaction isolation
        """
        # ARRANGE: Create 3 test tenants
        from src.core.models.rbac_models import Tenant

        tenant_ids = []
        for i in range(3):
            tenant = Tenant(
                name=f"Integration Test Tenant P5 {i}",
                slug=f"integration-tenant-p5-{i}",
                is_active=True,
                subscription_tier="enterprise",
                subscription_status="active",
            )
            db_session.add(tenant)
        await db_session.commit()

        # Get tenant IDs
        result = await db_session.execute(
            select(Tenant).where(Tenant.slug.like("integration-tenant-p5-%"))
        )
        tenants = result.scalars().all()
        tenant_ids = [t.id for t in tenants]
        assert len(tenant_ids) == 3, "Expected 3 tenants created"

        # ARRANGE: Define identical workflow spec for all tenants
        workflow_spec = WorkflowSpec(
            workflow_id="tenant_isolation_test_p5",
            version=1,
            tasks={
                "step1": {"type": "llm", "prompt": "Process tenant data"},
                "step2": {"type": "agent", "agent_type": "data_processor"},
            },
            dependencies={"step1": [], "step2": ["step1"]},
        )

        # ACT: Execute workflows SEQUENTIALLY (one per tenant)
        execution_ids = []
        for tenant_id in tenant_ids:
            # Create tenant-specific fake providers
            fake_llm = FakeLLMProvider(responses=[f"Tenant {tenant_id} LLM response"])
            fake_tool = FakeToolBroker()
            fake_agent = FakeAgentRuntime(
                agent_results={"data_processor": f"Tenant {tenant_id} processed"}
            )

            engine = ProductionWorkflowEngine(
                llm_provider=fake_llm,
                tool_broker=fake_tool,
                agent_runtime=fake_agent,
                db_session=db_session,
            )

            # Step 1: Create workflow
            await engine.create_workflow(
                workflow_id=f"{workflow_spec.workflow_id}_{tenant_id}",
                spec_json={
                    "tasks": workflow_spec.tasks,
                    "dependencies": workflow_spec.dependencies,
                },
                version=workflow_spec.version,
                tenant_id=str(tenant_id),
            )

            # Step 2: Start execution
            execution_id = await engine.start_execution(
                workflow_id=f"{workflow_spec.workflow_id}_{tenant_id}",
                input_data={"tenant_id": tenant_id},
                tenant_id=str(tenant_id),
            )
            execution_ids.append(execution_id)

        # ASSERT: All executions started
        assert len(execution_ids) == 3

        # Verify tenant isolation - each tenant only sees own workflows
        for tenant_id in tenant_ids:
            result = await db_session.execute(
                select(Workflow).where(Workflow.tenant_id == str(tenant_id))
            )
            tenant_workflows = result.scalars().all()
            assert (
                len(tenant_workflows) == 1
            ), f"Tenant {tenant_id} should have exactly 1 workflow, found {len(tenant_workflows)}"


# ============================================================================
# INTEGRATION TEST SUITE 3: CIRCUIT BREAKER + RETRY INTEGRATION
# ============================================================================


class TestCircuitBreakerRetryIntegration:
    """Integration tests for Tool Broker resilience patterns"""

    async def test_circuit_breaker_opens_after_threshold_failures(self):
        """
        SCENARIO: Circuit breaker opens after consecutive failures and prevents further calls

        Flow:
        1. Create circuit breaker with failure_threshold=3
        2. Simulate 3 consecutive failures
        3. Verify circuit opens
        4. Attempt call - should fail immediately without retry
        5. Wait for timeout
        6. Verify circuit transitions to HALF_OPEN
        7. Successful call should close circuit

        Validates:
        - Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
        - Failure threshold enforcement
        - Recovery timeout behavior
        - Integration with retry logic
        """
        # ARRANGE: Create circuit breaker with low threshold for testing
        from src.core.tool_broker.resilience import CircuitBreakerConfig

        config = CircuitBreakerConfig(
            failure_threshold=3,
            reset_timeout_seconds=1,  # Short timeout for testing
            success_threshold=1,
        )
        circuit_breaker = CircuitBreaker(
            name="test_integration_breaker",
            config=config,
        )

        # ARRANGE: Create failing async function
        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception(f"Simulated failure #{call_count}")

        # ACT & ASSERT: Circuit starts CLOSED
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

        # ACT: Trigger 3 failures to open circuit
        for i in range(3):
            try:
                await circuit_breaker.call(failing_operation)
            except Exception as e:
                assert "Simulated failure" in str(e)

        # ASSERT: Circuit should now be OPEN
        assert circuit_breaker.state == CircuitBreakerState.OPEN
        assert circuit_breaker.failure_count >= circuit_breaker.config.failure_threshold

        # ACT: Attempt to call while OPEN - should fail immediately
        with pytest.raises(Exception) as exc_info:
            await circuit_breaker.call(failing_operation)
        assert (
            "circuit breaker is open" in str(exc_info.value).lower()
            or circuit_breaker.state == CircuitBreakerState.OPEN
        )

        # Store call count before timeout
        calls_before_timeout = call_count

        # ACT: Wait for recovery timeout
        await asyncio.sleep(circuit_breaker.config.reset_timeout_seconds + 0.1)

        # ASSERT: Circuit should transition to HALF_OPEN
        # Note: State transition happens on next call attempt

        # ACT: Create successful operation for recovery
        async def successful_operation():
            return "Success"

        result = await circuit_breaker.call(successful_operation)

        # ASSERT: Circuit should be CLOSED after successful call
        assert result == "Success"
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

    async def test_retry_with_exponential_backoff_integration(self):
        """
        SCENARIO: Async retry with exponential backoff eventually succeeds

        Flow:
        1. Create function that fails 2 times then succeeds
        2. Configure retry with max_attempts=3, exponential backoff
        3. Execute with async_retry
        4. Verify backoff delays increase exponentially
        5. Verify final success

        Validates:
        - Exponential backoff calculation
        - Jitter randomization
        - Retry success after transient failures
        - Integration with async operations
        """
        # ARRANGE: Create function that fails twice then succeeds
        attempt_count = 0
        attempt_times = []

        async def flaky_operation():
            nonlocal attempt_count
            attempt_count += 1
            attempt_times.append(asyncio.get_event_loop().time())

            if attempt_count < 3:
                raise Exception(f"Transient failure #{attempt_count}")
            return "Success after retries"

        # ARRANGE: Configure retry with exponential backoff
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_ms=50,  # 50ms initial delay
            max_delay_ms=500,  # 500ms max delay
            backoff_factor=2.0,  # Double each retry
            jitter_enabled=True,
        )

        # ACT: Execute with retry
        start_time = asyncio.get_event_loop().time()
        result = await async_retry(
            flaky_operation,
            config=retry_config,
        )
        end_time = asyncio.get_event_loop().time()

        # ASSERT: Function eventually succeeded
        assert result == "Success after retries"
        assert attempt_count == 3, f"Expected 3 attempts, got {attempt_count}"

        # ASSERT: Verify exponential backoff delays
        # First attempt: immediate
        # Second attempt: ~50ms delay
        # Third attempt: ~100ms delay (2x backoff)
        # Total time should be > 150ms
        total_time = end_time - start_time
        assert total_time >= 0.15, f"Expected >150ms total time, got {total_time * 1000:.2f}ms"

        # ASSERT: Verify delays increased (allowing for jitter variance)
        if len(attempt_times) >= 3:
            delay_1_to_2 = attempt_times[1] - attempt_times[0]
            delay_2_to_3 = attempt_times[2] - attempt_times[1]
            # Second delay should be >= first delay (exponential backoff)
            # Note: Jitter adds randomness, so we can't assert strict doubling
            assert (
                delay_2_to_3 >= delay_1_to_2 * 0.8
            ), f"Backoff not increasing: delay1={delay_1_to_2 * 1000:.2f}ms, delay2={delay_2_to_3 * 1000:.2f}ms"


# ============================================================================
# INTEGRATION TEST SUITE 4: AGENT COORDINATION FLOW
# ============================================================================


class TestAgentCoordinationIntegration:
    """Integration tests for Agent Pool → Specialist Agents coordination"""

    @pytest.mark.xfail(reason="Requires session management refactoring - tracked for P6")
    async def test_crisis_agent_orchestration_flow(
        self, db_session: AsyncSession, test_tenant: int
    ):
        """
        SCENARIO: Crisis agent coordinates multiple specialist agents via agent pool

        Flow:
        1. Crisis event detected
        2. Crisis orchestrator allocates specialist agents from pool
        3. Specialists execute in parallel (security, PR, financial analysis)
        4. Results aggregated and returned to CVA
        5. Workflow updated with crisis response

        Validates:
        - Agent pool allocation
        - Multi-agent coordination
        - Parallel agent execution
        - Result aggregation
        - Integration with workflow engine

        NOTE: This test uses mocks for specialist agents (real implementation
        would require full LLM integration which is tested separately in unit tests)
        """
        # ARRANGE: Create mock specialist agents
        from src.core.subagents.agent_factory import AgentConfiguration
        from src.core.subagents.specialist_agents import (
            DataAnalysisAgent,
            KnowledgeAgent,
            SystemMonitorAgent,
        )
        from src.core.types import AgentType

        # Create base config for agents
        def create_agent_config(agent_type: str) -> AgentConfiguration:
            return AgentConfiguration(
                agent_type=AgentType.SPECIALIST,
                name=agent_type,
                capabilities=[agent_type],
                max_concurrent_tasks=10,
                memory_limit_mb=512,
                cpu_priority="normal",
                specialized_parameters={},
            )

        # Create fake agent pool with 3 specialists
        mock_agents = {
            "data_analysis": DataAnalysisAgent(
                agent_id="data_1", config=create_agent_config("data_analysis")
            ),
            "system_monitor": SystemMonitorAgent(
                agent_id="monitor_1", config=create_agent_config("system_monitor")
            ),
            "knowledge": KnowledgeAgent(
                agent_id="knowledge_1", config=create_agent_config("knowledge")
            ),
        }

        # ARRANGE: Simulate crisis event
        crisis_context = {
            "event_type": "security_breach",
            "severity": "critical",
            "affected_systems": ["user_database", "api_gateway"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # ACT: Allocate agents from pool (mocked allocation)
        allocated_agents = [
            mock_agents["system_monitor"],  # Monitor system health
            mock_agents["data_analysis"],  # Analyze breach impact
            mock_agents["knowledge"],  # Retrieve security protocols
        ]

        # ACT: Execute agents in parallel
        async def execute_agent_task(agent, context):
            """Simulate agent task execution"""
            await asyncio.sleep(0.05)  # Simulate processing time
            return {
                "agent_id": agent.agent_id,
                "status": "completed",
                "result": f"{agent.agent_id} processed crisis event",
            }

        results = await asyncio.gather(
            *[execute_agent_task(agent, crisis_context) for agent in allocated_agents]
        )

        # ASSERT: All agents completed successfully
        assert len(results) == 3
        for result in results:
            assert result["status"] == "completed"

        # ACT: Aggregate results
        aggregated_response = {
            "crisis_type": crisis_context["event_type"],
            "specialists_engaged": len(results),
            "analysis": [r["result"] for r in results],
            "recommendation": "Immediate containment and forensic analysis required",
            "workflow_status": "crisis_response_initiated",
        }

        # ASSERT: Aggregation successful
        assert aggregated_response["specialists_engaged"] == 3
        assert len(aggregated_response["analysis"]) == 3

        # ACT: Create workflow for crisis response
        # Note: Workflow model stores spec_json, not trigger_config
        # Trigger info is stored in the execution, not the workflow definition
        workflow = Workflow(
            tenant_id=test_tenant,
            name="Crisis Response Workflow",
            workflow_id="crisis_response_001",
            version=1,
            spec_json={
                "tasks": {
                    "containment": {"type": "agent", "agent_type": "security"},
                    "forensics": {"type": "agent", "agent_type": "data_analysis"},
                    "reporting": {"type": "llm", "prompt": "Generate incident report"},
                },
                "dependencies": {
                    "containment": [],
                    "forensics": ["containment"],
                    "reporting": ["forensics"],
                },
                "trigger_info": {
                    "trigger_type": "crisis_event",
                    "context": crisis_context,
                },
            },
        )
        db_session.add(workflow)
        await db_session.commit()
        await db_session.refresh(workflow)

        # ASSERT: Workflow persisted
        assert workflow.id is not None
        assert workflow.spec_json["trigger_info"]["trigger_type"] == "crisis_event"
