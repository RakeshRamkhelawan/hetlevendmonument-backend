"""
Base Department Agent Classes

Provides base classes for the 40 department-level agents:
- DepartmentAgent: Abstract base
- MLAgent: ML-based agents (prediction, classification)
- LLMAgent: LLM-based agents (generation, reasoning)
- VisionAgent: Vision-based agents (image analysis)
"""

import logging
from abc import abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.agents.symbiotic_agent import SymbioticAgent
from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)


class DepartmentType(str, Enum):
    """Department types."""

    UNASSIGNED = "unassigned"
    PRODUCT_INNOVATION = "product_innovation"
    OPERATIONS_SUPPLY_CHAIN = "operations_supply_chain"
    SALES_MARKETING = "sales_marketing"
    FINANCE_TREASURY = "finance_treasury"
    HR_CULTURE = "hr_culture"
    IT_SECURITY = "it_security"
    LEGAL_COMPLIANCE = "legal_compliance"
    CUSTOMER_EXPERIENCE = "customer_experience"
    STRATEGY_BUSINESS = "strategy_business"
    DATA_AI_GOVERNANCE = "data_ai_governance"


class AgentTechnology(str, Enum):
    """Agent technology types."""

    ML = "ml"
    LLM = "llm"
    VISION = "vision"
    HYBRID = "hybrid"


class DepartmentAgent(SymbioticAgent):
    """
    Base class for all department-level agents.

    Extends SymbioticAgent with department-specific functionality.
    All 40 agents inherit from this base.

    Attributes:
        department: Department this agent belongs to
        technology: ML, LLM, or Vision
        priority: critical, high, or medium
    """

    department: DepartmentType
    technology: AgentTechnology
    priority: str = "medium"  # critical, high, medium

    # SP-GOV-ARCH-6 (AUDIT-ARCH-2026-07-02 Dag 3 Groep C): default so subclasses that
    # don't define their own `department_capabilities` class attribute still work.
    # Subclasses set their real capability list as a CLASS attribute (matching the
    # ml_capabilities/llm_capabilities/vision_capabilities pattern already used by
    # MLAgent/LLMAgent/VisionAgent below), NOT as an instance attribute in their own
    # __init__ -- a class attribute is visible via `type(self)` before __init__ runs,
    # so it reaches EnhancedBaseAgent.__init__()'s ai_act_classifier.classify_agent()
    # call in the super().__init__() chain below. An instance attribute set after
    # super().__init__() returns would arrive too late for the classifier to see.
    department_capabilities: list[str] = []

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        # Auto-generate agent_type from class name
        agent_type = self.__class__.__name__.replace("Agent", "").lower()

        # Pass department as string to parent (SymbioticAgent expects string)
        # but preserve our enum attribute
        dept_value = self.department.value if hasattr(self, "department") else "general"

        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            tenant_id=tenant_id,
            department=dept_value,
            capabilities=list(type(self).department_capabilities) or [agent_type],
            **kwargs,
        )

        self.performance_metrics = {
            "tasks_completed": 0,
            "success_rate": 0.0,
            "avg_response_time": 0.0,
        }

        logger.info(
            f"DepartmentAgent {agent_id} initialized "
            f"(dept={dept_value}, tech={self.technology.value})"
        )

    async def observe(
        self, signal: Signal
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Observe: Extract department-specific context."""
        # Use class attributes (enum values)
        dept = (
            self.__class__.department.value if hasattr(self.__class__, "department") else "unknown"
        )
        tech = (
            self.__class__.technology.value if hasattr(self.__class__, "technology") else "unknown"
        )

        return {
            "department": dept,
            "technology": tech,
            "payload": signal.payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @abstractmethod
    async def orient(
        self, observation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Orient: Department-specific analysis."""
        pass

    @abstractmethod
    async def decide(
        self, orientation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Decide: Department-specific decision."""
        pass

    @abstractmethod
    async def act(self, decision: str) -> ExecutionResult:
        """Act: Department-specific execution."""
        pass

    def get_department_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get department-specific statistics."""
        # Use class attributes (enum values)
        dept = (
            self.__class__.department.value if hasattr(self.__class__, "department") else "unknown"
        )
        tech = (
            self.__class__.technology.value if hasattr(self.__class__, "technology") else "unknown"
        )

        return {
            "agent_id": self.agent_id,
            "department": dept,
            "technology": tech,
            "priority": self.priority,
            "capabilities": self.department_capabilities,
            "metrics": self.performance_metrics,
        }

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Execute task using OODA loop.

        This bridges the EnhancedBaseAgent interface with the
        symbiotic OODA loop pattern.
        """
        from src.core.als.infrastructure.signal_bus import Signal

        # Safely extract task attributes with proper type handling
        task_id: str = task.id if hasattr(task, "id") else "unknown"
        # TaskData doesn't have source_agent_id - use task_id as fallback
        source_agent_id: str = task_id
        payload: dict[str, Any] | None = (  # TODO(TYPE): replace Any with concrete type
            task.payload if hasattr(task, "payload") else None
        )  # TODO(TYPE): replace Any with concrete type

        # Convert task to signal
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=source_agent_id,
            target_agent_ids=[self.agent_id],
            tier=SignalTier.COGNITIVE,
            payload=payload if payload is not None else {"data": task},
        )

        # Execute OODA loop
        result = await self.execute_ooda(signal)

        # Ensure task_id is set on result (may be missing from act() implementations)
        if not result.task_id:
            result.task_id = task_id

        return result


class MLAgent(DepartmentAgent):
    """
    Base class for ML-based agents.

    Capabilities: prediction, classification, clustering, forecasting

    Examples:
    - Market Gap Analysis Agent
    - Inventory Forecasting Agent
    - Threat Hunter Agent
    """

    technology = AgentTechnology.ML

    # ML-specific capabilities
    ml_capabilities = [
        "prediction",
        "classification",
        "clustering",
        "forecasting",
        "anomaly_detection",
        "pattern_recognition",
    ]

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)
        self.model_version: str | None = None
        self.training_data_size: int = 0
        self.accuracy: float = 0.0

    async def predict(
        self, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Make prediction using ML model."""
        # Placeholder - actual ML logic in subclasses
        return {"prediction": None, "confidence": 0.0}

    async def classify(
        self, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Classify input data."""
        # Placeholder - actual classification in subclasses
        return "unknown"


class LLMAgent(DepartmentAgent):
    """
    Base class for LLM-based agents.

    Capabilities: generation, analysis, reasoning, synthesis

    Examples:
    - Technical Architect Agent
    - Vendor Negotiation Agent
    - GDPR Privacy Guard Agent
    """

    technology = AgentTechnology.LLM

    # LLM-specific capabilities
    llm_capabilities = [
        "text_generation",
        "analysis",
        "reasoning",
        "synthesis",
        "summarization",
        "question_answering",
    ]

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)
        self.model_name: str = "default"
        self.context_window: int = 4096
        self.temperature: float = 0.7

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Generate text using LLM."""
        # Placeholder - actual LLM logic in subclasses
        return f"Generated response for: {prompt[:50]}..."

    async def analyze(
        self, text: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze text using LLM."""
        # Placeholder - actual analysis in subclasses
        return {"sentiment": "neutral", "keywords": []}


class VisionAgent(MLAgent):
    """
    Base class for Vision-based agents.

    Capabilities: image analysis, pattern recognition, visual synthesis

    Examples:
    - UX/UI Design Synthesizer
    """

    technology = AgentTechnology.VISION

    # Vision-specific capabilities
    vision_capabilities = [
        "image_analysis",
        "pattern_recognition",
        "visual_synthesis",
        "object_detection",
        "style_transfer",
    ]

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)
        self.image_resolution: str = "1024x1024"
        self.color_space: str = "RGB"

    async def analyze_image(
        self, image_data: bytes
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze image using Vision model."""
        # Placeholder - actual vision logic in subclasses
        return {"objects": [], "colors": [], "composition": {}}

    async def generate_design(
        self, requirements: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bytes:  # TODO(TYPE): replace Any with concrete type
        """Generate design using Vision model."""
        # Placeholder - actual generation in subclasses
        return b"mock_image_data"


class HybridAgent(DepartmentAgent):
    """
    Base class for hybrid ML+LLM agents.

    Combines ML prediction with LLM reasoning.

    Examples:
    - Sentiment & Support Agent
    """

    technology = AgentTechnology.HYBRID

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)
        # ML and LLM capabilities are implemented directly in subclasses
        # rather than through separate component instances
        self._ml_capabilities: list[str] = []
        self._llm_capabilities: list[str] = []

    async def ml_predict(
        self, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """ML prediction - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement ml_predict")

    async def llm_generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """LLM generation - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement llm_generate")
