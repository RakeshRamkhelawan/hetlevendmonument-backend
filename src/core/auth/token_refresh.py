from __future__ import annotations

"""
Token Refresh Service with Automatic Rotation

Handles secure token refresh with automatic rotation.
- Validates old token
- Blacklists old token immediately
- Issues new token with fresh expiry
- Logs all rotation events to audit trail
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from jose import JWTError
from src.core.typing import AsyncRedisClient

if TYPE_CHECKING:
    from src.core.audit.audit_service import AuditService
    from src.core.auth.jwt_handler import JWTHandler as JWTService

logger = logging.getLogger(__name__)


class TokenRefreshService:
    """Secure token refresh with automatic rotation.

    - Validates old token is still valid
    - Blacklists old token from being reused (refresh attack prevention)
    - Issues new token with fresh expiry
    - Logs rotation event to audit trail for compliance
    """

    PREFIX_REFRESH_BLACKLIST = "token_refresh_blacklist:"

    def __init__(
        self,
        redis_client: AsyncRedisClient,
        jwt_service: "JWTService",
        audit_service: Optional["AuditService"] = None,
    ) -> None:
        """Initialize token refresh service.

        Args:
            redis_client: Async Redis client for blacklist storage
            jwt_service: JWT service for token creation/validation
            audit_service: Optional audit service for logging rotations
        """
        self.redis = redis_client
        self.jwt_service = jwt_service
        self.audit_service = audit_service

    async def refresh_token(self, old_token: str, client_ip: str | None = None) -> str:
        """Refresh JWT token with rotation.

        Args:
            old_token: Current JWT token to refresh
            client_ip: Client IP for audit logging (optional)

        Returns:
            New JWT token

        Raises:
            JWTError: If token is invalid or expired
            ValueError: If token was already refreshed (prevent reuse)
        """
        try:
            # Check if token was already refreshed (prevent refresh attacks)
            refresh_key = f"{self.PREFIX_REFRESH_BLACKLIST}{old_token[:50]}"
            already_refreshed = await self.redis.exists(refresh_key)
            if already_refreshed:
                raise ValueError(
                    "Token already refreshed - cannot reuse during same refresh window"
                )

            # Validate old token
            payload = self.jwt_service.verify_token(old_token)
            if payload is None:
                raise JWTError("Invalid token - payload is None")
            sub = payload.get("sub")
            if sub is None:
                raise JWTError("Invalid token - missing sub claim")
            user_id = int(sub.replace("user", ""))
            old_exp = payload.get("exp")
            if old_exp is None:
                raise JWTError("Invalid token - missing exp claim")

            # Create new token with fresh expiry (marked as fresh/rotated)
            new_token = self.jwt_service.create_access_token({"sub": str(user_id), "fresh": True})

            # Blacklist old token to prevent refresh window reuse
            # TTL = remaining validity of old token (prevent token confusion attacks)
            ttl_seconds = max(1, int(old_exp) - int(datetime.now(timezone.utc).timestamp()))
            await self.redis.setex(refresh_key, ttl_seconds, "rotated")

            # Log token rotation event to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_security_event(
                        event_type="token_rotated",
                        user_id=user_id,
                        old_token_fingerprint=old_token[:20] + "..." + old_token[-10:],
                        new_token_fingerprint=new_token[:20] + "..." + new_token[-10:],
                        client_ip=client_ip,
                        timestamp=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    # Audit failure should NOT block token refresh (fail-open)
                    logger.error(f"Failed to log token rotation: {e}")

            logger.info(f"Token refreshed/rotated for user {user_id}")
            return new_token

        except JWTError as e:
            logger.warning(f"Failed to refresh token - invalid/expired: {e}")
            raise
        except ValueError as e:
            logger.warning(f"Token refresh prevented - already rotated: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise
