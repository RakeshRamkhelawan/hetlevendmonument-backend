from __future__ import annotations

"""
AsyncRedisClient Session Manager - Production Implementation
Manages user sessions, tokens, device tracking, and multi-session support.
Uses AsyncRedisClient for fast, distributed session storage.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Optional, cast
from collections.abc import Awaitable

import redis.asyncio as redis

from src.core.config.config import get_settings
from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """User session information stored in AsyncRedisClient"""

    session_id: str
    user_id: int
    tenant_id: int
    device_name: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: str | None = None
    last_activity: str | None = None
    token: str | None = None
    refresh_token: str | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(UTC).isoformat()
        if self.last_activity is None:
            self.last_activity = datetime.now(UTC).isoformat()


class RedisSessionManager:
    """
    Production-grade session manager using AsyncRedisClient backend.
    Supports multi-device sessions, token refresh, and session expiration.
    """

    # AsyncRedisClient key patterns
    SESSION_KEY_PREFIX = "session:"
    USER_SESSIONS_SET_PREFIX = "user_sessions:"
    TOKEN_BLACKLIST_PREFIX = "token_blacklist:"
    REFRESH_TOKEN_PREFIX = "refresh_token:"

    def __init__(
        self,
        redis_client: AsyncRedisClient | None = None,
        session_ttl: int = 86400,  # 24 hours
        refresh_token_ttl: int = 604800,  # 7 days
    ) -> None:
        """
        Initialize session manager.

        Args:
            redis_client: Existing Redis client (created if None)
            session_ttl: Session TTL in seconds (default 24 hours)
            refresh_token_ttl: Refresh token TTL in seconds (default 7 days)
        """
        self.redis_client = redis_client
        self.session_ttl = session_ttl
        self.refresh_token_ttl = refresh_token_ttl
        self.connected = False

    async def connect(self) -> bool:
        """Establish AsyncRedisClient connection if not provided"""
        if self.redis_client is not None:
            self.connected = True
            return True

        try:
            settings = get_settings()
            from src.core.typing import create_async_redis_client

            client = await create_async_redis_client(
                settings.redis_url, decode_responses=True
            )
            self.redis_client = client
            await client.ping()
            self.connected = True
            logger.info("Session manager connected to AsyncRedisClient")
            return True
        except Exception as e:
            logger.error(f"Failed to connect session manager: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Close AsyncRedisClient connection"""
        if self.redis_client:
            try:
                await self.redis_client.close()
                self.connected = False
                logger.info("Session manager disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting session manager: {e}")

    async def create_session(
        self,
        user_id: int,
        tenant_id: int,
        token: str,
        refresh_token: str,
        device_name: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> str | None:
        """
        Create new user session.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            token: JWT access token
            refresh_token: JWT refresh token
            device_name: Device identifier
            user_agent: User agent string
            ip_address: Client IP address

        Returns:
            Session ID or None if failed
        """
        if not self.connected or self.redis_client is None:
            logger.warning("Session manager not connected")
            return None

        try:
            session_id = str(uuid.uuid4())

            session_data = SessionData(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                device_name=device_name,
                user_agent=user_agent,
                ip_address=ip_address,
                token=token,
                refresh_token=refresh_token,
            )

            session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
            user_sessions_key = f"{self.USER_SESSIONS_SET_PREFIX}{user_id}"

            # Store session data with TTL
            session_json = json.dumps(asdict(session_data), ensure_ascii=True)
            await self.redis_client.setex(session_key, self.session_ttl, session_json)

            # Add session ID to user's active sessions set
            await cast(
                Awaitable[int],
                self.redis_client.sadd(user_sessions_key, session_id),
            )

            # Store refresh token mapping
            refresh_key = f"{self.REFRESH_TOKEN_PREFIX}{refresh_token}"
            await self.redis_client.setex(refresh_key, self.refresh_token_ttl, session_id)

            logger.info(f"Session created: {session_id} for user {user_id} on tenant {tenant_id}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None

    async def get_session(self, session_id: str) -> SessionData | None:
        """Retrieve session data by session ID"""
        if not self.connected or self.redis_client is None:
            return None

        try:
            session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
            session_json = await self.redis_client.get(session_key)

            if session_json is None:
                logger.debug(f"Session not found: {session_id}")
                return None

            session_dict = json.loads(session_json)
            return SessionData(**session_dict)

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session data with new values"""
        if not self.connected or self.redis_client is None:
            return False

        try:
            session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
            session_json = await self.redis_client.get(session_key)

            if session_json is None:
                logger.warning(f"Session not found for update: {session_id}")
                return False

            session_dict = json.loads(session_json)

            # Update allowed fields
            allowed_fields = {
                "last_activity",
                "device_name",
                "user_agent",
                "ip_address",
            }
            for key, value in kwargs.items():
                if key in allowed_fields:
                    session_dict[key] = value

            session_dict["last_activity"] = datetime.now(UTC).isoformat()

            # Re-store with TTL
            updated_json = json.dumps(session_dict, ensure_ascii=True)
            await self.redis_client.setex(session_key, self.session_ttl, updated_json)

            logger.debug(f"Session updated: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke/delete a session"""
        if not self.connected or self.redis_client is None:
            return False

        try:
            session = await self.get_session(session_id)
            if session is None:
                return False

            session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
            user_sessions_key = f"{self.USER_SESSIONS_SET_PREFIX}{session.user_id}"

            # Delete session
            await self.redis_client.delete(session_key)

            # Remove from user's active sessions
            await cast(
                Awaitable[int],
                self.redis_client.srem(user_sessions_key, session_id),
            )

            # Add token to blacklist
            if session.token:
                blacklist_key = f"{self.TOKEN_BLACKLIST_PREFIX}{session.token}"
                await self.redis_client.setex(blacklist_key, self.session_ttl, "revoked")

            logger.info(f"Session revoked: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke session {session_id}: {e}")
            return False

    async def revoke_all_user_sessions(self, user_id: int) -> int:
        """Revoke all sessions for a user (logout all devices)"""
        if not self.connected or self.redis_client is None:
            return 0

        try:
            user_sessions_key = f"{self.USER_SESSIONS_SET_PREFIX}{user_id}"
            session_ids_raw: set[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[set[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.smembers(user_sessions_key),
            )

            if not session_ids_raw:
                return 0

            count = 0
            for session_id in session_ids_raw:
                if await self.revoke_session(session_id):
                    count += 1

            logger.info(f"Revoked {count} sessions for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to revoke all sessions for user {user_id}: {e}")
            return 0

    async def get_user_sessions(self, user_id: int) -> list[SessionData]:
        """Get all active sessions for a user (multi-device tracking)"""
        if not self.connected or self.redis_client is None:
            return []

        try:
            user_sessions_key = f"{self.USER_SESSIONS_SET_PREFIX}{user_id}"
            session_ids_raw: set[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[set[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.smembers(user_sessions_key),
            )

            sessions: list[SessionData] = []
            for session_id in session_ids_raw:
                session = await self.get_session(session_id)
                if session:
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            return []

    async def validate_refresh_token(self, refresh_token: str) -> str | None:
        """
        Validate refresh token and return associated session ID.

        Returns:
            Session ID if valid, None otherwise
        """
        if not self.connected or self.redis_client is None:
            return None

        try:
            refresh_key = f"{self.REFRESH_TOKEN_PREFIX}{refresh_token}"
            session_data = await self.redis_client.get(refresh_key)
            session_id: str | None = session_data
            return session_id

        except Exception as e:
            logger.error(f"Failed to validate refresh token: {e}")
            return None

    async def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is in blacklist (revoked)"""
        if not self.connected or self.redis_client is None:
            return False

        try:
            blacklist_key = f"{self.TOKEN_BLACKLIST_PREFIX}{token}"
            exists: int = await cast(
                Awaitable[int],
                self.redis_client.exists(blacklist_key),
            )
            return bool(exists)

        except Exception as e:
            logger.error(f"Failed to check token blacklist: {e}")
            return False

    async def get_session_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get session statistics"""
        if not self.connected or self.redis_client is None:
            return {"connected": False}

        try:
            # Count active sessions
            pattern = f"{self.SESSION_KEY_PREFIX}*"
            keys: list[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[list[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.keys(pattern),
            )
            active_sessions = len(keys)

            # Count refresh tokens
            refresh_pattern = f"{self.REFRESH_TOKEN_PREFIX}*"
            refresh_keys: list[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[list[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.keys(refresh_pattern),
            )
            refresh_tokens = len(refresh_keys)

            # Count blacklisted tokens
            blacklist_pattern = f"{self.TOKEN_BLACKLIST_PREFIX}*"
            blacklist_keys: list[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[list[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.keys(blacklist_pattern),
            )
            blacklisted_tokens = len(blacklist_keys)

            return {
                "connected": True,
                "active_sessions": active_sessions,
                "refresh_tokens": refresh_tokens,
                "blacklisted_tokens": blacklisted_tokens,
            }

        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return {"connected": True, "error": str(e)}

    async def cleanup_expired_sessions(self) -> int:
        """
        Cleanup sessions that have expired in AsyncRedisClient.
        AsyncRedisClient auto-expires based on TTL, but this cleans up orphaned references.

        Returns:
            Number of cleanup operations performed
        """
        if not self.connected or self.redis_client is None:
            return 0

        try:
            # Get all user session sets and remove non-existent sessions
            pattern = f"{self.USER_SESSIONS_SET_PREFIX}*"
            user_session_sets: list[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                Awaitable[list[Any]],  # TODO(TYPE): replace Any with concrete type
                self.redis_client.keys(pattern),
            )

            cleanup_count = 0
            for user_set_key in user_session_sets:
                session_ids_raw: set[Any] = await cast(  # TODO(TYPE): replace Any with concrete type
                    Awaitable[set[Any]],  # TODO(TYPE): replace Any with concrete type
                    self.redis_client.smembers(user_set_key),
                )

                for session_id in session_ids_raw:
                    session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
                    exists: int = await cast(
                        Awaitable[int],
                        self.redis_client.exists(session_key),
                    )

                    if not exists:
                        await cast(
                            Awaitable[int],
                            self.redis_client.srem(user_set_key, session_id),
                        )
                        cleanup_count += 1

            logger.info(f"Session cleanup: removed {cleanup_count} orphaned references")
            return cleanup_count

        except Exception as e:
            logger.error(f"Failed to cleanup sessions: {e}")
            return 0


# Global session manager instance
_session_manager: RedisSessionManager | None = None


async def get_session_manager() -> RedisSessionManager:
    """Get global session manager instance (singleton pattern)"""
    global _session_manager

    if _session_manager is None:
        _session_manager = RedisSessionManager()
        await _session_manager.connect()

    return _session_manager
