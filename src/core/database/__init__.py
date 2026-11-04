"""Database package exports for backward compatibility."""

import sys
from typing import Any

from .database import Base, get_db

# Backward-compat aliases used by older modules
get_session = get_db
get_database_session = get_db

_module = sys.modules[__name__]
if __name__ == "core.database":
    sys.modules.setdefault("src.core.database", _module)
elif __name__ == "src.core.database":
    sys.modules.setdefault("core.database", _module)

__all__ = ["Base", "get_db", "get_session", "get_database_session"]
