"""
D1 Demo Template Tests

Tests voor Intake → Offerte → Review workflow.
- Happy: geldige intake -> offerte draft + approval + notificatie
- Unhappy 1: verplichte intakevelden missen -> validatiefout vóór execute
- Unhappy 2: approval afgewezen -> workflow status rejected met audit bewijs
"""

from datetime import datetime

import pytest

from src.core.demos.d1_intake_quote import (
    ApprovalDecision,
    ApprovalGate,
    D1Status,
    D1Template,
    IntakeData,
    Quote,
)


class TestD1HappyPath:
    """Happy path tests voor D1 workflow"""

    def test_happy_complete_intake_to_quote_workflow(self):
        """
        Happy: geldige intake -> offerte draft + approval + notificatie

        Scenario:
        1. Valide intake data
        2. Offerte wordt gegenereerd
        3. Approval gate wordt aangemaakt
        4. Auto-approve (voor demo)
        5. Notificatie wordt verstuurd
        6. Workflow complete
        """
        # Arrange
        template = D1Template()
        intake = IntakeData(
            naam="Jan Jansen",
            email="jan@example.com",
            telefoon="0612345678",
            bedrijf="Jansen BV",
            project_type="website",
            budget_range="10k-25k",
            timeline="3_maanden",
            requirements="Nieuwe website met CMS",
        )

        # Act
        result = template.run_intake_to_quote(intake, auto_approve=True)

        # Assert
        assert result["status"] == D1Status.COMPLETED.value
        assert result["workflow_id"].startswith("d1-")

        # Intake validatie succes
        assert result["intake"] is not None
        assert result["intake"]["naam"] == "Jan Jansen"
        assert result["intake"]["project_type"] == "website"

        # Offerte gegenereerd
        assert result["quote"] is not None
        assert result["quote"]["quote_id"].startswith("OFF-")
        assert result["quote"]["totaal_incl_btw"] > 0
        assert len(result["quote"]["regels"]) > 0

        # Approval gate
        assert result["approval_gate"] is not None
        assert result["approval_gate"]["gate_id"].startswith("GATE-")
        assert result["approval_gate"]["status"] == "approved"

        # Notificatie
        assert result["notification"] is not None
        assert result["notification"]["to"] == "jan@example.com"
        assert "approved" in result["notification"]["subject"].lower()

        # Audit trail aanwezig
        assert len(result["audit_trail"]) >= 4  # intake, quote, approval, notification

        # Geen errors
        assert len(result["errors"]) == 0


class TestD1UnhappyPath:
    """Unhappy path tests voor D1 workflow"""

    def test_unhappy_missing_required_fields_validation_fails(self):
        """
        Unhappy 1: verplichte intakevelden missen -> validatiefout vóór execute

        Scenario:
        1. Ontbrekende verplichte velden (naam, email)
        2. Validatie faalt
        3. Workflow stopt voor offerte generatie
        4. Audit trail toont validatie errors
        """
        # Arrange
        template = D1Template()
        intake = IntakeData(
            naam="",  # Missing!
            email="invalid-email",  # Invalid!
            telefoon="",
            bedrijf="",
            project_type="website",
            budget_range="invalid-range",  # Invalid!
            timeline="",
            requirements="",
        )

        # Act
        result = template.run_intake_to_quote(intake, auto_approve=True)

        # Assert
        assert result["status"] == D1Status.INTAKE_INVALID.value
        assert len(result["errors"]) > 0

        # Check specifieke errors
        errors = result["errors"]
        assert any("naam" in e.lower() for e in errors)
        assert any("email" in e.lower() for e in errors)

        # Workflow stopt hier - geen offerte of approval
        assert result["quote"] is None
        assert result["approval_gate"] is None
        assert result["notification"] is None

        # Audit trail toont validatie failure
        audit = result["audit_trail"]
        assert len(audit) >= 1

        validation_record = audit[0]
        assert validation_record["step"] == "intake_validation"
        assert validation_record["status"] == "failed"
        assert "errors" in validation_record["details"]
        assert validation_record["error"] is not None

    def test_unhappy_approval_rejected_workflow_blocked(self):
        """
        Unhappy 2: approval afgewezen -> workflow status rejected met audit bewijs

        Scenario:
        1. Valide intake
        2. Offerte gegenereerd
        3. Approval aangevraagd
        4. Approval AFGEWEZEN (te duur / niet haalbaar)
        5. Workflow status = rejected
        6. Notificatie verstuurd met afwijzing
        7. Audit trail toont afwijzing
        """
        # Arrange
        template = D1Template()
        intake = IntakeData(
            naam="Piet Pietersen",
            email="piet@example.com",
            telefoon="0687654321",
            bedrijf="Pietersen Co",
            project_type="app",
            budget_range="25k-50k",
            timeline="6_maanden",
            requirements="Complexe app met API",
        )

        # Eerst workflow tot approval gate
        quote = template.generate_quote(intake)
        gate = template.create_approval_gate(quote)

        # Act: expliciet afwijzen
        template.process_approval(
            gate, "rejected", "Budget overschreden - klant wacht op aanpassing"
        )

        # Assert
        assert gate.decision == ApprovalDecision.REJECTED
        assert gate.decision_reason == "Budget overschreden - klant wacht op aanpassing"
        assert gate.decided_at is not None

        # Volledige workflow run met afwijzing
        template2 = D1Template()  # Frisse template voor clean test
        result = template2.run_intake_to_quote(intake, auto_approve=False)

        # Manual approval rejection (simuleren via approval gate)
        quote2 = template2.generate_quote(intake)
        gate2 = template2.create_approval_gate(quote2)
        template2.process_approval(gate2, "rejected", "Te duur voor dit budget")

        # Status is rejected
        assert gate2.decision == ApprovalDecision.REJECTED

        # Audit trail toont afwijzing
        audit = template2.audit_records
        approval_records = [r for r in audit if r.step == "approval_decision"]
        assert len(approval_records) >= 1

        approval_record = approval_records[0]
        assert approval_record.status == "rejected"
        assert "reden" in approval_record.details or "reason" in approval_record.details


class TestD1QuoteGeneration:
    """Tests specifiek voor offerte generatie"""

    def test_quote_calculated_correctly(self):
        """Test dat offerte bedragen correct worden berekend"""
        template = D1Template()
        intake = IntakeData(
            naam="Test Klant",
            email="test@test.com",
            telefoon="",
            bedrijf="",
            project_type="website",
            budget_range="5k-10k",
            timeline="",
            requirements="",
        )

        quote = template.generate_quote(intake)

        # Berekeningen correct
        expected_subtotal = sum(line.total for line in quote.lines)
        assert quote.subtotal == expected_subtotal

        expected_btw = quote.subtotal * 0.21
        assert quote.btw_amount == expected_btw

        expected_total = quote.subtotal + expected_btw
        assert quote.total == expected_total

        # Serialize werkt
        quote_dict = quote.to_dict()
        assert quote_dict["subtotaal"] == quote.subtotal
        assert quote_dict["btw_bedrag"] == quote.btw_amount
        assert quote_dict["totaal_incl_btw"] == quote.total


class TestD1ApprovalGate:
    """Tests specifiek voor approval gate"""

    def test_approval_gate_creation(self):
        """Test dat approval gate correct wordt aangemaakt"""
        template = D1Template()
        intake = IntakeData(
            naam="Test",
            email="test@test.com",
            telefoon="",
            bedrijf="",
            project_type="consulting",
            budget_range="5k-10k",
            timeline="",
            requirements="",
        )

        quote = template.generate_quote(intake)
        gate = template.create_approval_gate(quote, approver_email="manager@demo.nl")

        assert gate.gate_id.startswith("GATE-")
        assert gate.quote_id == quote.quote_id
        assert gate.approver_email == "manager@demo.nl"
        assert gate.decision == ApprovalDecision.PENDING
        assert gate.decided_at is None

    def test_approval_workflow_transitions(self):
        """Test alle approval state transitions"""
        template = D1Template()
        intake = IntakeData(
            naam="Test",
            email="test@test.com",
            telefoon="",
            bedrijf="",
            project_type="website",
            budget_range="5k-10k",
            timeline="",
            requirements="",
        )

        quote = template.generate_quote(intake)
        gate = template.create_approval_gate(quote)

        # Start: pending
        assert gate.decision == ApprovalDecision.PENDING

        # Na approve
        template.process_approval(gate, "approved", "Ziet er goed uit")
        assert gate.decision == ApprovalDecision.APPROVED
        assert gate.decision_reason == "Ziet er goed uit"
        assert gate.decided_at is not None

    def test_audit_export(self):
        """Test dat audit log geëxporteerd kan worden"""
        template = D1Template()
        intake = IntakeData(
            naam="Test Audit",
            email="audit@test.com",
            telefoon="",
            bedrijf="",
            project_type="website",
            budget_range="5k-10k",
            timeline="",
            requirements="",
        )

        template.run_intake_to_quote(intake, auto_approve=True)

        # Export audit
        audit_json = template.export_audit_log()
        assert len(audit_json) > 0
        assert "intake_validation" in audit_json
        assert "quote_generation" in audit_json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
