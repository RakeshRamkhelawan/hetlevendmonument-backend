"""Agent configs dependencies -- schemas + helper functions."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentConfigCreateRequest(BaseModel):
    agent_type: str = Field(..., examples=["email_specialist"])
    agent_id: str = Field(..., examples=["email-agent-1"])
    department: str | None = Field(default=None, examples=["hr"])
    department_user_id: int | None = Field(default=None, examples=[42])
    subscribed_topics: list[str] = Field(default_factory=list)
    is_active: bool = Field(default=True)
    config_json: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class AgentConfigUpdateRequest(BaseModel):
    agent_type: str | None = Field(default=None)
    department: str | None = Field(default=None)
    department_user_id: int | None = Field(default=None)
    subscribed_topics: list[str] | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    config_json: dict[str, Any] | None = Field(default=None)  # TODO(TYPE): replace Any with concrete type


class AgentConfigResponse(BaseModel):
    id: int
    tenant_id: int
    agent_type: str
    agent_id: str
    department: str | None
    department_user_id: int | None
    subscribed_topics: list[str]
    is_active: bool
    config_json: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: str | None

    model_config = ConfigDict(from_attributes=True)


class CircuitStatusResponse(BaseModel):
    agent_id: str
    state: str
    failure_threshold: int
    reset_timeout_seconds: int


def _to_response(cfg: Any) -> AgentConfigResponse:  # TODO(TYPE): replace Any with concrete type
    created_at = None
    if cfg.created_at is not None:
        created_at = (
            cfg.created_at.isoformat()
            if hasattr(cfg.created_at, "isoformat")
            else str(cfg.created_at)
        )
    return AgentConfigResponse(
        id=cfg.id,
        tenant_id=cfg.tenant_id,
        agent_type=cfg.agent_type,
        agent_id=cfg.agent_id,
        department=cfg.department,
        department_user_id=getattr(cfg, "department_user_id", None),
        subscribed_topics=list(cfg.subscribed_topics),
        is_active=cfg.is_active,
        config_json=dict(cfg.config_json),
        created_at=created_at,
    )
