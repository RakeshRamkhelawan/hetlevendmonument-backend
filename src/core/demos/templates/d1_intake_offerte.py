"""
D1 Template: Intake -> Offerte -> Review

Sales demo workflow voor lead intake, offerte generatie,
manager approval en klantnotificatie.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from src.core.contracts import (
    ApprovalThreshold,
    CapabilityRegistry,
    PolicyEnforcer,
    SpanStatus,
    TenantPolicy,
    TraceBuilder,
)
from src.core.contracts.policy import PlanTier


@dataclass
class D1Configuration:
    """Configuratie voor D1 template."""

    # Approval thresholds
    quote_approval_threshold: Decimal = Decimal("5000.00")
    auto_approve_below: Decimal = Decimal("1000.00")

    # Notificatie instellingen
    notification_channels: list[str] = field(default_factory=lambda: ["email"])
    default_template: str = "quote_notification"

    # Quote instellingen
    default_validity_days: int = 30
    max_discount_percentage: float = 20.0

    # Tenant config
    plan_tier: PlanTier = PlanTier.STARTER

    def to_policy(self, tenant_id: str) -> TenantPolicy:
        """Convert config naar TenantPolicy."""
        return TenantPolicy(
            tenant_id=tenant_id,
            plan_tier=self.plan_tier,
            enabled_capabilities={
                "d1_intake_lead",
                "d1_generate_quote",
                "d1_review_quote",
                "d1_notify_customer",
            },
            approval_thresholds={
                "d1_generate_quote": ApprovalThreshold(
                    amount_threshold=self.quote_approval_threshold,
                    approver_roles={"sales_manager", "finance"},
                    auto_approve_after_ms=48 * 3600 * 1000,  # 48h
                ),
            },
        )


@dataclass
class LeadData:
    """Lead intake data."""

    company_name: str
    contact_name: str
    email: str
    phone: str | None = None
    requirements: str | None = None
    budget_indication: Decimal | None = None
    timeline: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "email": self.email,
            "phone": self.phone,
            "requirements": self.requirements,
            "budget_indication": float(self.budget_indication) if self.budget_indication else None,
            "timeline": self.timeline,
        }


@dataclass
class QuoteLineItem:
    """Offerte regel item."""

    description: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.unit_price * Decimal(self.quantity)


@dataclass
class QuoteData:
    """Offerte data."""

    lead_id: str
    line_items: list[QuoteLineItem]
    discount_percentage: float = 0.0
    validity_days: int = 30

    @property
    def subtotal(self) -> Decimal:
        return Decimal(sum(item.total for item in self.line_items))

    @property
    def discount_amount(self) -> Decimal:
        return self.subtotal * (Decimal(self.discount_percentage) / 100)

    @property
    def total_amount(self) -> Decimal:
        return self.subtotal - self.discount_amount

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "lead_id": self.lead_id,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                }
                for item in self.line_items
            ],
            "discount_percentage": self.discount_percentage,
            "validity_days": self.validity_days,
        }


@dataclass
class ReviewDecision:
    """Review beslissing."""

    quote_id: str
    reviewer_id: str
    decision: str  # "approve", "reject", "request_revision"
    comments: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "quote_id": self.quote_id,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "comments": self.comments,
        }


class D1Template:
    """
    D1 Template: Intake -> Offerte -> Review

    Workflow:
    1. Intake lead -> Lead ID
    2. Generate quote -> Quote ID (pending approval)
    3. Review quote -> Approved/Rejected
    4. Notify customer -> Notification sent
    """

    def __init__(
        self,
        config: D1Configuration,
        capability_registry: CapabilityRegistry,
        tenant_id: str,
    ) -> None:
        self.config = config
        self.registry = capability_registry
        self.tenant_id = tenant_id
        self.policy = config.to_policy(tenant_id)
        self.enforcer = PolicyEnforcer(capability_registry)

    def intake_lead(self, lead: LeadData) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 1: Intake een nieuwe lead.

        Returns: Dict[str, Any] met lead_id, status, en intake_date  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d1_intake_offerte",
            user_id="system",
        )

        span = builder.start_node_span(
            node_id="intake_lead",
            capability_key="d1_intake_lead",
            input_data=lead.to_dict(),
        )

        # Check policy
        node = {"capability_key": "d1_intake_lead", "input": lead.to_dict()}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Lead intake blocked: {result.reason}")

        # Execute (simulated)
        lead_id = str(uuid.uuid4())[:8]
        output = {
            "lead_id": lead_id,
            "intake_date": datetime.now(timezone.utc).isoformat(),
            "status": "new",
        }

        span.add_event("lead_created", {"lead_id": lead_id})
        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)

        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "lead_id": lead_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def generate_quote(
        self,
        lead_id: str,
        line_items: list[QuoteLineItem],
        discount_percentage: float = 0.0,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 2: Genereer een offerte.

        Returns: Dict[str, Any] met quote_id, total_amount, status (draft/pending_approval)  # TODO(TYPE): replace Any with concrete type
        """
        quote_data = QuoteData(
            lead_id=lead_id,
            line_items=line_items,
            discount_percentage=discount_percentage,
            validity_days=self.config.default_validity_days,
        )

        # Validate discount
        if discount_percentage > self.config.max_discount_percentage:
            raise ValueError(
                f"Discount {discount_percentage}% exceeds maximum {self.config.max_discount_percentage}%"
            )

        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d1_intake_offerte",
        )

        span = builder.start_node_span(
            node_id="generate_quote",
            capability_key="d1_generate_quote",
            input_data=quote_data.to_dict(),
        )

        # Check policy (incl. approval threshold)
        node = {
            "capability_key": "d1_generate_quote",
            "input": {
                **quote_data.to_dict(),
                "amount": float(quote_data.total_amount),  # For approval check
            },
        }
        result = self.enforcer.check_execute_permission(node, self.policy)

        # Determine status
        requires_approval = quote_data.total_amount >= self.config.quote_approval_threshold
        status = "pending_approval" if requires_approval else "draft"

        # Execute (simulated)
        quote_id = str(uuid.uuid4())[:8]
        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=quote_data.validity_days)
        ).strftime("%Y-%m-%d")

        output = {
            "quote_id": quote_id,
            "quote_number": f"Q-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{quote_id}",
            "total_amount": float(quote_data.total_amount),
            "valid_until": valid_until,
            "status": status,
            "requires_approval": requires_approval,
        }

        if requires_approval:
            span.add_event("approval_required", {"amount": float(quote_data.total_amount)})
        else:
            span.add_event("auto_draft", {"amount": float(quote_data.total_amount)})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "quote_id": quote_id,
            "trace_id": trace.trace_id,
            **output,
            "status": "success" if not requires_approval else "pending_approval",
        }

    def review_quote(self, decision: ReviewDecision) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 3: Review een offerte.

        Returns: Dict[str, Any] met review_id, decision, reviewed_at  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d1_intake_offerte",
        )

        span = builder.start_node_span(
            node_id="review_quote",
            capability_key="d1_review_quote",
            input_data=decision.to_dict(),
        )

        # Check policy
        node = {"capability_key": "d1_review_quote", "input": decision.to_dict()}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Review blocked: {result.reason}")

        # Execute (simulated)
        review_id = str(uuid.uuid4())[:8]
        reviewed_at = datetime.now(timezone.utc).isoformat()

        output = {
            "review_id": review_id,
            "quote_id": decision.quote_id,
            "decision": decision.decision,
            "reviewed_at": reviewed_at,
        }

        span.add_event("review_completed", {"decision": decision.decision})

        status = SpanStatus.SUCCESS
        if decision.decision == "reject":
            status = SpanStatus.CANCELLED
        elif decision.decision == "request_revision":
            status = SpanStatus.PENDING_APPROVAL

        builder.end_span(span, status=status, output_data=output)
        trace = builder.complete(status=status)

        return {
            "review_id": review_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def notify_customer(
        self,
        lead_id: str,
        quote_id: str,
        channel: str = "email",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 4: Stuur notificatie naar klant.

        Returns: Dict[str, Any] met notification_id, sent_at, status  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d1_intake_offerte",
        )

        input_data = {
            "lead_id": lead_id,
            "quote_id": quote_id,
            "channel": channel,
            "template": self.config.default_template,
        }

        span = builder.start_node_span(
            node_id="notify_customer",
            capability_key="d1_notify_customer",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d1_notify_customer", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Notification blocked: {result.reason}")

        # Execute (simulated)
        notification_id = str(uuid.uuid4())[:8]
        sent_at = datetime.now(timezone.utc).isoformat()

        output = {
            "notification_id": notification_id,
            "sent_at": sent_at,
            "status": "sent",
            "channel": channel,
        }

        span.add_event("notification_sent", {"channel": channel})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "notification_id": notification_id,
            "trace_id": trace.trace_id,
            **output,
            "status": "success",  # Override output status
        }

    def execute_full_workflow(
        self,
        lead: LeadData,
        line_items: list[QuoteLineItem],
        reviewer_id: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Voer de complete D1 workflow uit.

        Returns: Dict[str, Any] met resultaten van alle stappen  # TODO(TYPE): replace Any with concrete type
        """
        results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow": "d1_intake_offerte",
            "steps": [],
        }

        try:
            # Step 1: Intake
            intake_result = self.intake_lead(lead)
            results["steps"].append({"step": "intake", "result": intake_result})
            lead_id = intake_result["lead_id"]

            # Step 2: Generate Quote
            quote_result = self.generate_quote(lead_id, line_items)
            results["steps"].append({"step": "generate_quote", "result": quote_result})
            quote_id = quote_result["quote_id"]

            # Step 3: Review (if needed)
            if quote_result.get("requires_approval") and reviewer_id:
                decision = ReviewDecision(
                    quote_id=quote_id,
                    reviewer_id=reviewer_id,
                    decision="approve",
                    comments="Auto-approved for demo",
                )
                review_result = self.review_quote(decision)
                results["steps"].append({"step": "review", "result": review_result})

            # Step 4: Notify
            notify_result = self.notify_customer(lead_id, quote_id)
            results["steps"].append({"step": "notify", "result": notify_result})

            results["status"] = "success"

        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)

        return results
