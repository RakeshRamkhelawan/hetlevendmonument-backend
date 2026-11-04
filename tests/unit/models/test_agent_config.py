"""Tests for AgentConfig ORM model."""
import pytest
from datetime import datetime
from src.core.models.agent_config import AgentConfig

def test_agent_config_defaults() -> None:
    cfg = AgentConfig(tenant_id=1, agent_type="email_specialist", agent_id="email-1")
    assert cfg.tenant_id == 1
    assert cfg.agent_type == "email_specialist"
    assert cfg.agent_id == "email-1"
    assert cfg.subscribed_topics == []
    assert cfg.is_active is True
    assert cfg.config_json == {}
    assert cfg.department is None

def test_agent_config_with_topics() -> None:
    cfg = AgentConfig(tenant_id=2, agent_type="hr_agent", agent_id="hr-1", department="hr", subscribed_topics=["user.created", "ticket.assigned"])
    assert cfg.subscribed_topics == ["user.created", "ticket.assigned"]
    assert cfg.department == "hr"

def test_agent_config_json_field() -> None:
    cfg = AgentConfig(tenant_id=1, agent_type="x", agent_id="x-1", config_json={"model": "gpt-4"})
    assert cfg.config_json == {"model": "gpt-4"}
