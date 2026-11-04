"""Agent configuration management package.

Provides YAML-based agent configuration loading, validation, and caching.

Example:
    >>> from src.core.agents.config import get_config_loader, AgentConfig
    >>> loader = get_config_loader()
    >>> config = loader.load("PythonProAgent")
    >>> print(config.prompts.system_prompt)

    >>> from src.core.agents.config import get_registry
    >>> registry = get_registry()
    >>> config = await registry.get("PythonProAgent")
"""

from typing import Any

from .loader import ConfigLoader, get_config_loader, reset_config_loader
from .models import (
    AgentBehaviour,
    AgentClassification,
    AgentConfig,
    AgentInfo,
    AgentMetadata,
    AgentPrompts,
    AgentStatus,
    AgentTechnical,
    Priority,
    ValidationStatus,
)
from .registry import AgentConfigRegistry, get_registry
from .validator import ConfigValidator, PromptValidator, ValidationResult

__all__ = [
    # Models
    "AgentConfig",
    "AgentInfo",
    "AgentClassification",
    "AgentTechnical",
    "AgentBehaviour",
    "AgentPrompts",
    "AgentMetadata",
    "AgentStatus",
    "ValidationStatus",
    "Priority",
    # Loader
    "ConfigLoader",
    "get_config_loader",
    "reset_config_loader",
    # Registry
    "AgentConfigRegistry",
    "get_registry",
    # Validator
    "ConfigValidator",
    "PromptValidator",
    "ValidationResult",
]

__version__ = "1.0.0"
