"""Subagents domain dependencies (ADR-033 Laag 1)."""

from src.core.agents.subagent_loader import AgentStatus, SubagentLoader, get_loader  # noqa: F401


def get_subagent_loader() -> SubagentLoader:
    """Return the singleton SubagentLoader instance."""
    return get_loader()


__all__ = ["AgentStatus", "SubagentLoader", "get_loader", "get_subagent_loader"]
