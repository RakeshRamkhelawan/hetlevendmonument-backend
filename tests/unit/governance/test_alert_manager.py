"""Tests for Alert Manager (Phase 2: Alert Fatigue solution).

Covers: AlertSeverity enum, GovernanceAlert model, _classify_severity,
_dedup_key (SHA-256), throttle windows, and AlertManager init.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from src.core.governance.alert_manager import AlertManager, AlertSeverity, GovernanceAlert


class TestAlertSeverityEnum:
    def test_all_four_levels_exist(self) -> None:
        values = {s.value for s in AlertSeverity}
        assert values == {"critical", "high", "medium", "low"}

    def test_is_str_enum(self) -> None:
        assert AlertSeverity.CRITICAL == "critical"


class TestGovernanceAlertModel:
    def test_tablename(self) -> None:
        assert GovernanceAlert.__tablename__ == "governance_alerts"

    def test_has_tenant_id_column(self) -> None:
        assert "tenant_id" in GovernanceAlert.__table__.c

    def test_tenant_id_is_not_nullable(self) -> None:
        assert GovernanceAlert.__table__.c["tenant_id"].nullable is False

    def test_has_dedup_key_column(self) -> None:
        assert "dedup_key" in GovernanceAlert.__table__.c

    def test_dedup_key_indexed(self) -> None:
        col = GovernanceAlert.__table__.c["dedup_key"]
        assert col.index is True

    def test_has_required_columns(self) -> None:
        cols = set(GovernanceAlert.__table__.c.keys())
        required = {
            "id",
            "tenant_id",
            "agent_name",
            "severity",
            "violation_type",
            "dedup_key",
            "occurrence_count",
            "acknowledged",
            "created_at",
            "last_seen_at",
        }
        assert required.issubset(cols)

    def test_occurrence_count_defaults_to_one(self) -> None:
        col = GovernanceAlert.__table__.c["occurrence_count"]
        assert col.default.arg == 1

    def test_acknowledged_defaults_to_zero(self) -> None:
        col = GovernanceAlert.__table__.c["acknowledged"]
        assert col.default.arg == 0


class TestAlertManagerThrottleWindows:
    def test_critical_throttle_is_five_minutes(self) -> None:
        assert AlertManager.THROTTLE[AlertSeverity.CRITICAL] == timedelta(minutes=5)

    def test_high_throttle_is_one_hour(self) -> None:
        assert AlertManager.THROTTLE[AlertSeverity.HIGH] == timedelta(hours=1)

    def test_medium_throttle_is_four_hours(self) -> None:
        assert AlertManager.THROTTLE[AlertSeverity.MEDIUM] == timedelta(hours=4)

    def test_low_throttle_is_one_day(self) -> None:
        assert AlertManager.THROTTLE[AlertSeverity.LOW] == timedelta(days=1)


class TestAlertManagerClassifySeverity:
    def test_pii_leakage_is_critical(self) -> None:
        assert AlertManager._classify_severity("pii_leakage") == AlertSeverity.CRITICAL

    def test_cross_tenant_access_is_critical(self) -> None:
        assert AlertManager._classify_severity("cross_tenant_access") == AlertSeverity.CRITICAL

    def test_safety_violation_is_critical(self) -> None:
        assert AlertManager._classify_severity("safety_violation") == AlertSeverity.CRITICAL

    def test_missing_approval_is_high(self) -> None:
        assert AlertManager._classify_severity("missing_approval") == AlertSeverity.HIGH

    def test_high_risk_unauthorized_is_high(self) -> None:
        assert AlertManager._classify_severity("high_risk_unauthorized") == AlertSeverity.HIGH

    def test_art5_blocked_is_high(self) -> None:
        assert AlertManager._classify_severity("art5_blocked") == AlertSeverity.HIGH

    def test_unknown_violation_defaults_to_medium(self) -> None:
        assert AlertManager._classify_severity("accuracy_drift") == AlertSeverity.MEDIUM
        assert AlertManager._classify_severity("some_other_thing") == AlertSeverity.MEDIUM


class TestAlertManagerDedupKey:
    def test_returns_64_char_hex_string(self) -> None:
        key = AlertManager._dedup_key(1, "bot", "pii_leakage")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_is_sha256_not_md5(self) -> None:
        """MD5 produces 32-char hex; SHA-256 produces 64-char hex."""
        key = AlertManager._dedup_key(1, "bot", "pii_leakage")
        assert len(key) == 64  # SHA-256 truncated to 64

    def test_different_tenants_produce_different_keys(self) -> None:
        key1 = AlertManager._dedup_key(1, "bot", "pii_leakage")
        key2 = AlertManager._dedup_key(2, "bot", "pii_leakage")
        assert key1 != key2

    def test_different_agents_produce_different_keys(self) -> None:
        key1 = AlertManager._dedup_key(1, "bot_a", "pii_leakage")
        key2 = AlertManager._dedup_key(1, "bot_b", "pii_leakage")
        assert key1 != key2

    def test_different_violations_produce_different_keys(self) -> None:
        key1 = AlertManager._dedup_key(1, "bot", "pii_leakage")
        key2 = AlertManager._dedup_key(1, "bot", "cross_tenant_access")
        assert key1 != key2

    def test_same_inputs_produce_same_key(self) -> None:
        key1 = AlertManager._dedup_key(1, "bot", "pii_leakage")
        key2 = AlertManager._dedup_key(1, "bot", "pii_leakage")
        # Same day → same key
        assert key1 == key2


class TestAlertManagerInit:
    def test_init_accepts_db_session(self) -> None:
        from unittest.mock import MagicMock

        manager = AlertManager(db=MagicMock())
        assert manager is not None
