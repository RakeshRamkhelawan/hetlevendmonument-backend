#!/usr/bin/env python3
"""
M-MDP Subagents Module
Specialized agent implementations for distributed intelligence
"""

from typing import Any

from .agent_factory import AgentFactory, create_agent_factory
from .agent_manager import AgentManager, create_agent_manager
from .agent_pool import AgentPool, create_agent_pool
from .specialist_agents import (
    CodeExecutionAgent,
    DataAnalysisAgent,
    KnowledgeAgent,
    PerformanceAgent,
    ReportingAgent,
    SystemMonitorAgent,
)

__all__ = [
    "AgentFactory",
    "create_agent_factory",
    "DataAnalysisAgent",
    "SystemMonitorAgent",
    "CodeExecutionAgent",
    "KnowledgeAgent",
    "ReportingAgent",
    "PerformanceAgent",
    "AgentManager",
    "create_agent_manager",
    "AgentPool",
    "create_agent_pool",
]
