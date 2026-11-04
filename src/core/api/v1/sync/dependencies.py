"""Sync domain dependencies (ADR-033 Laag 1).

Centraliseert forbidden imports uit json_router.py
zodat de router-bestanden geen directe domein-imports meer hebben.

NOTE: snapshot_read_limit en snapshot_write_limit zijn rate-limiter decorators.
Ze worden als @decorator gebruikt in json_router.py. Het is veilig om ze
via deze module te re-exporteren.
"""
from src.core.database.database import db_manager as db_manager, get_db
from src.core.database.redis import get_redis_client
from src.core.governance.models import CollaborationSnapshot
from src.core.governance.rate_limiter import snapshot_read_limit, snapshot_write_limit

__all__ = [
    "db_manager",
    "get_db",
    "get_redis_client",
    "CollaborationSnapshot",
    "snapshot_read_limit",
    "snapshot_write_limit",
]
