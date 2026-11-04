# -*- coding: utf-8 -*-
"""
VIBE_BE_005: Unit Tests for Workflow Models

Target: 95% coverage, 100% pass rate
"""

from datetime import datetime, timezone

import pytest

from src.core.models.workflow_models import (
    ExecutionStatus,
    NodeExecutionStatus,
    WorkflowExecution,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowTemplate,
)

# ============================================================================
# Enum Tests
# ============================================================================


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert WorkflowStatus.DRAFT == "draft"
        assert WorkflowStatus.ACTIVE == "active"
        assert WorkflowStatus.ARCHIVED == "archived"

    def test_all_values_are_strings(self):
        """Test all values are strings."""
        for status in WorkflowStatus:
            assert isinstance(status.value, str)


class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert ExecutionStatus.PENDING == "pending"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.SUCCEEDED == "succeeded"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.CANCELLED == "cancelled"
        assert ExecutionStatus.PAUSED == "paused"

    def test_count(self):
        """Test correct number of statuses."""
        assert len(ExecutionStatus) == 6


class TestNodeExecutionStatus:
    """Tests for NodeExecutionStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert NodeExecutionStatus.PENDING == "pending"
        assert NodeExecutionStatus.RUNNING == "running"
        assert NodeExecutionStatus.SUCCEEDED == "succeeded"
        assert NodeExecutionStatus.FAILED == "failed"
        assert NodeExecutionStatus.SKIPPED == "skipped"


# ============================================================================
# WorkflowTemplate Model Tests
# ============================================================================


class TestWorkflowTemplate:
    """Tests for WorkflowTemplate model."""

    def test_table_name(self):
        """Test table name."""
        assert WorkflowTemplate.__tablename__ == "workflow_templates"

    def test_required_columns(self):
        """Test required columns exist."""
        columns = [c.name for c in WorkflowTemplate.__table__.columns]
        assert "id" in columns
        assert "tenant_id" in columns
        assert "name" in columns
        assert "nodes" in columns
        assert "edges" in columns

    def test_has_indexes(self):
        """Test that indexes are defined."""
        indexes = [idx.name for idx in WorkflowTemplate.__table__.indexes]
        assert len(indexes) >= 2  # At least tenant+name and tenant+status

    def test_default_status(self):
        """Test default status is DRAFT."""
        # Check default from column definition
        status_col = WorkflowTemplate.__table__.columns["status"]
        assert status_col.default.arg == WorkflowStatus.DRAFT


# ============================================================================
# WorkflowInstance Model Tests
# ============================================================================


class TestWorkflowInstance:
    """Tests for WorkflowInstance model."""

    def test_table_name(self):
        """Test table name."""
        assert WorkflowInstance.__tablename__ == "workflow_instances"

    def test_required_columns(self):
        """Test required columns exist."""
        columns = [c.name for c in WorkflowInstance.__table__.columns]
        assert "id" in columns
        assert "tenant_id" in columns
        assert "template_id" in columns
        assert "config" in columns

    def test_has_scheduling_columns(self):
        """Test scheduling columns exist."""
        columns = [c.name for c in WorkflowInstance.__table__.columns]
        assert "schedule_cron" in columns
        assert "is_scheduled" in columns
        assert "next_run_at" in columns


# ============================================================================
# WorkflowExecution Model Tests
# ============================================================================


class TestWorkflowExecution:
    """Tests for WorkflowExecution model."""

    def test_table_name(self):
        """Test table name."""
        assert WorkflowExecution.__tablename__ == "workflow_executions"

    def test_required_columns(self):
        """Test required columns exist."""
        columns = [c.name for c in WorkflowExecution.__table__.columns]
        assert "id" in columns
        assert "tenant_id" in columns
        assert "instance_id" in columns
        assert "execution_id" in columns
        assert "status" in columns

    def test_has_progress_columns(self):
        """Test progress tracking columns exist."""
        columns = [c.name for c in WorkflowExecution.__table__.columns]
        assert "nodes_completed" in columns
        assert "nodes_total" in columns
        assert "progress_percent" in columns

    def test_has_error_columns(self):
        """Test error tracking columns exist."""
        columns = [c.name for c in WorkflowExecution.__table__.columns]
        assert "error_message" in columns
        assert "error_node_id" in columns
        assert "error_details" in columns

    def test_has_timing_columns(self):
        """Test timing columns exist."""
        columns = [c.name for c in WorkflowExecution.__table__.columns]
        assert "started_at" in columns
        assert "completed_at" in columns
        assert "duration_ms" in columns


# ============================================================================
# Model Relationships Tests
# ============================================================================


class TestModelRelationships:
    """Tests for model relationships."""

    def test_template_has_instances_relationship(self):
        """Test WorkflowTemplate has instances relationship."""
        assert hasattr(WorkflowTemplate, "instances")

    def test_instance_has_template_relationship(self):
        """Test WorkflowInstance has template relationship."""
        assert hasattr(WorkflowInstance, "template")

    def test_instance_has_executions_relationship(self):
        """Test WorkflowInstance has executions relationship."""
        assert hasattr(WorkflowInstance, "executions")

    def test_execution_has_instance_relationship(self):
        """Test WorkflowExecution has instance relationship."""
        assert hasattr(WorkflowExecution, "instance")


# ============================================================================
# Model Constraints Tests
# ============================================================================


class TestModelConstraints:
    """Tests for model constraints."""

    def test_execution_id_unique(self):
        """Test execution_id is unique."""
        exec_id_col = WorkflowExecution.__table__.columns["execution_id"]
        assert exec_id_col.unique is True

    def test_tenant_id_not_nullable(self):
        """Test tenant_id is not nullable across models."""
        for model in [WorkflowTemplate, WorkflowInstance, WorkflowExecution]:
            tenant_col = model.__table__.columns["tenant_id"]
            assert tenant_col.nullable is False
