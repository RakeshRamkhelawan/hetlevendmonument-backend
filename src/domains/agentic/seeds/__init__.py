"""
Agentic Seeds Package

This package contains seed data for the agentic system.
"""

from typing import Any

from .domain_contexts_seed import DOMAIN_CONTEXT_TEMPLATES
from .features_seed import PLATFORM_FEATURES
from .prompt_templates_seed import INITIAL_PROMPT_TEMPLATES
from .tools_seed import TOOL_DEFINITIONS

__all__ = [
    "PLATFORM_FEATURES",
    "TOOL_DEFINITIONS",
    "INITIAL_PROMPT_TEMPLATES",
    "DOMAIN_CONTEXT_TEMPLATES",
]
