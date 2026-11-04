from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CVAMode(Enum):
    """CVA operational modes"""

    REACTIVE = "reactive"
    PROACTIVE = "proactive"
    AUTONOMOUS = "autonomous"
    CEO_MODE = "ceo_mode"


class IntentType(Enum):
    """Enhanced intent classification"""

    SYSTEM_STATUS = "system_status"
    AGENT_MANAGEMENT = "agent_management"
    TASK_MANAGEMENT = "task_management"
    PERFORMANCE_MONITORING = "performance_monitoring"
    SYSTEM_CONTROL = "system_control"
    MULTI_COMMAND = "multi_command"
    STRATEGIC_PLANNING = "strategic_planning"
    CEO_DIRECTIVE = "ceo_directive"
    KNOWLEDGE_QUERY = "knowledge_query"
    DIRECT_QUESTION = "direct_question"
    UNKNOWN = "unknown"
    NAVIGATION = "navigation"
    CREATION = "creation"


@dataclass
class ParsedCommand:
    """Enhanced command parsing structure"""

    original_text: str
    intent: IntentType
    confidence: float
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    suggested_clarification: str | None = None


@dataclass
class AgentCapabilities:
    """Ultimate agent capabilities"""

    natural_language_understanding: bool = True
    proactive_monitoring: bool = True
    circuit_breaker_protection: bool = True
    intelligent_task_routing: bool = True
    multi_command_processing: bool = True
    performance_optimization: bool = True
    predictive_alerting: bool = True
    dynamic_llm_integration: bool = True
    ceo_level_orchestration: bool = True
    function_calling: bool = True


@dataclass
class UltimateExecutionResult:
    """Enhanced execution result with comprehensive analytics"""

    success: bool
    response: Any  # TODO(TYPE): replace Any with concrete type
    confidence: float = 0.0
    execution_time: float = 0.0
    suggestions: list[str] = field(default_factory=list)
    performance_metrics: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    alerts_generated: int = 0
    llm_provider_used: str | None = None
    orchestration_used: bool = False
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        if self.data is None:
            self.data = {}
