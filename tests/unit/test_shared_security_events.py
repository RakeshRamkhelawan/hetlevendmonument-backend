"""Unit tests for src/core/shared/security_events.py (SP-DSM-019)."""

import logging

import pytest

from src.core.shared.security_events import SecurityEvent, _SEVERITY_MAP, log_security_event


class TestSecurityEventConstants:
    def test_all_constants_present(self) -> None:
        expected = {
            "TENANT_CONTEXT_FAILED",
            "CROSS_TENANT_ATTEMPT",
            "TENANT_NOT_FOUND",
            "TENANT_SUSPENDED",
            "SUPERUSER_BYPASS",
            "QUOTA_EXCEEDED",
            "INVALID_JWT",
            "TOKEN_EXPIRED",
            "RESOURCE_NOT_FOUND_404",
            "LOGIN_SUCCESS",
            "LOGIN_FAILURE",
            "REGISTRATION_SUCCESS",
            "PASSWORD_RESET_REQUESTED",
            "PASSWORD_RESET_COMPLETED",
        }
        actual = {k for k in vars(SecurityEvent) if not k.startswith("_")}
        assert expected == actual

    def test_constant_values_are_strings(self) -> None:
        for attr in vars(SecurityEvent):
            if not attr.startswith("_"):
                assert isinstance(getattr(SecurityEvent, attr), str)


class TestSeverityMap:
    def test_cross_tenant_is_critical(self) -> None:
        assert _SEVERITY_MAP[SecurityEvent.CROSS_TENANT_ATTEMPT] == "critical"

    def test_quota_exceeded_is_high(self) -> None:
        assert _SEVERITY_MAP[SecurityEvent.QUOTA_EXCEEDED] == "high"

    def test_invalid_jwt_is_high(self) -> None:
        assert _SEVERITY_MAP[SecurityEvent.INVALID_JWT] == "high"

    def test_tenant_context_failed_is_high(self) -> None:
        assert _SEVERITY_MAP[SecurityEvent.TENANT_CONTEXT_FAILED] == "high"

    def test_superuser_bypass_is_low(self) -> None:
        assert _SEVERITY_MAP[SecurityEvent.SUPERUSER_BYPASS] == "low"

    def test_unknown_event_not_in_map(self) -> None:
        assert "unknown_event_xyz" not in _SEVERITY_MAP


class TestLogSecurityEvent:
    @pytest.mark.asyncio
    async def test_critical_event_logs_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR, logger="src.core.shared.security_events"):
            await log_security_event(event_type=SecurityEvent.CROSS_TENANT_ATTEMPT)
        assert any("SECURITY EVENT [CRITICAL]" in r.message for r in caplog.records)
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    @pytest.mark.asyncio
    async def test_high_event_logs_at_warning_level(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.core.shared.security_events"):
            await log_security_event(event_type=SecurityEvent.QUOTA_EXCEEDED)
        assert any("SECURITY EVENT [HIGH]" in r.message for r in caplog.records)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_low_event_logs_at_info_level(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="src.core.shared.security_events"):
            await log_security_event(event_type=SecurityEvent.SUPERUSER_BYPASS)
        assert any("SECURITY EVENT [LOW]" in r.message for r in caplog.records)
        assert any(r.levelno == logging.INFO for r in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_event_uses_threat_level_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="src.core.shared.security_events"):
            await log_security_event(event_type="unknown_event", threat_level="medium")
        assert any("SECURITY EVENT [MEDIUM]" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_governance_or_db_import(self) -> None:
        import src.core.shared.security_events as mod
        import inspect

        src = inspect.getsource(mod)
        assert "AuditService" not in src
        assert "from src.core.governance" not in src
        assert "AsyncSession" not in src

    @pytest.mark.asyncio
    async def test_log_message_contains_event_type(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.core.shared.security_events"):
            await log_security_event(
                event_type=SecurityEvent.QUOTA_EXCEEDED,
                user_id=42,
                tenant_id=7,
                request_path="/api/v1/agents",
            )
        assert any(SecurityEvent.QUOTA_EXCEEDED in r.message for r in caplog.records)
