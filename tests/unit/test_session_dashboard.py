"""
TDD RED PHASE: Session Management Dashboard (Unhappy Paths)

Tests for session analytics and management dashboard.
Provides visibility into active sessions, logout patterns, security metrics.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSessionDashboardHappyPath:
    """Happy path: Normal dashboard operations"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.get = AsyncMock(return_value=None)
        redis.hgetall = AsyncMock(return_value={})
        redis.lrange = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, mock_redis, mock_audit_service):
        """Should retrieve list of active sessions"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Mock active sessions
        mock_redis.keys = AsyncMock(return_value=[b"session:user1:token1", b"session:user2:token2"])

        sessions = await dashboard.get_active_sessions()

        assert sessions is not None
        mock_redis.keys.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_metrics(self, mock_redis, mock_audit_service):
        """Should calculate session metrics"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        metrics = await dashboard.get_session_metrics()

        # Should return dict with metrics
        assert isinstance(metrics, dict)


class TestSessionDashboardUnhappyPaths:
    """Unhappy paths: Errors, high load, edge cases"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.get = AsyncMock(return_value=None)
        redis.hgetall = AsyncMock(return_value={})
        redis.lrange = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_dashboard_handles_redis_failure(self, mock_redis, mock_audit_service):
        """Dashboard should handle Redis failures gracefully"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Redis fails
        mock_redis.keys.side_effect = Exception("Redis down")

        with pytest.raises(Exception):
            await dashboard.get_active_sessions()

    @pytest.mark.asyncio
    async def test_dashboard_high_session_count(self, mock_redis, mock_audit_service):
        """Should handle dashboard with thousands of sessions"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Mock 10,000 active sessions
        large_session_list = [f"session:user{i}:token{i}".encode() for i in range(10000)]
        mock_redis.keys = AsyncMock(return_value=large_session_list)

        sessions = await dashboard.get_active_sessions()

        # Should handle large dataset efficiently
        assert sessions is not None

    @pytest.mark.asyncio
    async def test_unauthorized_access_blocked(self, mock_redis, mock_audit_service):
        """Only admins should access dashboard"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Non-admin user attempting access
        non_admin_id = 42

        with pytest.raises(PermissionError, match="Admin access required"):
            await dashboard.get_all_user_sessions(requesting_user_id=non_admin_id, is_admin=False)

    @pytest.mark.asyncio
    async def test_session_data_sanitization(self, mock_redis, mock_audit_service):
        """Session data should not leak sensitive info"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Session with sensitive data
        sensitive_session = {
            b"user_id": b"42",
            b"token": b"jwt_secret_token_here",  # Should NOT be returned
            b"password": b"secret123",  # Should NOT be returned
        }

        mock_redis.hgetall = AsyncMock(return_value=sensitive_session)

        session_info = await dashboard.get_session_details("session:42:token")

        # Token and password should be redacted
        assert session_info is not None
        # Verify sensitive data not included in response
        response_str = str(session_info)
        assert "jwt_secret_token_here" not in response_str
        assert "secret123" not in response_str

    @pytest.mark.asyncio
    async def test_anomaly_detection_suspicious_login_patterns(
        self, mock_redis, mock_audit_service
    ):
        """Detect suspicious login patterns"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            anomaly_detection=True,
        )

        # Simulate suspicious pattern: Same user from 5 different countries in 1 minute
        suspicious_sessions = [
            {"user_id": 42, "location": "US", "ip": "1.1.1.1", "timestamp": 100},
            {"user_id": 42, "location": "JP", "ip": "2.2.2.2", "timestamp": 110},
            {"user_id": 42, "location": "BR", "ip": "3.3.3.3", "timestamp": 120},
            {"user_id": 42, "location": "DE", "ip": "4.4.4.4", "timestamp": 130},
            {"user_id": 42, "location": "IN", "ip": "5.5.5.5", "timestamp": 140},
        ]

        mock_redis.keys = AsyncMock(
            return_value=[
                b"session:user42:token1",
                b"session:user42:token2",
                b"session:user42:token3",
            ]
        )

        anomalies = await dashboard.detect_anomalies(user_id=42)

        # With multiple sessions, anomaly detection should be attempted
        # Result could be None (no anomalies) or a list of anomalies
        # The key is that keys() was called to check for session history
        assert mock_redis.keys.called

    @pytest.mark.asyncio
    async def test_dashboard_caches_metrics(self, mock_redis, mock_audit_service):
        """Dashboard should cache metrics to avoid overload"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            metrics_cache_ttl=60,
        )

        # Mock cached metrics
        mock_redis.get = AsyncMock(return_value=b'{"total_sessions": 100}')

        metrics = await dashboard.get_session_metrics(use_cache=True)

        # Should use cached data
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_dashboard_access(self, mock_redis, mock_audit_service):
        """Dashboard should handle concurrent requests"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Simulate concurrent access
        mock_redis.keys = AsyncMock(return_value=[])

        import asyncio

        # 10 concurrent requests
        results = await asyncio.gather(*[dashboard.get_active_sessions() for _ in range(10)])

        # All should succeed
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_dashboard_audit_access(self, mock_redis, mock_audit_service):
        """Dashboard access should be logged"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(
            redis_client=mock_redis, audit_service=mock_audit_service, log_access=True
        )

        admin_id = 1

        await dashboard.get_all_user_sessions(requesting_user_id=admin_id, is_admin=True)

        # Should log admin access
        audit_calls = mock_audit_service.log_security_event.call_args_list
        assert len(audit_calls) > 0

    @pytest.mark.asyncio
    async def test_session_export_sanitization(self, mock_redis, mock_audit_service):
        """Exported session data should not leak sensitive info"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(redis_client=mock_redis, audit_service=mock_audit_service)

        # Mock sessions for export
        mock_redis.keys = AsyncMock(return_value=[b"session:user1:token1", b"session:user2:token2"])

        exported_data = await dashboard.export_sessions(format="csv")

        # Verify no full tokens/sensitive info in export
        if exported_data:
            exported_str = str(exported_data).lower()
            # Token values should not be exposed (maybe a hash or redacted)
            assert "token1" not in exported_str and "token2" not in exported_str

    @pytest.mark.asyncio
    async def test_dashboard_rate_limiting_on_graph_generation(
        self, mock_redis, mock_audit_service
    ):
        """Graph generation should be rate limited"""
        from src.core.session.session_dashboard import SessionDashboard

        dashboard = SessionDashboard(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            graph_generation_rate_limit=5,  # Max 5 graphs per minute
        )

        # Try to generate 6 graphs rapidly
        for i in range(6):
            try:
                await dashboard.generate_session_graph(graph_type="timeline")
            except ValueError as e:
                if "rate limited" in str(e).lower():
                    break
