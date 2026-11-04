"""
Co-Pilot notification subsystem.

Components:
    NotificationBudgetTracker - enforces daily limit (default 25, user-configurable 0-100)
    NotificationDispatcher    - picks delivery channel based on severity
    DigestGenerator           - builds daily summary for smart-batching users
    WSPusher                  - pushes inline signals over WebSocket

Per ADR-027 and docs/copilot-architecture.md Section 9.
"""

from __future__ import annotations

from src.core.copilot.notification.digest import (
    Digest,
    DigestGenerator,
    DigestQueue,
    QueuedSignal,
)
from src.core.copilot.notification.dispatcher import (
    Channel,
    DispatchResult,
    NotificationDispatcher,
)
from src.core.copilot.notification.ws_pusher import WSPusher

__all__ = [
    "Channel",
    "Digest",
    "DigestGenerator",
    "DigestQueue",
    "DispatchResult",
    "NotificationDispatcher",
    "QueuedSignal",
    "WSPusher",
]
