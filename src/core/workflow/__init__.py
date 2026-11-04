"""
C.7 Production-Ready Workflow Engine
=====================================

Multi-tenant workflow orchestration with DAG execution, state management,
and async task processing.

Core Components:
- models: Database schema (SQLAlchemy 2.0)
- interfaces: Dependency injection abstractions
- state_machine: State transition validation
- engine: Workflow orchestration engine

Usage:
    from src.core.workflow.models import Workflow, WorkflowExecution
    from src.core.workflow.engine import ProductionWorkflowEngine, WorkflowSpec
    from src.core.workflow.interfaces import ILLMProvider, IAgentRuntime

Note: Imports are deferred to prevent config validation errors during pytest collection.
Import explicitly from submodules instead of using this __init__.py
"""

__version__ = "1.0.0"
__author__ = "SanskritiSetu Engineering Team"

# NOTE: Imports commented out to prevent DATABASE_URL validation errors during pytest
# Import directly from submodules instead:
#   from core.workflow.models import Workflow
#   from core.workflow.engine import ProductionWorkflowEngine

from typing import Any

from src.core.workflow.state_machine import WorkflowStateMachine, get_state_machine

__all__ = [
    # State Machine (only actually imported items)
    "WorkflowStateMachine",
    "get_state_machine",
]
