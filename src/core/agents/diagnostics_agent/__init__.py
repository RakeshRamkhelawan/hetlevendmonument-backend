#!/usr/bin/env python3
"""
DiagnosticsAgent - Fase 5 Implementation
System diagnostics and agent health monitoring
"""

__version__ = "1.0.0"

from typing import Any

# Re-export for backwards compatibility
from .routes import TaskExecutionRequest, execute_diagnostics_task, router

__all__ = ["TaskExecutionRequest", "execute_diagnostics_task", "router"]
