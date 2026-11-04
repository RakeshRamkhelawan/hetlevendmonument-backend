"""
Slice 6: ComplianceAgent Implementation (GREEN Phase - Minimal Code)

Policy compliance checking agent with RBAC enforcement and tenant isolation.

Responsibilities:
- Validate policy compliance
- Enforce RBAC (role-based access control)
- Enforce tenant isolation
- Detect policy violations
- Provide remediation guidance
"""

import logging
from typing import Any, cast

from src.core.agents.capabilities.schemas import (
    ComplianceContext,
    ComplianceIssue,
    ComplianceResult,
    ComplianceStatus,
)

logger = logging.getLogger(__name__)


class ComplianceAgent:
    """
    Policy compliance checking agent for action validation.

    Checks actions against policies (RBAC, privacy, security, financial)
    and returns compliance status with remediation guidance.
    """

    # Mock policy rules for development
    BLOCKED_ACTIONS = {
        "delete_sensitive_data",
        "share_pii",
        "disable_encryption",
        "delete_all_data",
        "admin_access",
        "unauthorized_admin_action",
        "access_restricted_resource",
    }

    WARNING_ACTIONS = {
        "export_data",
        "export_sensitive_data",
        "bulk_update",
    }

    SENSITIVE_RESOURCES = {
        "pii_database",
        "customer_pii",
        "data_store",
        "production_database",
        "confidential_docs",
        "customer_data",
        "pii_db",
        "system_critical",
    }

    def __init__(self) -> None:
        """Initialize ComplianceAgent."""
        logger.info("ComplianceAgent initialized")

    async def check_compliance(self, context: ComplianceContext) -> ComplianceResult:
        """
        Check compliance for an action.

        Args:
            context: ComplianceContext with action, resource, tenant, user

        Returns:
            ComplianceResult with status, issues, and passed checks
        """
        logger.info(
            f"Starting compliance check for action '{context.action}' on resource '{context.target_resource}'"
        )

        # Validate context
        self._validate_context(context)

        issues: list[ComplianceIssue] = []
        passed_checks: list[str] = []

        # Run compliance checks
        issues.extend(self._check_rbac(context, passed_checks))
        issues.extend(self._check_tenant_isolation(context, passed_checks))
        issues.extend(self._check_data_privacy(context, passed_checks))
        issues.extend(self._check_financial_policy(context, passed_checks))
        issues.extend(self._check_security_policy(context, passed_checks))

        # Check catch-all blocked/warning actions
        issues.extend(self._check_action_lists(context, passed_checks))

        # Determine overall status
        status = self._determine_status(context, issues)

        logger.info(
            f"Compliance check completed: status={status.value}, issues={len(issues)}, passed={len(passed_checks)}"
        )

        if status == ComplianceStatus.BLOCKED:
            logger.warning(f"Action '{context.action}' blocked due to policy violations")

        return ComplianceResult(
            status=status,
            issues=issues,
            passed_checks=passed_checks,
        )

    def _check_rbac(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check role-based access control."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for admin-only actions
        if context.action in ["admin_access", "unauthorized_admin_action"]:
            issues.append(
                ComplianceIssue(
                    policy_violated="RBAC: Insufficient permissions",
                    severity="critical",
                    message=f"Action '{context.action}' requires admin permissions",
                    remediation="Request admin access or contact system administrator",
                )
            )
        elif context.action == "modify_role":
            issues.append(
                ComplianceIssue(
                    policy_violated="RBAC: Role modification restricted",
                    severity="critical",
                    message=f"Action '{context.action}' requires elevated permissions and approval",
                    remediation="Contact system administrator or security team for role modifications",
                )
            )
        else:
            passed_checks.append("rbac_check")

        # Check approval limits for financial actions
        if context.action == "approve_payment":
            amount = cast(int, context.parameters.get("amount", 0))
            if amount > 10000:
                issues.append(
                    ComplianceIssue(
                        policy_violated="Financial policy: Approval limit exceeded",
                        severity="warning",
                        message=f"Payment amount ${amount} exceeds single-user approval limit",
                        remediation="Obtain secondary approval from manager or director",
                    )
                )
            else:
                passed_checks.append("approval_limit_check")

        return issues

    def _check_tenant_isolation(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check tenant boundary enforcement."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Extract tenant from resource or parameters
        resource_tenant_marker = f"tenant_{context.parameters.get('requesting_tenant', '')}"

        if resource_tenant_marker in context.target_resource:
            # Check if requesting tenant matches context tenant
            if str(context.tenant_id) not in context.target_resource:
                issues.append(
                    ComplianceIssue(
                        policy_violated="Tenant isolation: Cross-tenant access",
                        severity="critical",
                        message="Cannot access resources from different tenant",
                        remediation="Request access through proper tenant-sharing workflow",
                    )
                )
            else:
                passed_checks.append("tenant_isolation_check")
        else:
            # No cross-tenant concern
            passed_checks.append("tenant_isolation_check")

        return issues

    def _check_data_privacy(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check data privacy policies."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for PII/sensitive data actions
        if context.action == "share_pii":
            recipient = cast(str, context.parameters.get("recipient", ""))
            if "external" in recipient.lower():
                issues.append(
                    ComplianceIssue(
                        policy_violated="Data privacy: External PII sharing prohibited",
                        severity="critical",
                        message="Cannot share PII with external parties without consent",
                        remediation="Obtain user consent and legal approval before sharing PII",
                    )
                )
            else:
                passed_checks.append("pii_sharing_check")
        else:
            passed_checks.append("data_privacy_check")

        # Check export of sensitive data
        if context.action == "export_sensitive_data":
            issues.append(
                ComplianceIssue(
                    policy_violated="Data privacy: Sensitive data export",
                    severity="warning",
                    message="Exporting sensitive data for external use",
                    remediation="Ensure data anonymization and obtain required approvals",
                )
            )

        return issues

    def _check_financial_policy(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check financial compliance policies."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if context.action == "approve_invoice":
            amount = cast(int, context.parameters.get("amount", 0))
            if amount > 10000:
                issues.append(
                    ComplianceIssue(
                        policy_violated="Financial policy: High-value approval",
                        severity="warning",
                        message=f"Invoice amount ${amount} requires additional approval",
                        remediation="Obtain director-level approval for invoices over $10,000",
                    )
                )
            else:
                passed_checks.append("financial_approval_check")
        else:
            passed_checks.append("financial_policy_check")

        return issues

    def _check_security_policy(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check security policies."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for security-critical actions
        if context.action == "disable_encryption":
            issues.append(
                ComplianceIssue(
                    policy_violated="Security policy: Encryption required",
                    severity="critical",
                    message="Cannot disable encryption on data stores",
                    remediation="Maintain encryption at all times; contact security team if exception needed",
                )
            )
        elif context.action == "delete_all_data":
            issues.append(
                ComplianceIssue(
                    policy_violated="Security policy: Mass deletion prohibited",
                    severity="critical",
                    message="Mass data deletion requires manual approval",
                    remediation="Contact security team and obtain written approval for data deletion",
                )
            )
        else:
            passed_checks.append("security_policy_check")

        # Check bulk operations
        if context.action == "bulk_update":
            count = cast(int, context.parameters.get("count", 0))
            if count > 50:
                issues.append(
                    ComplianceIssue(
                        policy_violated="Security policy: Bulk operation limit",
                        severity="warning",
                        message=f"Bulk update of {count} records exceeds recommended limit",
                        remediation="Consider batching operations or review for unintended impact",
                    )
                )

        return issues

    def _check_action_lists(
        self, context: ComplianceContext, passed_checks: list[str]
    ) -> list[ComplianceIssue]:
        """Check if action is in catch-all blocked or warning lists."""
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check if action is in blocked list (and not already handled by specific checks)
        if context.action in self.BLOCKED_ACTIONS:
            # Only add issue if not already caught by specific policy checks
            issues.append(
                ComplianceIssue(
                    policy_violated="General policy: Blocked action",
                    severity="critical",
                    message=f"Action '{context.action}' is not permitted",
                    remediation="Contact system administrator for alternative approaches",
                )
            )

        # Check if action is in warning list (and not already handled)
        elif context.action in self.WARNING_ACTIONS:
            issues.append(
                ComplianceIssue(
                    policy_violated="General policy: Risky action",
                    severity="warning",
                    message=f"Action '{context.action}' requires caution and review",
                    remediation="Obtain proper approval and review before proceeding",
                )
            )
        else:
            passed_checks.append("action_list_check")

        return issues

    def _determine_status(
        self, context: ComplianceContext, issues: list[ComplianceIssue]
    ) -> ComplianceStatus:
        """Determine overall compliance status based on issues."""
        # Check for critical issues
        critical_issues = [i for i in issues if i.severity == "critical"]
        if critical_issues:
            return ComplianceStatus.BLOCKED

        # Check for warnings
        warning_issues = [i for i in issues if i.severity == "warning"]
        if warning_issues:
            return ComplianceStatus.WARNING

        # Check if action is in blocked list (catch-all)
        if context.action in self.BLOCKED_ACTIONS:
            return ComplianceStatus.BLOCKED

        # Check if action is in warning list (catch-all)
        if context.action in self.WARNING_ACTIONS:
            return ComplianceStatus.WARNING

        # Check if resource is sensitive
        if context.target_resource in self.SENSITIVE_RESOURCES:
            # Sensitive resource access requires explicit check pass
            if not issues:
                return ComplianceStatus.ALLOWED
            return ComplianceStatus.BLOCKED

        # Default: allowed
        return ComplianceStatus.ALLOWED

    def _validate_context(self, context: ComplianceContext) -> None:
        """
        Validate ComplianceContext inputs.

        Args:
            context: ComplianceContext to validate

        Raises:
            ValueError: If validation fails
        """
        if not context.action or context.action.strip() == "":
            raise ValueError("action is required and must be non-empty")

        if not context.tenant_id:
            raise ValueError("tenant_id is required")

        if not context.user_id:
            raise ValueError("user_id is required")

        logger.debug(f"Context validation passed for action '{context.action}'")
