"""
Comprehensive tests for src/core/agents/executor_agent.py
Target: 80%+ coverage for Phase 2 Agent System Core
Priority: #6 file (1,141 lines) with 0% coverage
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.agents.executor_agent import ExecutorAgent
from src.core.shared.interfaces import (
    AgentCapability,
    AgentType,
    ExecutionResult,
    IsolationLevel,
    TaskData,
)


class TestExecutorAgentInitialization:
    """Test ExecutorAgent initialization"""

    def test_initialization_default_id(self):
        """Test agent initializes with default ID"""
        agent = ExecutorAgent()

        assert agent.agent_id == "executor_agent_001"
        assert agent.agent_type == AgentType.SPECIALIST
        assert agent.specialization == "action_execution_automation"

    def test_initialization_custom_id(self):
        """Test agent initializes with custom ID"""
        agent = ExecutorAgent(agent_id="custom_executor_456")

        assert agent.agent_id == "custom_executor_456"
        assert agent.agent_type == AgentType.SPECIALIST

    def test_execution_domains_configured(self):
        """Test execution domains are properly configured"""
        agent = ExecutorAgent()

        assert len(agent.execution_domains) == 10
        assert "api_integration" in agent.execution_domains
        assert "workflow_automation" in agent.execution_domains
        assert "file_operations" in agent.execution_domains

    def test_supported_integrations_configured(self):
        """Test supported integrations"""
        agent = ExecutorAgent()

        assert "rest_api" in agent.supported_integrations
        assert "database" in agent.supported_integrations
        assert "slack" in agent.supported_integrations
        assert "docker" in agent.supported_integrations

    def test_safety_checks_configured(self):
        """Test safety checks are configured"""
        agent = ExecutorAgent()

        assert "command_validation" in agent.safety_checks
        assert "api_rate_limiting" in agent.safety_checks
        assert "rollback_capability" in agent.safety_checks

    def test_initial_monitoring_state(self):
        """Test initial monitoring state"""
        agent = ExecutorAgent()

        assert agent.execution_history == []
        assert agent.api_usage_tracker == {}
        assert agent.safety_violations == []
        assert agent.llm_client is None
        assert agent.sandbox_manager is None


class TestExecutorAgentInitialize:
    """Test async initialization"""

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.TenantTaalmodel")
    @patch("src.core.agents.executor_agent.SandboxManagerFactory.create_manager")
    @patch("src.core.agents.executor_agent.ExecutorAgent._setup_execution_environment")
    async def test_initialize_success(self, mock_setup, mock_sandbox, mock_llm):
        """Test successful initialization"""
        mock_llm.return_value = Mock()
        mock_sandbox.return_value = Mock()
        mock_setup.return_value = None

        agent = ExecutorAgent()
        result = await agent.initialize()

        assert result is True
        assert agent.llm_client is not None
        assert agent.sandbox_manager is not None
        mock_llm.assert_called_once_with(agent.tenant_id)
        mock_sandbox.assert_called_once_with(IsolationLevel.CONTAINER)
        mock_setup.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.SandboxManagerFactory.create_manager")
    async def test_initialize_sandbox_failure(self, mock_sandbox):
        """Een storing in de sandbox laat initialize mislukken; het taalmodel wordt pas bij gebruik opgevraagd.

        Gewijzigd 2026-10-20 (ADR-041 B14): `create_llm_client("anthropic")` kon bij het initialiseren falen; het
        model van de tenant (`TenantTaalmodel`) wordt lazy opgehaald, dus er is hier geen modelstoring meer.
        """
        mock_sandbox.side_effect = Exception("sandbox error")

        agent = ExecutorAgent()
        result = await agent.initialize()

        assert result is False

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.TenantTaalmodel")
    @patch("src.core.agents.executor_agent.SandboxManagerFactory.create_manager")
    @patch("src.core.agents.executor_agent.ExecutorAgent._setup_execution_environment")
    async def test_initialize_setup_failure(self, mock_setup, mock_sandbox, mock_llm):
        """Test initialization handles setup failure"""
        mock_llm.return_value = Mock()
        mock_sandbox.return_value = Mock()
        mock_setup.side_effect = Exception("Setup error")

        agent = ExecutorAgent()
        result = await agent.initialize()

        assert result is False


class TestExecutorAgentSetupEnvironment:
    """Test execution environment setup"""

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.aiohttp.ClientSession")
    @patch("src.core.agents.executor_agent.Path")
    async def test_setup_environment_creates_workspace(self, mock_path, mock_session):
        """Test environment setup creates workspace directory"""
        mock_dir = Mock()
        mock_path.return_value = mock_dir
        mock_session.return_value = Mock()

        agent = ExecutorAgent()
        await agent._setup_execution_environment()

        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert agent.http_session is not None

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.aiohttp.ClientSession")
    @patch("src.core.agents.executor_agent.Path")
    async def test_setup_environment_error_handling(self, mock_path, mock_session):
        """Test environment setup error handling"""
        mock_path.side_effect = Exception("Filesystem error")

        agent = ExecutorAgent()

        with pytest.raises(Exception) as exc_info:
            await agent._setup_execution_environment()

        assert "Filesystem error" in str(exc_info.value)


class TestExecutorAgentCapabilities:
    """Test agent capabilities"""

    @pytest.mark.asyncio
    async def test_get_capabilities_returns_list(self):
        """Test get_capabilities returns list of capabilities"""
        agent = ExecutorAgent()

        capabilities = await agent.get_capabilities()

        assert isinstance(capabilities, list)
        assert len(capabilities) == 10

    @pytest.mark.asyncio
    async def test_api_integration_capability(self):
        """Test API integration capability"""
        agent = ExecutorAgent()

        capabilities = await agent.get_capabilities()
        api_cap = next(c for c in capabilities if c.name == "api_integration")

        assert api_cap is not None
        assert "REST API" in api_cap.description
        assert "network" in api_cap.resource_requirements

    @pytest.mark.asyncio
    async def test_workflow_automation_capability(self):
        """Test workflow automation capability"""
        agent = ExecutorAgent()

        capabilities = await agent.get_capabilities()
        wf_cap = next(c for c in capabilities if c.name == "workflow_automation")

        assert wf_cap is not None
        assert "workflow_result" in wf_cap.output_types
        assert wf_cap.resource_requirements["memory"] == "1GB"

    @pytest.mark.asyncio
    async def test_file_operations_capability(self):
        """Test file operations capability"""
        agent = ExecutorAgent()

        capabilities = await agent.get_capabilities()
        file_cap = next(c for c in capabilities if c.name == "file_operations")

        assert file_cap is not None
        assert "storage" in file_cap.resource_requirements
        assert "file_result" in file_cap.output_types


class TestExecutorAgentTaskProcessing:
    """Test task processing functionality"""

    @pytest.mark.asyncio
    async def test_process_task_is_not_overridden_by_subclass(self):
        """ExecutorAgent must NOT override process_task() -- doing so would bypass
        EnhancedBaseAgent's governance pipeline (GDPR opt-out, EU-AI-006
        governance-contract check, prompt-injection sanitisation). process_task must
        stay the inherited base-class template method, which itself calls
        _execute_task() (the real business logic, tested separately below)."""
        from src.core.agents.base_agent import EnhancedBaseAgent

        assert ExecutorAgent.process_task is EnhancedBaseAgent.process_task

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    async def test_process_task_safety_check_fails(self, mock_safety):
        """Test process_task handles failed safety check"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-unsafe",
            title="Unsafe Task",
            description="Task that fails safety check",
            metadata={"type": "system_commands"},
        )

        mock_safety.return_value = {
            "safe": False,
            "reason": "Dangerous command detected",
        }

        result = await agent.process_task(task)

        assert result.success is False
        assert "Safety check failed" in result.error_message
        assert "Dangerous command" in result.error_message

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    @patch("src.core.agents.executor_agent.ExecutorAgent._execute_api_integration")
    async def test_process_task_api_integration(self, mock_execute, mock_safety):
        """Test process_task routes to API integration"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-api",
            title="API Integration",
            description="Execute API call",
            metadata={"type": "api_integration"},
        )

        mock_safety.return_value = {"safe": True}
        mock_execute.return_value = {
            "status_code": 200,
            "response": "Success",
            "execution_status": "completed",
        }

        result = await agent.process_task(task)

        assert result.success is True
        assert result.task_id == "task-api"
        mock_execute.assert_called_once_with(task)

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    @patch("src.core.agents.executor_agent.ExecutorAgent._execute_workflow_automation")
    async def test_process_task_workflow_automation(self, mock_execute, mock_safety):
        """Test process_task routes to workflow automation"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-workflow",
            title="Workflow Automation",
            description="Execute workflow",
            metadata={"type": "workflow_automation"},
        )

        mock_safety.return_value = {"safe": True}
        mock_execute.return_value = {"execution_status": "completed", "steps": 5}

        result = await agent.process_task(task)

        assert result.success is True
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    @patch("src.core.agents.executor_agent.ExecutorAgent._execute_file_operations")
    async def test_process_task_file_operations(self, mock_execute, mock_safety):
        """Test process_task routes to file operations"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-file",
            title="File Operations",
            description="Perform file operations",
            metadata={"type": "file_operations"},
        )

        mock_safety.return_value = {"safe": True}
        mock_execute.return_value = {
            "execution_status": "completed",
            "files_processed": 10,
        }

        result = await agent.process_task(task)

        assert result.success is True
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    async def test_process_task_error_handling(self, mock_safety):
        """Test process_task handles errors"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-error",
            title="Error Task",
            description="Task that will fail",
            metadata={"type": "api_integration"},
        )

        mock_safety.return_value = {"safe": True}

        with patch.object(
            agent, "_execute_api_integration", side_effect=Exception("Execution error")
        ):
            result = await agent.process_task(task)

            assert result.success is False
            assert "Execution error" in result.error_message

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    @patch("src.core.agents.executor_agent.ExecutorAgent._execute_general_task")
    @patch("src.core.agents.executor_agent.ExecutorAgent._log_execution")
    @patch("src.core.agents.executor_agent.ExecutorAgent._calculate_success_rate")
    async def test_process_task_execution_time_recorded(
        self, mock_success_rate, mock_log, mock_execute, mock_safety
    ):
        """Test execution time is recorded"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-time",
            title="Timed Task",
            description="Test execution time",
            metadata={"type": "general_execution"},
        )

        mock_safety.return_value = {"safe": True, "checks_passed": []}
        mock_execute.return_value = {"execution_status": "completed"}
        mock_success_rate.return_value = 0.95

        result = await agent.process_task(task)

        assert result.execution_time > 0
        assert isinstance(result.execution_time, float)

    @pytest.mark.asyncio
    @patch("src.core.agents.executor_agent.ExecutorAgent._perform_safety_check")
    @patch("src.core.agents.executor_agent.ExecutorAgent._execute_general_task")
    @patch("src.core.agents.executor_agent.ExecutorAgent._log_execution")
    @patch("src.core.agents.executor_agent.ExecutorAgent._calculate_success_rate")
    async def test_process_task_logs_generated(
        self, mock_success_rate, mock_log, mock_execute, mock_safety
    ):
        """Test logs are generated during task processing"""
        agent = ExecutorAgent()

        task = TaskData(
            id="task-logs",
            title="Log Task",
            description="Test logging",
            metadata={"type": "general_execution"},
        )

        mock_safety.return_value = {"safe": True, "checks_passed": []}
        mock_execute.return_value = {"execution_status": "completed"}
        mock_success_rate.return_value = 0.98

        result = await agent.process_task(task)

        assert len(result.logs) > 0
        assert any("ExecutorAgent" in log for log in result.logs)
