"""Governance domain events -- typed event dataclasses for event bus emission.

All fields use stdlib types only. No ORM models, no AsyncSession.
Handlers in governance/event_handlers.py create their own sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditLogEmitEvent:
    """Emitted when a component wants to write a generic audit log entry."""

    tenant_id: int
    event_type: str
    threat_level: str
    client_ip: str
    endpoint: str
    description: str
    event_metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )


@dataclass
class SecurityAuditEvent:
    """Emitted when a security-relevant action occurs (RBAC, workflow, etc.)."""

    tenant_id: int
    event_type: str
    action: str
    entity_id: str
    details: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )
    user_id: int | None = None


@dataclass
class ConsentAuditEvent:
    """Emitted when a consent state changes (twin consent, GDPR, etc.)."""

    tenant_id: int
    action: str
    consent_type: str
    user_id: str | None = None
    details: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )
