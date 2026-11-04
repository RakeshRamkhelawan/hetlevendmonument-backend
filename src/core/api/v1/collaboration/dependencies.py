"""Collaboration domain dependencies (ADR-033 Laag 1)."""

from src.core.services.collaboration_service import (
    UserPresence as UserPresence,  # noqa: F401
    get_collaboration_manager as get_collaboration_manager,  # noqa: F401
)
