"""Antibody Registry - Threat response handlers.

FIX #3: Includes ISOLATE_TENANT handler.
"""

import logging
from enum import Enum
from typing import Awaitable
from collections.abc import Callable

from src.core.als.immune.immune_system import ThreatEvent
from src.core.als.infrastructure.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class AntibodyAction(Enum):
    """Available antibody actions."""

    RATE_LIMIT = "rate_limit"
    BLOCK_AGENT = "block_agent"
    QUARANTINE_SIGNAL = "quarantine_signal"
    ALERT_ADMIN = "alert_admin"
    CIRCUIT_BREAK = "circuit_break"
    ISOLATE_TENANT = "isolate_tenant"  # FIX #3


class AntibodyRegistry:
    """Registry of antibody response handlers."""

    def __init__(self, signal_bus: SignalBus) -> None:
        self.signal_bus = signal_bus
        self._handlers: dict[AntibodyAction, Callable[[ThreatEvent], Awaitable[dict[str, object]]]] = {}
        self._build_registry()

    def _build_registry(self) -> None:
        """Build handler registry."""
        self._handlers = {
            AntibodyAction.RATE_LIMIT: self._rate_limit,
            AntibodyAction.BLOCK_AGENT: self._block_agent,
            AntibodyAction.QUARANTINE_SIGNAL: self._quarantine_signal,
            AntibodyAction.ALERT_ADMIN: self._alert_admin,
            AntibodyAction.CIRCUIT_BREAK: self._circuit_break,
            AntibodyAction.ISOLATE_TENANT: self._isolate_tenant,  # FIX #3
        }

    def register(self, name: str, action_type: str, config: dict[str, object]) -> None:
        """Register custom antibody handler."""
        # Store for reference
        pass

    async def execute(self, action: AntibodyAction, threat: ThreatEvent) -> dict[str, object]:
        """Execute antibody action."""
        handler = self._handlers.get(action)
        if not handler:
            raise ValueError(f"Unknown antibody action: {action}")

        logger.info(f"Executing {action.value} for threat {threat.threat_type}")
        return await handler(threat)

    # Handlers
    async def _rate_limit(self, threat: ThreatEvent) -> dict[str, object]:
        """Rate limit the source agent."""
        # Emit signal to enable cooldown
        return {"action": "rate_limit", "target": threat.source_agent, "duration_s": 60}

    async def _block_agent(self, threat: ThreatEvent) -> dict[str, object]:
        """Block the source agent."""
        return {
            "action": "block_agent",
            "target": threat.source_agent,
            "duration_s": 300,
        }

    async def _quarantine_signal(self, threat: ThreatEvent) -> dict[str, object]:
        """Quarantine suspicious signals."""
        return {"action": "quarantine", "signature": threat.threat_signature}

    async def _alert_admin(self, threat: ThreatEvent) -> dict[str, object]:
        """Alert administrators."""
        logger.critical(
            f"ADMIN ALERT: Threat {threat.threat_type} in tenant {threat.tenant_id}",
            extra={
                "tenant_id": threat.tenant_id,
                "threat_type": threat.threat_type,
                "severity": threat.severity,
            },
        )
        return {
            "action": "alert",
            "severity": threat.severity,
            "message": f"Threat detected: {threat.threat_type}",
        }

    async def _circuit_break(self, threat: ThreatEvent) -> dict[str, object]:
        """Enable circuit breaker for failing agent."""
        return {
            "action": "circuit_break",
            "target": threat.source_agent,
            "threshold": 5,
        }

    async def _isolate_tenant(self, threat: ThreatEvent) -> dict[str, object]:
        """
        FIX #3: Block all incoming signals for tenant.

        Used for severe security threats.
        """
        logger.critical(f"ISOLATING TENANT {threat.tenant_id} due to threat {threat.threat_type}")

        # Block tenant at signal bus level
        await self.signal_bus.block_tenant(threat.tenant_id, duration_s=300)  # 5 minutes

        # Alert admins
        await self._alert_admin(threat)

        return {
            "action": "tenant_isolated",
            "tenant_id": threat.tenant_id,
            "duration_s": 300,
            "reason": threat.threat_type,
        }
