#!/usr/bin/env python3
"""
Ethical Reasoning System - TASK-119
(Refactored: Now delegates to modules in src/core/agents/ethical/)
"""


from src.core.agents.ethical.engine import EthicalReasoningSystem
from src.core.agents.ethical.models import (
    EthicalDilemma,
    EthicalFramework,
    EthicalRule,
    LogicalOperator,
    LogicalStatement,
    ReasoningChain,
)

__all__ = [
    "EthicalReasoningSystem",
    "EthicalFramework",
    "LogicalOperator",
    "EthicalRule",
    "LogicalStatement",
    "ReasoningChain",
    "EthicalDilemma",
]
