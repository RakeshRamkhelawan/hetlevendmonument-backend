#!/usr/bin/env python3
"""
Strategy Engine for Sanskriti Setu AI Multi-Agent System
Advanced strategic planning, analysis, and decision-making engine

NOTE: This module now re-exports from src.core.strategy for backward compatibility.
The actual implementation has been refactored into a service-based architecture.
"""

# Re-export all public APIs from the new strategy package

from src.core.strategy.facade import StrategyEngine
from src.core.strategy.factory import (
    TenantContextError,
    develop_comprehensive_strategy,
    get_strategy_engine,
    get_strategy_engine_for_tenant,
    resolve_strategy_engine,
    strategy_engine,
)
from src.core.strategy.llm_client import (
    LLMMessage,
    LLMResponse,
    StrategyLLMClient,
    create_strategy_llm_client,
)
from src.core.strategy.repository import InMemoryStrategyRepository, StrategyRepository
from src.core.strategy.services import (
    AnalysisService,
    InsightService,
    ObjectiveService,
    StrategyDevelopmentService,
)
from src.core.strategy.types import (
    STRATEGY_TEMPLATES,
    StrategicContext,
    StrategicInsight,
    StrategicObjective,
    StrategicPriority,
    StrategyType,
)

__all__ = [
    # Enums and Types
    "StrategyType",
    "StrategicPriority",
    "StrategicObjective",
    "StrategicInsight",
    "StrategicContext",
    "STRATEGY_TEMPLATES",
    # Main Classes
    "StrategyEngine",
    "StrategyDevelopmentService",
    "ObjectiveService",
    "InsightService",
    "AnalysisService",
    "StrategyLLMClient",
    "StrategyRepository",
    "InMemoryStrategyRepository",
    # Factory Functions
    "get_strategy_engine_for_tenant",
    "get_strategy_engine",
    "develop_comprehensive_strategy",
    "resolve_strategy_engine",
    "create_strategy_llm_client",
    # Legacy
    "strategy_engine",
    "LLMMessage",
    "LLMResponse",
    "TenantContextError",
]
