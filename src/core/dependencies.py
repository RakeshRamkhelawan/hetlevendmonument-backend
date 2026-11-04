"""Shared FastAPI Dependencies.

Lazy imports break the infra <-> agent_runtime circular dependency.
"""

from typing import TYPE_CHECKING, cast

from fastapi import Request

if TYPE_CHECKING:
    from src.core.agents.agent_registry import AgentRegistry
    from src.core.autonomy.autonomous_agent import AutonomousAgent
    from src.core.collaboration.task_distributor import TaskDistributor


def get_autonomous_agent_dependency(request: Request) -> "AutonomousAgent":
    return cast("AutonomousAgent", request.app.state.autonomous_agent)


def get_task_distributor(request: Request) -> "TaskDistributor":
    # Lazy init: create TaskDistributor on first request if not set during lifespan
    if not hasattr(request.app.state, "task_distributor"):
        from src.core.collaboration.task_distributor import TaskDistributor

        request.app.state.task_distributor = TaskDistributor()
    return cast("TaskDistributor", request.app.state.task_distributor)


def get_agent_registry(request: Request) -> "AgentRegistry":
    # Lazy init: create AgentRegistry on first request if not set during lifespan
    if not hasattr(request.app.state, "agent_registry"):
        from src.core.agents.agent_registry import AgentRegistry

        request.app.state.agent_registry = AgentRegistry()
    return cast("AgentRegistry", request.app.state.agent_registry)
