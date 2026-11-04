"""
Tests for demo template type annotations.

Verifies:
- Happy path: proper type hints using lowercase list/dict (Python 3.9+)
- Unhappy path: no typing.List/Dict references remain
"""

import pytest
from decimal import Decimal
from typing import get_type_hints

from src.core.demos.templates.d1_intake_offerte import (
    D1Configuration,
    D1Template,
    LeadData,
    QuoteLineItem,
    QuoteData,
    ReviewDecision,
)
from src.core.demos.templates.d2_order_fulfilment import (
    D2Configuration,
    D2Template,
    OrderItem,
    Order,
    PickingItem,
)
from src.core.demos.templates.d3_factuur_controle import (
    D3Configuration,
    D3Template,
    Invoice,
    Deviation,
    ApprovalRequest,
)


class TestD1TemplateTypes:
    """Test D1 template type annotations."""

    def test_happy_path_generate_quote_signature(self) -> None:
        """Verify generate_quote uses lowercase list[QuoteLineItem] not List."""
        hints = get_type_hints(D1Template.generate_quote)
        # Check line_items parameter
        assert "line_items" in hints
        # Should be list, not List from typing
        annotation = hints["line_items"]
        assert str(annotation).startswith("list[")

    def test_happy_path_execute_workflow_signature(self) -> None:
        """Verify execute_full_workflow uses lowercase list[QuoteLineItem]."""
        hints = get_type_hints(D1Template.execute_full_workflow)
        assert "line_items" in hints
        annotation = hints["line_items"]
        assert str(annotation).startswith("list[")

    def test_unhappy_path_no_typing_list_in_d1_module(self) -> None:
        """Unhappy path: ensure no typing.List remains in d1_intake_offerte."""
        import src.core.demos.templates.d1_intake_offerte as d1_module
        import inspect

        source = inspect.getsource(d1_module)
        # Check imports: should not have List or Dict from typing
        lines = [line for line in source.split("\n") if line.startswith("from typing import")]
        for line in lines:
            assert "List" not in line, f"Found List in import: {line}"
            assert "Dict" not in line, f"Found Dict in import: {line}"

    def test_d1_configuration_notification_channels_type(self) -> None:
        """Verify notification_channels uses lowercase list[str]."""
        config = D1Configuration()
        assert isinstance(config.notification_channels, list)
        # Type hint check
        hints = get_type_hints(D1Configuration)
        assert "notification_channels" in hints


class TestD2TemplateTypes:
    """Test D2 template type annotations."""

    def test_happy_path_ingest_orders_signature(self) -> None:
        """Verify ingest_orders uses lowercase list[Order]."""
        hints = get_type_hints(D2Template.ingest_orders)
        assert "orders" in hints
        annotation = hints["orders"]
        assert str(annotation).startswith("list[")

    def test_happy_path_simulate_fulfilment_signature(self) -> None:
        """Verify simulate_fulfilment uses lowercase list[dict[str, Any]]."""
        hints = get_type_hints(D2Template.simulate_fulfilment)
        assert "picking_items" in hints
        annotation = hints["picking_items"]
        # Should be list[dict[...], not List[Dict[...]]
        assert str(annotation).startswith("list[")

    def test_unhappy_path_no_typing_list_in_d2_module(self) -> None:
        """Unhappy path: ensure no typing.List remains in d2_order_fulfilment."""
        import src.core.demos.templates.d2_order_fulfilment as d2_module
        import inspect

        source = inspect.getsource(d2_module)
        # Check imports: should not have List or Dict from typing
        lines = [line for line in source.split("\n") if line.startswith("from typing import")]
        for line in lines:
            assert "List" not in line, f"Found List in import: {line}"
            assert "Dict" not in line, f"Found Dict in import: {line}"

    def test_d2_configuration_update_channels_type(self) -> None:
        """Verify update_channels uses lowercase list[str]."""
        config = D2Configuration()
        assert isinstance(config.update_channels, list)


class TestD3TemplateTypes:
    """Test D3 template type annotations."""

    def test_happy_path_ingest_invoices_signature(self) -> None:
        """Verify ingest_invoices uses lowercase list[Invoice]."""
        hints = get_type_hints(D3Template.ingest_invoices)
        assert "invoices" in hints
        annotation = hints["invoices"]
        assert str(annotation).startswith("list[")

    def test_happy_path_calculate_risk_score_signature(self) -> None:
        """Verify calculate_risk_score uses lowercase list[dict[str, Any]]."""
        hints = get_type_hints(D3Template.calculate_risk_score)
        assert "deviations" in hints
        annotation = hints["deviations"]
        assert str(annotation).startswith("list[")

    def test_happy_path_generate_daily_report_signature(self) -> None:
        """Verify generate_daily_report uses lowercase types."""
        hints = get_type_hints(D3Template.generate_daily_report)
        assert "invoices" in hints
        assert "approvals" in hints
        # Both should use list
        assert str(hints["invoices"]).startswith("list[")
        assert str(hints["approvals"]).startswith("list[")

    def test_unhappy_path_no_typing_list_in_d3_module(self) -> None:
        """Unhappy path: ensure no typing.List remains in d3_factuur_controle."""
        import src.core.demos.templates.d3_factuur_controle as d3_module
        import inspect

        source = inspect.getsource(d3_module)
        # Check imports: should not have List or Dict from typing
        lines = [line for line in source.split("\n") if line.startswith("from typing import")]
        for line in lines:
            assert "List" not in line, f"Found List in import: {line}"
            assert "Dict" not in line, f"Found Dict in import: {line}"


class TestIntegration:
    """Integration tests verifying type safety across all templates."""

    def test_all_dataclass_to_dict_methods_return_dict(self) -> None:
        """Verify all to_dict methods return dict[str, Any]."""
        lead = LeadData(
            company_name="Test Inc",
            contact_name="John",
            email="john@test.com",
        )
        result = lead.to_dict()
        assert isinstance(result, dict)
        assert "company_name" in result

        order = Order(
            order_id="O1",
            customer_name="Acme",
            customer_email="acme@test.com",
            items=[OrderItem(sku="SKU1", description="Test", quantity=1)],
        )
        result = order.to_dict()
        assert isinstance(result, dict)
        assert "order_id" in result

        invoice = Invoice(
            invoice_number="INV001",
            vendor="Vendor Inc",
            amount=Decimal("1000.00"),
        )
        result = invoice.to_dict()
        assert isinstance(result, dict)
        assert "invoice_number" in result

    def test_d1_workflow_returns_dict(self) -> None:
        """Verify D1 workflow execution returns dict."""
        from src.core.contracts import CapabilityRegistry

        registry = CapabilityRegistry()
        config = D1Configuration()
        template = D1Template(config, registry, "test-tenant")

        lead = LeadData(
            company_name="Test Corp",
            contact_name="Alice",
            email="alice@test.com",
        )
        items = [QuoteLineItem(description="Service A", quantity=1, unit_price=Decimal("100"))]

        result = template.execute_full_workflow(lead, items)
        assert isinstance(result, dict)
        assert "workflow" in result
        assert "steps" in result

    def test_d2_workflow_returns_dict(self) -> None:
        """Verify D2 workflow execution returns dict."""
        from src.core.contracts import CapabilityRegistry

        registry = CapabilityRegistry()
        config = D2Configuration()
        template = D2Template(config, registry, "test-tenant")

        order = Order(
            order_id="O1",
            customer_name="Test Customer",
            customer_email="test@example.com",
            items=[OrderItem(sku="SKU001", description="Product A", quantity=2)],
        )

        result = template.execute_full_workflow([order])
        assert isinstance(result, dict)
        assert "workflow" in result

    def test_d3_workflow_returns_dict(self) -> None:
        """Verify D3 workflow execution returns dict."""
        from src.core.contracts import CapabilityRegistry

        registry = CapabilityRegistry()
        config = D3Configuration()
        template = D3Template(config, registry, "test-tenant")

        invoice = Invoice(
            invoice_number="INV001",
            vendor="Test Vendor",
            amount=Decimal("2000.00"),
        )

        result = template.execute_full_workflow([invoice])
        assert isinstance(result, dict)
        assert "workflow" in result
