#!/usr/bin/env python3
"""
Analyzer Agent Implementation
(Refactored: Now delegates to modules in src/core/agents/analyzer/)
"""


# Re-export from new structure
from src.core.agents.analyzer.agent import AnalyzerAgent


def create_analyzer_agent(agent_id: str = "analyzer_agent_001") -> AnalyzerAgent:
    """Factory function for AnalyzerAgent"""
    return AnalyzerAgent(agent_id=agent_id)


__all__ = ["AnalyzerAgent", "create_analyzer_agent"]
