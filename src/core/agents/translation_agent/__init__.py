"""
Translation Agent Package
Text translation capabilities for Sanskriti Setu platform
ASCII-only compliance enforced
"""

__version__ = "1.0.0"
__agent_id__ = "translation_agent"
__capabilities__ = ["text_translation", "language_processing"]
__supported_task_types__ = ["translate_text"]

from typing import Any

# Re-export for backwards compatibility
from .routes import TaskExecutionRequest, execute_translation_task, router

__all__ = [
    "TaskExecutionRequest",
    "execute_translation_task",
    "router",
]
