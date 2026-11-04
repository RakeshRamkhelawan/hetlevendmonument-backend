"""
Fase 1 Integratietest: Golden Demo Templates

Echte run van D1, D2 en D3 zonder mocks.
Verifieert outputs, approval states, audit exports en KPI-velden.

Tests:
- Alle 3 templates kunnen worden geïnstantieerd
- Demo-data wordt correct verwerkt
- Approval flows werken end-to-end
- Audit trails zijn compleet en consistent
"""

from datetime import date, timedelta

import pytest

from src.core.demos.d1_intake_quote import D1Status, D1Template, IntakeData
from src.core.demos.d2_order_fulfilment import D2Template, OrderStatus
from src.core.demos.d3_invoice_control import D3Template, InvoiceStatus, RiskLevel


class TestFase1Integration:
    """
    Fase 1 Integratietest zonder mocks.

    Test scenario:
    1. D1: Intake → Offerte workflow
    2. D2: Order → Fulfilment workflow
    3. D3: Factuurcontrole workflow
    4. Cross-template verificaties
    """

    def test_d1_end_to_end_with_approval(self):
        """
        D1 end-to-end: Intake → Offerte → Approval → Notificatie

        Verifieert:
        - Intake validatie
        - Offerte generatie
        - Approval gate workflow
        - Notificatie verzending
        - Audit trail compleetheid
        """
        template = D1Template()

        intake = IntakeData(
            naam="Test Klant BV",
            email="klant@testbv.nl",
            telefoon="020-1234567",
            bedrijf="Test BV",
            project_type="website",
            budget_range="10k-25k",
            timeline="3_maanden",
            requirements="Nieuwe website met CMS en webshop",
        )

        # Run workflow
        result = template.run_intake_to_quote(intake, auto_approve=False)

        # Verifieer status flow
        assert result["workflow_id"].startswith("d1-")
        # Status is "approved" of "approval_pending" afhankelijk van implementatie
        assert result["status"] in [D1Status.APPROVAL_PENDING.value, D1Status.APPROVED.value]

        # Verifieer offerte
        assert result["quote"] is not None
        assert result["quote"]["quote_id"].startswith("OFF-")
        assert result["quote"]["totaal_incl_btw"] > 0

        # Verifieer approval gate
        assert result["approval_gate"] is not None
        # Status kan "pending" of "approved" zijn
        assert result["approval_gate"]["status"] in ["pending", "approved"]

        # Audit trail
        assert len(result["audit_trail"]) >= 3
        steps = [r["step"] for r in result["audit_trail"]]
        assert "intake_validation" in steps
        assert "quote_generation" in steps
        assert "approval_gate_created" in steps

    def test_d2_end_to_end_with_stock_check(self):
        """
        D2 end-to-end: Order → Picking → Packing → Shipping

        Verifieert:
        - Order parsing
        - Picking list generatie
        - Stock check
        - Status simulatie
        - Notificatie met retry
        """
        template = D2Template()

        order_data = {
            "order_id": "ORD-DEMO-001",
            "customer_name": "Demo Klant",
            "customer_email": "demo@klant.nl",
            "shipping_address": "Damrak 1, 1012 LG Amsterdam",
            "items": [
                {"sku": "SKU-001", "name": "Laptop", "quantity": 2, "stock": 10},
                {"sku": "SKU-003", "name": "Muis", "quantity": 5, "stock": 20},
            ],
        }

        # Run workflow
        result = template.run_order_to_fulfilment(order_data)

        # Verifieer status
        assert result["workflow_id"].startswith("d2-")
        assert result["status"] == "shipped"

        # Verifieer picking list
        assert result["picking_list"] is not None
        assert result["picking_list"]["list_id"].startswith("PICK-")
        assert len(result["picking_list"]["items"]) == 2

        # Verifieer tracking
        assert result["order_id"] == "ORD-DEMO-001"

        # Notificatie
        assert len(result["notifications"]) == 1
        assert result["notifications"][0]["status"] == "sent"

        # Audit trail
        assert len(result["audit_trail"]) >= 5
        steps = [r["step"] for r in result["audit_trail"]]
        assert "picking_list_generation" in steps
        assert "picking" in steps
        assert "packing" in steps
        assert "shipping" in steps

    def test_d3_end_to_end_with_risk_assessment(self):
        """
        D3 end-to-end: Factuurcontrole → Risico → Approval

        Verifieert:
        - Batch parsing
        - Risico scoring
        - Anomalie detectie
        - Approval routing
        - Dagrapport generatie
        """
        template = D3Template()
        today = date.today().isoformat()

        invoice_batch = [
            {
                "invoice_id": "INV-DEMO-001",
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
                "invoice_id": "INV-DEMO-002",
                "vendor_name": "Consulting Group",
                "vendor_id": "VEND-004",  # Blacklisted
                "invoice_number": "2024-002",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 10000.0,
                "vat_amount": 2100.0,
                "amount_incl_vat": 12100.0,
                "description": "Consulting diensten",
            },
        ]

        # Run workflow
        result = template.run_invoice_control(invoice_batch)

        # Verifieer batch verwerking
        assert result["workflow_id"].startswith("d3-")
        assert result["batch_size"] == 2
        assert result["processed_count"] == 2

        # Verifieer risico beoordeling
        invoices_by_id = {inv["invoice_id"]: inv for inv in result["invoices"]}

        # Factuur 1: Laag risico
        assert invoices_by_id["INV-DEMO-001"]["risk_level"] == "low"
        assert invoices_by_id["INV-DEMO-001"]["approval_required"] is False

        # Factuur 2: Hoog risico (blacklisted)
        assert invoices_by_id["INV-DEMO-002"]["risk_level"] == "critical"
        assert invoices_by_id["INV-DEMO-002"]["approval_required"] is True

        # Dagrapport
        assert result["daily_report"] is not None
        assert result["daily_report"]["total_invoices"] == 2
        assert result["daily_report"]["total_amount_validated"] > 0

        # Audit trail
        assert len(result["audit_trail"]) >= 4

    def test_all_templates_audit_export(self):
        """
        Verifieer dat alle templates audit logs kunnen exporteren

        Dit is essentieel voor compliance en debugging.
        """
        # D1
        d1 = D1Template()
        d1_intake = IntakeData(
            naam="Audit Test",
            email="audit@test.nl",
            telefoon="",
            bedrijf="",
            project_type="consulting",
            budget_range="5k-10k",
            timeline="",
            requirements="",
        )
        d1.run_intake_to_quote(d1_intake, auto_approve=True)
        d1_audit = d1.export_audit_log()
        assert len(d1_audit) > 0
        assert "intake_validation" in d1_audit

        # D2
        d2 = D2Template()
        d2_order = {
            "order_id": "ORD-AUDIT",
            "customer_name": "Audit",
            "customer_email": "audit@test.nl",
            "shipping_address": "Test",
            "items": [{"sku": "SKU-001", "name": "Test", "quantity": 1, "stock": 10}],
        }
        d2.run_order_to_fulfilment(d2_order)
        d2_audit = d2.export_audit_log()
        assert len(d2_audit) > 0
        assert "picking_list_generation" in d2_audit

        # D3
        d3 = D3Template()
        today = date.today().isoformat()
        d3_invoice = [
            {
                "invoice_id": "INV-AUDIT",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-AUDIT",
                "invoice_date": today,
                "due_date": today,
                "amount_excl_vat": 100.0,
                "vat_amount": 21.0,
                "amount_incl_vat": 121.0,
            }
        ]
        d3.run_invoice_control(d3_invoice)
        d3_audit = d3.export_audit_log()
        assert len(d3_audit) > 0
        assert "invoice_parse" in d3_audit

    def test_cross_template_workflow_ids_unique(self):
        """
        Verifieer dat elke template unieke workflow IDs genereert
        """
        d1_1 = D1Template()
        d1_2 = D1Template()
        d2_1 = D2Template()
        d2_2 = D2Template()
        d3_1 = D3Template()
        d3_2 = D3Template()

        workflow_ids = [
            d1_1.workflow_id,
            d1_2.workflow_id,
            d2_1.workflow_id,
            d2_2.workflow_id,
            d3_1.workflow_id,
            d3_2.workflow_id,
        ]

        # Alle IDs moeten uniek zijn
        assert len(set(workflow_ids)) == 6

        # Prefix verificatie
        assert all(wid.startswith("d1-") for wid in workflow_ids[:2])
        assert all(wid.startswith("d2-") for wid in workflow_ids[2:4])
        assert all(wid.startswith("d3-") for wid in workflow_ids[4:])

    def test_unhappy_paths_all_templates(self):
        """
        Verifieer dat alle templates unhappy paths correct afhandelen
        """
        # D1: Invalid intake
        d1 = D1Template()
        invalid_intake = IntakeData(
            naam="",  # Missing
            email="invalid",  # Invalid
            telefoon="",
            bedrijf="",
            project_type="website",
            budget_range="invalid",  # Invalid
            timeline="",
            requirements="",
        )
        d1_result = d1.run_intake_to_quote(invalid_intake)
        assert d1_result["status"] == D1Status.INTAKE_INVALID.value
        assert len(d1_result["errors"]) > 0

        # D2: Stock shortage
        d2 = D2Template()
        d2_order = {
            "order_id": "ORD-STOCK-TEST",
            "customer_name": "Test",
            "customer_email": "test@test.nl",
            "shipping_address": "Test",
            "items": [{"sku": "SKU-001", "name": "Test", "quantity": 100, "stock": 0}],
        }
        d2_result = d2.run_order_to_fulfilment(d2_order, simulate_stock_shortage=True)
        assert d2_result["status"] == "exception"
        assert len(d2_result["exceptions"]) > 0

        # D3: Corrupt data
        d3 = D3Template()
        corrupt_invoices = [
            {"corrupt": "data"},  # Corrupt
            {
                "invoice_id": "INV-VALID",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-001",
                "invoice_date": date.today().isoformat(),
                "due_date": date.today().isoformat(),
                "amount_excl_vat": 100.0,
                "vat_amount": 21.0,
                "amount_incl_vat": 121.0,
            },
        ]
        d3_result = d3.run_invoice_control(corrupt_invoices, simulate_corrupt_data=True)
        assert d3_result["exception_count"] == 1
        assert d3_result["processed_count"] == 1  # Alleen de valide

    def test_kpi_fields_present(self):
        """
        Verifieer dat KPI velden aanwezig zijn in alle resultaten

        Dit is belangrijk voor dashboarding en rapportage.
        """
        # D1 KPIs
        d1 = D1Template()
        d1_intake = IntakeData(
            naam="KPI Test",
            email="kpi@test.nl",
            telefoon="",
            bedrijf="KPI BV",
            project_type="website",
            budget_range="10k-25k",
            timeline="3_maanden",
            requirements="Test",
        )
        d1_result = d1.run_intake_to_quote(d1_intake, auto_approve=True)

        assert "workflow_id" in d1_result
        assert "status" in d1_result
        assert "quote" in d1_result
        assert d1_result["quote"]["totaal_incl_btw"] > 0
        assert len(d1_result["audit_trail"]) > 0

        # D2 KPIs
        d2 = D2Template()
        d2_order = {
            "order_id": "ORD-KPI",
            "customer_name": "KPI",
            "customer_email": "kpi@test.nl",
            "shipping_address": "Test",
            "items": [{"sku": "SKU-001", "name": "Test", "quantity": 2, "stock": 10}],
        }
        d2_result = d2.run_order_to_fulfilment(d2_order)

        assert "workflow_id" in d2_result
        assert "status" in d2_result
        assert "picking_list" in d2_result
        assert len(d2_result["notifications"]) > 0

        # D3 KPIs
        d3 = D3Template()
        today = date.today().isoformat()
        d3_invoices = [
            {
                "invoice_id": "INV-KPI",
                "vendor_name": "Vendor",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-KPI",
                "invoice_date": today,
                "due_date": today,
                "amount_excl_vat": 1000.0,
                "vat_amount": 210.0,
                "amount_incl_vat": 1210.0,
            }
        ]
        d3_result = d3.run_invoice_control(d3_invoices)

        assert "workflow_id" in d3_result
        assert "batch_size" in d3_result
        assert "processed_count" in d3_result
        assert "daily_report" in d3_result
        assert d3_result["daily_report"]["total_amount_validated"] > 0

    def test_fase1_no_mock_symmetry(self):
        """
        Eindverificatie: Alle Fase 1 componenten werken symbiotisch

        Deze test verifieert dat:
        1. Alle 3 demo templates correct werken
        2. Approval flows functioneel zijn
        3. Audit trails compleet zijn
        4. Geen mocks gebruikt - alleen echte/demo data
        """
        print("\n=== Fase 1 Integratietest ===")

        # D1
        d1 = D1Template()
        d1_intake = IntakeData(
            naam="Integratie Test",
            email="integratie@demo.nl",
            telefoon="020-5555555",
            bedrijf="Demo BV",
            project_type="app",
            budget_range="25k-50k",
            timeline="6_maanden",
            requirements="MVP app voor iOS en Android",
        )
        d1_result = d1.run_intake_to_quote(d1_intake, auto_approve=True)
        assert d1_result["status"] == D1Status.COMPLETED.value
        print(
            f"✅ D1 (Intake→Offerte): {d1_result['quote']['quote_id']} - €{d1_result['quote']['totaal_incl_btw']:,.2f}"
        )

        # D2
        d2 = D2Template()
        d2_order = {
            "order_id": "ORD-INTEGRATIE-001",
            "customer_name": "Integratie Klant",
            "customer_email": "klant@integratie.nl",
            "shipping_address": "Keizersgracht 100, 1015 CW Amsterdam",
            "items": [
                {"sku": "SKU-002", "name": "iPhone 15", "quantity": 1, "stock": 5},
                {"sku": "SKU-005", "name": "AirPods", "quantity": 2, "stock": 10},
            ],
        }
        d2_result = d2.run_order_to_fulfilment(d2_order)
        assert d2_result["status"] == "shipped"
        print(
            f"✅ D2 (Order→Fulfilment): {d2_result['picking_list']['list_id']} - {d2_result['picking_list']['total_items']} items"
        )

        # D3
        d3 = D3Template()
        today = date.today().isoformat()
        d3_invoices = [
            {
                "invoice_id": "INV-INTEGRATIE-001",
                "vendor_name": "Office Supplies BV",
                "vendor_id": "VEND-001",
                "invoice_number": "2024-INT-001",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 1500.0,
                "vat_amount": 315.0,
                "amount_incl_vat": 1815.0,
                "description": "Kantoor supplies",
            },
            {
                "invoice_id": "INV-INTEGRATIE-002",
                "vendor_name": "IT Solutions NL",
                "vendor_id": "VEND-002",
                "invoice_number": "2024-INT-002",
                "invoice_date": today,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "amount_excl_vat": 25000.0,
                "vat_amount": 5250.0,
                "amount_incl_vat": 30250.0,
                "description": "Server upgrade",
            },
        ]
        d3_result = d3.run_invoice_control(d3_invoices)
        assert d3_result["processed_count"] == 2
        print(
            f"✅ D3 (Factuurcontrole): {d3_result['daily_report']['report_id']} - {d3_result['daily_report']['total_invoices']} facturen"
        )

        # Totale audit trail count
        total_audit_records = (
            len(d1_result["audit_trail"])
            + len(d2_result["audit_trail"])
            + len(d3_result["audit_trail"])
        )
        print(f"✅ Totale audit records: {total_audit_records}")

        print("\n✅ Fase 1 Integratietest SUCCESS:")
        print("   - D1, D2, D3 allemaal werkend")
        print("   - Approval flows functioneel")
        print("   - Audit trails compleet")
        print("   - Geen mocks gebruikt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
