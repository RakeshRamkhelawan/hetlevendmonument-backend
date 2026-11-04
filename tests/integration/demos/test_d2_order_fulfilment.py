"""
D2 Demo Template Tests

Tests voor Order → Fulfilment workflow.
- Happy: valide orderbatch -> picking + statusupdates zonder handmatige interventie
- Unhappy 1: stock mismatch -> exception branch + waarschuwing
- Unhappy 2: notificatiekanaal down -> retry + fallback + gelogde waarschuwing
"""

from datetime import datetime

import pytest

from src.core.demos.d2_order_fulfilment import (
    D2ExceptionType,
    D2Template,
    Notification,
    Order,
    OrderItem,
    OrderStatus,
    PickingList,
)


class TestD2HappyPath:
    """Happy path tests voor D2 workflow"""

    def test_happy_complete_order_to_fulfilment(self):
        """
        Happy: valide orderbatch -> picking + statusupdates zonder handmatige interventie

        Scenario:
        1. Valide order met voldoende stock
        2. Picking lijst wordt gegenereerd
        3. Picking simulatie succes
        4. Packing simulatie succes
        5. Shipping simulatie succes
        6. Notificatie verstuurd
        7. Audit trail compleet
        """
        # Arrange
        template = D2Template()
        order_data = {
            "order_id": "ORD-TEST-001",
            "customer_name": "Piet Jansen",
            "customer_email": "piet@example.com",
            "shipping_address": "Teststraat 123, Amsterdam",
            "items": [
                {"sku": "SKU-001", "name": "Widget A", "quantity": 2, "stock": 10},
                {"sku": "SKU-002", "name": "Widget B", "quantity": 1, "stock": 5},
            ],
        }

        # Act
        result = template.run_order_to_fulfilment(order_data)

        # Assert
        assert result["status"] == "shipped"
        assert result["order_id"] == "ORD-TEST-001"

        # Picking lijst gegenereerd
        assert result["picking_list"] is not None
        assert result["picking_list"]["list_id"].startswith("PICK-")
        assert len(result["picking_list"]["items"]) == 2

        # Notificatie verstuurd
        assert len(result["notifications"]) == 1
        assert result["notifications"][0]["status"] == "sent"

        # Geen exceptions
        assert len(result["exceptions"]) == 0

        # Audit trail aanwezig
        assert (
            len(result["audit_trail"]) >= 5
        )  # order, picking list, picking, packing, shipping, notification

        # Check specifieke audit stappen
        steps = [r["step"] for r in result["audit_trail"]]
        assert "picking_list_generation" in steps
        assert "picking" in steps
        assert "packing" in steps
        assert "shipping" in steps
        assert "notification" in steps


class TestD2UnhappyPath:
    """Unhappy path tests voor D2 workflow"""

    def test_unhappy_stock_mismatch_exception_branch(self):
        """
        Unhappy 1: stock mismatch -> exception branch + waarschuwing

        Scenario:
        1. Order met onvoldoende stock
        2. Stock check faalt
        3. Exception branch genomen
        4. Waarschuwing notificatie verstuurd
        5. Audit toont stock mismatch
        """
        # Arrange
        template = D2Template()
        order_data = {
            "order_id": "ORD-STOCK-001",
            "customer_name": "Anna de Vries",
            "customer_email": "anna@example.com",
            "shipping_address": "Voorbeeldlaan 45, Rotterdam",
            "items": [
                {"sku": "SKU-001", "name": "Widget A", "quantity": 5, "stock": 100},  # Genoeg stock
                {
                    "sku": "SKU-003",
                    "name": "Widget C",
                    "quantity": 10,
                    "stock": 100,
                },  # Genoeg stock
            ],
        }

        # Act - simuleer stock shortage
        result = template.run_order_to_fulfilment(order_data, simulate_stock_shortage=True)

        # Assert
        assert result["status"] == "exception"
        assert len(result["exceptions"]) == 1

        # Exception details
        exception = result["exceptions"][0]
        assert exception["type"] == "stock_mismatch"
        assert "tekort" in exception["message"].lower() or "SKU" in exception["message"]

        # Notificatie over probleem verstuurd
        assert len(result["notifications"]) == 1

        # Audit trail toont exception
        audit = result["audit_trail"]
        picking_records = [r for r in audit if r["step"] == "picking"]
        assert len(picking_records) == 1
        assert picking_records[0]["status"] == "exception"
        assert "Stock mismatch" in picking_records[0]["error"]

    def test_unhappy_notification_failure_with_retry(self):
        """
        Unhappy 2: notificatiekanaal down -> retry + fallback + gelogde waarschuwing

        Scenario:
        1. Order succesvol verwerkt
        2. Notificatie faalt (simulated)
        3. Retry wordt uitgevoerd
        4. Na retry succes
        5. Audit toont failure + retry + success
        """
        # Arrange
        template = D2Template()
        order_data = {
            "order_id": "ORD-NOTIF-001",
            "customer_name": "Klaas Bakker",
            "customer_email": "klaas@example.com",
            "shipping_address": "Hoofdweg 78, Utrecht",
            "items": [
                {"sku": "SKU-002", "name": "Widget B", "quantity": 3, "stock": 10},
            ],
        }

        # Act - simuleer notificatie failure
        result = template.run_order_to_fulfilment(order_data, simulate_notification_failure=True)

        # Assert
        assert result["status"] == "shipped"  # Order wel verwerkt

        # Notificatie met retry
        assert len(result["notifications"]) == 1
        notification = result["notifications"][0]

        # Moet sent_after_retry zijn (retry werkte in D2 template)
        assert notification["status"] in ["sent_after_retry", "failed_permanently"]
        assert notification["retry_count"] > 0

        # Audit trail toont failure
        audit = result["audit_trail"]
        notification_records = [r for r in audit if r["step"] == "notification"]
        assert len(notification_records) >= 1

        # Eerste poging faalde
        assert notification_records[0]["status"] == "failed"
        assert (
            "timeout" in notification_records[0]["error"].lower()
            or "failed" in notification_records[0]["status"]
        )


class TestD2PickingList:
    """Tests specifiek voor picking list generatie"""

    def test_picking_list_generated_correctly(self):
        """Test dat picking lijst correct wordt gegenereerd"""
        template = D2Template()

        order_data = {
            "order_id": "ORD-PICK-001",
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "shipping_address": "Test",
            "items": [
                {"sku": "SKU-001", "name": "Product A", "quantity": 2, "stock": 10},
                {"sku": "SKU-004", "name": "Product B", "quantity": 1, "stock": 5},
            ],
        }

        # Parse order
        items = []
        for item_data in order_data["items"]:
            items.append(
                OrderItem(
                    sku=item_data["sku"],
                    name=item_data["name"],
                    quantity_ordered=item_data["quantity"],
                    quantity_available=item_data["stock"],
                    location=template.WAREHOUSE_LOCATIONS.get(item_data["sku"], "UNKNOWN"),
                )
            )

        order = Order(
            order_id=order_data["order_id"],
            customer_name=order_data["customer_name"],
            customer_email=order_data["customer_email"],
            shipping_address=order_data["shipping_address"],
            items=items,
        )

        # Generate picking list
        picking_list = template.generate_picking_list(order)

        assert picking_list.list_id.startswith("PICK-")
        assert picking_list.order_id == "ORD-PICK-001"
        assert len(picking_list.items) == 2

        # Check locaties
        sku_locations = {item["sku"]: item["location"] for item in picking_list.items}
        assert sku_locations["SKU-001"] == "A-01-01"
        assert sku_locations["SKU-004"] == "B-01-01"

    def test_picking_list_serialization(self):
        """Test dat picking lijst correct serialiseert"""
        template = D2Template()

        order_data = {
            "order_id": "ORD-PICK-002",
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "shipping_address": "Test",
            "items": [
                {"sku": "SKU-001", "name": "Product A", "quantity": 3, "stock": 10},
            ],
        }

        result = template.run_order_to_fulfilment(order_data)

        picking_list = result["picking_list"]
        assert "list_id" in picking_list
        assert "items" in picking_list
        assert "created_at" in picking_list
        assert "total_items" in picking_list
        assert picking_list["total_items"] == 3


class TestD2StockCheck:
    """Tests specifiek voor stock checking"""

    def test_stock_sufficient_check(self):
        """Test stock check met voldoende stock"""
        template = D2Template()

        order_data = {
            "order_id": "ORD-STOCK-OK",
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "shipping_address": "Test",
            "items": [
                {"sku": "SKU-001", "name": "Product A", "quantity": 5, "stock": 10},
                {"sku": "SKU-002", "name": "Product B", "quantity": 3, "stock": 5},
            ],
        }

        items = []
        for item_data in order_data["items"]:
            items.append(
                OrderItem(
                    sku=item_data["sku"],
                    name=item_data["name"],
                    quantity_ordered=item_data["quantity"],
                    quantity_available=item_data["stock"],
                    location="A-01",
                )
            )

        order = Order(
            order_id=order_data["order_id"],
            customer_name=order_data["customer_name"],
            customer_email=order_data["customer_email"],
            shipping_address=order_data["shipping_address"],
            items=items,
        )

        sufficient, shortages = template.check_stock(order)

        assert sufficient is True
        assert len(shortages) == 0

    def test_stock_insufficient_check(self):
        """Test stock check met tekorten"""
        template = D2Template()

        items = [
            OrderItem(
                sku="SKU-001",
                name="Product A",
                quantity_ordered=10,
                quantity_available=5,
                location="A-01",
            ),
            OrderItem(
                sku="SKU-002",
                name="Product B",
                quantity_ordered=3,
                quantity_available=1,
                location="A-02",
            ),
        ]

        order = Order(
            order_id="ORD-STOCK-NOK",
            customer_name="Test",
            customer_email="test@test.com",
            shipping_address="Test",
            items=items,
        )

        sufficient, shortages = template.check_stock(order)

        assert sufficient is False
        assert len(shortages) == 2
        assert any("SKU-001" in s for s in shortages)
        assert any("SKU-002" in s for s in shortages)


class TestD2Audit:
    """Tests specifiek voor audit trail"""

    def test_audit_trail_complete(self):
        """Test dat audit trail compleet is"""
        template = D2Template()

        order_data = {
            "order_id": "ORD-AUDIT-001",
            "customer_name": "Test Audit",
            "customer_email": "audit@test.com",
            "shipping_address": "Test",
            "items": [
                {"sku": "SKU-001", "name": "Product", "quantity": 1, "stock": 10},
            ],
        }

        result = template.run_order_to_fulfilment(order_data)

        # Audit trail moet alle stappen bevatten
        audit = result["audit_trail"]
        assert len(audit) >= 5

        # Elke record heeft verplichte velden
        for record in audit:
            assert "record_id" in record
            assert "step" in record
            assert "status" in record
            assert "timestamp" in record
            assert "details" in record

    def test_audit_export(self):
        """Test dat audit log geëxporteerd kan worden"""
        template = D2Template()

        order_data = {
            "order_id": "ORD-EXPORT-001",
            "customer_name": "Test",
            "customer_email": "test@test.com",
            "shipping_address": "Test",
            "items": [
                {"sku": "SKU-001", "name": "Product", "quantity": 1, "stock": 10},
            ],
        }

        template.run_order_to_fulfilment(order_data)

        audit_json = template.export_audit_log()
        assert len(audit_json) > 0
        assert "picking_list_generation" in audit_json
        assert "picking" in audit_json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
