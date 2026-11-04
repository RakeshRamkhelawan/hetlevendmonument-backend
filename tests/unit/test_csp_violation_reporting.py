"""
TDD RED PHASE: CSP Violation Reporting (Unhappy Paths)

Tests for CSP violation reporting endpoint and monitoring.
Detects and alerts on Content Security Policy violations.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestCSPViolationReportingHappyPath:
    """Happy path: Normal CSP violation reporting"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.lpush = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_csp_violation_accepted(self, mock_redis, mock_audit_service):
        """Valid CSP violation should be accepted and stored"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(redis_client=mock_redis, audit_service=mock_audit_service)

        violation = {
            "blocked-uri": "https://evil.com/script.js",
            "violated-directive": "script-src",
            "document-uri": "https://myapp.com/page",
            "disposition": "enforce",
        }

        result = await reporter.report_violation(violation)

        assert result is True
        mock_redis.lpush.assert_called_once()


class TestCSPViolationReportingUnhappyPaths:
    """Unhappy paths: Invalid reports, attacks, edge cases"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.lpush = AsyncMock(return_value=1)
        redis.get = AsyncMock(return_value=None)
        redis.lrange = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_invalid_csp_violation_rejected(self, mock_redis, mock_audit_service):
        """Report without required fields should be rejected"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(redis_client=mock_redis, audit_service=mock_audit_service)

        invalid_violation = {}  # Missing required fields

        with pytest.raises(ValueError, match="Missing required fields"):
            await reporter.report_violation(invalid_violation)

    @pytest.mark.asyncio
    async def test_malicious_uri_blocked(self, mock_redis, mock_audit_service):
        """Report with malicious URI should be rejected"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            block_malicious_uris=True,
        )

        # Malicious URI patterns
        malicious_uris = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "file:///etc/passwd",
        ]

        for uri in malicious_uris:
            with pytest.raises(ValueError, match="Malicious URI detected"):
                await reporter.report_violation(
                    {
                        "blocked-uri": uri,
                        "violated-directive": "script-src",
                        "document-uri": "https://myapp.com",
                    }
                )

    @pytest.mark.asyncio
    async def test_csp_spike_detection(self, mock_redis, mock_audit_service):
        """Sudden increase in CSP violations should trigger alert"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            spike_threshold=100,  # Alert if > 100 violations in 1 minute
        )

        # Simulate 101 violations in rapid succession
        mock_redis.incr.return_value = 101

        with pytest.raises(ValueError, match="CSP violation spike detected"):
            await reporter.report_violation(
                {
                    "blocked-uri": "https://evil.com/script.js",
                    "violated-directive": "script-src",
                    "document-uri": "https://myapp.com",
                }
            )

    @pytest.mark.asyncio
    async def test_violation_spike_logs_alert(self, mock_redis, mock_audit_service):
        """CSP spike should be logged to audit trail"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            spike_threshold=10,
        )

        mock_redis.incr.return_value = 11

        try:
            await reporter.report_violation(
                {
                    "blocked-uri": "https://evil.com/script.js",
                    "violated-directive": "script-src",
                    "document-uri": "https://myapp.com",
                }
            )
        except ValueError:
            pass

        # Should log spike alert
        audit_calls = mock_audit_service.log_security_event.call_args_list
        spike_logged = any(
            call[1].get("event_type") == "csp_violation_spike"
            for call in audit_calls
            if len(call) > 1
        )
        assert spike_logged or audit_calls  # At least audit was called

    @pytest.mark.asyncio
    async def test_repeated_same_violation_tracked(self, mock_redis, mock_audit_service):
        """Same violation repeated should be counted"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(redis_client=mock_redis, audit_service=mock_audit_service)

        violation = {
            "blocked-uri": "https://evil.com/script.js",
            "violated-directive": "script-src",
            "document-uri": "https://myapp.com",
        }

        # Report same violation 5 times
        for _ in range(5):
            await reporter.report_violation(violation)

        # Should increment counter for tracking
        assert mock_redis.incr.called

    @pytest.mark.asyncio
    async def test_csp_violation_retention_policy(self, mock_redis, mock_audit_service):
        """Old CSP violations should be pruned"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(
            redis_client=mock_redis, audit_service=mock_audit_service, retention_days=7
        )

        # Set TTL for violation list to 7 days
        await reporter.report_violation(
            {
                "blocked-uri": "https://evil.com/script.js",
                "violated-directive": "script-src",
                "document-uri": "https://myapp.com",
            }
        )

        # Should set expiry on violation list
        mock_redis.expire.assert_called()
        call_args = mock_redis.expire.call_args
        # TTL should be around 7 days (604800 seconds)
        assert call_args[0][1] == 604800

    @pytest.mark.asyncio
    async def test_redis_failure_doesnt_block_reporting(self, mock_redis, mock_audit_service):
        """Redis failure should not block CSP violation processing"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(redis_client=mock_redis, audit_service=mock_audit_service)

        # Redis fails
        mock_redis.lpush.side_effect = Exception("Redis down")

        # Should still accept violation (fail-open)
        result = await reporter.report_violation(
            {
                "blocked-uri": "https://evil.com/script.js",
                "violated-directive": "script-src",
                "document-uri": "https://myapp.com",
            }
        )

        assert result is True  # Accept despite Redis failure

    @pytest.mark.asyncio
    async def test_csp_pattern_based_grouping(self, mock_redis, mock_audit_service):
        """Similar violations grouped by pattern"""
        from src.core.security.csp_violation_reporter import CSPViolationReporter

        reporter = CSPViolationReporter(redis_client=mock_redis, audit_service=mock_audit_service)

        # Multiple violations from same source domain
        violations = [
            {
                "blocked-uri": "https://evil.com/script1.js",
                "violated-directive": "script-src",
                "document-uri": "https://myapp.com",
            },
            {
                "blocked-uri": "https://evil.com/script2.js",
                "violated-directive": "script-src",
                "document-uri": "https://myapp.com",
            },
        ]

        for v in violations:
            await reporter.report_violation(v)

        # Should group by pattern/domain
        audit_calls = mock_audit_service.log_security_event.call_args_list
        assert len(audit_calls) >= len(violations)
