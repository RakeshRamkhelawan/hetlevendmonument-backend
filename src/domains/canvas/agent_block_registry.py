"""
Thin wrapper that exposes the AgentBlockRegistry singleton.

The registry itself lives in agent_blocks.py alongside the AgentBlock model.
This module exists so API routers can import the factory without a circular dep.
"""

from src.domains.canvas.agent_blocks import AgentBlockRegistry, agent_block_registry


def get_agent_block_registry() -> AgentBlockRegistry:
    return agent_block_registry
