from __future__ import annotations

"""
Session Management Dashboard - Provides visibility into active sessions

Admin-only dashboard showing:
- Active sessions per user
- Logout patterns and frequencies
- Anomaly detection (suspicious login patterns)
- Security metrics and trends
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from src.core.typing import AsyncRedisClient

if TYPE_CHECKING:
    from src.core.audit.audit_service import AuditService

logger = logging.getLogger(__name__)


class SessionDashboard:
    """Session management and analytics dashboard.

    - Track active sessions
    - Detect suspicious patterns
    - Admin-only access with audit logging
    - Sensitive data sanitization
    - High concurrency support
    """

    PREFIX_SESSION = "session:"
    PREFIX_ANOMALY = "anomaly:"
    PREFIX_METRICS = "metrics:session:"
    PREFIX_CACHE = "cache:metrics:"

    def __init__(
        self,
        redis_client: AsyncRedisClient,
        audit_service: Optional["AuditService"] = None,
        anomaly_detection: bool = True,
        log_access: bool = True,
        metrics_cache_ttl: int = 300,
        graph_generation_rate_limit: int = 5,
    ) -> None:
        """Initialize session dashboard.

        Args:
            redis_client: AsyncRedisClient async client
            audit_service: Optional audit service
            anomaly_detection: Enable anomaly detection
            log_access: Log all dashboard accesses
            metrics_cache_ttl: Cache TTL for metrics (seconds)
            graph_generation_rate_limit: Max graphs per minute
        """
        self.redis = redis_client
        self.audit_service = audit_service
        self.anomaly_detection = anomaly_detection
        self.log_access = log_access
        self.metrics_cache_ttl = metrics_cache_ttl
        self.graph_generation_rate_limit = graph_generation_rate_limit

    async def get_active_sessions(self, limit: int = 1000) -> list[str]:
        """Get list of active sessions.

        Args:
            limit: Max sessions to return

        Returns: List[Any] of active session keys  # TODO(TYPE): replace Any with concrete type
        """
        try:
            pattern = f"{self.PREFIX_SESSION}*"
            keys = await self.redis.keys(pattern)
            return keys[:limit] or []
        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            raise

    async def get_all_user_sessions(
        self,
        requesting_user_id: int,
        is_admin: bool = False,
        user_id: int | None = None,
    ) -> dict[int, list[str]]:
        """Get sessions for specific user (admin only).

        Args:
            requesting_user_id: Admin requesting data
            is_admin: Whether requester is admin
            user_id: Optional specific user to query

        Returns: Dict[str, Any] mapping user_id to session list  # TODO(TYPE): replace Any with concrete type

        Raises:
            PermissionError: If not admin
        """
        if not is_admin:
            raise PermissionError("Admin access required to view user sessions")

        # Log access
        if self.log_access and self.audit_service:
            try:
                await self.audit_service.log_security_event(
                    event_type="dashboard_access",
                    admin_id=requesting_user_id,
                    query_user_id=user_id,
                    timestamp=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error(f"Failed to log dashboard access: {e}")

        try:
            if user_id is not None:
                # Get sessions for specific user
                pattern = f"{self.PREFIX_SESSION}user{user_id}:*"
                keys = await self.redis.keys(pattern)
                return {user_id: keys or []}
            else:
                # Get all sessions grouped by user
                all_sessions: dict[int, list[str]] = {}
                pattern = f"{self.PREFIX_SESSION}*"
                keys = await self.redis.keys(pattern)

                for key in keys:
                    # Parse user_id from key: session:user{id}:token
                    try:
                        parts = key.split(":")
                        if len(parts) >= 2:
                            user_part = parts[1]
                            if user_part.startswith("user"):
                                uid = int(user_part[4:])
                                if uid not in all_sessions:
                                    all_sessions[uid] = []
                                all_sessions[uid].append(key)
                    except (ValueError, IndexError):
                        continue

                return all_sessions
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return {}

    async def get_session_details(self, session_key: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get details for specific session (sanitized).

        Args:
            session_key: Redis session key

        Returns:
            Sanitized session details (no tokens/passwords)
        """
        try:
            session_data = await self.redis.hgetall(session_key)

            if not session_data:
                return None

            # Sanitize sensitive fields
            sanitized: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            BLOCKED_FIELDS = ["token", "password", "secret", "api_key"]

            for key, value in session_data.items():
                # Decode bytes keys from Redis
                if isinstance(key, bytes):
                    key = key.decode()

                key_lower = key.lower()

                # Skip sensitive fields
                if any(blocked in key_lower for blocked in BLOCKED_FIELDS):
                    continue

                # Include safe fields
                if isinstance(value, bytes):
                    value = value.decode()

                sanitized[key] = value

            return sanitized
        except Exception as e:
            logger.error(f"Failed to get session details: {e}")
            return None

    async def get_session_metrics(self, use_cache: bool = True) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get session metrics.

        Args:
            use_cache: Use cached metrics if available

        Returns: Dict[str, Any] with session metrics  # TODO(TYPE): replace Any with concrete type
        """
        try:
            if use_cache:
                # Check cache first
                cached = await self.redis.get(f"{self.PREFIX_CACHE}summary")
                if cached:
                    return {"cached": True, "data": cached}

            # Get active sessions
            sessions = await self.get_active_sessions()

            metrics = {
                "total_active_sessions": len(sessions),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cached": False,
            }

            # Cache metrics
            try:
                await self.redis.setex(
                    f"{self.PREFIX_CACHE}summary", self.metrics_cache_ttl, str(metrics)
                )
            except Exception as e:
                logger.debug(f"Failed to cache metrics: {e}")

            return metrics
        except Exception as e:
            logger.error(f"Failed to get session metrics: {e}")
            return {}

    async def detect_anomalies(self, user_id: int) -> list[dict[str, Any]] | None:  # TODO(TYPE): replace Any with concrete type
        """Detect suspicious login patterns.

        Args:
            user_id: User to check

        Returns: List[Any] of detected anomalies or None  # TODO(TYPE): replace Any with concrete type
        """
        if not self.anomaly_detection:
            return None

        try:
            # Get user's session history
            pattern = f"{self.PREFIX_SESSION}user{user_id}:*"
            sessions = await self.redis.keys(pattern)

            if len(sessions) < 2:
                return None

            # Check for suspicious patterns
            # (e.g., multiple countries in short timeframe)
            anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # This is a simplified check - full implementation would
            # analyze IP geolocation, timestamps, etc.
            if len(sessions) > 5:
                anomalies.append(
                    {
                        "type": "rapid_sessions",
                        "severity": "medium",
                        "description": f"{len(sessions)} sessions detected",
                    }
                )

            return anomalies if anomalies else None
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {e}")
            return None

    async def export_sessions(self, format: str = "json") -> str | None:
        """Export session data (sanitized).

        Args:
            format: Export format (json, csv)

        Returns:
            Exported data or None
        """
        try:
            sessions = await self.get_active_sessions()

            if not sessions:
                return None

            # Build sanitized export
            export_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_count": len(sessions),
                "sessions": [],
            }

            # Sanitize: extract only user_id from session key, redact token
            sanitized_sessions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for s in sessions:
                session_key = s.decode() if isinstance(s, bytes) else s
                # Extract user_id from "session:userN:tokenX" format
                parts = session_key.split(":")
                if len(parts) >= 2:
                    # Include only session key without token
                    sanitized_key = f"session:{parts[1]}:[REDACTED]"
                    sanitized_sessions.append(sanitized_key)
                else:
                    sanitized_sessions.append(session_key)

            export_data["sessions"] = sanitized_sessions[:10]  # Limit to first 10 for safety

            if format == "csv":
                # Convert to CSV format (simplified, with redacted tokens)
                lines = ["session_key,timestamp"]
                for s in export_data["sessions"]:
                    lines.append(f"{s},{export_data['timestamp']}")
                return "\n".join(lines)

            return str(export_data)
        except Exception as e:
            logger.error(f"Failed to export sessions: {e}")
            return None

    async def generate_session_graph(self, graph_type: str = "timeline") -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate session graph (rate limited).

        Args:
            graph_type: Type of graph (timeline, heatmap, etc)

        Returns:
            Graph data or raises ValueError if rate limited
        """
        try:
            # Check rate limit
            rate_limit_key = f"dashboard:graph_generation:{graph_type}"
            current_count = await self.redis.incr(rate_limit_key)

            if current_count == 1:
                await self.redis.expire(rate_limit_key, 60)  # 1 minute window

            if current_count > self.graph_generation_rate_limit:
                raise ValueError(
                    f"Graph generation rate limited. Max {self.graph_generation_rate_limit} per minute"
                )

            # Generate graph (placeholder)
            return {
                "type": graph_type,
                "data": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate graph: {e}")
            return {}
