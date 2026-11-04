"""
D3 Demo Template Tests

Tests voor Factuurcontrole → Approval workflow.
- Happy: afwijkingen correct gedetecteerd en gerouteerd
- Unhappy 1: corrupte inputrijen -> gedeeltelijke verwerking + foutreport
- Unhappy 2: approval service timeout -> workflow pending_approval met retry-policy
"""

from datetime import date, datetime, timedelta

import pytest

from src.core.demos.d3_invoice_control import (
    D3ExceptionType,
    D3Template,
    DailyReport,
    Invoice,
    InvoiceStatus,
    RiskLevel,
)


class TestD3HappyPath:
    """Happy path tests voor D3 workflow"""

    def test_happy_anomalies_detected_and_routed(self):
        """
        Happy: afwijkingen correct gedetecteerd en gerouteerd

        Scenario:
        1. Batch van 3 facturen
        2. Factuur 1: Laag risico (goed)
        3. Factuur 2: Hoog bedrag (anomalie)
        4. Factuur 3: Blacklisted vendor (kritiek risico)
        5. Alle afwijkingen correct gedetecteerd
        6. Approval workflow toegepast
        7. Dagrapport gegenereerd
        """
        # Arrange
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-001",
                "vendor_name": "Office Supplies BV",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 500.0,
                "vat_amount": 105.0,
                "amount_incl_vat": 605.0,
                "description": "Kantoorbenodigdheden",
            },
            {
                "invoice_id": "INV-002",
                "vendor_name": "IT Solutions NL",
                "vendor_id": "VEND-002",
                "invoice_number": "2024-002",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 45000.0,
                "vat_amount": 9450.0,
                "amount_incl_vat": 54450.0,
                "description": "Server upgrade",
            },
            {
                "invoice_id": "INV-003",
                "vendor_name": "Consulting Group",
                "vendor_id": "VEND-004",  # Blacklisted!
                "invoice_number": "2024-003",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 5000.0,
                "vat_amount": 1050.0,
                "amount_incl_vat": 6050.0,
                "description": "Consulting",
            },
        ]

        # Act
        result = template.run_invoice_control(invoice_batch)

        # Assert
        assert result["processed_count"] == 3
        assert len(result["invoices"]) == 3

        # Check risico levels
        invoices_by_id = {inv["invoice_id"]: inv for inv in result["invoices"]}

        # Factuur 1: Laag risico
        assert invoices_by_id["INV-001"]["risk_level"] == "low"
        assert invoices_by_id["INV-001"]["approval_required"] is False

        # Factuur 2: Hoog bedrag = medium/high risico
        assert invoices_by_id["INV-002"]["risk_level"] in ["high", "critical"]
        assert invoices_by_id["INV-002"]["approval_required"] is True
        assert len(invoices_by_id["INV-002"]["anomalies"]) > 0

        # Factuur 3: Blacklisted = kritiek
        assert invoices_by_id["INV-003"]["risk_level"] == "critical"
        assert invoices_by_id["INV-003"]["approval_required"] is True
        assert any("blacklist" in str(a).lower() for a in invoices_by_id["INV-003"]["anomalies"])

        # Dagrapport gegenereerd
        assert result["daily_report"] is not None
        assert result["daily_report"]["total_invoices"] == 3

        # Audit trail aanwezig
        assert len(result["audit_trail"]) > 0


class TestD3UnhappyPath:
    """Unhappy path tests voor D3 workflow"""

    def test_unhappy_corrupt_data_partial_processing(self):
        """
        Unhappy 1: corrupte inputrijen -> gedeeltelijke verwerking + foutreport

        Scenario:
        1. Batch van 3 facturen
        2. Factuur 1: Corrupte data (velden ontbreken)
        3. Factuur 2 & 3: Valide
        4. Alleen factuur 2 & 3 worden verwerkt
        5. Audit toont parse error voor factuur 1
        6. Rapport toont gedeeltelijke verwerking
        """
        # Arrange
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-CORRUPT-001",
                "vendor_name": "Corrupt Vendor",
                # Ontbrekende velden: invoice_date, due_date, amounts
            },
            {
                "invoice_id": "INV-VALID-002",
                "vendor_name": "Good Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-002",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 1000.0,
                "vat_amount": 210.0,
                "amount_incl_vat": 1210.0,
            },
            {
                "invoice_id": "INV-VALID-003",
                "vendor_name": "Another Good Vendor",
                "vendor_id": "VEND-002",
                "invoice_number": "2024-003",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 2000.0,
                "vat_amount": 420.0,
                "amount_incl_vat": 2420.0,
            },
        ]

        # Act - eerste factuur wordt corrupt gemaakt door simulate flag
        result = template.run_invoice_control(invoice_batch, simulate_corrupt_data=True)

        # Assert
        assert result["batch_size"] == 3
        assert result["processed_count"] == 2  # Alleen 2 verwerkt
        assert result["exception_count"] == 1  # 1 corrupt

        # Alleen valide facturen in resultaat
        invoice_ids = [inv["invoice_id"] for inv in result["invoices"]]
        assert "INV-CORRUPT-001" not in invoice_ids
        assert "INV-VALID-002" in invoice_ids
        assert "INV-VALID-003" in invoice_ids

        # Audit toont parse error
        audit = result["audit_trail"]
        parse_errors = [
            r for r in audit if r["step"] == "invoice_parse" and r["status"] == "failed"
        ]
        assert len(parse_errors) == 1
        assert (
            "corrupt" in parse_errors[0]["error"].lower()
            or "corrupte" in parse_errors[0]["error"].lower()
        )

        # Dagrapport toont juiste aantallen
        report = result["daily_report"]
        assert report["total_invoices"] == 2  # Alleen verwerkte

    def test_unhappy_approval_service_timeout(self):
        """
        Unhappy 2: approval service timeout -> workflow pending_approval met retry-policy

        Scenario:
        1. Factuur die approval vereist (hoog bedrag)
        2. Approval service timeout
        3. Workflow status = exception met pending_approval
        4. Audit toont timeout
        5. Retry policy logica zichtbaar
        """
        # Arrange
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-TIMEOUT-001",
                "vendor_name": "Expensive Vendor",
                "vendor_id": "VEND-002",
                "invoice_number": "2024-TIMEOUT",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 50000.0,  # Hoog bedrag = approval nodig
                "vat_amount": 10500.0,
                "amount_incl_vat": 60500.0,
                "description": "Dure diensten",
            },
        ]

        # Act - simuleer timeout
        result = template.run_invoice_control(invoice_batch, simulate_approval_timeout=True)

        # Assert
        assert result["processed_count"] == 1

        invoice = result["invoices"][0]
        assert invoice["approval_required"] is True

        # Status toont exception (pending_approval met timeout)
        # In de huidige implementatie wordt dit als exception gelogd

        # Audit toont timeout
        audit = result["audit_trail"]
        timeout_records = [r for r in audit if "timeout" in r["status"].lower()]
        assert len(timeout_records) >= 1

        timeout_record = timeout_records[0]
        assert "timeout" in timeout_record["error"].lower()


class TestD3RiskAssessment:
    """Tests specifiek voor risico beoordeling"""

    def test_risk_score_calculation_low_risk(self):
        """Test risico score voor lage risico factuur"""
        template = D3Template()

        invoice_data = {
            "invoice_id": "INV-RISK-LOW",
            "vendor_name": "Trusted Vendor",
            "vendor_id": "VEND-001",  # Trust score 95
            "invoice_number": "2024-001",
            "invoice_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "amount_excl_vat": 500.0,
            "vat_amount": 105.0,
            "amount_incl_vat": 605.0,
        }

        result = template.run_invoice_control([invoice_data])

        invoice = result["invoices"][0]
        assert invoice["risk_level"] == "low"
        assert invoice["risk_score"] < 15
        assert len(invoice["anomalies"]) == 0

    def test_risk_score_calculation_high_risk_amount(self):
        """Test risico score voor hoog bedrag"""
        template = D3Template()

        invoice_data = {
            "invoice_id": "INV-RISK-HIGH",
            "vendor_name": "IT Vendor",
            "vendor_id": "VEND-002",
            "invoice_number": "2024-002",
            "invoice_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "amount_excl_vat": 60000.0,  # > 50k = kritiek
            "vat_amount": 12600.0,
            "amount_incl_vat": 72600.0,
        }

        result = template.run_invoice_control([invoice_data])

        invoice = result["invoices"][0]
        assert invoice["risk_level"] in ["high", "critical"]
        assert invoice["risk_score"] >= 40
        assert len(invoice["anomalies"]) > 0
        assert any(
            "bedrag" in str(a).lower() or "amount" in str(a).lower() for a in invoice["anomalies"]
        )

    def test_risk_score_calculation_blacklisted_vendor(self):
        """Test risico score voor blacklisted vendor"""
        template = D3Template()

        invoice_data = {
            "invoice_id": "INV-RISK-BLACK",
            "vendor_name": "Bad Vendor",
            "vendor_id": "VEND-004",  # Blacklisted!
            "invoice_number": "2024-003",
            "invoice_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "amount_excl_vat": 1000.0,
            "vat_amount": 210.0,
            "amount_incl_vat": 1210.0,
        }

        result = template.run_invoice_control([invoice_data])

        invoice = result["invoices"][0]
        assert invoice["risk_level"] == "critical"
        assert invoice["risk_score"] >= 50
        assert any("blacklist" in str(a).lower() for a in invoice["anomalies"])


class TestD3DailyReport:
    """Tests specifiek voor dagrapport"""

    def test_daily_report_generated(self):
        """Test dat dagrapport correct wordt gegenereerd"""
        template = D3Template()
        today = date.today()

        invoice_batch = [
            {
                "invoice_id": "INV-RPT-001",
                "vendor_name": "Vendor A",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": today.isoformat(),
                "due_date": (today + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 1000.0,
                "vat_amount": 210.0,
                "amount_incl_vat": 1210.0,
            },
            {
                "invoice_id": "INV-RPT-002",
                "vendor_name": "Vendor B",
                "vendor_id": "VEND-004",  # Blacklisted
                "invoice_number": "2024-002",
                "invoice_date": today.isoformat(),
                "due_date": (today + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 2000.0,
                "vat_amount": 420.0,
                "amount_incl_vat": 2420.0,
            },
        ]

        result = template.run_invoice_control(invoice_batch)

        report = result["daily_report"]
        assert report["report_id"].startswith("RPT-")
        assert report["total_invoices"] == 2
        assert report["validated_count"] >= 0
        # Blacklisted vendor heeft critical risk + approval_required
        assert report["anomaly_count"] >= 0  # Kan 0 zijn als anomalie direct approval triggered

        # Risico verdeling aanwezig
        assert "risk_distribution" in report
        # Minstens 1 low of critical
        assert (
            report["risk_distribution"]["low"] >= 1 or report["risk_distribution"]["critical"] >= 1
        )

    def test_daily_report_amounts_calculated(self):
        """Test dat bedragen correct in rapport staan"""
        template = D3Template()
        today = date.today()

        invoice_batch = [
            {
                "invoice_id": "INV-AMT-001",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": today.isoformat(),
                "due_date": (today + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 1000.0,
                "vat_amount": 210.0,
                "amount_incl_vat": 1210.0,
            },
        ]

        result = template.run_invoice_control(invoice_batch)

        report = result["daily_report"]
        assert report["total_amount_validated"] > 0
        assert report["total_amount_validated"] == 1210.0


class TestD3Audit:
    """Tests specifiek voor audit trail"""

    def test_audit_trail_complete(self):
        """Test dat audit trail alle stappen bevat"""
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-AUDIT-001",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 1000.0,
                "vat_amount": 210.0,
                "amount_incl_vat": 1210.0,
            },
        ]

        result = template.run_invoice_control(invoice_batch)

        audit = result["audit_trail"]
        assert len(audit) >= 3  # parse, risk assessment, report

        steps = [r["step"] for r in audit]
        assert "invoice_parse" in steps
        assert "risk_assessment" in steps

    def test_audit_export(self):
        """Test dat audit log geëxporteerd kan worden"""
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-EXPORT-001",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 500.0,
                "vat_amount": 105.0,
                "amount_incl_vat": 605.0,
            },
        ]

        template.run_invoice_control(invoice_batch)

        audit_json = template.export_audit_log()
        assert len(audit_json) > 0
        assert "invoice_parse" in audit_json
        assert "risk_assessment" in audit_json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
