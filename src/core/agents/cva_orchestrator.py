#!/usr/bin/env python3
"""
CVA Orchestrator - Production-Ready Dynamic Integration
Top-level coordinator for NLP, LLM, and memory layers.
(Delegates to modules in ultimate_cva/)
"""

# Re-export from new structure
from src.core.agents.ultimate_cva.agent import UltimateCVAAgent, create_ultimate_cva_agent
from src.core.agents.ultimate_cva.models import (
    AgentCapabilities,
    CVAMode,
    IntentType,
    ParsedCommand,
    UltimateExecutionResult,
)

# Re-export main class as module level for imports like "from cva_orchestrator import UltimateCVAAgent"
__all__ = [
    "UltimateCVAAgent",
    "create_ultimate_cva_agent",
    "CVAMode",
    "IntentType",
    "ParsedCommand",
    "UltimateExecutionResult",
    "AgentCapabilities",
]
