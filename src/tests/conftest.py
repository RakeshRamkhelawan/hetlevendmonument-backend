"""
pytest configuration for src/tests

CRITICAL: Load .env file BEFORE any module imports to prevent config validation errors
"""

# Load environment from .env FIRST (before ANY other imports)
import os as _os
from pathlib import Path as _Path

from dotenv import load_dotenv as _load_dotenv

# Find and load .env file
_env_path = _Path(__file__).parent.parent / ".env"
if _env_path.exists():
    _load_dotenv(_env_path, override=False)
else:
    # Fallback to memory database for testing
    _os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Now safe to import other modules
import sys

# Add project root to Python path
project_root = _Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
