"""Re-exports of cross-module types for use within agent_runtime (ADR-034).

Generated agents import from here instead of directly from src.core.llm,
src.core.shared.interfaces, and src.core.shared.llm_client. This keeps
agent_runtime cross-module fan-out within Grade B budget (SP-DSM-006).
"""

from src.core.llm.agent_model_matcher import (
    AgentCategory as AgentCategory,
    AgentProfile as AgentProfile,
    TaskCharacteristics as TaskCharacteristics,
    TaskComplexity as TaskComplexity,
    agent_model_matcher as agent_model_matcher,
)
from src.core.shared.interfaces import (
    AgentCapability as AgentCapability,
    ExecutionResult as ExecutionResult,
    TaskData as TaskData,
)
from src.core.shared.llm_client import (
    LLMClient as LLMClient,
    LLMProvider as LLMProvider,
    create_llm_client_from_config as create_llm_client_from_config,
    get_default_llm_config as get_default_llm_config,
)

__all__ = [
    "AgentCategory",
    "AgentProfile",
    "TaskCharacteristics",
    "TaskComplexity",
    "agent_model_matcher",
    "AgentCapability",
    "ExecutionResult",
    "TaskData",
    "LLMClient",
    "LLMProvider",
    "create_llm_client_from_config",
    "get_default_llm_config",
]
