"""A2A-compatible Agent Card schema.

Provides a canonical, validated contract for agent identity/capabilities so
all agent families expose a uniform discovery surface.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCardAuth(BaseModel):
    """Authentication metadata for an agent endpoint."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="none", description="none|api_key|oauth2")
    scopes: list[str] = Field(default_factory=list)


class AgentCard(BaseModel):
    """Canonical Agent Card model used for A2A interoperability."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(default="")
    agent_type: str = Field(min_length=1)
    version: str = Field(default="1.0.0")
    capabilities: list[str] = Field(default_factory=list)
    protocols: list[str] = Field(
        default_factory=lambda: ["unified-message-bus-v1"],
        description="Supported communication protocols",
    )
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    endpoint: str | None = None
    authentication: AgentCardAuth = Field(default_factory=AgentCardAuth)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


def build_agent_card(
    *,
    agent_id: str,
    name: str,
    agent_type: str,
    description: str,
    capabilities: list[str],
    endpoint: str | None,
    metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> AgentCard:
    """Build and validate a canonical Agent Card from runtime fields."""
    return AgentCard(
        agent_id=agent_id,
        name=name,
        agent_type=agent_type,
        description=description or "",
        capabilities=capabilities or ["general_assistance"],
        endpoint=endpoint,
        metadata=metadata or {},
    )


def validate_agent_card(data: dict[str, Any]) -> AgentCard:  # TODO(TYPE): replace Any with concrete type
    """Validate raw card payload and return a typed AgentCard."""
    return AgentCard.model_validate(data)
