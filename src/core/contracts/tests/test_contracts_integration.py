"""
Integratie tests voor Contract Foundation

Test dat alle modules (capability, policy, enforcement, trace) samenwerken.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from src.core.contracts import (  # Capability; Policy; Enforcement; Trace
    ApprovalThreshold,
    CapabilityContract,
    CapabilityRegistry,
    CapabilityResolver,
    ComplianceProfile,
    EnforcementResult,
    ExecutionTrace,
    PlanTier,
    PolicyEnforcer,
    SpanStatus,
    TenantPolicy,
    TraceBuilder,
)


@pytest.fixture
def registry_with_capabilities():
    """Registry met realistische capabilities."""
    reg = CapabilityRegistry()

    # CRM capabilities
    reg.register(
        CapabilityContract(
            capability_key="crm_create_contact",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "phone": {"type": "string"},
                },
                "required": ["name"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "created_at": {"type": "string"},
                },
            },
        )
    )

    # Email capability
    reg.register(
        CapabilityContract(
            capability_key="email_send",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "attachments": {"type": "array"},
                },
                "required": ["to", "subject", "body"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "sent_at": {"type": "string"},
                },
            },
        )
    )

    # Payment capability
    reg.register(
        CapabilityContract(
            capability_key="payment_process",
            input_schema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["amount", "currency"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        )
    )

    return reg


@pytest.fixture
def pro_policy():
    """Pro tier policy met payment approval."""
    return TenantPolicy(
        tenant_id="tenant-pro-001",
        plan_tier=PlanTier.PRO,
        enabled_capabilities={
            "crm_create_contact",
            "email_send",
            "payment_process",
        },
        approval_thresholds={
            "payment_process": ApprovalThreshold(
                amount_threshold=Decimal("1000.00"),
                approver_roles={"finance_manager", "admin"},
                auto_approve_after_ms=86400000,  # 24h
            ),
        },
        compliance_profile=ComplianceProfile.GDPR,
    )


class TestEndToEndExecution:
    """End-to-end execution flow tests."""

    def test_successful_execution_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Successful execution wordt getraced."""
        # Setup
        enforcer = PolicyEnforcer(registry_with_capabilities)

        # Create trace builder
        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_onboarding",
            user_id="user-123",
        )

        # Workflow node
        node = {
            "capability_key": "crm_create_contact",
            "input": {"name": "John Doe", "email": "john@example.com"},
        }

        # Check permissions
        result = enforcer.check_execute_permission(node, pro_policy)
        assert result.can_execute is True

        # Start node span
        span = builder.start_node_span(
            node_id="create_customer",
            capability_key="crm_create_contact",
            input_data=node["input"],
        )

        # Simulate execution
        span.add_event("input_validated")
        span.add_event("database_insert")

        # End span
        builder.end_span(
            span,
            status=SpanStatus.SUCCESS,
            output_data={"contact_id": "cust-123", "created_at": "2026-01-01T00:00:00Z"},
        )

        # Complete trace
        trace = builder.complete(status=SpanStatus.SUCCESS)

        # Verify
        assert trace is not None
        assert trace.status == SpanStatus.SUCCESS
        assert len(trace.spans) == 2  # Root + node
        root_span = trace.get_root_span()
        assert root_span is not None
        assert root_span.status == SpanStatus.SUCCESS

        node_span = trace.get_span(span.span_id)
        assert node_span is not None
        assert node_span.status == SpanStatus.SUCCESS
        assert len(node_span.events) == 2

    def test_denied_execution_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Denied execution wordt getraced."""
        enforcer = PolicyEnforcer(registry_with_capabilities)

        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_payment",
        )

        # Payment > threshold
        node = {
            "capability_key": "payment_process",
            "input": {"amount": 2000, "currency": "EUR"},
        }

        # Check permissions - requires approval
        result = enforcer.check_execute_permission(node, pro_policy)
        assert result.can_execute is False
        assert result.requires_approval is True

        # Start span
        span = builder.start_node_span(
            node_id="process_payment",
            capability_key="payment_process",
            input_data=node["input"],
        )

        # End span met pending approval
        builder.end_span(
            span,
            status=SpanStatus.PENDING_APPROVAL,
            status_message="Amount exceeds threshold, waiting for approval",
        )

        trace = builder.complete(status=SpanStatus.PENDING_APPROVAL)

        assert trace.status == SpanStatus.PENDING_APPROVAL
        node_span = trace.get_span(span.span_id)
        assert node_span is not None
        assert node_span.status == SpanStatus.PENDING_APPROVAL

    def test_failed_execution_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Failed execution wordt getraced."""
        enforcer = PolicyEnforcer(registry_with_capabilities)

        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_email",
        )

        # Invalid input (missing required field)
        node = {
            "capability_key": "email_send",
            "input": {"to": "test@example.com"},  # Missing subject, body
        }

        # Check permissions
        result = enforcer.check_execute_permission(node, pro_policy)
        assert result.can_execute is False
        assert result.violation_type == "INVALID_INPUT"

        # Trace wordt nog steeds gemaakt
        span = builder.start_node_span(
            node_id="send_welcome_email",
            capability_key="email_send",
            input_data=node["input"],
        )

        span.add_event("validation_failed", {"error": "Missing required fields"})

        builder.end_span(
            span,
            status=SpanStatus.FAILED,
            status_message="Input validation failed: Missing required fields: subject, body",
        )

        trace = builder.complete(status=SpanStatus.FAILED)

        # Verify (root span + node span = 2 failed spans)
        assert trace.status == SpanStatus.FAILED
        failed_spans = trace.get_failed_spans()
        assert len(failed_spans) == 2
        # Node span is the child
        node_failed = [
            s for s in failed_spans if s.attributes.get("node_id") == "send_welcome_email"
        ]
        assert len(node_failed) == 1
        assert node_failed[0] is not None

    def test_workflow_with_multiple_nodes(self, registry_with_capabilities, pro_policy):
        """Happy path: Workflow met meerdere nodes."""
        enforcer = PolicyEnforcer(registry_with_capabilities)

        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_customer_onboarding",
        )

        # Node 1: Create contact (allowed)
        node1 = {
            "capability_key": "crm_create_contact",
            "input": {"name": "Alice", "email": "alice@example.com"},
        }

        result1 = enforcer.check_execute_permission(node1, pro_policy)
        assert result1.can_execute is True

        span1 = builder.start_node_span(
            node_id="create_contact",
            capability_key="crm_create_contact",
            input_data=node1["input"],
        )
        builder.end_span(span1, status=SpanStatus.SUCCESS, output_data={"contact_id": "cust-1"})

        # Node 2: Send email (allowed)
        node2 = {
            "capability_key": "email_send",
            "input": {
                "to": "alice@example.com",
                "subject": "Welcome!",
                "body": "Thanks for joining!",
            },
        }

        result2 = enforcer.check_execute_permission(node2, pro_policy)
        assert result2.can_execute is True

        span2 = builder.start_node_span(
            node_id="send_welcome",
            capability_key="email_send",
            input_data=node2["input"],
        )
        builder.end_span(span2, status=SpanStatus.SUCCESS, output_data={"message_id": "msg-1"})

        trace = builder.complete(status=SpanStatus.SUCCESS)

        # Root + 2 nodes = 3 spans
        assert len(trace.spans) == 3

        # Check tree structure
        tree = trace.get_span_tree()
        assert len(tree["children"]) == 2

    def test_capability_not_enabled_traced(self, registry_with_capabilities):
        """Happy path: Capability not enabled wordt getraced."""
        # Starter policy zonder payment
        starter_policy = TenantPolicy(
            tenant_id="tenant-starter-001",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"crm_create_contact"},  # Geen payment
        )

        enforcer = PolicyEnforcer(registry_with_capabilities)

        builder = TraceBuilder(
            tenant_id="tenant-starter-001",
            workflow_id="workflow_upgrade",
        )

        node = {
            "capability_key": "payment_process",
            "input": {"amount": 100, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, starter_policy)
        assert result.can_execute is False
        assert result.violation_type == "CAPABILITY_NOT_ENABLED"
        assert result.execution_context.get("suggested_tier") == "pro"

        # Trace wordt gemaakt voor audit
        span = builder.start_node_span(
            node_id="attempt_payment",
            capability_key="payment_process",
            input_data=node["input"],
        )

        builder.end_span(
            span,
            status=SpanStatus.FAILED,
            status_message=f"Capability not enabled. Suggested tier: {result.execution_context.get('suggested_tier')}",
        )

        trace = builder.complete(status=SpanStatus.FAILED)

        assert trace.status == SpanStatus.FAILED


class TestComplianceIntegration:
    """Test compliance features integratie."""

    def test_gdpr_compliance_traced(self, registry_with_capabilities):
        """Happy path: GDPR compliance wordt getraced."""
        gdpr_policy = TenantPolicy(
            tenant_id="tenant-gdpr",
            plan_tier=PlanTier.ENTERPRISE,
            enabled_capabilities={"crm_create_contact"},
            compliance_profile=ComplianceProfile.GDPR,
        )

        builder = TraceBuilder(
            tenant_id="tenant-gdpr",
            workflow_id="workflow_gdpr_onboarding",
        )

        # Add compliance attributes
        trace = builder.trace
        trace.attributes["compliance_profile"] = gdpr_policy.compliance_profile.value
        trace.attributes["data_residency"] = "EU"
        trace.attributes["retention_days"] = gdpr_policy.compliance_profile.retention_days

        span = builder.start_node_span(
            node_id="create_contact",
            capability_key="crm_create_contact",
            input_data={"name": "GDPR User", "email": "user@example.com"},
        )

        # PII wordt geredacteerd
        assert "***REDACTED***" not in str(span.input_data)  # Email is OK

        builder.end_span(span, status=SpanStatus.SUCCESS)

        trace = builder.complete(status=SpanStatus.SUCCESS)

        assert trace.attributes["compliance_profile"] == "gdpr"
        assert trace.attributes["data_residency"] == "EU"
        assert trace.attributes["retention_days"] == 365  # 1 jaar (max per audit policy)

    def test_pii_redaction_in_trace(self, registry_with_capabilities, pro_policy):
        """Happy path: PII wordt geredacteerd in trace."""
        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_sensitive",
        )

        span = builder.start_node_span(
            node_id="login",
            capability_key="crm_create_contact",
            input_data={
                "username": "john_doe",
                "password": "super_secret_123",
                "api_token": "abc123xyz",
            },
        )

        assert span.input_data is not None
        assert span.input_data["username"] == "john_doe"
        assert span.input_data["password"] == "***REDACTED***"
        assert span.input_data["api_token"] == "***REDACTED***"


class TestRetryAndFallback:
    """Test retry en fallback integratie."""

    def test_retry_attempt_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Retry attempts worden getraced."""
        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_retry_test",
        )

        # Parent node span
        node_span = builder.start_node_span(
            node_id="send_email",
            capability_key="email_send",
            input_data={"to": "test@test.com", "subject": "Hi", "body": "Hello"},
        )

        # Retry spans
        for i in range(1, 4):  # Retry attempts 1, 2, 3 (eerste was 0)
            retry_span = builder.start_capability_span(
                capability_key="email_send",
                parent_span_id=node_span.span_id,
                retry_attempt=i,
                is_fallback=False,
            )
            retry_span.add_event(f"attempt_{i}")

            if i < 2:
                # Fail first 2 attempts
                builder.end_span(retry_span, status=SpanStatus.FAILED)
            else:
                # Success on 3rd attempt
                builder.end_span(retry_span, status=SpanStatus.SUCCESS)

        builder.end_span(node_span, status=SpanStatus.SUCCESS)

        trace = builder.complete(status=SpanStatus.SUCCESS)

        # Root + node + 3 retries = 5 spans
        assert len(trace.spans) == 5

        # Check retry info
        retry_spans = [s for s in trace.spans if s.retry_attempt > 0]
        assert len(retry_spans) == 3  # retry_attempt 1, 2, 3

    def test_fallback_execution_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Fallback execution wordt getraced."""
        builder = TraceBuilder(
            tenant_id="tenant-pro-001",
            workflow_id="workflow_fallback_test",
        )

        node_span = builder.start_node_span(
            node_id="send_notification",
            capability_key="email_send",
            input_data={"to": "test@test.com", "subject": "Hi", "body": "Hello"},
        )

        # Primary attempt fails
        primary_span = builder.start_capability_span(
            capability_key="email_send",
            parent_span_id=node_span.span_id,
            is_fallback=False,
        )
        builder.end_span(primary_span, status=SpanStatus.FAILED)

        # Fallback to SMS (simulated)
        fallback_span = builder.start_capability_span(
            capability_key="sms_send",  # Fallback capability
            parent_span_id=node_span.span_id,
            is_fallback=True,
            fallback_from="email_send",
        )
        builder.end_span(fallback_span, status=SpanStatus.SUCCESS)

        builder.end_span(node_span, status=SpanStatus.SUCCESS)

        trace = builder.complete(status=SpanStatus.SUCCESS)

        # Find fallback span
        fallback_spans = [s for s in trace.spans if s.is_fallback]
        assert len(fallback_spans) == 1
        fallback_span = fallback_spans[0]
        assert fallback_span.fallback_from == "email_send"


class TestQueryAndAudit:
    """Test query en audit features."""

    @pytest.mark.asyncio
    async def test_trace_query_by_tenant(self, registry_with_capabilities):
        """Happy path: Query traces by tenant."""
        from core.contracts.trace import InMemoryTraceStore

        store = InMemoryTraceStore()

        # Create traces voor verschillende tenants
        for i in range(3):
            builder = TraceBuilder(
                tenant_id="tenant-a",
                workflow_id=f"workflow-{i}",
            )
            trace = builder.complete(status=SpanStatus.SUCCESS)
            await store.save(trace)

        for i in range(2):
            builder = TraceBuilder(
                tenant_id="tenant-b",
                workflow_id=f"workflow-{i}",
            )
            trace = builder.complete(status=SpanStatus.SUCCESS)
            await store.save(trace)

        # Query
        results = await store.query(tenant_id="tenant-a")

        assert len(results) == 3
        for r in results:
            assert r.tenant_id == "tenant-a"

    @pytest.mark.asyncio
    async def test_trace_query_by_status(self, registry_with_capabilities):
        """Happy path: Query traces by status."""
        from core.contracts.trace import InMemoryTraceStore

        store = InMemoryTraceStore()

        # Success traces
        for i in range(2):
            builder = TraceBuilder(tenant_id="t1", workflow_id=f"wf-{i}")
            trace = builder.complete(status=SpanStatus.SUCCESS)
            await store.save(trace)

        # Failed traces
        for i in range(3):
            builder = TraceBuilder(tenant_id="t1", workflow_id=f"wf-fail-{i}")
            trace = builder.complete(status=SpanStatus.FAILED)
            await store.save(trace)

        # Query failed
        results = await store.query(status=SpanStatus.FAILED)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_failed_spans_for_audit(self, registry_with_capabilities):
        """Happy path: Get failed spans voor audit."""
        builder = TraceBuilder(
            tenant_id="tenant-001",
            workflow_id="workflow_audit",
        )

        # Mix van success en failed spans
        for i in range(5):
            span = builder.start_node_span(
                node_id=f"step-{i}",
                capability_key="email_send",
                input_data={"to": "test@test.com", "subject": f"Test {i}", "body": "Hello"},
            )

            if i % 2 == 0:
                builder.end_span(span, status=SpanStatus.SUCCESS)
            else:
                builder.end_span(span, status=SpanStatus.FAILED)

        trace = builder.complete(status=SpanStatus.FAILED)

        failed_spans = trace.get_failed_spans()

        # Root span (failed) + step-1 (failed) + step-3 (failed) = 3 failed spans
        assert len(failed_spans) == 3


class TestWorkflowNodeValidation:
    """Test workflow node validatie met tracing."""

    def test_valid_node_executes_and_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Valid node wordt uitgevoerd en getraced."""
        enforcer = PolicyEnforcer(registry_with_capabilities)
        resolver = CapabilityResolver(registry_with_capabilities)

        node = {
            "capability_key": "email_send",
            "input": {
                "to": "test@example.com",
                "subject": "Test",
                "body": "Hello World",
            },
        }

        # Validate node
        validation = resolver.validate_node(node)
        assert validation.is_valid is True

        # Check policy
        result = enforcer.check_execute_permission(node, pro_policy)
        assert result.can_execute is True

        # Execute en trace
        builder = TraceBuilder(tenant_id="t1", workflow_id="wf1")
        span = builder.start_node_span(
            node_id="send_email",
            capability_key="email_send",
            input_data=node["input"],
        )
        builder.end_span(span, status=SpanStatus.SUCCESS)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        assert trace.status == SpanStatus.SUCCESS

    def test_invalid_node_blocked_and_traced(self, registry_with_capabilities, pro_policy):
        """Happy path: Invalid node wordt geblokkeerd en getraced."""
        enforcer = PolicyEnforcer(registry_with_capabilities)
        resolver = CapabilityResolver(registry_with_capabilities)

        node = {
            "capability_key": "email_send",
            "input": {
                "to": "test@example.com",
                # Missing required: subject, body
            },
        }

        # Validate node
        validation = resolver.validate_node(node)
        assert validation.is_valid is False
        assert len(validation.errors) > 0

        # Check policy
        result = enforcer.check_execute_permission(node, pro_policy)
        assert result.can_execute is False
        assert result.violation_type == "INVALID_INPUT"

        # Trace de poging
        builder = TraceBuilder(tenant_id="t1", workflow_id="wf1")
        span = builder.start_node_span(
            node_id="send_email",
            capability_key="email_send",
            input_data=node["input"],
        )
        span.add_event("validation_failed", {"errors": validation.errors})
        builder.end_span(span, status=SpanStatus.FAILED, status_message="Input validation failed")
        trace = builder.complete(status=SpanStatus.FAILED)

        assert trace.status == SpanStatus.FAILED
