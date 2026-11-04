"""
D1 Demo Template: Intake -> Offerte -> Review

Workflow:
1. Intake formulier validatie
2. Offerte generatie (demo-data based)
3. Approval gate voor prijs/voorwaarden
4. Notificatie (simulated)

Gebruikt demo-data, geen externe API's.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class D1Status(Enum):
    """D1 workflow status"""

    PENDING = "pending"
    INTAKE_VALID = "intake_valid"
    INTAKE_INVALID = "intake_invalid"
    QUOTE_GENERATED = "quote_generated"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NOTIFIED = "notified"
    COMPLETED = "completed"


class ApprovalDecision(Enum):
    """Approval gate decision"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class IntakeData:
    """Klant intake formulier data"""

    naam: str
    email: str
    telefoon: str
    bedrijf: str
    project_type: str  # "website", "app", "consulting"
    budget_range: str  # "5k-10k", "10k-25k", "25k-50k", "50k+"
    timeline: str  # "1_maand", "3_maanden", "6_maanden"
    requirements: str

    # Validatie regels
    REQUIRED_FIELDS = ["naam", "email", "project_type", "budget_range"]

    def validate(self) -> tuple[bool, list[str]]:
        """Valideer intake data"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(self, field_name, None)
            if not value or str(value).strip() == "":
                errors.append(f"Verplicht veld '{field_name}' ontbreekt")

        # Email validatie (basic)
        if self.email and "@" not in self.email:
            errors.append("Ongeldig email formaat")

        # Budget range validatie
        valid_budgets = ["5k-10k", "10k-25k", "25k-50k", "50k+"]
        if self.budget_range and self.budget_range not in valid_budgets:
            errors.append(f"Ongeldig budget range. Keuzes: {', '.join(valid_budgets)}")

        return len(errors) == 0, errors


@dataclass
class QuoteLine:
    """Offerte regel"""

    item: str
    description: str
    quantity: int
    unit_price: float
    total: float = field(init=False)

    def __post_init__(self) -> None:
        self.total = self.quantity * self.unit_price


@dataclass
class Quote:
    """Gegenereerde offerte"""

    quote_id: str
    intake_data: IntakeData
    lines: list[QuoteLine]
    subtotal: float = field(init=False)
    btw_percentage: float = 21.0
    btw_amount: float = field(init=False)
    total: float = field(init=False)
    valid_until: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    terms: str = "Betaling binnen 14 dagen na akkoord"

    def __post_init__(self) -> None:
        self.subtotal = sum(line.total for line in self.lines)
        self.btw_amount = self.subtotal * (self.btw_percentage / 100)
        self.total = self.subtotal + self.btw_amount

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize quote to dict"""
        return {
            "quote_id": self.quote_id,
            "klant": {
                "naam": self.intake_data.naam,
                "email": self.intake_data.email,
                "bedrijf": self.intake_data.bedrijf,
            },
            "regels": [
                {
                    "item": line.item,
                    "omschrijving": line.description,
                    "aantal": line.quantity,
                    "prijs_per_stuk": line.unit_price,
                    "totaal": line.total,
                }
                for line in self.lines
            ],
            "subtotaal": self.subtotal,
            "btw_percentage": self.btw_percentage,
            "btw_bedrag": self.btw_amount,
            "totaal_incl_btw": self.total,
            "geldig_tot": self.valid_until.isoformat(),
            "betalingsvoorwaarden": self.terms,
        }


@dataclass
class ApprovalGate:
    """Approval gate voor offerte review"""

    gate_id: str
    quote_id: str
    approver_email: str
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decision_reason: str = ""
    decided_at: datetime | None = None

    def approve(self, reason: str = "") -> None:
        """Goedkeuren"""
        self.decision = ApprovalDecision.APPROVED
        self.decision_reason = reason or "Goedgekeurd"
        self.decided_at = datetime.now(timezone.utc)

    def reject(self, reason: str) -> None:
        """Afkeuren"""
        self.decision = ApprovalDecision.REJECTED
        self.decision_reason = reason
        self.decided_at = datetime.now(timezone.utc)


@dataclass
class D1AuditRecord:
    """Audit record voor D1 workflow"""

    record_id: str
    workflow_id: str
    step: str
    status: str
    timestamp: datetime
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None


class D1Template:
    """
    D1 Demo Template: Intake -> Offerte -> Review

    Gebruik:
        template = D1Template()
        result = template.run_intake_to_quote(intake_data)
    """

    # Demo prijzen per project type (no-cost, geen externe API)
    PRICING = {
        "website": {
            "5k-10k": [
                QuoteLine("Basis website", "5 pagina's, responsive", 1, 3500),
                QuoteLine("SEO optimalisatie", "Basis SEO setup", 1, 1500),
            ],
            "10k-25k": [
                QuoteLine("Premium website", "10+ pagina's, CMS", 1, 8500),
                QuoteLine("SEO + Analytics", "Uitgebreide setup", 1, 3500),
                QuoteLine("Content creatie", "10 pagina's content", 1, 2500),
            ],
        },
        "app": {
            "10k-25k": [
                QuoteLine("MVP app", "iOS/Android, basis features", 1, 12000),
                QuoteLine("App store setup", "Publicatie support", 1, 2000),
            ],
            "25k-50k": [
                QuoteLine("Full app", "iOS/Android, advanced features", 1, 28000),
                QuoteLine("Backend API", "REST API + database", 1, 12000),
                QuoteLine("App store setup", "Publicatie support", 1, 2000),
            ],
        },
        "consulting": {
            "5k-10k": [
                QuoteLine("Strategie sessies", "4 sessies a 2 uur", 8, 500),
                QuoteLine("Rapportage", "Analyse + advies", 1, 2000),
            ],
            "10k-25k": [
                QuoteLine("Intensief traject", "10 sessies a 2 uur", 20, 500),
                QuoteLine("Deep dive analyse", "Uitgebreide rapportage", 1, 5000),
            ],
        },
    }

    def __init__(self) -> None:
        self.audit_records: list[D1AuditRecord] = []
        self.workflow_id = f"d1-{uuid.uuid4().hex[:8]}"

    def _log_audit(
        self, step: str, status: str, details: dict[str, Any], error: str | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Log audit record"""
        record = D1AuditRecord(
            record_id=str(uuid.uuid4()),
            workflow_id=self.workflow_id,
            step=step,
            status=status,
            timestamp=datetime.now(timezone.utc),
            details=details,
            error_message=error,
        )
        self.audit_records.append(record)

    def validate_intake(self, intake_data: IntakeData) -> tuple[bool, list[str]]:
        """
        Stap 1: Intake validatie

        Returns:
            (success, errors)
        """
        valid, errors = intake_data.validate()

        if valid:
            self._log_audit(
                step="intake_validation",
                status="success",
                details={"naam": intake_data.naam, "project_type": intake_data.project_type},
            )
        else:
            self._log_audit(
                step="intake_validation",
                status="failed",
                details={"errors": errors},
                error="; ".join(errors),
            )

        return valid, errors

    def generate_quote(self, intake_data: IntakeData) -> Quote:
        """
        Stap 2: Genereer offerte op basis van demo-data

        Returns:
            Quote object
        """
        quote_id = f"OFF-{uuid.uuid4().hex[:6].upper()}"

        # Lookup pricing based on project type and budget
        project_pricing = self.PRICING.get(intake_data.project_type, {})
        lines = project_pricing.get(intake_data.budget_range, [])

        # Fallback: generieke offerte
        if not lines:
            lines = [
                QuoteLine("Consulting", "Op maat gemaakte oplossing", 1, 5000),
            ]

        quote = Quote(
            quote_id=quote_id,
            intake_data=intake_data,
            lines=lines,
        )

        self._log_audit(
            step="quote_generation",
            status="success",
            details={
                "quote_id": quote_id,
                "total": quote.total,
                "regels": len(lines),
            },
        )

        return quote

    def create_approval_gate(
        self, quote: Quote, approver_email: str = "sales@demo.nl"
    ) -> ApprovalGate:
        """
        Stap 3: Creeer approval gate

        Returns:
            ApprovalGate object
        """
        gate = ApprovalGate(
            gate_id=f"GATE-{uuid.uuid4().hex[:6].upper()}",
            quote_id=quote.quote_id,
            approver_email=approver_email,
        )

        self._log_audit(
            step="approval_gate_created",
            status="pending",
            details={
                "gate_id": gate.gate_id,
                "quote_id": quote.quote_id,
                "approver": approver_email,
            },
        )

        return gate

    def process_approval(self, gate: ApprovalGate, decision: str, reason: str = "") -> bool:
        """
        Stap 3b: Verwerk approval beslissing

        Args:
            gate: ApprovalGate instance
            decision: "approved" of "rejected"
            reason: Optionele reden

        Returns:
            True if approved, False if rejected
        """
        if decision == "approved":
            gate.approve(reason)
            self._log_audit(
                step="approval_decision",
                status="approved",
                details={
                    "gate_id": gate.gate_id,
                    "reason": reason,
                },
            )
            return True
        else:
            gate.reject(reason or "Afgekeurd")
            self._log_audit(
                step="approval_decision",
                status="rejected",
                details={
                    "gate_id": gate.gate_id,
                    "reason": reason,
                },
            )
            return False

    def send_notification(
        self, intake_data: IntakeData, quote: Quote, gate: ApprovalGate
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 4: Simuleer notificatie (no-cost, geen externe API)

        Returns:
            Notificatie details
        """
        notification = {
            "to": intake_data.email,
            "subject": f"Offerte {quote.quote_id} - {gate.decision.value}",
            "body": f"""
Beste {intake_data.naam},

Uw offerte ({quote.quote_id}) is {gate.decision.value}.

Totaal bedrag: EUR{quote.total:,.2f} incl. BTW

{gate.decision_reason}

Met vriendelijke groet,
Demo Sales Team
            """.strip(),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

        self._log_audit(
            step="notification_sent",
            status="success",
            details={
                "recipient": intake_data.email,
                "subject": notification["subject"],
            },
        )

        return notification

    def run_intake_to_quote(
        self, intake_data: IntakeData, auto_approve: bool = False
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Complete D1 workflow: Intake -> Offerte -> Review -> Notificatie

        Args:
            intake_data: Intake formulier data
            auto_approve: Of de approval automatisch moet worden goedgekeurd (voor demo)

        Returns:
            Workflow resultaat met audit trail
        """
        result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow_id": self.workflow_id,
            "status": D1Status.PENDING.value,
            "intake": None,
            "quote": None,
            "approval_gate": None,
            "notification": None,
            "audit_trail": [],
            "errors": [],
        }

        # Stap 1: Intake validatie
        valid, errors = self.validate_intake(intake_data)
        if not valid:
            result["status"] = D1Status.INTAKE_INVALID.value
            result["errors"] = errors
            result["audit_trail"] = [self._record_to_dict(r) for r in self.audit_records]
            return result

        result["status"] = D1Status.INTAKE_VALID.value
        result["intake"] = {
            "naam": intake_data.naam,
            "email": intake_data.email,
            "project_type": intake_data.project_type,
        }

        # Stap 2: Offerte generatie
        quote = self.generate_quote(intake_data)
        result["quote"] = quote.to_dict()
        result["status"] = D1Status.QUOTE_GENERATED.value

        # Stap 3: Approval gate
        gate = self.create_approval_gate(quote)
        result["approval_gate"] = {
            "gate_id": gate.gate_id,
            "status": gate.decision.value,
        }
        result["status"] = D1Status.APPROVAL_PENDING.value

        # Stap 3b: Approval verwerking
        if auto_approve:
            self.process_approval(gate, "approved", "Automatisch goedgekeurd voor demo")

        result["approval_gate"]["status"] = gate.decision.value
        result["approval_gate"]["decision_reason"] = gate.decision_reason

        if gate.decision == ApprovalDecision.REJECTED:
            result["status"] = D1Status.REJECTED.value
        else:
            result["status"] = D1Status.APPROVED.value

        # Stap 4: Notificatie
        notification = self.send_notification(intake_data, quote, gate)
        result["notification"] = notification

        if gate.decision == ApprovalDecision.APPROVED:
            result["status"] = D1Status.COMPLETED.value

        # Audit trail toevoegen
        result["audit_trail"] = [self._record_to_dict(r) for r in self.audit_records]

        return result

    def _record_to_dict(self, record: D1AuditRecord) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert audit record to dict"""
        return {
            "record_id": record.record_id,
            "step": record.step,
            "status": record.status,
            "timestamp": record.timestamp.isoformat(),
            "details": record.details,
            "error": record.error_message,
        }

    def export_audit_log(self) -> str:
        """Export audit log als JSON string"""
        return json.dumps([self._record_to_dict(r) for r in self.audit_records], indent=2)


class D1WorkflowRunner:
    """
    Runner voor D1 workflow integratie met bestaande workflow engine.

    Deze class biedt een interface tussen de D1 template en de
    C7 workflow engine.
    """

    def __init__(self, tenant_id: str = "demo") -> None:
        self.tenant_id = tenant_id

    def create_workflow_def(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Creeer C7 workflow definition voor D1

        Returns:
            Workflow spec compatibel met C7Workflow
        """
        return {
            "workflow_id": "d1-intake-quote-review",
            "name": "D1: Intake naar Offerte Review",
            "description": "Demo workflow: klant intake -> offerte generatie -> approval -> notificatie",
            "version": 1,
            "nodes": [
                {
                    "id": "intake-validation",
                    "type": "task",
                    "name": "Intake Validatie",
                    "capability": "d1.validate_intake",
                },
                {
                    "id": "quote-generation",
                    "type": "task",
                    "name": "Offerte Generatie",
                    "capability": "d1.generate_quote",
                },
                {
                    "id": "approval-gate",
                    "type": "approval",
                    "name": "Offerte Approval",
                    "capability": "d1.approval_gate",
                },
                {
                    "id": "notification",
                    "type": "task",
                    "name": "Notificatie Versturen",
                    "capability": "d1.send_notification",
                },
            ],
            "edges": [
                {"from": "intake-validation", "to": "quote-generation", "condition": "success"},
                {"from": "quote-generation", "to": "approval-gate"},
                {"from": "approval-gate", "to": "notification", "condition": "approved"},
                {"from": "approval-gate", "to": "notification", "condition": "rejected"},
            ],
        }
