#!/usr/bin/env python3
"""
Specialist Agents - M-MDP Specialized Agent Implementations
(Refactored: Now delegates to individual modules in specialists/)
"""


from .specialists.code_execution_agent import CodeExecutionAgent

# Re-export agents for backward compatibility
from .specialists.data_analysis_agent import DataAnalysisAgent
from .specialists.knowledge_agent import KnowledgeAgent
from .specialists.performance_agent import PerformanceAgent
from .specialists.reporting_agent import ReportingAgent
from .specialists.system_monitor_agent import SystemMonitorAgent

__all__ = [
    "CodeExecutionAgent",
    "DataAnalysisAgent",
    "KnowledgeAgent",
    "PerformanceAgent",
    "ReportingAgent",
    "SystemMonitorAgent",
]
