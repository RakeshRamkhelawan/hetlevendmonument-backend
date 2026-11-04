"""Immune System - Automated threat detection and response.

The immune system protects the symbiotic organism by:
1. Detecting threats (anomalies, attacks, misuse)
2. Learning from past threats (memory cells)
3. Automatically responding (antibodies)
4. Isolating compromised tenants

Inspired by biological immune systems.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING, cast
from collections.abc import Callable

from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier

if TYPE_CHECKING:
    from src.core.als.immune.antibody_registry import AntibodyAction

from src.core.als.models.immune_antibody import ImmuneAntibody
from src.core.als.models.immune_memory_cell import ImmuneMemoryCell
from src.core.database.session import get_db_session

logger = logging.getLogger("ImmuneSystem")


@dataclass
class ThreatEvent:
    """A detected security threat."""

    tenant_id: int
    threat_type: str
    threat_signature: str  # Hash of pattern
    source_agent: str | None
    payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    severity: str  # low, medium, high, critical
    timestamp: datetime


class ImmuneSystem:
    """
    Immune System for the symbiotic organism.

    Monitors signals for threats and automatically responds.
    """

    def __init__(
        self,
        tenant_id: int,
        signal_bus: SignalBus,
        antibody_registry: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.tenant_id = tenant_id
        self.signal_bus = signal_bus
        self._memory_cells: dict[str, ImmuneMemoryCell] = {}

        # Lazy import to avoid circular dependency
        if antibody_registry is None:
            from src.core.als.immune.antibody_registry import AntibodyRegistry

            self.antibodies = AntibodyRegistry(signal_bus)
        else:
            self.antibodies = antibody_registry

    async def initialize(self) -> bool:
        """Load antibodies and memory cells from database."""
        try:
            await self._load_antibodies()
            await self._load_memory_cells()

            logger.info(
                f"ImmuneSystem initialized for tenant {self.tenant_id}",
                extra={
                    "tenant_id": self.tenant_id,
                    "antibodies_loaded": len(self.antibodies._handlers),
                    "memory_cells_loaded": len(self._memory_cells),
                },
            )
            return True
        except Exception as e:
            logger.error(f"ImmuneSystem initialization failed: {e}")
            return False

    async def start_monitoring(self) -> None:
        """Start monitoring signals for threats."""
        # Listen to REFLEX channel (high-priority threats)
        # Cast async handler to expected type for signal bus compatibility
        asyncio.create_task(
            self.signal_bus.listen(
                tenant_id=self.tenant_id,
                tier=SignalTier.REFLEX,
                handler=cast(
                    Callable[..., Any], self._handle_reflex_signal
                ),  # TODO(TYPE): replace Any with concrete type
            )
        )

        # Listen to COGNITIVE channel (anomaly detection)
        asyncio.create_task(
            self.signal_bus.listen(
                tenant_id=self.tenant_id,
                tier=SignalTier.COGNITIVE,
                handler=cast(
                    Callable[..., Any], self._handle_cognitive_signal
                ),  # TODO(TYPE): replace Any with concrete type
            )
        )

        logger.info(f"ImmuneSystem monitoring started for tenant {self.tenant_id}")

    async def detect_threat(self, signal: Signal) -> ThreatEvent | None:
        """
        Analyze signal for threat patterns.

        Returns ThreatEvent if threat detected, None otherwise.
        """
        # Check for known threat signatures
        payload_str = json.dumps(signal.payload, sort_keys=True)
        signature = hashlib.sha256(payload_str.encode()).hexdigest()[:32]

        if signature in self._memory_cells:
            memory = self._memory_cells[signature]

            # Reinforce memory (learning)
            memory.reinforced_count = (memory.reinforced_count or 0) + 1
            memory.last_reinforced = datetime.now(timezone.utc)

            return ThreatEvent(
                tenant_id=signal.tenant_id,
                threat_type=memory.threat_type,
                threat_signature=signature,
                source_agent=signal.source_agent_id,
                payload=signal.payload,
                severity="high",  # Known threat
                timestamp=datetime.now(timezone.utc),
            )

        # Check for anomaly patterns
        if self._is_anomalous(signal):
            return ThreatEvent(
                tenant_id=signal.tenant_id,
                threat_type="anomaly",
                threat_signature=signature,
                source_agent=signal.source_agent_id,
                payload=signal.payload,
                severity="medium",
                timestamp=datetime.now(timezone.utc),
            )

        return None

    async def respond_to_threat(
        self, threat: ThreatEvent
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Respond to detected threat.

        Selects appropriate antibody and executes response.
        """
        logger.critical(
            f"Threat detected: {threat.threat_type}",
            extra={
                "tenant_id": threat.tenant_id,
                "threat_type": threat.threat_type,
                "threat_signature": threat.threat_signature,
                "severity": threat.severity,
            },
        )

        # Select antibody based on threat type
        action = self._select_antibody(threat)

        # Execute response
        from src.core.als.immune.antibody_registry import AntibodyAction

        action_enum = action if isinstance(action, AntibodyAction) else AntibodyAction.ALERT_ADMIN
        result = await self.antibodies.execute(action_enum, threat)

        # Create memory cell for learning
        await self._create_memory_cell(threat, result)

        return result

    async def create_antibody(
        self,
        name: str,
        target_pattern: str,
        action_type: str,
        action_config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ImmuneAntibody:
        """
        Create new antibody (automated response rule).

        Args:
            name: Antibody identifier
            target_pattern: Pattern to match
            action_type: Type of response
            action_config: Response parameters
        """

        async with get_db_session() as session:
            antibody = ImmuneAntibody(
                tenant_id=self.tenant_id,
                name=name,
                target_antigen=target_pattern,
                action_type=action_type,
                action_config=action_config,
                is_auto_generated=False,
            )

            session.add(antibody)
            await session.commit()
            await session.refresh(antibody)

            logger.info(
                f"Created antibody {name}",
                extra={
                    "antibody_name": name,
                    "action_type": action_type,
                    "tenant_id": self.tenant_id,
                },
            )

            return antibody

    # Private methods
    async def _handle_reflex_signal(self, signal: Signal) -> None:
        """Handle high-priority REFLEX signals."""
        threat = await self.detect_threat(signal)
        if threat:
            await self.respond_to_threat(threat)

    async def _handle_cognitive_signal(self, signal: Signal) -> None:
        """Handle COGNITIVE signals for anomaly detection."""
        # Check for suspicious patterns
        if self._is_suspicious(signal):
            threat = ThreatEvent(
                tenant_id=signal.tenant_id,
                threat_type="suspicious_activity",
                threat_signature=self._calculate_signature(signal),
                source_agent=signal.source_agent_id,
                payload=signal.payload,
                severity="low",
                timestamp=datetime.now(timezone.utc),
            )
            await self.respond_to_threat(threat)

    async def _load_antibodies(self) -> None:
        """Load antibodies from database."""
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(ImmuneAntibody).where(
                    ImmuneAntibody.tenant_id == self.tenant_id,
                    ImmuneAntibody.is_active.is_(True),
                )
            )
            antibodies = result.scalars().all()

            for antibody in antibodies:
                config = antibody.action_config if antibody.action_config is not None else {}
                self.antibodies.register(antibody.name, antibody.action_type, config)

    async def _load_memory_cells(self) -> None:
        """Load threat memory cells from database."""
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(ImmuneMemoryCell).where(ImmuneMemoryCell.tenant_id == self.tenant_id)
            )
            cells = result.scalars().all()

            for cell in cells:
                self._memory_cells[cell.threat_signature] = cell

    async def _create_memory_cell(
        self,
        threat: ThreatEvent,
        outcome: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Create memory cell from threat experience."""

        async with get_db_session() as session:
            cell = ImmuneMemoryCell(
                tenant_id=threat.tenant_id,
                threat_signature=threat.threat_signature,
                threat_type=threat.threat_type,
                threat_description=str(threat.payload)[:500],
                antibodies_used=[outcome.get("action", "unknown")],
                outcome=outcome,
            )

            session.add(cell)
            await session.commit()

            # Update cache
            self._memory_cells[threat.threat_signature] = cell

    def _is_anomalous(self, signal: Signal) -> bool:
        """Check if signal is anomalous."""
        # Simple heuristics - can be enhanced with ML
        payload_size = len(json.dumps(signal.payload))

        # Large payloads might be suspicious
        if payload_size > 1000000:  # 1MB
            return True

        # Check for suspicious patterns
        payload_str = json.dumps(signal.payload)
        suspicious = ["drop", "delete", "truncate", "exec(", "eval("]
        if any(s in payload_str.lower() for s in suspicious):
            return True

        return False

    def _is_suspicious(self, signal: Signal) -> bool:
        """Check if signal is suspicious."""
        # High frequency from same agent
        # TODO: Implement rate tracking
        return False

    def _calculate_signature(self, signal: Signal) -> str:
        """Calculate threat signature from signal."""
        payload_str = json.dumps(signal.payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:32]

    def _select_antibody(self, threat: ThreatEvent) -> AntibodyAction:
        """Select appropriate antibody for threat."""
        from src.core.als.immune.antibody_registry import AntibodyAction

        # Map threat types to actions
        action_map: dict[str, AntibodyAction] = {
            "rate_limit_breach": AntibodyAction.RATE_LIMIT,
            "malicious_payload": AntibodyAction.BLOCK_AGENT,
            "anomaly": AntibodyAction.QUARANTINE_SIGNAL,
            "critical": AntibodyAction.ISOLATE_TENANT,
        }

        return action_map.get(threat.threat_type, AntibodyAction.ALERT_ADMIN)
