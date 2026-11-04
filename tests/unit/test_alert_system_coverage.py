"""
Comprehensive tests for src/core/monitoring/alert_system.py
Coverage target: 100% of alert system module
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest

from src.core.monitoring.alert_system import Alert, AlertLevel, AlertSystem, get_alert_system


class TestAlertLevel:
    """Test AlertLevel enum"""

    def test_alert_level_values(self):
        """Test AlertLevel enum has correct values"""
        # Assert
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.CRITICAL.value == "critical"
        assert AlertLevel.EMERGENCY.value == "emergency"

    def test_alert_level_all_levels_defined(self):
        """Test all expected alert levels are defined"""
        # Arrange
        expected_levels = {"INFO", "WARNING", "CRITICAL", "EMERGENCY"}

        # Act
        actual_levels = {level.name for level in AlertLevel}

        # Assert
        assert actual_levels == expected_levels


class TestAlert:
    """Test Alert dataclass"""

    def test_alert_initialization(self):
        """Test Alert can be initialized with required fields"""
        # Arrange
        now = datetime.now(timezone.utc)
        metadata = {"user_id": "123", "component_version": "1.0"}

        # Act
        alert = Alert(
            level=AlertLevel.WARNING,
            message="Test alert message",
            component="test_component",
            timestamp=now,
            metadata=metadata,
        )

        # Assert
        assert alert.level == AlertLevel.WARNING
        assert alert.message == "Test alert message"
        assert alert.component == "test_component"
        assert alert.timestamp == now
        assert alert.metadata == metadata
        assert alert.resolved is False  # Default value

    def test_alert_resolved_default_false(self):
        """Test Alert.resolved defaults to False"""
        # Act
        alert = Alert(
            level=AlertLevel.INFO,
            message="Test",
            component="test",
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

        # Assert
        assert alert.resolved is False

    def test_alert_resolved_can_be_set(self):
        """Test Alert.resolved can be set to True"""
        # Act
        alert = Alert(
            level=AlertLevel.INFO,
            message="Test",
            component="test",
            timestamp=datetime.now(timezone.utc),
            metadata={},
            resolved=True,
        )

        # Assert
        assert alert.resolved is True

    def test_alert_metadata_can_be_empty(self):
        """Test Alert can have empty metadata"""
        # Act
        alert = Alert(
            level=AlertLevel.INFO,
            message="Test",
            component="test",
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

        # Assert
        assert alert.metadata == {}


class TestAlertSystemInitialization:
    """Test AlertSystem initialization"""

    def test_alert_system_initialization(self):
        """Test AlertSystem initializes with empty state"""
        # Act
        system = AlertSystem()

        # Assert
        assert system.active_alerts == []
        assert len(system.alert_handlers) == 4  # One for each AlertLevel
        assert all(system.alert_handlers[level] == [] for level in AlertLevel)

    def test_alert_system_handlers_initialized_for_all_levels(self):
        """Test alert handlers initialized for all alert levels"""
        # Act
        system = AlertSystem()

        # Assert
        for level in AlertLevel:
            assert level in system.alert_handlers
            assert isinstance(system.alert_handlers[level], list)


class TestTriggerAlert:
    """Test AlertSystem.trigger_alert method"""

    def test_trigger_alert_creates_alert(self):
        """Test trigger_alert creates and returns Alert object"""
        # Arrange
        system = AlertSystem()

        # Act
        alert = system.trigger_alert(
            level=AlertLevel.WARNING,
            message="Test alert",
            component="test_component",
            user_id="123",
            action="test_action",
        )

        # Assert
        assert isinstance(alert, Alert)
        assert alert.level == AlertLevel.WARNING
        assert alert.message == "Test alert"
        assert alert.component == "test_component"
        assert alert.metadata["user_id"] == "123"
        assert alert.metadata["action"] == "test_action"

    def test_trigger_alert_adds_to_active_alerts(self):
        """Test trigger_alert adds alert to active_alerts list"""
        # Arrange
        system = AlertSystem()

        # Act
        alert = system.trigger_alert(AlertLevel.INFO, "Test message", "component")

        # Assert
        assert len(system.active_alerts) == 1
        assert system.active_alerts[0] == alert

    def test_trigger_alert_sets_timestamp(self):
        """Test trigger_alert sets current timestamp"""
        # Arrange
        system = AlertSystem()
        before = datetime.now(timezone.utc)

        # Act
        alert = system.trigger_alert(AlertLevel.INFO, "Test", "component")
        after = datetime.now(timezone.utc)

        # Assert
        assert before <= alert.timestamp <= after

    def test_trigger_alert_calls_registered_handlers(self):
        """Test trigger_alert calls all registered handlers for that level"""
        # Arrange
        system = AlertSystem()
        handler1 = Mock()
        handler2 = Mock()
        system.add_handler(AlertLevel.CRITICAL, handler1)
        system.add_handler(AlertLevel.CRITICAL, handler2)

        # Act
        alert = system.trigger_alert(AlertLevel.CRITICAL, "Critical alert", "component")

        # Assert
        handler1.assert_called_once_with(alert)
        handler2.assert_called_once_with(alert)

    def test_trigger_alert_doesnt_call_wrong_level_handlers(self):
        """Test trigger_alert only calls handlers for matching level"""
        # Arrange
        system = AlertSystem()
        info_handler = Mock()
        critical_handler = Mock()
        system.add_handler(AlertLevel.INFO, info_handler)
        system.add_handler(AlertLevel.CRITICAL, critical_handler)

        # Act
        system.trigger_alert(AlertLevel.INFO, "Info message", "component")

        # Assert
        info_handler.assert_called_once()
        critical_handler.assert_not_called()

    def test_trigger_alert_handler_exception_caught(self, caplog):
        """Test trigger_alert catches and logs handler exceptions"""
        # Arrange
        import logging

        caplog.set_level(logging.ERROR)

        system = AlertSystem()
        failing_handler = Mock(side_effect=Exception("Handler failed"))
        system.add_handler(AlertLevel.WARNING, failing_handler)

        # Act
        alert = system.trigger_alert(AlertLevel.WARNING, "Test", "component")

        # Assert - Alert still created despite handler failure
        assert alert is not None
        assert any("handler failed" in record.message.lower() for record in caplog.records)

    def test_trigger_alert_logging(self, caplog):
        """Test trigger_alert logs the alert"""
        # Arrange
        import logging

        caplog.set_level(logging.INFO)

        system = AlertSystem()

        # Act
        system.trigger_alert(AlertLevel.EMERGENCY, "Emergency alert message", "critical_component")

        # Assert
        assert any("alert triggered" in record.message.lower() for record in caplog.records)
        assert any("emergency" in record.message.lower() for record in caplog.records)


class TestResolveAlert:
    """Test AlertSystem.resolve_alert method"""

    def test_resolve_alert_marks_resolved(self):
        """Test resolve_alert sets alert.resolved to True"""
        # Arrange
        system = AlertSystem()
        alert = system.trigger_alert(AlertLevel.INFO, "Test", "component")

        # Act
        system.resolve_alert(alert)

        # Assert
        assert alert.resolved is True

    def test_resolve_alert_logging(self, caplog):
        """Test resolve_alert logs the resolution"""
        # Arrange
        import logging

        caplog.set_level(logging.INFO)

        system = AlertSystem()
        alert = system.trigger_alert(AlertLevel.WARNING, "Test alert", "component")

        # Act
        system.resolve_alert(alert)

        # Assert
        assert any("alert resolved" in record.message.lower() for record in caplog.records)
        assert any("test alert" in record.message.lower() for record in caplog.records)


class TestGetActiveAlerts:
    """Test AlertSystem.get_active_alerts method"""

    def test_get_active_alerts_returns_unresolved_only(self):
        """Test get_active_alerts returns only unresolved alerts"""
        # Arrange
        system = AlertSystem()
        alert1 = system.trigger_alert(AlertLevel.INFO, "Alert 1", "comp1")
        alert2 = system.trigger_alert(AlertLevel.WARNING, "Alert 2", "comp2")
        alert3 = system.trigger_alert(AlertLevel.CRITICAL, "Alert 3", "comp3")

        system.resolve_alert(alert2)

        # Act
        active = system.get_active_alerts()

        # Assert
        assert len(active) == 2
        assert alert1 in active
        assert alert2 not in active
        assert alert3 in active

    def test_get_active_alerts_empty_when_all_resolved(self):
        """Test get_active_alerts returns empty list when all resolved"""
        # Arrange
        system = AlertSystem()
        alert1 = system.trigger_alert(AlertLevel.INFO, "Alert 1", "comp1")
        alert2 = system.trigger_alert(AlertLevel.WARNING, "Alert 2", "comp2")

        system.resolve_alert(alert1)
        system.resolve_alert(alert2)

        # Act
        active = system.get_active_alerts()

        # Assert
        assert active == []

    def test_get_active_alerts_empty_when_no_alerts(self):
        """Test get_active_alerts returns empty list when no alerts"""
        # Arrange
        system = AlertSystem()

        # Act
        active = system.get_active_alerts()

        # Assert
        assert active == []


class TestAddHandler:
    """Test AlertSystem.add_handler method"""

    def test_add_handler_registers_handler(self):
        """Test add_handler adds handler to correct level"""
        # Arrange
        system = AlertSystem()
        handler = Mock()

        # Act
        system.add_handler(AlertLevel.CRITICAL, handler)

        # Assert
        assert handler in system.alert_handlers[AlertLevel.CRITICAL]

    def test_add_handler_multiple_handlers_same_level(self):
        """Test multiple handlers can be added to same level"""
        # Arrange
        system = AlertSystem()
        handler1 = Mock()
        handler2 = Mock()
        handler3 = Mock()

        # Act
        system.add_handler(AlertLevel.WARNING, handler1)
        system.add_handler(AlertLevel.WARNING, handler2)
        system.add_handler(AlertLevel.WARNING, handler3)

        # Assert
        assert len(system.alert_handlers[AlertLevel.WARNING]) == 3
        assert all(
            h in system.alert_handlers[AlertLevel.WARNING] for h in [handler1, handler2, handler3]
        )

    def test_add_handler_different_levels_independent(self):
        """Test handlers for different levels are independent"""
        # Arrange
        system = AlertSystem()
        info_handler = Mock()
        critical_handler = Mock()

        # Act
        system.add_handler(AlertLevel.INFO, info_handler)
        system.add_handler(AlertLevel.CRITICAL, critical_handler)

        # Assert
        assert info_handler in system.alert_handlers[AlertLevel.INFO]
        assert info_handler not in system.alert_handlers[AlertLevel.CRITICAL]
        assert critical_handler in system.alert_handlers[AlertLevel.CRITICAL]
        assert critical_handler not in system.alert_handlers[AlertLevel.INFO]


class TestGetAlertSystem:
    """Test get_alert_system function"""

    def test_get_alert_system_returns_instance(self):
        """Test get_alert_system returns AlertSystem instance"""
        # Act
        system = get_alert_system()

        # Assert
        assert isinstance(system, AlertSystem)

    def test_get_alert_system_singleton(self):
        """Test get_alert_system returns same instance (singleton)"""
        # Act
        system1 = get_alert_system()
        system2 = get_alert_system()

        # Assert
        assert system1 is system2

    def test_get_alert_system_lazy_initialization(self):
        """Test get_alert_system creates instance on first call"""
        # Arrange
        import src.core.monitoring.alert_system as module

        module._alert_system = None

        # Act & Assert - Not initialized yet
        assert module._alert_system is None

        system = get_alert_system()

        # Assert - Now initialized
        assert module._alert_system is not None
        assert module._alert_system is system
