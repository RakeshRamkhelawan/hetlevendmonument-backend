"""Subagents domain schemas (ADR-033 Laag 1)."""

from typing import Any

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """Agent information model."""

    name: str
    type: str
    status: str
    description: str
    capabilities: list[str]
    priority: int
    error: str | None = None


class AgentListResponse(BaseModel):
    """Response model for agent listing."""

    total_agents: int
    agents: list[AgentInfo]
    status_summary: dict[str, int]


class AgentLoadRequest(BaseModel):
    """Request model for loading agents."""

    agent_names: list[str] = Field(..., description="List of agent names to load")
    force_reload: bool = Field(False, description="Force reload if already loaded")


class AgentInstantiateRequest(BaseModel):
    """Request model for instantiating agents."""

    agent_name: str = Field(..., description="Name of the agent to instantiate")
    config: dict[str, Any] = Field(default_factory=dict, description="Agent configuration")


class AgentActionRequest(BaseModel):
    """Request model for agent actions."""

    agent_name: str = Field(..., description="Name of the target agent")
    action: str = Field(..., description="Action to perform")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class LoaderMetrics(BaseModel):
    """Loader metrics model."""

    total_agents: int
    loaded_agents: int
    active_agents: int
    status_distribution: dict[str, int]
    agent_types: list[str]
    loaded_modules: int
