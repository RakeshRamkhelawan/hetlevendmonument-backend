"""
D3 Template: Factuurcontrole -> Approval

Finance demo workflow voor batch factuurcontrole, afwijkingsdetectie,
risicoscore berekening, approval routing en dagrapport generatie.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from src.core.contracts import (
    ApprovalThreshold,
    CapabilityRegistry,
    PlanTier,
    PolicyEnforcer,
    SpanStatus,
    TenantPolicy,
    TraceBuilder,
)


@dataclass
class D3Configuration:
    """Configuratie voor D3 template."""

    # Detectie instellingen
    tolerance_percentage: Decimal = Decimal("5.0")
    check_po_match: bool = True

    # Risk scoring
    high_risk_threshold: int = 75
    medium_risk_threshold: int = 50

    # Approval routing
    auto_approve_below: Decimal = Decimal("500.00")
    escalation_hours: int = 24

    # Tenant config
    plan_tier: PlanTier = PlanTier.STARTER

    def to_policy(self, tenant_id: str) -> TenantPolicy:
        """Convert config naar TenantPolicy."""
        return TenantPolicy(
            tenant_id=tenant_id,
            plan_tier=self.plan_tier,
            enabled_capabilities={
                "d3_ingest_invoices",
                "d3_detect_deviations",
                "d3_calculate_risk_score",
                "d3_route_for_approval",
                "d3_generate_daily_report",
            },
            approval_thresholds={
                "d3_route_for_approval": ApprovalThreshold(
                    amount_threshold=self.auto_approve_below,
                    approver_roles={"finance_manager", "cfo"},
                    auto_approve_after_ms=self.escalation_hours * 3600 * 1000,
                ),
            },
        )


@dataclass
class Invoice:
    """Factuur data."""

    invoice_number: str
    vendor: str
    amount: Decimal
    due_date: str | None = None
    purchase_order: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "invoice_number": self.invoice_number,
            "vendor": self.vendor,
            "amount": float(self.amount),
            "due_date": self.due_date,
            "purchase_order": self.purchase_order,
            "description": self.description,
        }


@dataclass
class Deviation:
    """Afwijking detectie resultaat."""

    invoice_number: str
    deviation_type: str
    severity: str
    details: str | None = None


@dataclass
class ApprovalRequest:
    """Approval request data."""

    invoice_number: str
    risk_level: str
    amount: Decimal
    requested_approver_role: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "invoice_number": self.invoice_number,
            "risk_level": self.risk_level,
            "amount": float(self.amount),
            "requested_approver_role": self.requested_approver_role,
        }


class D3Template:
    """
    D3 Template: Factuurcontrole -> Approval

    Workflow:
    1. Ingest invoices (CSV/XML/PDF/manual) -> Batch ID
    2. Detect deviations -> Deviations list
    3. Calculate risk score -> Risk level
    4. Route for approval -> Approval request
    5. Generate daily report -> Report file
    """

    def __init__(
        self,
        config: D3Configuration,
        capability_registry: CapabilityRegistry,
        tenant_id: str,
    ) -> None:
        self.config = config
        self.registry = capability_registry
        self.tenant_id = tenant_id
        self.policy = config.to_policy(tenant_id)
        self.enforcer = PolicyEnforcer(capability_registry)

    def ingest_invoices(
        self,
        invoices: list[Invoice],
        source: str = "csv",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 1: Ingest facturen.

        Returns: Dict[str, Any] met batch_id, processed, failed, total_amount  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d3_factuur_controle",
        )

        input_data = {
            "source": source,
            "invoices": [inv.to_dict() for inv in invoices],
        }

        span = builder.start_node_span(
            node_id="ingest_invoices",
            capability_key="d3_ingest_invoices",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d3_ingest_invoices", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Invoice ingest blocked: {result.reason}")

        # Validate invoices
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        valid_invoices: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, inv in enumerate(invoices):
            if not inv.invoice_number or not inv.vendor or inv.amount <= 0:
                errors.append(
                    {
                        "invoice_index": i,
                        "error": "Invalid invoice data",
                        "invoice_number": inv.invoice_number,
                    }
                )
            else:
                valid_invoices.append(inv)

        # Execute (simulated)
        batch_id = str(uuid.uuid4())[:8]
        total_amount = sum(inv.amount for inv in valid_invoices)

        output = {
            "batch_id": batch_id,
            "processed": len(valid_invoices),
            "failed": len(errors),
            "total_amount": float(total_amount),
        }

        span.add_event(
            "batch_created",
            {
                "batch_id": batch_id,
                "processed": len(valid_invoices),
                "failed": len(errors),
            },
        )

        status = SpanStatus.SUCCESS if len(valid_invoices) > 0 else SpanStatus.FAILED
        builder.end_span(span, status=status, output_data=output)
        trace = builder.complete(status=status)

        return {
            "batch_id": batch_id,
            "status": "success" if status == SpanStatus.SUCCESS else "partial_failure",
            "trace_id": trace.trace_id,
            **output,
        }

    def detect_deviations(
        self,
        batch_id: str,
        invoices: list[Invoice],
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 2: Detecteer afwijkingen.

        Returns: Dict[str, Any] met check_id, deviations_found, deviations list  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d3_factuur_controle",
        )

        input_data = {
            "batch_id": batch_id,
            "tolerance_percentage": float(self.config.tolerance_percentage),
            "check_po_match": self.config.check_po_match,
        }

        span = builder.start_node_span(
            node_id="detect_deviations",
            capability_key="d3_detect_deviations",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d3_detect_deviations", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Deviation detection blocked: {result.reason}")

        # Detect deviations (simulated rules)
        deviations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for inv in invoices:
            # Rule 1: High amount check
            if inv.amount > Decimal("10000"):
                deviations.append(
                    {
                        "invoice_number": inv.invoice_number,
                        "deviation_type": "high_amount",
                        "severity": "medium",
                        "details": f"Amount {inv.amount} exceeds threshold",
                    }
                )

            # Rule 2: Missing PO check
            if self.config.check_po_match and not inv.purchase_order:
                deviations.append(
                    {
                        "invoice_number": inv.invoice_number,
                        "deviation_type": "missing_po",
                        "severity": "high",
                        "details": "No purchase order reference",
                    }
                )

            # Rule 3: Duplicate check (simulated - same vendor + amount)
            for other in invoices:
                if other.invoice_number != inv.invoice_number:
                    if other.vendor == inv.vendor and other.amount == inv.amount:
                        deviations.append(
                            {
                                "invoice_number": inv.invoice_number,
                                "deviation_type": "potential_duplicate",
                                "severity": "high",
                                "details": f"Similar to {other.invoice_number}",
                            }
                        )
                        break

        # Execute (simulated)
        check_id = str(uuid.uuid4())[:8]

        output = {
            "check_id": check_id,
            "deviations_found": len(deviations),
            "deviations": deviations,
        }

        span.add_event("deviations_detected", {"count": len(deviations)})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "check_id": check_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def calculate_risk_score(
        self,
        invoice: Invoice,
        deviations: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 3: Bereken risico score.

        Returns: Dict[str, Any] met risk_score, risk_level, factors  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d3_factuur_controle",
        )

        input_data = {
            "invoice_number": invoice.invoice_number,
            "amount": float(invoice.amount),
            "deviation_flags": deviations,
        }

        span = builder.start_node_span(
            node_id="calculate_risk_score",
            capability_key="d3_calculate_risk_score",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d3_calculate_risk_score", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Risk calculation blocked: {result.reason}")

        # Calculate risk score (simulated algorithm)
        score = 0
        factors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Amount factor
        if invoice.amount > Decimal("10000"):
            score += 30
            factors.append("high_amount")
        elif invoice.amount > Decimal("5000"):
            score += 15
            factors.append("medium_amount")

        # Deviation factors
        for dev in deviations:
            if dev.get("severity") == "high":
                score += 25
                factors.append(f"high_severity_{dev['deviation_type']}")
            elif dev.get("severity") == "medium":
                score += 15
                factors.append(f"medium_severity_{dev['deviation_type']}")

        # Cap at 100
        score = min(100, score)

        # Determine level
        if score >= self.config.high_risk_threshold:
            risk_level = "high"
        elif score >= self.config.medium_risk_threshold:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Execute (simulated)
        output = {
            "risk_score": score,
            "risk_level": risk_level,
            "factors": factors,
        }

        span.add_event("risk_calculated", {"score": score, "level": risk_level})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def route_for_approval(
        self,
        invoice: Invoice,
        risk_level: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 4: Route voor approval.

        Returns: Dict[str, Any] met approval_request_id, assigned_approvers, status  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d3_factuur_controle",
        )

        input_data = {
            "invoice_number": invoice.invoice_number,
            "risk_level": risk_level,
            "amount": float(invoice.amount),
        }

        span = builder.start_node_span(
            node_id="route_for_approval",
            capability_key="d3_route_for_approval",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d3_route_for_approval", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Approval routing blocked: {result.reason}")

        # Determine routing
        assigned_approvers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        status = "pending"

        # Auto-approve low amounts
        if invoice.amount <= self.config.auto_approve_below and risk_level == "low":
            status = "auto_approved"
            assigned_approvers = ["system"]
        else:
            # Route based on risk level
            if risk_level == "critical":
                assigned_approvers = ["cfo", "finance_director"]
            elif risk_level == "high":
                assigned_approvers = ["finance_manager"]
            elif risk_level == "medium":
                assigned_approvers = ["team_lead"]
            else:  # low
                assigned_approvers = ["team_member"]

        # Execute (simulated)
        approval_request_id = str(uuid.uuid4())[:8]

        output = {
            "approval_request_id": approval_request_id,
            "assigned_approvers": assigned_approvers,
            "escalation_time_hours": self.config.escalation_hours,
            "status": status,
        }

        span.add_event(
            "approval_routed",
            {
                "request_id": approval_request_id,
                "status": status,
                "approvers": assigned_approvers,
            },
        )

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "approval_request_id": approval_request_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def generate_daily_report(
        self,
        batch_id: str,
        invoices: list[Invoice],
        approvals: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 5: Genereer dagrapport.

        Returns: Dict[str, Any] met report_id, total_invoices, approved_count, etc.  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d3_factuur_controle",
        )

        input_data = {
            "batch_id": batch_id,
            "report_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "include_approvals": True,
        }

        span = builder.start_node_span(
            node_id="generate_daily_report",
            capability_key="d3_generate_daily_report",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d3_generate_daily_report", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Report generation blocked: {result.reason}")

        # Calculate stats
        total_amount = sum(inv.amount for inv in invoices)
        approved_count = sum(
            1 for a in approvals if a.get("status") in ["auto_approved", "approved"]
        )
        pending_count = sum(1 for a in approvals if a.get("status") == "pending")
        rejected_count = sum(1 for a in approvals if a.get("status") == "rejected")

        # Execute (simulated)
        report_id = str(uuid.uuid4())[:8]
        generated_at = datetime.now(timezone.utc).isoformat()

        output = {
            "report_id": report_id,
            "total_invoices": len(invoices),
            "total_amount": float(total_amount),
            "approved_count": approved_count,
            "pending_count": pending_count,
            "rejected_count": rejected_count,
            "generated_at": generated_at,
        }

        span.add_event("report_generated", {"report_id": report_id})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "report_id": report_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def execute_full_workflow(
        self,
        invoices: list[Invoice],
        source: str = "csv",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Voer de complete D3 workflow uit.

        Returns: Dict[str, Any] met resultaten van alle stappen  # TODO(TYPE): replace Any with concrete type
        """
        results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow": "d3_factuur_controle",
            "steps": [],
        }

        try:
            # Step 1: Ingest
            ingest_result = self.ingest_invoices(invoices, source)
            results["steps"].append({"step": "ingest", "result": ingest_result})
            batch_id = ingest_result["batch_id"]

            if ingest_result["processed"] == 0:
                raise ValueError("No valid invoices to process")

            # Step 2: Detect Deviations
            detection_result = self.detect_deviations(batch_id, invoices)
            results["steps"].append({"step": "detect", "result": detection_result})
            deviations = detection_result["deviations"]

            # Step 3 & 4: Risk Score + Approval Routing (per invoice)
            approvals: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for invoice in invoices:
                # Find deviations for this invoice
                inv_deviations = [
                    d for d in deviations if d["invoice_number"] == invoice.invoice_number
                ]

                # Calculate risk
                risk_result = self.calculate_risk_score(invoice, inv_deviations)

                # Route for approval
                approval_result = self.route_for_approval(
                    invoice,
                    risk_result["risk_level"],
                )

                approvals.append(
                    {
                        "invoice_number": invoice.invoice_number,
                        "risk_score": risk_result["risk_score"],
                        "risk_level": risk_result["risk_level"],
                        **approval_result,
                    }
                )

            results["steps"].append({"step": "risk_and_approval", "approvals": approvals})

            # Step 5: Generate Report
            report_result = self.generate_daily_report(batch_id, invoices, approvals)
            results["steps"].append({"step": "report", "result": report_result})

            results["status"] = "success"
            results["summary"] = {
                "total_invoices": len(invoices),
                "total_amount": float(sum(inv.amount for inv in invoices)),
                "deviations_found": len(deviations),
                "pending_approvals": sum(1 for a in approvals if a.get("status") == "pending"),
            }

        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)

        return results
