"""
Audit Logger - Slice 4
Sprint 4 - S4.4: Audit logger per step & User feedback loop

Provides structured audit logging for:
- Compliance tracking
- Procedure execution history
- Feedback loop integration
- PII redaction
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.models import ProcedureExecution


class AuditLogger:
    """
    Structured audit logger for procedure executions.

    Features:
    - Writes to procedure_execution.audit_trail (JSONB)
    - Outputs to stdout in JSON format (for Fluentd/log aggregators)
    - Automatic PII redaction
    - Feedback metadata support
    """

    # Sensitive field names to redact
    SENSITIVE_KEYS = {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "api_token",
        "auth_token",
        "bearer",
        "credential",
        "private_key",
        "ssn",
        "social_security",
        "credit_card",
        "cvv",
    }

    def __init__(self, db: AsyncSession, write_to_stdout: bool = False) -> None:
        """
        Initialize Audit Logger.

        Args:
            db: Database session
            write_to_stdout: Whether to write events to stdout (for log aggregation)
        """
        self.db = db
        self.write_to_stdout = write_to_stdout

    def _redact_sensitive_data(
        self,
        data: Any,  # TODO(TYPE): replace Any with recursive JsonValue alias when Python 3.12+ TypeAlias is available
    ) -> Any:  # TODO(TYPE): recursive JSON type: str | int | float | bool | None | dict[str, Any] | list[Any]
        """
        Recursively redact sensitive data from dict/list structures.

        Args:
            data: Data structure to redact

        Returns:
            Data with sensitive fields redacted
        """
        if isinstance(data, dict):
            return {
                key: (
                    "***REDACTED***"
                    if key.lower() in self.SENSITIVE_KEYS
                    else self._redact_sensitive_data(value)
                )
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [self._redact_sensitive_data(item) for item in data]
        else:
            return data

    async def log_step_event(
        self,
        execution_id: UUID,
        step_name: str,
        capability: str,
        inputs: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): inputs are caller-defined; narrow per call-site if needed
        outputs: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): outputs are caller-defined; narrow per call-site if needed
        status: str,
        error_message: str | None = None,
        error_type: str | None = None,
        metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        | None = None,  # TODO(TYPE): metadata is caller-defined; narrow per call-site if needed
    ) -> dict[str, Any]:  # TODO(TYPE): AuditEvent TypedDict when all call-sites are known  # TODO(TYPE): replace Any with concrete type
        """
        Log a procedure step execution event.

        Args:
            execution_id: Procedure execution ID
            step_name: Name of the step
            capability: Capability type (planner/retriever/executor/compliance/reviewer)
            inputs: Step input data
            outputs: Step output data
            status: Execution status (success/failed/completed)
            error_message: Optional error message
            error_type: Optional error type
            metadata: Optional metadata (e.g., feedback)

        Returns:
            The logged event dict
        """
        # Create event structure
        event = {
            "execution_id": str(execution_id),
            "step_name": step_name,
            "capability": capability,
            "inputs": self._redact_sensitive_data(inputs),
            "outputs": self._redact_sensitive_data(outputs),
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        # Add error details if present
        if error_message:
            event["error_message"] = error_message
        if error_type:
            event["error_type"] = error_type

        # Add metadata if present
        if metadata:
            event["metadata"] = metadata

        # Write to stdout for Fluentd/log aggregation
        if self.write_to_stdout:
            print(json.dumps(event), file=sys.stdout, flush=True)

        # Persist to database (append to audit_trail JSONB array)
        await self._append_to_audit_trail(execution_id, event)

        return event

    async def _append_to_audit_trail(
        self, execution_id: UUID, event: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): event should be AuditEvent TypedDict
        """
        Append event to procedure_execution.audit_trail in database.

        Args:
            execution_id: Procedure execution ID
            event: Event dict to append
        """
        # First, get current audit_trail
        stmt = select(ProcedureExecution).where(ProcedureExecution.id == execution_id)
        result = await self.db.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            # Append to existing trail
            current_trail = execution.audit_trail or []
            current_trail.append(event)

            # Update database
            update_stmt = (
                update(ProcedureExecution)
                .where(ProcedureExecution.id == execution_id)
                .values(audit_trail=current_trail)
            )
            await self.db.execute(update_stmt)
            await self.db.commit()

    async def get_audit_trail(
        self, execution_id: UUID
    ) -> list[dict[str, Any]]:  # TODO(TYPE): list[AuditEvent] once TypedDict is defined  # TODO(TYPE): replace Any with concrete type
        """
        Retrieve full audit trail for a procedure execution.

        Args:
            execution_id: Procedure execution ID

        Returns: List of audit event dicts
        """
        stmt = select(ProcedureExecution).where(ProcedureExecution.id == execution_id)
        result = await self.db.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution and execution.audit_trail:
            # SQLAlchemy JSONB column returns list at runtime; cast for mypy
            return cast(
                list[dict[str, Any]], execution.audit_trail  # TODO(TYPE): replace Any with concrete type
            )  # TODO(TYPE): cast to list[AuditEvent] once TypedDict is defined
        return []

    async def log_feedback(
        self,
        execution_id: UUID,
        step_name: str,
        feedback_type: str,
        feedback_value: str | int | float | bool,  # scalar feedback: rating, label, or score
        user_id: int | None = None,
    ) -> None:
        """
        Log user feedback for a procedure step.

        Args:
            execution_id: Procedure execution ID
            step_name: Step that received feedback
            feedback_type: Type of feedback (correct/incorrect/rating/comment)
            feedback_value: Feedback value
            user_id: Optional user ID who provided feedback
        """
        metadata = {
            "feedback_type": feedback_type,
            "feedback_value": feedback_value,
            "feedback_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            metadata["user_id"] = user_id

        await self.log_step_event(
            execution_id=execution_id,
            step_name=step_name,
            capability="feedback",
            inputs={},
            outputs={},
            status="feedback_received",
            metadata=metadata,
        )
