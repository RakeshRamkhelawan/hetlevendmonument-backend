"""
D3 Demo Template: Factuurcontrole -> Approval

Workflow:
1. Batch controle met afwijkingsdetectie
2. Risico score berekening
3. Approval-only exceptions
4. Dagrapport output

Gebruikt demo-data, geen externe API's.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class InvoiceStatus(Enum):
    """Factuur controle status"""

    PENDING = "pending"
    VALIDATED = "validated"
    ANOMALY_DETECTED = "anomaly_detected"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXCEPTION = "exception"


class RiskLevel(Enum):
    """Risico niveau voor factuur"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class D3ExceptionType(Enum):
    """D3 exception types"""

    CORRUPT_DATA = "corrupt_data"
    APPROVAL_TIMEOUT = "approval_timeout"
    DUPLICATE_INVOICE = "duplicate_invoice"
    VENDOR_BLACKLISTED = "vendor_blacklisted"


@dataclass
class Invoice:
    """Factuur voor controle"""

    invoice_id: str
    vendor_name: str
    vendor_id: str
    invoice_number: str
    invoice_date: date
    due_date: date
    amount_excl_vat: float
    vat_amount: float
    amount_incl_vat: float
    currency: str = "EUR"
    description: str = ""
    purchase_order_ref: str | None = None

    # Controle status
    status: InvoiceStatus = InvoiceStatus.PENDING
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = 0.0
    anomalies: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type

    # Approval tracking
    approval_required: bool = False
    approval_reason: str = ""
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None

    # Exception tracking
    exception_type: D3ExceptionType | None = None
    exception_message: str | None = None

    @property
    def total_amount(self) -> float:
        """Totaal factuur bedrag"""
        return self.amount_incl_vat

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize naar dict"""
        return {
            "invoice_id": self.invoice_id,
            "vendor_name": self.vendor_name,
            "vendor_id": self.vendor_id,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "amount_excl_vat": self.amount_excl_vat,
            "vat_amount": self.vat_amount,
            "amount_incl_vat": self.amount_incl_vat,
            "currency": self.currency,
            "description": self.description,
            "purchase_order_ref": self.purchase_order_ref,
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "anomalies": self.anomalies,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
        }


@dataclass
class ValidationRule:
    """Validatie regel voor factuur controle"""

    rule_id: str
    name: str
    description: str
    check_fn: Any  # Functie die (invoice) -> (passed, message) returned  # TODO(TYPE): replace Any with concrete type
    risk_level: RiskLevel


@dataclass
class DailyReport:
    """Dagrapport voor factuur controle"""

    report_id: str
    report_date: date
    total_invoices: int
    validated_count: int
    anomaly_count: int
    approval_pending_count: int
    rejected_count: int
    exception_count: int
    total_amount_validated: float
    total_amount_flagged: float
    risk_distribution: dict[str, int]
    anomalies_summary: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize naar dict"""
        return {
            "report_id": self.report_id,
            "report_date": self.report_date.isoformat(),
            "total_invoices": self.total_invoices,
            "validated_count": self.validated_count,
            "anomaly_count": self.anomaly_count,
            "approval_pending_count": self.approval_pending_count,
            "rejected_count": self.rejected_count,
            "exception_count": self.exception_count,
            "total_amount_validated": self.total_amount_validated,
            "total_amount_flagged": self.total_amount_flagged,
            "risk_distribution": self.risk_distribution,
            "anomalies_summary": self.anomalies_summary,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class D3AuditRecord:
    """Audit record voor D3 workflow"""

    record_id: str
    workflow_id: str
    invoice_id: str
    step: str
    status: str
    timestamp: datetime
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None


class D3Template:
    """
    D3 Demo Template: Factuurcontrole -> Approval

    Gebruik:
        template = D3Template()
        result = template.run_invoice_control(invoice_batch)
    """

    # Demo vendor database (no-cost, geen externe API)
    VENDOR_DATABASE = {
        "VEND-001": {"name": "Office Supplies BV", "trust_score": 95, "blacklisted": False},
        "VEND-002": {"name": "IT Solutions NL", "trust_score": 88, "blacklisted": False},
        "VEND-003": {"name": "Marketing Agency X", "trust_score": 72, "blacklisted": False},
        "VEND-004": {"name": "Consulting Group", "trust_score": 45, "blacklisted": True},  # Riskant
        "VEND-005": {"name": "Logistics Partner", "trust_score": 92, "blacklisted": False},
    }

    # Risico drempels
    RISK_THRESHOLDS: dict[str, int] = {
        "amount_high": 10000,  # > 10k = medium risk
        "amount_critical": 50000,  # > 50k = high risk
        "trust_low": 60,  # trust score < 60 = medium risk
        "trust_critical": 30,  # trust score < 30 = high risk
    }

    def __init__(self) -> None:
        self.audit_records: list[D3AuditRecord] = []
        self.workflow_id = f"d3-{uuid.uuid4().hex[:8]}"
        self._processed_invoices: list[Invoice] = []
        self._approval_timeouts = 0

    def _log_audit(
        self,
        invoice_id: str,
        step: str,
        status: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        error: str | None = None,
    ) -> "D3AuditRecord":
        """Log audit record"""
        record = D3AuditRecord(
            record_id=str(uuid.uuid4()),
            workflow_id=self.workflow_id,
            invoice_id=invoice_id,
            step=step,
            status=status,
            timestamp=datetime.now(timezone.utc),
            details=details,
            error_message=error,
        )
        self.audit_records.append(record)
        return record

    def parse_invoice_data(self, invoice_data: dict[str, Any]) -> Invoice | None:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 1: Parse factuur data

        Args:
            invoice_data: Raw factuur data

        Returns:
            Invoice object of None als corrupt
        """
        try:
            invoice = Invoice(
                invoice_id=invoice_data.get("invoice_id", f"INV-{uuid.uuid4().hex[:8]}"),
                vendor_name=invoice_data.get("vendor_name", ""),
                vendor_id=invoice_data.get("vendor_id", ""),
                invoice_number=invoice_data.get("invoice_number", ""),
                invoice_date=datetime.strptime(invoice_data["invoice_date"], "%Y-%m-%d").date(),
                due_date=datetime.strptime(invoice_data["due_date"], "%Y-%m-%d").date(),
                amount_excl_vat=float(invoice_data.get("amount_excl_vat", 0)),
                vat_amount=float(invoice_data.get("vat_amount", 0)),
                amount_incl_vat=float(invoice_data.get("amount_incl_vat", 0)),
                currency=invoice_data.get("currency", "EUR"),
                description=invoice_data.get("description", ""),
                purchase_order_ref=invoice_data.get("purchase_order_ref"),
            )

            self._log_audit(
                invoice_id=invoice.invoice_id,
                step="invoice_parse",
                status="success",
                details={"vendor": invoice.vendor_name, "amount": invoice.amount_incl_vat},
            )

            return invoice

        except (KeyError, ValueError, TypeError) as e:
            # Corrupte data
            invoice_id = invoice_data.get("invoice_id", f"INV-{uuid.uuid4().hex[:8]}")
            self._log_audit(
                invoice_id=invoice_id,
                step="invoice_parse",
                status="failed",
                details={"raw_data": str(invoice_data)[:200]},
                error=f"Corrupte data: {str(e)}",
            )
            return None

    def calculate_risk_score(
        self, invoice: Invoice
    ) -> tuple[RiskLevel, float, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 2: Bereken risico score

        Args:
            invoice: Invoice object

        Returns:
            (risk_level, risk_score, anomalies)
        """
        score = 0.0
        anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check 1: Bedrag
        if invoice.amount_incl_vat > self.RISK_THRESHOLDS["amount_critical"]:
            score += 40
            anomalies.append(
                {
                    "type": "high_amount",
                    "severity": "high",
                    "message": f"Bedrag EUR{invoice.amount_incl_vat:,.2f} boven drempel",
                    "threshold": self.RISK_THRESHOLDS["amount_critical"],
                }
            )
        elif invoice.amount_incl_vat > self.RISK_THRESHOLDS["amount_high"]:
            score += 20
            anomalies.append(
                {
                    "type": "elevated_amount",
                    "severity": "medium",
                    "message": f"Bedrag EUR{invoice.amount_incl_vat:,.2f} verhoogd",
                    "threshold": self.RISK_THRESHOLDS["amount_high"],
                }
            )

        # Check 2: Vendor trust score
        vendor = self.VENDOR_DATABASE.get(invoice.vendor_id, {})
        trust_score = int(str(vendor.get("trust_score", 50)))

        if vendor.get("blacklisted", False):
            score += 50
            anomalies.append(
                {
                    "type": "blacklisted_vendor",
                    "severity": "critical",
                    "message": f"Vendor {invoice.vendor_name} op blacklist",
                }
            )
        elif trust_score < self.RISK_THRESHOLDS["trust_critical"]:
            score += 30
            anomalies.append(
                {
                    "type": "untrusted_vendor",
                    "severity": "high",
                    "message": f"Vendor trust score ({trust_score}) zeer laag",
                }
            )
        elif trust_score < self.RISK_THRESHOLDS["trust_low"]:
            score += 15
            anomalies.append(
                {
                    "type": "low_trust_vendor",
                    "severity": "medium",
                    "message": f"Vendor trust score ({trust_score}) laag",
                }
            )

        # Check 3: Due date (als > 90 dagen = riskant)
        days_until_due = (invoice.due_date - date.today()).days
        if days_until_due < 0:
            score += 25
            anomalies.append(
                {
                    "type": "overdue",
                    "severity": "high",
                    "message": f"Factuur al {abs(days_until_due)} dagen vervallen",
                }
            )
        elif days_until_due > 90:
            score += 10
            anomalies.append(
                {
                    "type": "long_due_date",
                    "severity": "low",
                    "message": f"Lange betaaltermijn ({days_until_due} dagen)",
                }
            )

        # Bepaal risk level
        if score >= 50:
            risk_level = RiskLevel.CRITICAL
        elif score >= 30:
            risk_level = RiskLevel.HIGH
        elif score >= 15:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        self._log_audit(
            invoice_id=invoice.invoice_id,
            step="risk_assessment",
            status="success",
            details={
                "risk_score": score,
                "risk_level": risk_level.value,
                "anomalies": len(anomalies),
            },
        )

        return risk_level, score, anomalies

    def determine_approval_need(self, invoice: Invoice) -> tuple[bool, str]:
        """
        Stap 3: Bepaal of approval nodig is

        Args:
            invoice: Invoice met risico beoordeling

        Returns:
            (approval_required, reason)
        """
        # Approval nodig bij HIGH of CRITICAL risk
        if invoice.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return True, f"Verplichte approval voor {invoice.risk_level.value} risico"

        # Approval nodig bij anomalieen
        if len(invoice.anomalies) >= 2:
            return True, "Meerdere afwijkingen gedetecteerd"

        # Approval voor bedragen > 25k
        if invoice.amount_incl_vat > 25000:
            return True, "Hoog bedrag vereist approval"

        return False, ""

    def process_approval(
        self, invoice: Invoice, decision: str, approver: str, reason: str = ""
    ) -> bool:
        """
        Stap 4: Verwerk approval beslissing

        Args:
            invoice: Invoice object
            decision: "approved" of "rejected"
            approver: Wie heeft geapproved
            reason: Optionele reden

        Returns:
            True if approved
        """
        if decision == "approved":
            invoice.status = InvoiceStatus.APPROVED
            invoice.approved_by = approver
            invoice.approved_at = datetime.now(timezone.utc)

            self._log_audit(
                invoice_id=invoice.invoice_id,
                step="approval_decision",
                status="approved",
                details={
                    "approver": approver,
                    "reason": reason,
                },
            )
            return True
        else:
            invoice.status = InvoiceStatus.REJECTED
            invoice.rejection_reason = reason

            self._log_audit(
                invoice_id=invoice.invoice_id,
                step="approval_decision",
                status="rejected",
                details={
                    "approver": approver,
                    "reason": reason,
                },
            )
            return False

    def simulate_approval_timeout(self, invoice: Invoice) -> bool:
        """
        Simuleer approval timeout (voor unhappy test)

        Returns:
            True als timeout opgetreden
        """
        self._approval_timeouts += 1
        invoice.status = InvoiceStatus.EXCEPTION
        invoice.exception_type = D3ExceptionType.APPROVAL_TIMEOUT
        invoice.exception_message = "Approval service timeout - workflow pending"

        self._log_audit(
            invoice_id=invoice.invoice_id,
            step="approval_request",
            status="timeout",
            details={"timeout_seconds": 30},
            error="Approval service timeout",
        )

        return True

    def generate_daily_report(self, report_date: date) -> DailyReport:
        """
        Stap 5: Genereer dagrapport

        Args:
            report_date: Datum voor rapport

        Returns:
            DailyReport object
        """
        report_id = f"RPT-{uuid.uuid4().hex[:6].upper()}"

        # Filter invoices voor deze dag
        day_invoices = [inv for inv in self._processed_invoices if inv.invoice_date == report_date]

        # Tel statussen
        validated = sum(1 for inv in day_invoices if inv.status == InvoiceStatus.VALIDATED)
        anomalies = sum(1 for inv in day_invoices if inv.status == InvoiceStatus.ANOMALY_DETECTED)
        approval_pending = sum(
            1 for inv in day_invoices if inv.status == InvoiceStatus.APPROVAL_REQUIRED
        )
        rejected = sum(1 for inv in day_invoices if inv.status == InvoiceStatus.REJECTED)
        exceptions = sum(1 for inv in day_invoices if inv.status == InvoiceStatus.EXCEPTION)

        # Bereken bedragen
        amount_validated = sum(
            inv.amount_incl_vat for inv in day_invoices if inv.status == InvoiceStatus.VALIDATED
        )
        amount_flagged = sum(
            inv.amount_incl_vat
            for inv in day_invoices
            if inv.status in [InvoiceStatus.ANOMALY_DETECTED, InvoiceStatus.APPROVAL_REQUIRED]
        )

        # Risico verdeling
        risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for inv in day_invoices:
            risk_dist[inv.risk_level.value] = risk_dist.get(inv.risk_level.value, 0) + 1

        # Anomalies summary
        anomalies_summary: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for inv in day_invoices:
            if inv.anomalies:
                anomalies_summary.append(
                    {
                        "invoice_id": inv.invoice_id,
                        "vendor": inv.vendor_name,
                        "anomalies": inv.anomalies,
                    }
                )

        report = DailyReport(
            report_id=report_id,
            report_date=report_date,
            total_invoices=len(day_invoices),
            validated_count=validated,
            anomaly_count=anomalies,
            approval_pending_count=approval_pending,
            rejected_count=rejected,
            exception_count=exceptions,
            total_amount_validated=amount_validated,
            total_amount_flagged=amount_flagged,
            risk_distribution=risk_dist,
            anomalies_summary=anomalies_summary,
        )

        self._log_audit(
            invoice_id="REPORT",
            step="daily_report_generation",
            status="success",
            details={
                "report_id": report_id,
                "total_invoices": len(day_invoices),
            },
        )

        return report

    def run_invoice_control(
        self,
        invoice_batch: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        auto_approve_threshold: RiskLevel = RiskLevel.MEDIUM,
        simulate_corrupt_data: bool = False,
        simulate_approval_timeout: bool = False,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Complete D3 workflow: Factuurcontrole -> Approval

        Args:
            invoice_batch: List[Any] van factuur data dicts  # TODO(TYPE): replace Any with concrete type
            auto_approve_threshold: Tot welk risico level automatisch approven
            simulate_corrupt_data: Als True, corrupt eerste factuur
            simulate_approval_timeout: Als True, simuleer approval timeout

        Returns:
            Workflow resultaat met audit trail en dagrapport
        """
        result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow_id": self.workflow_id,
            "batch_size": len(invoice_batch),
            "processed_count": 0,
            "exception_count": 0,
            "invoices": [],
            "daily_report": None,
            "audit_trail": [],
        }

        processed_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for idx, invoice_data in enumerate(invoice_batch):
            # Simuleer corrupte data voor eerste factuur (unhappy test)
            if simulate_corrupt_data and idx == 0:
                invoice_data = {"corrupt": "data", "missing": "fields"}

            # Stap 1: Parse factuur
            invoice = self.parse_invoice_data(invoice_data)

            if invoice is None:
                # Corrupte data - skip maar log
                result["exception_count"] += 1
                continue

            # Stap 2: Risico beoordeling
            risk_level, risk_score, anomalies = self.calculate_risk_score(invoice)
            invoice.risk_level = risk_level
            invoice.risk_score = risk_score
            invoice.anomalies = anomalies

            if anomalies:
                invoice.status = InvoiceStatus.ANOMALY_DETECTED
            else:
                invoice.status = InvoiceStatus.VALIDATED

            # Stap 3: Approval nodig?
            approval_needed, approval_reason = self.determine_approval_need(invoice)

            if approval_needed:
                invoice.approval_required = True
                invoice.approval_reason = approval_reason
                invoice.status = InvoiceStatus.APPROVAL_REQUIRED

                # Stap 4: Approval verwerking (of timeout)
                if simulate_approval_timeout:
                    self.simulate_approval_timeout(invoice)
                else:
                    # Auto-approve voor demo (bij lage drempel)
                    if risk_level.value in ["low", "medium"]:
                        self.process_approval(
                            invoice, "approved", "system_auto", "Auto-approved voor demo"
                        )

            # Sla processed invoice op
            self._processed_invoices.append(invoice)
            processed_ids.append(invoice.invoice_id)
            result["processed_count"] += 1

            # Voeg toe aan resultaat
            result["invoices"].append(invoice.to_dict())

        # Stap 5: Genereer dagrapport (gebruik datum van eerste factuur of vandaag)
        report_date = date.today()
        if self._processed_invoices:
            report_date = self._processed_invoices[0].invoice_date

        daily_report = self.generate_daily_report(report_date)
        result["daily_report"] = daily_report.to_dict()

        # Audit trail
        result["audit_trail"] = [self._record_to_dict(r) for r in self.audit_records]

        return result

    def _record_to_dict(self, record: D3AuditRecord) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert audit record to dict"""
        return {
            "record_id": record.record_id,
            "invoice_id": record.invoice_id,
            "step": record.step,
            "status": record.status,
            "timestamp": record.timestamp.isoformat(),
            "details": record.details,
            "error": record.error_message,
        }

    def export_audit_log(self) -> str:
        """Export audit log als JSON string"""
        return json.dumps([self._record_to_dict(r) for r in self.audit_records], indent=2)


class D3WorkflowRunner:
    """
    Runner voor D3 workflow integratie met bestaande workflow engine.
    """

    def __init__(self, tenant_id: str = "demo") -> None:
        self.tenant_id = tenant_id

    def create_workflow_def(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Creeer C7 workflow definition voor D3"""
        return {
            "workflow_id": "d3-invoice-control",
            "name": "D3: Factuurcontrole naar Approval",
            "description": "Demo workflow: batch controle -> risico score -> approval -> dagrapport",
            "version": 1,
            "nodes": [
                {
                    "id": "invoice-parse",
                    "type": "task",
                    "name": "Factuur Parse",
                    "capability": "d3.parse_invoice",
                },
                {
                    "id": "risk-assessment",
                    "type": "task",
                    "name": "Risico Beoordeling",
                    "capability": "d3.calculate_risk",
                },
                {
                    "id": "anomaly-check",
                    "type": "decision",
                    "name": "Afwijking Check",
                    "capability": "d3.check_anomalies",
                },
                {
                    "id": "approval-gate",
                    "type": "approval",
                    "name": "Approval Gate",
                    "capability": "d3.approval_required",
                },
                {
                    "id": "daily-report",
                    "type": "task",
                    "name": "Dagrapport",
                    "capability": "d3.generate_report",
                },
            ],
            "edges": [
                {"from": "invoice-parse", "to": "risk-assessment"},
                {"from": "risk-assessment", "to": "anomaly-check"},
                {"from": "anomaly-check", "to": "approval-gate", "condition": "anomalies_found"},
                {"from": "anomaly-check", "to": "daily-report", "condition": "no_anomalies"},
                {"from": "approval-gate", "to": "daily-report"},
            ],
        }
