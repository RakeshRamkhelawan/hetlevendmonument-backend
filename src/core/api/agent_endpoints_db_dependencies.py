"""Database dependency facade for agent_endpoints.py (ADR-033 flat-file patroon)."""

from src.core.database.database import get_db as get_db

__all__ = ["get_db"]
