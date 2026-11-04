"""
D2 Demo Template: Order -> Fulfilment simulatie

Workflow:
1. Order feed ingest (CSV/JSON)
2. Picking lijst generatie
3. Status simulatie (picked -> packed -> shipped)
4. Team/klant update

Gebruikt demo-data, geen externe API's.
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderStatus(Enum):
    """Order status in fulfilment flow"""

    RECEIVED = "received"
    PICKING = "picking"
    PICKED = "picked"
    PACKING = "packing"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class D2ExceptionType(Enum):
    """Fulfilment exception types"""

    STOCK_MISMATCH = "stock_mismatch"
    NOTIFICATION_FAILED = "notification_failed"
    DAMAGED_ITEM = "damaged_item"
    ADDRESS_INVALID = "address_invalid"


@dataclass
class OrderItem:
    """Item in een order"""

    sku: str
    name: str
    quantity_ordered: int
    quantity_available: int
    location: str  # Warehouse locatie (bv. "A-12-3")

    @property
    def stock_sufficient(self) -> bool:
        """Check of er voldoende stock is"""
        return self.quantity_available >= self.quantity_ordered

    @property
    def shortage(self) -> int:
        """Hoeveel tekort (0 als voldoende)"""
        return max(0, self.quantity_ordered - self.quantity_available)


@dataclass
class Order:
    """Klant order"""

    order_id: str
    customer_name: str
    customer_email: str
    shipping_address: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.RECEIVED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Fulfilment tracking
    picked_at: datetime | None = None
    packed_at: datetime | None = None
    shipped_at: datetime | None = None
    tracking_code: str | None = None

    # Exception tracking
    exception_type: D2ExceptionType | None = None
    exception_message: str | None = None


@dataclass
class PickingList:
    """Picking lijst voor warehouse"""

    list_id: str
    order_id: str
    items: list[dict[str, Any]]  # SKU, locatie, aantal  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize naar dict"""
        return {
            "list_id": self.list_id,
            "order_id": self.order_id,
            "items": self.items,
            "created_at": self.created_at.isoformat(),
            "total_items": sum(item["quantity"] for item in self.items),
        }


@dataclass
class Notification:
    """Notificatie (simulated)"""

    notification_id: str
    channel: str  # "email", "sms", "webhook"
    recipient: str
    subject: str
    body: str
    status: str = "pending"  # pending, sent, failed
    retry_count: int = 0
    max_retries: int = 3
    sent_at: datetime | None = None
    error_message: str | None = None


@dataclass
class D2AuditRecord:
    """Audit record voor D2 workflow"""

    record_id: str
    workflow_id: str
    order_id: str
    step: str
    status: str
    timestamp: datetime
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None


class D2Template:
    """
    D2 Demo Template: Order -> Fulfilment simulatie

    Gebruik:
        template = D2Template()
        result = template.run_order_to_fulfilment(order_data)
    """

    # Demo warehouse locaties
    WAREHOUSE_LOCATIONS = {
        "SKU-001": "A-01-01",
        "SKU-002": "A-01-02",
        "SKU-003": "A-02-01",
        "SKU-004": "B-01-01",
        "SKU-005": "B-02-01",
    }

    def __init__(self) -> None:
        self.audit_records: list[D2AuditRecord] = []
        self.workflow_id = f"d2-{uuid.uuid4().hex[:8]}"
        self._notifications: list[Notification] = []
        self._notification_failures = 0

    def _log_audit(
        self,
        order_id: str,
        step: str,
        status: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        error: str | None = None,
    ) -> "D2AuditRecord":
        """Log audit record"""
        record = D2AuditRecord(
            record_id=str(uuid.uuid4()),
            workflow_id=self.workflow_id,
            order_id=order_id,
            step=step,
            status=status,
            timestamp=datetime.now(timezone.utc),
            details=details,
            error_message=error,
        )
        self.audit_records.append(record)
        return record

    def parse_order_csv(self, csv_content: str) -> list[Order]:
        """
        Stap 1a: Parse order feed uit CSV

        Args:
            csv_content: CSV string met orders

        Returns: List[Any] van Order objecten  # TODO(TYPE): replace Any with concrete type
        """
        orders: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            reader = csv.DictReader(io.StringIO(csv_content))

            for row in reader:
                # Parse items uit JSON string in CSV
                items_json = row.get("items", "[]")
                try:
                    items_data = json.loads(items_json)
                except json.JSONDecodeError:
                    items_data = []
                items: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for item_data in items_data:
                    sku = item_data.get("sku", "")
                    item = OrderItem(
                        sku=sku,
                        name=item_data.get("name", ""),
                        quantity_ordered=item_data.get("quantity", 0),
                        quantity_available=item_data.get("stock", 0),
                        location=self.WAREHOUSE_LOCATIONS.get(sku, "UNKNOWN"),
                    )
                    items.append(item)

                order = Order(
                    order_id=row.get("order_id", f"ORD-{uuid.uuid4().hex[:8]}"),
                    customer_name=row.get("customer_name", ""),
                    customer_email=row.get("customer_email", ""),
                    shipping_address=row.get("shipping_address", ""),
                    items=items,
                )
                orders.append(order)

                self._log_audit(
                    order_id=order.order_id,
                    step="order_parse",
                    status="success",
                    details={"items_count": len(items)},
                )

        except Exception as e:
            self._log_audit(
                order_id="batch", step="order_parse", status="failed", details={}, error=str(e)
            )

        return orders

    def generate_picking_list(self, order: Order) -> PickingList:
        """
        Stap 2: Genereer picking lijst

        Args:
            order: Order object

        Returns:
            PickingList object
        """
        list_id = f"PICK-{uuid.uuid4().hex[:6].upper()}"

        items: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in order.items:
            items.append(
                {
                    "sku": item.sku,
                    "name": item.name,
                    "location": item.location,
                    "quantity": item.quantity_ordered,
                    "stock_sufficient": item.stock_sufficient,
                }
            )

        picking_list = PickingList(
            list_id=list_id,
            order_id=order.order_id,
            items=items,
        )

        self._log_audit(
            order_id=order.order_id,
            step="picking_list_generation",
            status="success",
            details={
                "list_id": list_id,
                "items": len(items),
            },
        )

        return picking_list

    def check_stock(self, order: Order) -> tuple[bool, list[str]]:
        """
        Check stock availability

        Returns:
            (sufficient, list of shortages)
        """
        shortages: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in order.items:
            if not item.stock_sufficient:
                shortages.append(
                    f"SKU {item.sku}: nodig {item.quantity_ordered}, "
                    f"beschikbaar {item.quantity_available} (tekort: {item.shortage})"
                )

        return len(shortages) == 0, shortages

    def simulate_picking(self, order: Order) -> bool:
        """
        Stap 3a: Simuleer picking proces

        Args:
            order: Order object

        Returns:
            True if success, False if exception
        """
        # Check stock
        stock_ok, shortages = self.check_stock(order)

        if not stock_ok:
            order.status = OrderStatus.EXCEPTION
            order.exception_type = D2ExceptionType.STOCK_MISMATCH
            order.exception_message = "; ".join(shortages)

            self._log_audit(
                order_id=order.order_id,
                step="picking",
                status="exception",
                details={"shortages": shortages},
                error="Stock mismatch",
            )
            return False

        # Simuleer picking tijd
        order.status = OrderStatus.PICKING
        order.picked_at = datetime.now(timezone.utc)
        order.status = OrderStatus.PICKED

        self._log_audit(
            order_id=order.order_id,
            step="picking",
            status="success",
            details={"items_picked": len(order.items)},
        )

        return True

    def simulate_packing(self, order: Order) -> bool:
        """
        Stap 3b: Simuleer packing proces

        Args:
            order: Order object

        Returns:
            True if success
        """
        order.status = OrderStatus.PACKING
        order.packed_at = datetime.now(timezone.utc)
        order.status = OrderStatus.PACKED

        # Genereer tracking code
        order.tracking_code = f"TRACK-{uuid.uuid4().hex[:10].upper()}"

        self._log_audit(
            order_id=order.order_id,
            step="packing",
            status="success",
            details={"tracking_code": order.tracking_code},
        )

        return True

    def simulate_shipping(self, order: Order) -> bool:
        """
        Stap 3c: Simuleer shipping

        Args:
            order: Order object

        Returns:
            True if success
        """
        order.status = OrderStatus.SHIPPED
        order.shipped_at = datetime.now(timezone.utc)

        self._log_audit(
            order_id=order.order_id,
            step="shipping",
            status="success",
            details={
                "tracking_code": order.tracking_code,
                "carrier": "DemoExpress",
            },
        )

        return True

    def send_notification(
        self, order: Order, channel: str = "email", simulate_failure: bool = False
    ) -> Notification:
        """
        Stap 4: Verstuur notificatie (simulated)

        Args:
            order: Order object
            channel: "email", "sms", of "webhook"
            simulate_failure: Als True, simuleer een failure (voor unhappy test)

        Returns:
            Notification object
        """
        notification_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"

        if order.status == OrderStatus.EXCEPTION:
            subject = f"Order {order.order_id} - Probleem gemeld"
            body = f"""
Er is een probleem opgetreden met uw order:

{order.exception_message}

Ons team neemt contact met u op.
            """.strip()
        else:
            subject = f"Order {order.order_id} - Verzonden"
            body = f"""
Uw order is verzonden!

Tracking code: {order.tracking_code}
            """.strip()

        notification = Notification(
            notification_id=notification_id,
            channel=channel,
            recipient=order.customer_email,
            subject=subject,
            body=body,
        )

        # Simuleer verzending (met mogelijke failure)
        if simulate_failure:
            notification.status = "failed"
            notification.error_message = "Connection timeout to SMTP server"
            self._notification_failures += 1

            self._log_audit(
                order_id=order.order_id,
                step="notification",
                status="failed",
                details={
                    "channel": channel,
                    "recipient": order.customer_email,
                },
                error="Connection timeout to SMTP server",
            )
        else:
            notification.status = "sent"
            notification.sent_at = datetime.now(timezone.utc)

            self._log_audit(
                order_id=order.order_id,
                step="notification",
                status="success",
                details={
                    "channel": channel,
                    "recipient": order.customer_email,
                },
            )

        self._notifications.append(notification)
        return notification

    def retry_notification(self, notification: Notification) -> bool:
        """
        Retry een failed notificatie

        Args:
            notification: Failed Notification object

        Returns:
            True als retry succesvol
        """
        if notification.retry_count >= notification.max_retries:
            return False

        notification.retry_count += 1

        # Simuleer retry (altijd succes na retry in demo)
        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        notification.error_message = None

        return True

    def run_order_to_fulfilment(
        self,
        order_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        simulate_stock_shortage: bool = False,
        simulate_notification_failure: bool = False,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Complete D2 workflow: Order -> Fulfilment

        Args:
            order_data: Order data dict
            simulate_stock_shortage: Als True, simuleer stock tekort
            simulate_notification_failure: Als True, simuleer notificatie failure

        Returns:
            Workflow resultaat met audit trail
        """
        result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "workflow_id": self.workflow_id,
            "order_id": None,
            "status": "pending",
            "picking_list": None,
            "notifications": [],
            "exceptions": [],
            "audit_trail": [],
        }

        # Stap 1: Order aanmaken
        items: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item_data in order_data.get("items", []):
            qty_available = item_data.get("stock", 100)
            if simulate_stock_shortage:
                qty_available = 0  # Simuleer geen stock

            sku = item_data.get("sku", "")
            items.append(
                OrderItem(
                    sku=sku,
                    name=item_data.get("name", ""),
                    quantity_ordered=item_data.get("quantity", 0),
                    quantity_available=qty_available,
                    location=self.WAREHOUSE_LOCATIONS.get(sku, "UNKNOWN"),
                )
            )

        order = Order(
            order_id=order_data.get("order_id", f"ORD-{uuid.uuid4().hex[:8]}"),
            customer_name=order_data.get("customer_name", ""),
            customer_email=order_data.get("customer_email", ""),
            shipping_address=order_data.get("shipping_address", ""),
            items=items,
        )

        result["order_id"] = order.order_id

        # Stap 2: Picking lijst genereren
        picking_list = self.generate_picking_list(order)
        result["picking_list"] = picking_list.to_dict()

        # Stap 3: Picking (kan exception geven bij stock mismatch)
        picking_ok = self.simulate_picking(order)

        if not picking_ok:
            # Exception branch - stuur waarschuwing
            result["status"] = "exception"
            result["exceptions"].append(
                {
                    "type": "stock_mismatch",
                    "message": order.exception_message,
                }
            )

            # Notificatie over probleem
            notification = self.send_notification(
                order, simulate_failure=simulate_notification_failure
            )

            # Retry als notificatie faalde
            if notification.status == "failed":
                retry_ok = self.retry_notification(notification)
                if retry_ok:
                    result["notifications"].append(
                        {
                            "notification_id": notification.notification_id,
                            "status": "sent_after_retry",
                            "retry_count": notification.retry_count,
                        }
                    )
                else:
                    result["notifications"].append(
                        {
                            "notification_id": notification.notification_id,
                            "status": "failed_permanently",
                            "retry_count": notification.retry_count,
                        }
                    )
            else:
                result["notifications"].append(
                    {
                        "notification_id": notification.notification_id,
                        "status": notification.status,
                    }
                )

            result["audit_trail"] = [self._record_to_dict(r) for r in self.audit_records]
            return result

        # Stap 4: Packing
        self.simulate_packing(order)

        # Stap 5: Shipping
        self.simulate_shipping(order)

        result["status"] = "shipped"

        # Stap 6: Notificatie
        notification = self.send_notification(order, simulate_failure=simulate_notification_failure)

        # Retry als notificatie faalde
        if notification.status == "failed":
            retry_ok = self.retry_notification(notification)
            if retry_ok:
                result["notifications"].append(
                    {
                        "notification_id": notification.notification_id,
                        "status": "sent_after_retry",
                        "retry_count": notification.retry_count,
                    }
                )
            else:
                result["notifications"].append(
                    {
                        "notification_id": notification.notification_id,
                        "status": "failed_permanently",
                        "retry_count": notification.retry_count,
                    }
                )
        else:
            result["notifications"].append(
                {
                    "notification_id": notification.notification_id,
                    "status": notification.status,
                }
            )

        result["audit_trail"] = [self._record_to_dict(r) for r in self.audit_records]

        return result

    def _record_to_dict(self, record: D2AuditRecord) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert audit record to dict"""
        return {
            "record_id": record.record_id,
            "order_id": record.order_id,
            "step": record.step,
            "status": record.status,
            "timestamp": record.timestamp.isoformat(),
            "details": record.details,
            "error": record.error_message,
        }

    def export_audit_log(self) -> str:
        """Export audit log als JSON string"""
        return json.dumps([self._record_to_dict(r) for r in self.audit_records], indent=2)


class D2WorkflowRunner:
    """
    Runner voor D2 workflow integratie met bestaande workflow engine.
    """

    def __init__(self, tenant_id: str = "demo") -> None:
        self.tenant_id = tenant_id

    def create_workflow_def(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Creeer C7 workflow definition voor D2"""
        return {
            "workflow_id": "d2-order-fulfilment",
            "name": "D2: Order naar Fulfilment",
            "description": "Demo workflow: order ingest -> picking -> packing -> shipping -> notificatie",
            "version": 1,
            "nodes": [
                {
                    "id": "order-ingest",
                    "type": "task",
                    "name": "Order Ingest",
                    "capability": "d2.parse_order",
                },
                {
                    "id": "picking-list",
                    "type": "task",
                    "name": "Picking Lijst",
                    "capability": "d2.generate_picking_list",
                },
                {
                    "id": "stock-check",
                    "type": "decision",
                    "name": "Stock Check",
                    "capability": "d2.check_stock",
                },
                {
                    "id": "picking",
                    "type": "task",
                    "name": "Picking",
                    "capability": "d2.simulate_picking",
                },
                {
                    "id": "packing",
                    "type": "task",
                    "name": "Packing",
                    "capability": "d2.simulate_packing",
                },
                {
                    "id": "shipping",
                    "type": "task",
                    "name": "Shipping",
                    "capability": "d2.simulate_shipping",
                },
                {
                    "id": "notification",
                    "type": "task",
                    "name": "Notificatie",
                    "capability": "d2.send_notification",
                },
            ],
            "edges": [
                {"from": "order-ingest", "to": "picking-list"},
                {"from": "picking-list", "to": "stock-check"},
                {"from": "stock-check", "to": "picking", "condition": "stock_sufficient"},
                {"from": "stock-check", "to": "notification", "condition": "stock_shortage"},
                {"from": "picking", "to": "packing"},
                {"from": "packing", "to": "shipping"},
                {"from": "shipping", "to": "notification"},
            ],
        }
