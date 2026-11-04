"""
Comprehensive tests for src/core/types.py
Coverage target: 100% of types module
"""

from enum import Enum

import pytest

from src.core.types import (
    AgentStatus,
    AgentType,
    IsolationLevel,
    TaskPriority,
    TaskStatus,
    TriggerType,
    WorkflowState,
)


class TestTriggerType:
    """Test TriggerType enum"""

    def test_trigger_type_values(self):
        """Test TriggerType has all expected values"""
        # Assert
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.SCHEDULED.value == "scheduled"
        assert TriggerType.AUTO.value == "auto"
        assert TriggerType.EVENT_DRIVEN.value == "event_driven"
        assert TriggerType.INTELLIGENT.value == "intelligent"
        assert TriggerType.USER_INITIATED.value == "user_initiated"
        assert TriggerType.EMERGENCY.value == "emergency"

    def test_trigger_type_is_string_enum(self):
        """Test TriggerType is a string enum"""
        # Assert
        assert issubclass(TriggerType, str)
        assert issubclass(TriggerType, Enum)

    def test_trigger_type_all_members(self):
        """Test TriggerType has all expected members"""
        # Arrange
        expected = {
            "MANUAL",
            "SCHEDULED",
            "AUTO",
            "EVENT_DRIVEN",
            "INTELLIGENT",
            "USER_INITIATED",
            "EMERGENCY",
        }

        # Act
        actual = {member.name for member in TriggerType}

        # Assert
        assert actual == expected


class TestWorkflowState:
    """Test WorkflowState enum"""

    def test_workflow_state_values(self):
        """Test WorkflowState has all expected values"""
        # Assert
        assert WorkflowState.PENDING.value == "pending"
        assert WorkflowState.RUNNING.value == "running"
        assert WorkflowState.SUCCEEDED.value == "succeeded"
        assert WorkflowState.FAILED.value == "failed"
        assert WorkflowState.CANCELLED.value == "cancelled"
        assert WorkflowState.TIMEOUT.value == "timeout"

    def test_workflow_state_is_string_enum(self):
        """Test WorkflowState is a string enum"""
        # Assert
        assert issubclass(WorkflowState, str)
        assert issubclass(WorkflowState, Enum)

    def test_workflow_state_all_members(self):
        """Test WorkflowState has all expected members"""
        # Arrange
        expected = {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"}

        # Act
        actual = {member.name for member in WorkflowState}

        # Assert
        assert actual == expected


class TestTaskStatus:
    """Test TaskStatus enum"""

    def test_task_status_values(self):
        """Test TaskStatus has all expected values"""
        # Assert
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.APPROVAL_REQUIRED.value == "approval_required"

    def test_task_status_is_string_enum(self):
        """Test TaskStatus is a string enum"""
        # Assert
        assert issubclass(TaskStatus, str)
        assert issubclass(TaskStatus, Enum)

    def test_task_status_all_members(self):
        """Test TaskStatus has all expected members"""
        # Arrange
        expected = {
            "PENDING",
            "IN_PROGRESS",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "APPROVAL_REQUIRED",
        }

        # Act
        actual = {member.name for member in TaskStatus}

        # Assert
        assert actual == expected


class TestTaskPriority:
    """Test TaskPriority enum"""

    def test_task_priority_values(self):
        """Test TaskPriority has correct integer values"""
        # Assert
        assert TaskPriority.LOW.value == 1
        assert TaskPriority.MEDIUM.value == 3
        assert TaskPriority.HIGH.value == 5
        assert TaskPriority.CRITICAL.value == 9

    def test_task_priority_is_int_enum(self):
        """Test TaskPriority is an integer enum"""
        # Assert
        assert issubclass(TaskPriority, int)
        assert issubclass(TaskPriority, Enum)

    def test_task_priority_ordering(self):
        """Test TaskPriority values are ordered correctly"""
        # Assert
        assert TaskPriority.LOW < TaskPriority.MEDIUM
        assert TaskPriority.MEDIUM < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.CRITICAL

    def test_task_priority_all_members(self):
        """Test TaskPriority has all expected members"""
        # Arrange
        expected = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        # Act
        actual = {member.name for member in TaskPriority}

        # Assert
        assert actual == expected


class TestAgentType:
    """Test AgentType enum"""

    def test_agent_type_core_values(self):
        """Test AgentType core agent types"""
        # Assert
        assert AgentType.CVA.value == "cva"
        assert AgentType.ORCHESTRATOR.value == "orchestrator"
        assert AgentType.ETHICS.value == "ethics"
        assert AgentType.SPECIALIST.value == "specialist"
        assert AgentType.SANDBOX.value == "sandbox"

    def test_agent_type_domain_values(self):
        """Test AgentType domain agent types"""
        # Assert
        assert AgentType.CORE.value == "core"
        assert AgentType.SPECIALIZED.value == "specialized"
        assert AgentType.ANALYTICAL.value == "analytical"
        assert AgentType.CREATIVE.value == "creative"
        assert AgentType.TECHNICAL.value == "technical"

    def test_agent_type_subagent_values(self):
        """Test AgentType subagent types"""
        # Assert
        assert AgentType.COORDINATOR.value == "coordinator"
        assert AgentType.ANALYZER.value == "analyzer"
        assert AgentType.EXECUTOR.value == "executor"
        assert AgentType.MONITOR.value == "monitor"
        assert AgentType.BRIDGE.value == "bridge"

    def test_agent_type_specialized_subagents(self):
        """Test AgentType specialized subagent types"""
        # Assert
        assert AgentType.DATA_ANALYSIS.value == "data_analysis"
        assert AgentType.SYSTEM_MONITOR.value == "system_monitor"
        assert AgentType.CODE_REVIEWER.value == "code_reviewer"
        assert AgentType.DEPLOYMENT_SPECIALIST.value == "deployment_specialist"
        assert AgentType.SECURITY_AUDITOR.value == "security_auditor"
        assert AgentType.PERFORMANCE_OPTIMIZER.value == "performance_optimizer"

    def test_agent_type_is_string_enum(self):
        """Test AgentType is a string enum"""
        # Assert
        assert issubclass(AgentType, str)
        assert issubclass(AgentType, Enum)

    def test_agent_type_has_many_members(self):
        """Test AgentType has comprehensive list of agent types"""
        # Act
        all_members = {member.name for member in AgentType}

        # Assert - Should have at least 20 different agent types
        assert len(all_members) >= 20

    def test_agent_type_includes_code_execution(self):
        """Test AgentType includes CODE_EXECUTION type"""
        # Assert
        assert AgentType.CODE_EXECUTION.value == "code_execution"

    def test_agent_type_includes_knowledge_retrieval(self):
        """Test AgentType includes KNOWLEDGE_RETRIEVAL type"""
        # Assert
        assert AgentType.KNOWLEDGE_RETRIEVAL.value == "knowledge_retrieval"


class TestAgentStatus:
    """Test AgentStatus enum"""

    def test_agent_status_values(self):
        """Test AgentStatus has all expected values"""
        # Assert
        assert AgentStatus.ACTIVE.value == "active"
        assert AgentStatus.INACTIVE.value == "inactive"
        assert AgentStatus.TRAINING.value == "training"
        assert AgentStatus.ARCHIVED.value == "archived"

    def test_agent_status_is_string_enum(self):
        """Test AgentStatus is a string enum"""
        # Assert
        assert issubclass(AgentStatus, str)
        assert issubclass(AgentStatus, Enum)

    def test_agent_status_all_members(self):
        """Test AgentStatus has all expected members"""
        # Arrange
        expected = {"ACTIVE", "INACTIVE", "TRAINING", "ARCHIVED"}

        # Act
        actual = {member.name for member in AgentStatus}

        # Assert
        assert actual == expected


class TestIsolationLevel:
    """Test IsolationLevel enum"""

    def test_isolation_level_values(self):
        """Test IsolationLevel has all expected values"""
        # Assert
        assert IsolationLevel.MOCK.value == "mock"
        assert IsolationLevel.PROCESS.value == "process"
        assert IsolationLevel.CONTAINER.value == "container"
        assert IsolationLevel.DOCKER.value == "docker"
        assert IsolationLevel.VM.value == "vm"

    def test_isolation_level_is_string_enum(self):
        """Test IsolationLevel is a string enum"""
        # Assert
        assert issubclass(IsolationLevel, str)
        assert issubclass(IsolationLevel, Enum)

    def test_isolation_level_all_members(self):
        """Test IsolationLevel has all expected members"""
        # Arrange
        expected = {"MOCK", "PROCESS", "CONTAINER", "DOCKER", "VM"}

        # Act
        actual = {member.name for member in IsolationLevel}

        # Assert
        assert actual == expected


class TestModuleStructure:
    """Test module organization and exports"""

    def test_module_exports_all_enums(self):
        """Test module exports all expected enums"""
        # Act
        import src.core.types as types_module

        # Assert
        assert hasattr(types_module, "TriggerType")
        assert hasattr(types_module, "WorkflowState")
        assert hasattr(types_module, "TaskStatus")
        assert hasattr(types_module, "TaskPriority")
        assert hasattr(types_module, "AgentType")
        assert hasattr(types_module, "AgentStatus")
        assert hasattr(types_module, "IsolationLevel")

    def test_all_exports_are_enums(self):
        """Test all exported types are Enum classes"""
        # Arrange
        import src.core.types as types_module

        enums_to_test = [
            types_module.TriggerType,
            types_module.WorkflowState,
            types_module.TaskStatus,
            types_module.TaskPriority,
            types_module.AgentType,
            types_module.AgentStatus,
            types_module.IsolationLevel,
        ]

        # Assert
        for enum_class in enums_to_test:
            assert issubclass(enum_class, Enum)


class TestEnumUsability:
    """Test enums can be used in practical scenarios"""

    def test_trigger_type_can_be_compared(self):
        """Test TriggerType values can be compared"""
        # Act & Assert
        assert TriggerType.MANUAL == TriggerType.MANUAL
        assert TriggerType.MANUAL != TriggerType.SCHEDULED

    def test_workflow_state_can_be_used_in_conditions(self):
        """Test WorkflowState can be used in conditional logic"""
        # Arrange
        state = WorkflowState.RUNNING

        # Act & Assert
        if state == WorkflowState.RUNNING:
            success = True
        else:
            success = False

        assert success is True

    def test_task_priority_can_be_sorted(self):
        """Test TaskPriority values can be sorted"""
        # Arrange
        priorities = [
            TaskPriority.LOW,
            TaskPriority.CRITICAL,
            TaskPriority.MEDIUM,
            TaskPriority.HIGH,
        ]

        # Act
        sorted_priorities = sorted(priorities)

        # Assert
        assert sorted_priorities[0] == TaskPriority.LOW
        assert sorted_priorities[1] == TaskPriority.MEDIUM
        assert sorted_priorities[2] == TaskPriority.HIGH
        assert sorted_priorities[3] == TaskPriority.CRITICAL

    def test_agent_type_value_matches_string(self):
        """Test AgentType value can be used as string"""
        # Arrange
        agent_type = AgentType.CVA

        # Act
        type_str = agent_type.value

        # Assert
        assert type_str == "cva"
        assert isinstance(type_str, str)

    def test_enums_can_be_created_from_string(self):
        """Test enums can be created from their string values"""
        # Act & Assert
        assert TriggerType("manual") == TriggerType.MANUAL
        assert WorkflowState("pending") == WorkflowState.PENDING
        assert TaskStatus("completed") == TaskStatus.COMPLETED
        assert AgentStatus("active") == AgentStatus.ACTIVE
        assert IsolationLevel("docker") == IsolationLevel.DOCKER
