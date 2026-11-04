"""
Configuration module initialization
"""

from typing import Any

from src.core.config.config import Settings, get_settings
from src.core.config.unified_config import UnifiedConfig, get_config

settings = get_settings()

__all__ = ["UnifiedConfig", "get_config", "Settings", "get_settings", "settings"]
