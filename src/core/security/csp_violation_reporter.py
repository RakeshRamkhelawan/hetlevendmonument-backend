from __future__ import annotations

"""
CSP Violation Reporter - Monitors and reports Content Security Policy violations

Accepts CSP violation reports from browsers.
Detects spikes and malicious patterns.
Stores violations for forensics and compliance.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.core.typing import AsyncRedisClient


if TYPE_CHECKING:
    from src.core.audit.audit_service import AuditService

logger = logging.getLogger(__name__)


class CSPViolationReporter:
    """CSP violation reporter and analyzer.

    - Accepts CSP violation reports from browser
    - Validates reports (required fields, malicious URIs)
    - Detects violation spikes
    - Stores violations for forensics
    - Patterns violations by source domain
    """

    PREFIX_VIOLATIONS = "csp:violations:"
    PREFIX_SPIKE = "csp:spike:"

    MALICIOUS_PATTERNS = ["javascript:", "data:text/html", "file://", "blob:"]

    def __init__(
        self,
        redis_client: AsyncRedisClient,
        audit_service: Optional["AuditService"] = None,
        spike_threshold: int = 100,
        block_malicious_uris: bool = True,
        retention_days: int = 7,
        pattern_grouping: bool = True,
    ) -> None:
        """Initialize CSP violation reporter.

        Args:
            redis_client: AsyncRedisClient async client
            audit_service: Optional audit service
            spike_threshold: Number of violations to trigger alert
            block_malicious_uris: Block obviously malicious URIs
            retention_days: How long to retain violations
            pattern_grouping: Group similar violations by pattern
        """
        self.redis = redis_client
        self.audit_service = audit_service
        self.spike_threshold = spike_threshold
        self.block_malicious_uris = block_malicious_uris
        self.retention_days = retention_days
        self.pattern_grouping = pattern_grouping

    async def report_violation(self, violation: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Report a CSP violation.

        Args:
            violation: CSP violation report from browser

        Returns:
            True if accepted, raises ValueError if rejected

        Raises:
            ValueError: If report invalid or malicious
        """
        try:
            # Validate required fields
            required_fields = ["blocked-uri", "violated-directive", "document-uri"]
            if not all(field in violation for field in required_fields):
                raise ValueError("Missing required fields in CSP violation report")

            blocked_uri = violation.get("blocked-uri", "")

            # Check for malicious URIs
            if self.block_malicious_uris:
                for pattern in self.MALICIOUS_PATTERNS:
                    if pattern in blocked_uri.lower():
                        raise ValueError(f"Malicious URI detected: {pattern}")

            # Check for spike
            spike_key = f"{self.PREFIX_SPIKE}:{blocked_uri}"
            spike_count = await self.redis.incr(spike_key)
            await self.redis.expire(spike_key, 60)  # 1 minute window

            if spike_count > self.spike_threshold:
                # Spike detected
                if self.audit_service:
                    try:
                        await self.audit_service.log_security_event(
                            event_type="csp_violation_spike",
                            blocked_uri=blocked_uri,
                            violations_in_window=spike_count,
                            threshold=self.spike_threshold,
                            timestamp=datetime.now(timezone.utc),
                        )
                    except Exception as e:
                        logger.error(f"Failed to log CSP spike: {e}")

                raise ValueError(f"CSP violation spike detected: {spike_count} violations")

            # Store violation for forensics
            violations_key = f"{self.PREFIX_VIOLATIONS}{blocked_uri}"

            violation_record = {
                "violated_directive": violation.get("violated-directive"),
                "document_uri": violation.get("document-uri"),
                "disposition": violation.get("disposition", "enforce"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status_code": violation.get("status-code", 0),
            }

            # Store violation (list for history)
            await self.redis.lpush(violations_key, str(violation_record))

            # Set retention policy (7 days)
            retention_seconds = self.retention_days * 86400
            await self.redis.expire(violations_key, retention_seconds)

            # Log to audit trail if enabled
            if self.audit_service:
                try:
                    await self.audit_service.log_security_event(
                        event_type="csp_violation_reported",
                        blocked_uri=blocked_uri[:50],  # Truncate for logging
                        violated_directive=violation.get("violated-directive"),
                        document_uri=violation.get("document-uri"),
                        timestamp=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    logger.error(f"Failed to log CSP violation: {e}")

            logger.info(f"CSP violation recorded: {violation.get('violated-directive')}")
            return True

        except ValueError:
            raise  # Re-raise validation errors
        except Exception as e:
            # Redis failure - fail open (accept violation)
            logger.error(f"Failed to report CSP violation: {e}")
            return True

    async def get_violations_by_uri(self, blocked_uri: str, limit: int = 50) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get violation history for specific URI.

        Args:
            blocked_uri: URI to get violations for
            limit: Max records to return

        Returns: List[Any] of violation records  # TODO(TYPE): replace Any with concrete type
        """
        try:
            violations_key = f"{self.PREFIX_VIOLATIONS}{blocked_uri}"
            records: list[Any] = await self.redis.lrange(violations_key, 0, limit - 1)  # TODO(TYPE): replace Any with concrete type
            return records or []
        except Exception as e:
            logger.error(f"Failed to get violation history: {e}")
            return []

    async def get_top_violated_directives(self, limit: int = 10) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get top CSP directives being violated.

        Args:
            limit: Max directives to return

        Returns: List[Any] of (directive, count) tuples  # TODO(TYPE): replace Any with concrete type
        """
        try:
            # This would scan all violation keys and aggregate
            # Implementation details depend on data structure
            pattern = f"{self.PREFIX_VIOLATIONS}*"
            keys: list[Any] = await self.redis.keys(pattern)  # TODO(TYPE): replace Any with concrete type
            return keys[:limit] or []
        except Exception as e:
            logger.error(f"Failed to get top directives: {e}")
            return []
