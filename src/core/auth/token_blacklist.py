from __future__ import annotations

"""
Token Blacklist Service for JWT Revocation/Logout

Enables immediate token revocation by storing tokens in Redis[Any] with TTL.  # TODO(TYPE): replace Any with concrete type
When user logs out, their JWT token is added to blacklist.
Protected endpoints check token blacklist before processing request.

Architecture:
  1. User logs out -> Token added to Redis[Any] blacklist  # TODO(TYPE): replace Any with concrete type
  2. Token TTL = Token expiry time (automatic cleanup)
  3. Protected endpoints verify token against blacklist
  4. Fail-open: If Redis[Any] down, allow token (availability > strict security)  # TODO(TYPE): replace Any with concrete type
  5. Audit logging: All revocations logged to audit trail for compliance
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.core.typing import AsyncRedisClient

if TYPE_CHECKING:
    from src.core.audit.audit_service import AuditService

logger = logging.getLogger(__name__)


class TokenBlacklist:
    """Redis-based token blacklist for JWT revocation.

    Stores revoked tokens with TTL matching token expiry time.
    Automatically cleans up expired tokens.
    Logs all revocations to audit trail for compliance.
    """

    PREFIX = "token_blacklist:"

    def __init__(self, redis_client: AsyncRedisClient, audit_service: Optional["AuditService"] = None) -> None:
        """Initialize token blacklist with Redis client.

        Args:
            redis_client: Async Redis client for token storage
            audit_service: Optional audit service for logging revocations
        """
        self.redis = redis_client
        self.audit_service = audit_service

    async def revoke_token(
        self,
        token: str,
        expires_in_seconds: int,
        user_id: int | None = None,
        client_ip: str | None = None,
    ) -> bool:
        """Add token to blacklist (revoke it).

        Args:
            token: JWT token to revoke
            expires_in_seconds: TTL in seconds (token expiry time)
            user_id: User ID for audit logging
            client_ip: Client IP address for audit logging

        Returns:
            True if successful, False if error
        """
        try:
            key = f"{self.PREFIX}{token[:50]}"  # Use first 50 chars as key
            await self.redis.setex(key, expires_in_seconds, "revoked")

            # Log to audit trail (non-blocking)
            if self.audit_service:
                try:
                    await self.audit_service.log_security_event(
                        event_type="token_revoked",
                        user_id=user_id,
                        token_fingerprint=token[:20] + "..." + token[-10:],
                        expires_in_seconds=expires_in_seconds,
                        client_ip=client_ip,
                        timestamp=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    # Audit failure should NOT block revocation (fail-open)
                    logger.error(f"Failed to log token revocation: {e}")

            logger.info(f"Token revoked for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")
            return False

    async def is_token_revoked(self, token: str) -> bool:
        """Check if token is blacklisted (revoked).

        Args:
            token: JWT token to check

        Returns:
            True if token is revoked, False if valid
        """
        try:
            key = f"{self.PREFIX}{token[:50]}"
            exists = await self.redis.exists(key)
            is_blacklisted: bool = exists > 0
            return is_blacklisted
        except Exception as e:
            logger.error(f"Failed to check token blacklist: {e}")
            return False  # Fail-open: allow token if Redis down

    async def revoke_all_user_tokens(self, user_id: int, revoked_by: int | None = None) -> int:
        """Revoke ALL tokens for a specific user (e.g., on account compromise).

        Args:
            user_id: User ID whose tokens to revoke
            revoked_by: Admin user ID if this was an admin action

        Returns:
            Number of tokens revoked
        """
        try:
            # Find all tokens for this user
            cursor = 0
            keys_to_delete: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            pattern = f"{self.PREFIX}*user:{user_id}:*"

            # Scan through Redis keys
            cursor, keys = await self.redis.scan(cursor, match=pattern)
            keys_to_delete.extend(keys)

            # Delete all matched tokens
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)

            # Log to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_security_event(
                        event_type="bulk_token_revocation",
                        target_user_id=user_id,
                        tokens_revoked=len(keys_to_delete),
                        revoked_by=revoked_by,
                        is_admin_action=revoked_by is not None,
                        timestamp=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    logger.error(f"Failed to log bulk revocation: {e}")

            logger.warning(f"Revoked {len(keys_to_delete)} tokens for user {user_id}")
            return len(keys_to_delete)

        except Exception as e:
            logger.error(f"Failed to revoke all user tokens: {e}")
            return 0
