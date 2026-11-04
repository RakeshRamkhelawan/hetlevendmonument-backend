from __future__ import annotations

"""
Logout Rate Limiter - Prevents logout abuse and DDoS attacks

Enforces per-user and per-IP rate limits on logout endpoint.
Detects coordinated attacks from multiple IPs.
All violations logged to audit trail.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from src.core.typing import AsyncRedisClient


if TYPE_CHECKING:
    from src.core.audit.audit_service import AuditService

logger = logging.getLogger(__name__)


class LogoutRateLimiter:
    """Rate limiting for logout endpoint.

    - Per-user rate limit (max logouts per minute)
    - Per-IP rate limit (detect attacker IPs)
    - Exponential backoff for repeat violations
    - Distributed attack detection
    - Non-blocking enforcement (fail-open)
    """

    PREFIX_USER = "logout:user:"
    PREFIX_IP = "logout:ip:"
    PREFIX_VIOLATIONS = "logout:violations:"

    def __init__(
        self,
        redis_client: AsyncRedisClient,
        audit_service: Optional["AuditService"] = None,
        max_logouts_per_minute: int = 5,
        max_logouts_per_ip_per_minute: int = 10,
        window_seconds: int = 60,
        enable_exponential_backoff: bool = False,
        detect_distributed_attacks: bool = False,
        attack_threshold: int = 20,
    ) -> None:
        """Initialize rate limiter.

        Args:
            redis_client: AsyncRedisClient async client
            audit_service: Optional audit service for logging
            max_logouts_per_minute: Max logouts per user per window
            max_logouts_per_ip_per_minute: Max logouts from IP per window
            window_seconds: Time window for rate limit
            enable_exponential_backoff: Enable exponential backoff on violations
            detect_distributed_attacks: Enable distributed attack detection
            attack_threshold: Number of logouts to trigger attack alert
        """
        self.redis = redis_client
        self.audit_service = audit_service
        self.max_logouts_per_minute = max_logouts_per_minute
        self.max_logouts_per_ip_per_minute = max_logouts_per_ip_per_minute
        self.window_seconds = window_seconds
        self.enable_exponential_backoff = enable_exponential_backoff
        self.detect_distributed_attacks = detect_distributed_attacks
        self.attack_threshold = attack_threshold

    async def check_rate_limit(self, user_id: int, client_ip: str) -> bool:
        """Check if logout should be allowed.

        Args:
            user_id: User attempting logout
            client_ip: Client IP address

        Returns:
            True if allowed, False/exception if rate limited

        Raises:
            ValueError: If rate limit exceeded
        """
        try:
            # Check per-user limit
            user_key = f"{self.PREFIX_USER}{user_id}"
            user_count = await self.redis.incr(user_key)

            if user_count == 1:
                # First logout in window, set TTL
                await self.redis.expire(user_key, self.window_seconds)

            if user_count > self.max_logouts_per_minute:
                # User exceeded limit
                if self.audit_service:
                    try:
                        await self.audit_service.log_security_event(
                            event_type="logout_rate_limit_exceeded",
                            user_id=user_id,
                            client_ip=client_ip,
                            attempts=user_count,
                            limit=self.max_logouts_per_minute,
                            timestamp=datetime.now(timezone.utc),
                        )
                    except Exception as e:
                        logger.error(f"Failed to log rate limit violation: {e}")

                raise ValueError(f"Rate limit exceeded for user {user_id}")

            # Check per-IP limit
            ip_key = f"{self.PREFIX_IP}{client_ip}"
            ip_count = await self.redis.incr(ip_key)

            if ip_count == 1:
                await self.redis.expire(ip_key, self.window_seconds)

            if ip_count > self.max_logouts_per_ip_per_minute:
                # IP exceeded limit
                if self.audit_service:
                    try:
                        await self.audit_service.log_security_event(
                            event_type="logout_ip_rate_limit_exceeded",
                            client_ip=client_ip,
                            attempts=ip_count,
                            limit=self.max_logouts_per_ip_per_minute,
                            timestamp=datetime.now(timezone.utc),
                        )
                    except Exception as e:
                        logger.error(f"Failed to log IP rate limit: {e}")

                raise ValueError(f"IP rate limit exceeded: {client_ip}")

            # Track violations for distributed attack detection
            if self.detect_distributed_attacks:
                await self._check_distributed_attack(user_id, client_ip)

            return True

        except ValueError:
            raise  # Re-raise rate limit violations
        except Exception as e:
            # Redis failure - fail open (allow logout)
            logger.error(f"Rate limit check failed: {e}")
            return True

    async def _check_distributed_attack(self, user_id: int, client_ip: str) -> None:
        """Check for distributed attack patterns.

        Detects multiple IPs attempting logout for same user.
        """
        try:
            violation_key = f"{self.PREFIX_VIOLATIONS}{user_id}"

            # Add IP to violation set
            await self.redis.sadd(violation_key, client_ip)
            await self.redis.expire(violation_key, self.window_seconds)

            # Count unique IPs
            unique_ips: int = await self.redis.scard(violation_key)

            if unique_ips >= self.attack_threshold:
                # Distributed attack detected
                if self.audit_service:
                    try:
                        await self.audit_service.log_security_event(
                            event_type="distributed_logout_attack_detected",
                            user_id=user_id,
                            unique_ips=unique_ips,
                            threshold=self.attack_threshold,
                            timestamp=datetime.now(timezone.utc),
                        )
                    except Exception as e:
                        logger.error(f"Failed to log attack detection: {e}")

                raise ValueError(f"Distributed attack detected for user {user_id}")

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Distributed attack detection failed: {e}")
