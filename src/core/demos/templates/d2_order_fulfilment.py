"""
D2 Template: Order -> Fulfilment simulatie

Operations demo workflow voor order ingest, pickinglijst generatie,
fulfilment simulatie en stakeholder updates.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.contracts import (
    CapabilityRegistry,
    PlanTier,
    PolicyEnforcer,
    SpanStatus,
    TenantPolicy,
    TraceBuilder,
)


@dataclass
class D2Configuration:
    """Configuratie voor D2 template."""

    # Simulatie instellingen
    simulation_speed: str = "fast"  # "realtime" of "fast"
    failure_scenario: str = "none"  # "none", "stock_mismatch", "system_error"

    # Warehouse config
    default_warehouse_zone: str = "A"
    priority_threshold: int = 10  # Orders > dit aantal items = high priority

    # Notificatie instellingen
    update_channels: list[str] = field(default_factory=lambda: ["email", "internal"])

    # Tenant config
    plan_tier: PlanTier = PlanTier.STARTER

    def to_policy(self, tenant_id: str) -> TenantPolicy:
        """Convert config naar TenantPolicy."""
        return TenantPolicy(
            tenant_id=tenant_id,
            plan_tier=self.plan_tier,
            enabled_capabilities={
                "d2_ingest_orders",
                "d2_generate_picking_list",
                "d2_simulate_fulfilment",
                "d2_update_stakeholders",
            },
        )


@dataclass
class OrderItem:
    """Order item."""

    sku: str
    description: str
    quantity: int
    location: str = "A-01"


@dataclass
class Order:
    """Order data."""

    order_id: str
    customer_name: str
    customer_email: str
    items: list[OrderItem]
    priority: str = "normal"

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "order_id": self.order_id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "items": [
                {
                    "sku": item.sku,
                    "description": item.description,
                    "quantity": item.quantity,
                    "location": item.location,
                }
                for item in self.items
            ],
            "priority": self.priority,
            "total_items": self.total_items,
        }


@dataclass
class PickingItem:
    """Picking list item."""

    sku: str
    description: str
    quantity: int
    location: str
    order_id: str


class D2Template:
    """
    D2 Template: Order -> Fulfilment simulatie

    Workflow:
    1. Ingest orders (CSV/JSON/manual) -> Batch ID
    2. Generate picking list -> Picking list ID
    3. Simulate fulfilment -> Simulation events
    4. Update stakeholders -> Notifications sent
    """

    def __init__(
        self,
        config: D2Configuration,
        capability_registry: CapabilityRegistry,
        tenant_id: str,
    ) -> None:
        self.config = config
        self.registry = capability_registry
        self.tenant_id = tenant_id
        self.policy = config.to_policy(tenant_id)
        self.enforcer = PolicyEnforcer(capability_registry)

    def ingest_orders(
        self,
        orders: list[Order],
        source: str = "manual",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 1: Ingest orders.

        Returns: Dict[str, Any] met batch_id, orders_processed, orders_failed  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d2_order_fulfilment",
        )

        input_data = {
            "source": source,
            "data": [order.to_dict() for order in orders],
        }

        span = builder.start_node_span(
            node_id="ingest_orders",
            capability_key="d2_ingest_orders",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d2_ingest_orders", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Order ingest blocked: {result.reason}")

        # Validate orders
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, order in enumerate(orders):
            if not order.items:
                errors.append(
                    {
                        "order_index": i,
                        "error": "Order has no items",
                    }
                )

        # Execute (simulated)
        batch_id = str(uuid.uuid4())[:8]
        processed = len(orders) - len(errors)

        output = {
            "batch_id": batch_id,
            "orders_processed": processed,
            "orders_failed": len(errors),
            "errors": errors,
        }

        span.add_event("batch_created", {"batch_id": batch_id, "count": processed})

        status = SpanStatus.SUCCESS if processed > 0 else SpanStatus.FAILED
        builder.end_span(span, status=status, output_data=output)
        trace = builder.complete(status=status)

        return {
            "batch_id": batch_id,
            "status": "success" if status == SpanStatus.SUCCESS else "partial_failure",
            "trace_id": trace.trace_id,
            **output,
        }

    def generate_picking_list(
        self,
        batch_id: str,
        orders: list[Order],
        warehouse_zone: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 2: Genereer picking lijst.

        Returns: Dict[str, Any] met picking_list_id, items, estimated_time  # TODO(TYPE): replace Any with concrete type
        """
        zone = warehouse_zone or self.config.default_warehouse_zone

        # Determine priority
        total_items = sum(order.total_items for order in orders)
        priority = "high" if total_items > self.config.priority_threshold else "normal"

        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d2_order_fulfilment",
        )

        input_data = {
            "batch_id": batch_id,
            "warehouse_zone": zone,
            "priority": priority,
        }

        span = builder.start_node_span(
            node_id="generate_picking_list",
            capability_key="d2_generate_picking_list",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d2_generate_picking_list", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Picking list generation blocked: {result.reason}")

        # Generate picking items (flatten orders)
        picking_items: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for order in orders:
            for item in order.items:
                picking_items.append(
                    {
                        "sku": item.sku,
                        "description": item.description,
                        "quantity": item.quantity,
                        "location": item.location,
                        "order_id": order.order_id,
                    }
                )

        # Sort by location for efficiency
        picking_items.sort(key=lambda x: x["location"])

        # Calculate estimated time (simulated)
        estimated_time = len(picking_items) * 2 + total_items * 0.5

        # Execute (simulated)
        picking_list_id = str(uuid.uuid4())[:8]

        output = {
            "picking_list_id": picking_list_id,
            "items": picking_items,
            "total_items": total_items,
            "estimated_time_minutes": estimated_time,
        }

        span.add_event("picking_list_generated", {"items": len(picking_items)})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "picking_list_id": picking_list_id,
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def simulate_fulfilment(
        self,
        picking_list_id: str,
        picking_items: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 3: Simuleer fulfilment.

        Returns: Dict[str, Any] met simulation_id, events, duration, status  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d2_order_fulfilment",
        )

        input_data = {
            "picking_list_id": picking_list_id,
            "simulation_speed": self.config.simulation_speed,
            "failure_scenario": self.config.failure_scenario,
        }

        span = builder.start_node_span(
            node_id="simulate_fulfilment",
            capability_key="d2_simulate_fulfilment",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d2_simulate_fulfilment", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Fulfilment simulation blocked: {result.reason}")

        # Simulate fulfilment events
        events: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        start_time = time.time()

        # Event 1: Started
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "picking_started",
                "picking_list_id": picking_list_id,
            }
        )
        span.add_event("picking_started")

        # Simulate picking items
        for item in picking_items:
            if self.config.failure_scenario == "stock_mismatch" and item["sku"].endswith("X"):
                events.append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "stock_mismatch",
                        "sku": item["sku"],
                        "message": "Stock count mismatch detected",
                    }
                )
                span.add_event("stock_mismatch", {"sku": item["sku"]})
                break

            events.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "item_picked",
                    "sku": item["sku"],
                    "quantity": item["quantity"],
                }
            )

        # Check for system error scenario
        status = "completed"
        if self.config.failure_scenario == "system_error":
            events.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "system_error",
                    "message": "Warehouse system temporarily unavailable",
                }
            )
            span.add_event("system_error")
            status = "failed"
        elif self.config.failure_scenario == "stock_mismatch":
            status = "failed"
        else:
            # Event 2: Completed
            events.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "picking_completed",
                    "items_picked": len(picking_items),
                }
            )
            span.add_event("picking_completed")

        duration = time.time() - start_time

        # Execute (simulated)
        simulation_id = str(uuid.uuid4())[:8]

        output = {
            "simulation_id": simulation_id,
            "status": status,
            "events": events,
            "duration_seconds": duration,
        }

        span_status = SpanStatus.SUCCESS if status == "completed" else SpanStatus.FAILED
        builder.end_span(span, status=span_status, output_data=output)
        trace = builder.complete(status=span_status)

        return {
            "simulation_id": simulation_id,
            "status": status,
            "trace_id": trace.trace_id,
            **output,
        }

    def update_stakeholders(
        self,
        batch_id: str,
        orders: list[Order],
        simulation_status: str,
        update_type: str = "both",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Stap 4: Update stakeholders.

        Returns: Dict[str, Any] met updates_sent, failed_deliveries  # TODO(TYPE): replace Any with concrete type
        """
        # Build trace
        builder = TraceBuilder(
            tenant_id=self.tenant_id,
            workflow_id="d2_order_fulfilment",
        )

        input_data = {
            "batch_id": batch_id,
            "update_type": update_type,
            "status": simulation_status,
        }

        span = builder.start_node_span(
            node_id="update_stakeholders",
            capability_key="d2_update_stakeholders",
            input_data=input_data,
        )

        # Check policy
        node = {"capability_key": "d2_update_stakeholders", "input": input_data}
        result = self.enforcer.check_execute_permission(node, self.policy)

        if not result.can_execute:
            builder.end_span(
                span,
                status=SpanStatus.FAILED,
                status_message=result.reason,
            )
            builder.complete(status=SpanStatus.FAILED)
            raise PermissionError(f"Stakeholder update blocked: {result.reason}")

        # Calculate updates
        updates_sent = 0
        failed_deliveries = 0

        if update_type in ["team", "both"]:
            updates_sent += 1  # Team notification

        if update_type in ["customer", "both"]:
            updates_sent += len(orders)  # One per customer

        # Simulate occasional failure
        if simulation_status == "failed":
            failed_deliveries = 1
            updates_sent -= 1

        output = {
            "updates_sent": max(0, updates_sent),
            "failed_deliveries": failed_deliveries,
        }

        span.add_event("updates_sent", {"count": updates_sent})

        builder.end_span(span, status=SpanStatus.SUCCESS, output_data=output)
        trace = builder.complete(status=SpanStatus.SUCCESS)

        return {
            "status": "success",
            "trace_id": trace.trace_id,
            **output,
        }

    def execute_full_workflow(
        self,
        orders: list[Order],
        source: str = "manual",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Voer de complete D2 workflow uit.

        Returns: Dict[str, Any] met resultaten van alle stappen  # TODO(TYPE): replace Any with concrete type
        """
        results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow": "d2_order_fulfilment",
            "steps": [],
        }

        try:
            # Step 1: Ingest
            ingest_result = self.ingest_orders(orders, source)
            results["steps"].append({"step": "ingest", "result": ingest_result})
            batch_id = ingest_result["batch_id"]

            if ingest_result["orders_failed"] == len(orders):
                raise ValueError("All orders failed validation")

            # Step 2: Generate Picking List
            picking_result = self.generate_picking_list(batch_id, orders)
            results["steps"].append({"step": "picking_list", "result": picking_result})
            picking_list_id = picking_result["picking_list_id"]
            picking_items = picking_result["items"]

            # Step 3: Simulate Fulfilment
            simulation_result = self.simulate_fulfilment(picking_list_id, picking_items)
            results["steps"].append({"step": "simulation", "result": simulation_result})
            simulation_status = simulation_result["status"]

            # Step 4: Update Stakeholders
            update_result = self.update_stakeholders(batch_id, orders, simulation_status)
            results["steps"].append({"step": "update", "result": update_result})

            results["status"] = (
                "success" if simulation_status == "completed" else "completed_with_issues"
            )

        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)

        return results
