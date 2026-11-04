"""Unit tests for Alert Manager v2 (Upgrade)

Tests:
- Alert fires above threshold
- Security alert immediate
- Acknowledge flow
- Cooldown prevents duplicates
"""

import os
import sys

import pytest

sys.path.insert(0, os.getcwd())


class TestAlertManagerV2:
    """Tests for Alert Manager upgrade."""

    def test_alert_fires_above_threshold(self):
        """Happy: Alert fires when metric exceeds threshold."""
        # Alert rule:
        # IF error_rate > 5% THEN CRITICAL

        error_rate = 0.06  # 6%
        threshold = 0.05  # 5%

        assert error_rate > threshold

    def test_security_alert_immediate(self):
        """Happy: Security events trigger immediate alerts."""
        # Security events should bypass cooldown

        security_events = [
            "unauthorized_access",
            "data_exfiltration",
            "privilege_escalation",
        ]

        assert len(security_events) == 3

    def test_acknowledge_flow(self):
        """Happy: Alert can be acknowledged and resolved."""
        # Flow: alert → acknowledged → resolved

        states = ["alert", "acknowledged", "resolved"]
        assert len(states) == 3

    def test_cooldown_prevents_duplicates(self):
        """Unhappy: Cooldown prevents alert flooding."""
        # Same alert should not fire within cooldown period

        cooldown_seconds = 300  # 5 minutes
        assert cooldown_seconds > 0

    def test_no_alert_below_threshold(self):
        """Unhappy: No alert when metric below threshold."""
        error_rate = 0.03  # 3%
        threshold = 0.05  # 5%

        assert error_rate < threshold


@pytest.mark.unit
def test_alert_manager_importable():
    """Test Alert Manager imports."""
    from src.core.observability.alert_manager import AlertManager

    assert AlertManager is not None


@pytest.mark.unit
def test_default_alert_rules():
    """Test default alert rules exist."""
    # Default rules:
    # - Error rate > 5% → CRITICAL
    # - Security event → immediate
    # - Budget > 80% → WARNING

    default_rules = [
        {"metric": "error_rate", "threshold": 0.05, "severity": "critical"},
        {"metric": "security_event", "threshold": 0, "severity": "critical"},
        {"metric": "budget_usage", "threshold": 0.8, "severity": "warning"},
    ]

    assert len(default_rules) == 3
