"""
Workflow domain schemas -- moved from src/core/api/workflow_refinement_endpoints.py
to break agent_runtime <-> core_api circular dependency (SP-API-009 Dag 2).
"""

from typing import Any

from pydantic import BaseModel, Field


class WorkflowNode(BaseModel):
    """Workflow node definition"""

    id: str
    name: str
    type: str
    x: float = 0
    y: float = 0
    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class WorkflowEdge(BaseModel):
    """Workflow edge/connection definition"""

    id: str
    source: str
    target: str
    type: str = "smoothstep"


class WorkflowDefinition(BaseModel):
    """Complete workflow definition"""

    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class RefinementSuggestion(BaseModel):
    """A suggested refinement to the workflow"""

    id: str
    type: str = Field(
        ...,
        description="Refinement type: add_node, remove_node, update_node, optimize, etc.",
    )
    title: str = Field(..., description="Short title of the suggestion")
    description: str = Field(..., description="Detailed description")
    reasoning: str = Field("", description="Why this refinement is recommended")
    impact: str = Field("medium", description="Impact level: low, medium, high")
    action_data: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict,
        description="Data needed to apply this refinement",
    )
