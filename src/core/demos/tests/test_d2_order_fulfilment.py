"""
Tests voor D2 Template: Order -> Fulfilment simulatie

Happy paths:
- Order ingest success
- Picking list generation
- Fulfilment simulation completed
- Stakeholder updates
- Full workflow execution

Unhappy paths:
- Empty order items
- Stock mismatch scenario
- System error scenario
- Invalid source format
"""

from typing import Any, List

import pytest

from src.core.contracts import CapabilityRegistry
from src.core.demos.capabilities import D2_CAPABILITIES
from src.core.demos.templates.d2_order_fulfilment import (
    D2Configuration,
    D2Template,
    Order,
    OrderItem,
)


@pytest.fixture
def d2_registry() -> CapabilityRegistry:
    """Registry met D2 capabilities."""
    reg = CapabilityRegistry()
    for cap in D2_CAPABILITIES.values():
        reg.register(cap)
    return reg


@pytest.fixture
def d2_config() -> D2Configuration:
    """Default D2 configuratie."""
    return D2Configuration(
        simulation_speed="fast",
        failure_scenario="none",
    )


@pytest.fixture
def d2_template(d2_registry: CapabilityRegistry, d2_config: D2Configuration) -> D2Template:
    """D2 template instance."""
    return D2Template(
        config=d2_config,
        capability_registry=d2_registry,
        tenant_id="tenant-test-001",
    )


@pytest.fixture
def sample_orders() -> list[Order]:
    """Sample orders."""
    return [
        Order(
            order_id="ORD-001",
            customer_name="Alice",
            customer_email="alice@example.com",
            items=[
                OrderItem("SKU-001", "Widget A", 2, "A-01"),
                OrderItem("SKU-002", "Widget B", 1, "A-02"),
            ],
            priority="normal",
        ),
        Order(
            order_id="ORD-002",
            customer_name="Bob",
            customer_email="bob@example.com",
            items=[
                OrderItem("SKU-003", "Gadget X", 5, "B-01"),
            ],
            priority="high",
        ),
    ]


class TestD2IngestOrders:
    """Test order ingest."""

    def test_ingest_orders_success(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Order ingest slaagt."""
        result: dict[str, Any] = d2_template.ingest_orders(sample_orders, source="manual")  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "success"
        assert "batch_id" in result
        assert result["orders_processed"] == 2
        assert result["orders_failed"] == 0

    def test_ingest_orders_empty_list(self, d2_template: D2Template) -> None:
        """Happy path: Lege order lijst."""
        result: dict[str, Any] = d2_template.ingest_orders([], source="manual")  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "partial_failure"
        assert result["orders_processed"] == 0

    def test_ingest_orders_invalid_items(self, d2_template: D2Template) -> None:
        """Unhappy path: Orders zonder items."""
        invalid_orders: list[Order] = [
            Order(
                order_id="ORD-BAD",
                customer_name="Test",
                customer_email="test@test.com",
                items=[],  # Leeg!
            ),
        ]

        result: dict[str, Any] = d2_template.ingest_orders(invalid_orders, source="manual")  # TODO(TYPE): replace Any with concrete type

        assert result["orders_failed"] == 1
        assert result["errors"][0]["error"] == "Order has no items"

    def test_ingest_orders_csv_source(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: CSV source."""
        result: dict[str, Any] = d2_template.ingest_orders(sample_orders, source="csv")  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "success"

    def test_ingest_orders_json_source(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: JSON source."""
        result: dict[str, Any] = d2_template.ingest_orders(sample_orders, source="json")  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "success"


class TestD2GeneratePickingList:
    """Test picking list generation."""

    def test_generate_picking_list_success(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Picking list generatie."""
        # Eerst orders ingesteren
        ingest_result: dict[str, Any] = d2_template.ingest_orders(sample_orders)  # TODO(TYPE): replace Any with concrete type
        batch_id = ingest_result["batch_id"]

        result: dict[str, Any] = d2_template.generate_picking_list(batch_id, sample_orders)  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "success"
        assert "picking_list_id" in result
        assert result["total_items"] == 8  # 2+1+5
        assert len(result["items"]) == 3
        assert "estimated_time_minutes" in result

    def test_generate_picking_list_priority(self, d2_template: D2Template) -> None:
        """Happy path: Priority bepaling."""
        high_volume_orders: list[Order] = [
            Order(
                order_id="ORD-BIG",
                customer_name="Big Customer",
                customer_email="big@example.com",
                items=[OrderItem(f"SKU-{i}", f"Item {i}", 10, "A-01") for i in range(20)],
            ),
        ]

        ingest_result: dict[str, Any] = d2_template.ingest_orders(high_volume_orders)  # TODO(TYPE): replace Any with concrete type
        batch_id = ingest_result["batch_id"]

        result: dict[str, Any] = d2_template.generate_picking_list(batch_id, high_volume_orders)  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "success"
        assert result["total_items"] == 200


class TestD2SimulateFulfilment:
    """Test fulfilment simulatie."""

    def test_simulate_fulfilment_success(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Simulatie completed."""
        # Setup
        ingest_result: dict[str, Any] = d2_template.ingest_orders(sample_orders)  # TODO(TYPE): replace Any with concrete type
        picking_result: dict[str, Any] = d2_template.generate_picking_list(  # TODO(TYPE): replace Any with concrete type
            ingest_result["batch_id"], sample_orders
        )

        result: dict[str, Any] = d2_template.simulate_fulfilment(  # TODO(TYPE): replace Any with concrete type
            picking_result["picking_list_id"],
            picking_result["items"],
        )

        assert result["status"] == "completed"
        assert "simulation_id" in result
        assert len(result["events"]) > 0
        assert "duration_seconds" in result

    def test_simulate_fulfilment_stock_mismatch(
        self, d2_registry: CapabilityRegistry, sample_orders: list[Order]
    ) -> None:
        """Unhappy path: Stock mismatch scenario."""
        config = D2Configuration(
            simulation_speed="fast",
            failure_scenario="stock_mismatch",
        )
        template = D2Template(
            config=config,
            capability_registry=d2_registry,
            tenant_id="tenant-test-001",
        )

        # Items met "X" suffix trigger stock mismatch
        orders_with_x: list[Order] = [
            Order(
                order_id="ORD-X",
                customer_name="Test",
                customer_email="test@test.com",
                items=[
                    OrderItem("SKU-X", "Problematic Item", 1, "A-01"),
                ],
            ),
        ]

        ingest_result: dict[str, Any] = template.ingest_orders(orders_with_x)  # TODO(TYPE): replace Any with concrete type
        picking_result: dict[str, Any] = template.generate_picking_list(  # TODO(TYPE): replace Any with concrete type
            ingest_result["batch_id"], orders_with_x
        )

        result: dict[str, Any] = template.simulate_fulfilment(  # TODO(TYPE): replace Any with concrete type
            picking_result["picking_list_id"],
            picking_result["items"],
        )

        assert result["status"] == "failed"
        assert any("stock_mismatch" in str(e) for e in result["events"])

    def test_simulate_fulfilment_system_error(
        self, d2_registry: CapabilityRegistry, sample_orders: list[Order]
    ) -> None:
        """Unhappy path: System error scenario."""
        config = D2Configuration(
            simulation_speed="fast",
            failure_scenario="system_error",
        )
        template = D2Template(
            config=config,
            capability_registry=d2_registry,
            tenant_id="tenant-test-001",
        )

        ingest_result: dict[str, Any] = template.ingest_orders(sample_orders)  # TODO(TYPE): replace Any with concrete type
        picking_result: dict[str, Any] = template.generate_picking_list(  # TODO(TYPE): replace Any with concrete type
            ingest_result["batch_id"], sample_orders
        )

        result: dict[str, Any] = template.simulate_fulfilment(  # TODO(TYPE): replace Any with concrete type
            picking_result["picking_list_id"],
            picking_result["items"],
        )

        assert result["status"] == "failed"
        assert any("system_error" in str(e) for e in result["events"])


class TestD2UpdateStakeholders:
    """Test stakeholder updates."""

    def test_update_team_only(self, d2_template: D2Template, sample_orders: list[Order]) -> None:
        """Happy path: Alleen team notificatie."""
        result: dict[str, Any] = d2_template.update_stakeholders(  # TODO(TYPE): replace Any with concrete type
            batch_id="batch-123",
            orders=sample_orders,
            simulation_status="completed",
            update_type="team",
        )

        assert result["status"] == "success"
        assert result["updates_sent"] >= 1

    def test_update_customer_only(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Alleen klant notificatie."""
        result: dict[str, Any] = d2_template.update_stakeholders(  # TODO(TYPE): replace Any with concrete type
            batch_id="batch-123",
            orders=sample_orders,
            simulation_status="completed",
            update_type="customer",
        )

        assert result["status"] == "success"
        assert result["updates_sent"] == 2  # 2 orders = 2 klanten

    def test_update_both(self, d2_template: D2Template, sample_orders: list[Order]) -> None:
        """Happy path: Team + klant notificatie."""
        result: dict[str, Any] = d2_template.update_stakeholders(  # TODO(TYPE): replace Any with concrete type
            batch_id="batch-123",
            orders=sample_orders,
            simulation_status="completed",
            update_type="both",
        )

        assert result["status"] == "success"
        assert result["updates_sent"] == 3  # 1 team + 2 klanten

    def test_update_failed_simulation(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Failed simulation geeft waarschuwing."""
        result: dict[str, Any] = d2_template.update_stakeholders(  # TODO(TYPE): replace Any with concrete type
            batch_id="batch-123",
            orders=sample_orders,
            simulation_status="failed",
            update_type="both",
        )

        assert result["status"] == "success"
        assert result["failed_deliveries"] == 1


class TestD2FullWorkflow:
    """Test complete workflow."""

    def test_full_workflow_success(
        self, d2_template: D2Template, sample_orders: list[Order]
    ) -> None:
        """Happy path: Complete workflow slaagt."""
        result: dict[str, Any] = d2_template.execute_full_workflow(sample_orders)  # TODO(TYPE): replace Any with concrete type

        assert result["workflow"] == "d2_order_fulfilment"
        assert result["status"] == "success"
        assert len(result["steps"]) == 4

        step_names = [s["step"] for s in result["steps"]]
        assert "ingest" in step_names
        assert "picking_list" in step_names
        assert "simulation" in step_names
        assert "update" in step_names

    def test_full_workflow_all_fail(self, d2_template: D2Template) -> None:
        """Unhappy path: Alle orders invalid."""
        invalid_orders: list[Order] = [
            Order(
                order_id="ORD-BAD",
                customer_name="Test",
                customer_email="test@test.com",
                items=[],  # Geen items
            ),
        ]

        result: dict[str, Any] = d2_template.execute_full_workflow(invalid_orders)  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "failed"
        assert "error" in result

    def test_full_workflow_stock_mismatch(self, d2_registry: CapabilityRegistry) -> None:
        """Unhappy path: Workflow met stock mismatch."""
        config = D2Configuration(failure_scenario="stock_mismatch")
        template = D2Template(
            config=config,
            capability_registry=d2_registry,
            tenant_id="tenant-test-001",
        )

        orders: list[Order] = [
            Order(
                order_id="ORD-X",
                customer_name="Test",
                customer_email="test@test.com",
                items=[OrderItem("SKU-X", "Item", 1, "A-01")],
            ),
        ]

        result: dict[str, Any] = template.execute_full_workflow(orders)  # TODO(TYPE): replace Any with concrete type

        assert result["status"] == "completed_with_issues"


class TestD2OrderCalculations:
    """Test order berekeningen."""

    def test_order_total_items(self) -> None:
        """Happy path: Total items berekening."""
        order = Order(
            order_id="TEST",
            customer_name="Test",
            customer_email="test@test.com",
            items=[
                OrderItem("SKU-1", "Item 1", 5, "A-01"),
                OrderItem("SKU-2", "Item 2", 3, "A-02"),
            ],
        )

        assert order.total_items == 8

    def test_order_empty_items(self) -> None:
        """Happy path: Lege order items."""
        order = Order(
            order_id="TEST",
            customer_name="Test",
            customer_email="test@test.com",
            items=[],
        )

        assert order.total_items == 0
