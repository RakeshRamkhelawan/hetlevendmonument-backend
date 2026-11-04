"""
Unit tests for Audit Logger & Feedback - Slice 4

Tests structured audit logging for compliance and improvement.
Sprint 4 - S4.4: Audit logger per step & User feedback loop
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    session = AsyncMock()

    # Mock execute to return a proper result
    mock_result = Mock()
    mock_execution = Mock()
    mock_execution.audit_trail = []
    mock_result.scalar_one_or_none.return_value = mock_execution

    # Set execute as AsyncMock that returns mock_result
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()

    return session


class TestAuditLogger:
    """Test suite for audit logging."""

    @pytest.mark.asyncio
    async def test_log_step_event(self, mock_db_session):
        """JSON structure should contain capability, inputs and timestamp."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        event = await logger.log_step_event(
            execution_id=execution_id,
            step_name="budget_check",
            capability="executor",
            inputs={"amount": 5000, "department": "finance"},
            outputs={"approved": True, "remaining_budget": 10000},
            status="success",
        )

        # Verify event structure
        assert event["execution_id"] == str(execution_id)
        assert event["step_name"] == "budget_check"
        assert event["capability"] == "executor"
        assert event["inputs"] == {"amount": 5000, "department": "finance"}
        assert event["outputs"] == {"approved": True, "remaining_budget": 10000}
        assert event["status"] == "success"
        assert "timestamp" in event

        # Verify timestamp is ISO format
        timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert isinstance(timestamp, datetime)

    @pytest.mark.asyncio
    async def test_sensitive_data_redaction(self, mock_db_session):
        """PII in logs should be masked."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        # Log event with sensitive data
        event = await logger.log_step_event(
            execution_id=execution_id,
            step_name="user_auth",
            capability="executor",
            inputs={
                "username": "john.doe",
                "password": "super_secret_123",
                "api_token": "abc123xyz",
                "secret": "my_secret_value",
                "amount": 5000,  # Not sensitive
            },
            outputs={"success": True},
            status="success",
        )

        # Verify sensitive fields are redacted
        assert event["inputs"]["username"] == "john.doe"  # Not in redaction list
        assert event["inputs"]["password"] == "***REDACTED***"
        assert event["inputs"]["api_token"] == "***REDACTED***"
        assert event["inputs"]["secret"] == "***REDACTED***"
        assert event["inputs"]["amount"] == 5000  # Not redacted

    @pytest.mark.asyncio
    async def test_log_writes_to_stdout_json(self, mock_db_session, capsys):
        """Audit events should be written to stdout in JSON format."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session, write_to_stdout=True)

        execution_id = uuid4()

        await logger.log_step_event(
            execution_id=execution_id,
            step_name="test_step",
            capability="executor",
            inputs={"test": "value"},
            outputs={"result": "success"},
            status="success",
        )

        # Capture stdout
        captured = capsys.readouterr()

        # Verify JSON was written to stdout
        assert captured.out.strip()
        log_line = json.loads(captured.out.strip())
        assert log_line["step_name"] == "test_step"
        assert log_line["capability"] == "executor"

    @pytest.mark.asyncio
    async def test_log_persists_to_database(self, mock_db_session):
        """Audit events should be persisted to procedure_execution.audit_trail."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        await logger.log_step_event(
            execution_id=execution_id,
            step_name="approval_step",
            capability="reviewer",
            inputs={"amount": 10000},
            outputs={"approved": False, "reason": "exceeds_limit"},
            status="completed",
        )

        # Verify database was updated (2 calls: SELECT + UPDATE)
        assert mock_db_session.execute.call_count == 2
        assert mock_db_session.commit.called

    @pytest.mark.asyncio
    async def test_nested_sensitive_data_redaction(self, mock_db_session):
        """Sensitive data in nested structures should be redacted."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        event = await logger.log_step_event(
            execution_id=execution_id,
            step_name="complex_step",
            capability="executor",
            inputs={
                "user": {
                    "name": "John Doe",
                    "password": "secret123",
                    "preferences": {"theme": "dark"},
                },
                "config": {"api_token": "token_xyz", "timeout": 30},
            },
            outputs={},
            status="success",
        )

        # Verify nested redaction
        assert event["inputs"]["user"]["name"] == "John Doe"
        assert event["inputs"]["user"]["password"] == "***REDACTED***"
        assert event["inputs"]["user"]["preferences"]["theme"] == "dark"
        assert event["inputs"]["config"]["api_token"] == "***REDACTED***"
        assert event["inputs"]["config"]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_error_logging(self, mock_db_session):
        """Errors should be logged with stack traces."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        event = await logger.log_step_event(
            execution_id=execution_id,
            step_name="failing_step",
            capability="executor",
            inputs={"test": "value"},
            outputs={},
            status="failed",
            error_message="Budget exceeded",
            error_type="ValidationError",
        )

        # Verify error details
        assert event["status"] == "failed"
        assert event["error_message"] == "Budget exceeded"
        assert event["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_feedback_loop_integration(self, mock_db_session):
        """Audit events should support feedback metadata."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        event = await logger.log_step_event(
            execution_id=execution_id,
            step_name="procedure_match",
            capability="planner",
            inputs={"query": "approve invoice"},
            outputs={"procedure_id": "invoice.approval.v1", "confidence": 0.85},
            status="success",
            metadata={
                "user_feedback": "correct",
                "feedback_timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Verify feedback metadata
        assert "metadata" in event
        assert event["metadata"]["user_feedback"] == "correct"
        assert "feedback_timestamp" in event["metadata"]

    @pytest.mark.asyncio
    async def test_audit_trail_query(self, mock_db_session):
        """Should be able to query audit trail by execution_id."""
        from src.core.observability.audit_logger import AuditLogger

        logger = AuditLogger(mock_db_session)

        execution_id = uuid4()

        # Mock database response with audit trail
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = Mock(
            audit_trail=[
                {"step_name": "step1", "status": "success"},
                {"step_name": "step2", "status": "success"},
            ]
        )
        # Override the execute mock for this specific test
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Get audit trail
        trail = await logger.get_audit_trail(execution_id)

        assert len(trail) == 2
        assert trail[0]["step_name"] == "step1"
        assert trail[1]["step_name"] == "step2"
