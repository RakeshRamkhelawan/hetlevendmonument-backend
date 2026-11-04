"""Oversight Gate for EU AI Act compliance.

Task 2: Pre-execution Governance
Implements fail-closed pre-execution validation combining:
- Risk classification (from ai_act_classifier)
- Policy validation (via PolicyEngine)
- Audit logging (via AuditService)

Reference: Regulation (EU) 2024/1689 Article 14 (Human Oversight)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from src.core.governance.ai_act_classifier import AIActRiskLevel, classify_agent

logger = logging.getLogger(__name__)


@dataclass
class OversightResult:
    """Result of oversight gate check.

    Attributes:
        allowed: Whether execution is permitted
        requires_human_approval: Whether human approval is required first
        risk_level: EU AI Act risk level of the agent/action
        reason: Human-readable explanation of the decision
    """

    allowed: bool
    requires_human_approval: bool
    risk_level: AIActRiskLevel
    reason: str


class PolicyEngineProtocol(Protocol):
    """Protocol for policy engine dependency."""

    async def validate_action(
        self,
        action: str,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate action against policies.

        Returns:
            Dict with 'allowed' (bool) and 'violations' (list)
        """
        ...


class AuditServiceProtocol(Protocol):
    """Protocol for audit service dependency."""

    async def log_security_event(
        self,
        event_type: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Log security event for audit trail."""
        ...


class OversightGate:
    """Pre-execution oversight gate for EU AI Act compliance.

    Implements fail-closed governance:
    - Blocks execution on policy violations
    - Requires human approval for high-risk actions
    - Logs all decisions for audit trail
    - Blocks on errors (never fails open)

    Args:
        policy_engine: Policy validation service
        audit_service: Audit logging service
    """

    # Actions that always require human approval (breakthrough actions)
    BREAKTHROUGH_ACTIONS = {
        "code_generation",
        "file_creation",
        "database_migration",
        "deployment",
        "config_change",
        "permission_change",
    }

    def __init__(
        self,
        policy_engine: PolicyEngineProtocol | None = None,
        audit_service: AuditServiceProtocol | None = None,
    ) -> None:
        """Initialize oversight gate.

        Args:
            policy_engine: Service for policy validation
            audit_service: Service for audit logging
        """
        self.policy_engine = policy_engine
        self.audit_service = audit_service
        logger.info("OversightGate initialized")

    async def check(
        self,
        agent_name: str,
        agent_department: str,
        agent_specialisation: str,
        agent_capabilities: list[str],
        task_action: str,
        task_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> OversightResult:
        """Check if agent action is permitted.

        Performs risk classification, policy validation, and determines
        if human approval is required.

        Args:
            agent_name: Name of the agent
            agent_department: Department the agent belongs to
            agent_specialisation: Agent's specialisation
            agent_capabilities: List of agent capabilities
            task_action: Action the agent wants to perform
            task_params: Parameters for the action
            tenant_id: Optional tenant context
            user_id: Optional user context

        Returns:
            OversightResult with decision and metadata
        """
        try:
            # Step 1: Risk classification
            risk_level = classify_agent(
                name=agent_name,
                department=agent_department,
                specialisation=agent_specialisation,
                capabilities=agent_capabilities,
            )

            # Step 1b: Art. 5 absolute block -- no policy override, no human approval
            if risk_level == AIActRiskLevel.UNACCEPTABLE:
                result = OversightResult(
                    allowed=False,
                    requires_human_approval=False,
                    risk_level=AIActRiskLevel.UNACCEPTABLE,
                    reason="BLOCKED: Article 5 EU AI Act prohibits this capability.",
                )
                await self._log_decision(result, agent_name, task_action, tenant_id)
                return result

            # Step 2: Department assignment validation (Task #4)
            dept_validation = self._validate_department_assignment(
                agent_name=agent_name,
                agent_department=agent_department,
                task_params=task_params,
                tenant_id=tenant_id,
            )
            if dept_validation:
                await self._log_decision(dept_validation, agent_name, task_action, tenant_id)
                return dept_validation

            # Step 3: Policy validation (if policy engine available)
            policy_violations: list[str] = []
            if self.policy_engine:
                try:
                    policy_result = await self.policy_engine.validate_action(
                        action=task_action,
                        params=task_params,
                        context={
                            "agent_name": agent_name,
                            "agent_department": agent_department,
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                        },
                    )
                    if not policy_result.get("allowed", True):
                        policy_violations = policy_result.get("violations", ["Policy violation"])
                except Exception as e:
                    logger.error(f"Policy validation error: {e}")
                    # Fail closed on policy error
                    return OversightResult(
                        allowed=False,
                        requires_human_approval=False,
                        risk_level=risk_level,
                        reason=f"Policy validation error: {e}",
                    )

            # Step 4: Determine if human approval is required
            requires_approval = False
            reason_parts: list[str] = []

            # High-risk agents require approval
            if risk_level == AIActRiskLevel.HIGH_RISK:
                requires_approval = True
                reason_parts.append("High-risk agent requires human approval")

            # Breakthrough actions require approval
            if task_action in self.BREAKTHROUGH_ACTIONS:
                requires_approval = True
                reason_parts.append(f"Breakthrough action '{task_action}' requires approval")

            # Policy violations block execution
            if policy_violations:
                result = OversightResult(
                    allowed=False,
                    requires_human_approval=False,
                    risk_level=risk_level,
                    reason=f"Policy violations: {', '.join(policy_violations)}",
                )
                await self._log_decision(result, agent_name, task_action, tenant_id)
                return result

            # Build success reason
            if not reason_parts:
                reason = f"{risk_level.value} risk operation approved"
            else:
                reason = "; ".join(reason_parts)

            result = OversightResult(
                allowed=True,
                requires_human_approval=requires_approval,
                risk_level=risk_level,
                reason=reason,
            )

            await self._log_decision(result, agent_name, task_action, tenant_id)
            return result

        except Exception as e:
            logger.error(f"Oversight gate error: {e}")
            # Fail closed on any error
            return OversightResult(
                allowed=False,
                requires_human_approval=False,
                risk_level=AIActRiskLevel.HIGH_RISK,  # Assume worst case
                reason=f"Oversight gate error: {e}",
            )

    def _validate_department_assignment(
        self,
        agent_name: str,
        agent_department: str,
        task_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int | None,
    ) -> OversightResult | None:
        """Task #4: Validate department assignment compatibility.

        Checks if agent's department matches the task's required_department.
        Returns OversightResult rejection if there's a mismatch.
        Allows "unassigned" agents to execute any department task.

        Args:
            agent_name: Name of the agent
            agent_department: Department the agent belongs to
            task_params: Task parameters (may contain required_department)
            tenant_id: Optional tenant context for logging

        Returns:
            OversightResult rejection if validation fails, None if validation passes
        """
        # Extract required_department from task parameters
        required_department = task_params.get("required_department") or task_params.get("department")

        # No requirement specified -- validation passes
        if not required_department:
            return None

        # Normalize department names for comparison
        required_dept_normalized = str(required_department).lower().strip()
        agent_dept_normalized = str(agent_department).lower().strip()

        # "unassigned" agents are universal and can execute any department task
        if agent_dept_normalized == "unassigned":
            logger.debug(
                "[OVERSIGHT] Department validation: unassigned agent %s allowed for %s task",
                agent_name,
                required_department,
                extra={"tenant_id": tenant_id, "agent": agent_name},
            )
            return None

        # Validate exact department match
        if agent_dept_normalized != required_dept_normalized:
            logger.warning(
                "[OVERSIGHT] Department validation failed: %s (dept=%s) cannot execute %s task",
                agent_name,
                agent_department,
                required_department,
                extra={
                    "tenant_id": tenant_id,
                    "agent": agent_name,
                    "agent_dept": agent_department,
                    "required_dept": required_department,
                },
            )
            result = OversightResult(
                allowed=False,
                requires_human_approval=False,
                risk_level=AIActRiskLevel.HIGH_RISK,
                reason=f"Department mismatch: Agent ({agent_department}) cannot execute {required_department} task",
            )
            return result

        # Department matches -- validation passes
        logger.debug(
            "[OVERSIGHT] Department validation passed: %s (dept=%s) allowed for %s task",
            agent_name,
            agent_department,
            required_department,
            extra={"tenant_id": tenant_id, "agent": agent_name},
        )
        return None

    async def _log_decision(
        self,
        result: OversightResult,
        agent_name: str,
        task_action: str,
        tenant_id: int | None,
    ) -> None:
        """Log oversight decision to audit trail.

        Args:
            result: Oversight decision
            agent_name: Name of agent
            task_action: Action being performed
            tenant_id: Optional tenant context
        """
        if not self.audit_service:
            return

        try:
            # Include department validation flag if reason mentions department mismatch
            is_dept_validation = "Department mismatch" in result.reason or "Department validation" in result.reason
            await self.audit_service.log_security_event(
                event_type="OVERSIGHT_DECISION",
                details={
                    "agent_name": agent_name,
                    "action": task_action,
                    "allowed": result.allowed,
                    "requires_human_approval": result.requires_human_approval,
                    "risk_level": result.risk_level.value,
                    "reason": result.reason,
                    "tenant_id": tenant_id,
                    "department_validation": is_dept_validation,
                },
            )
        except Exception as e:
            logger.error(f"Failed to log oversight decision: {e}")
