"""
Analyzer Agent Implementation (Modular)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.sandbox.sandbox_manager import SandboxManagerFactory
from src.core.shared.interfaces import (
    AgentCapability,
    ExecutionResult,
    SandboxEnvironment,
    TaskData,
)
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel
from src.core.types import AgentType, IsolationLevel

# Modular imports
from .capabilities import get_analyzer_capabilities
from .handlers import (
    general,
    ml,
    pattern,
    predictive,
    preprocessing,
    statistical,
    timeseries,
    visualization,
)

logger = logging.getLogger(__name__)


class AnalyzerAgent(EnhancedBaseAgent):
    """Specialist agent for advanced data processing, analytics, and ML workflows (Modular)"""

    def __init__(self, agent_id: str = "analyzer_agent_001", tenant_id: int = 1) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.SPECIALIST, tenant_id=tenant_id)
        self.specialization = "data_analytics_ml"
        self.analysis_domains = [
            "statistical_analysis",
            "machine_learning",
            "data_preprocessing",
            "pattern_recognition",
            "predictive_modeling",
            "data_visualization",
            "time_series_analysis",
        ]
        self.llm_client: ChatTaalmodel | None = None
        self.sandbox_manager: Any | None = None  # TODO(TYPE): replace Any with concrete type

    async def initialize(self) -> bool:
        """Initialize the analyzer agent"""
        try:
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).
            self.llm_client = TenantTaalmodel(self.tenant_id)
            self.sandbox_manager = SandboxManagerFactory.create_manager(IsolationLevel.CONTAINER)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AnalyzerAgent: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get analyzer agent capabilities"""
        return get_analyzer_capabilities()

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process data analytics and ML tasks via modular handlers"""
        start_time = datetime.now(timezone.utc)
        task_type = task.metadata.get("type", "general_analysis")

        try:
            if task_type == "statistical_analysis":
                result = await statistical.process_statistical_analysis(
                    task, self.llm_client, self._execute_python_analysis
                )
            elif task_type == "machine_learning":
                result = await ml.process_machine_learning(
                    task, self.llm_client, self._execute_python_analysis
                )
            elif task_type == "data_preprocessing":
                result = await preprocessing.process_data_preprocessing(
                    task, self._execute_python_analysis
                )
            elif task_type == "pattern_recognition":
                result = await pattern.process_pattern_recognition(
                    task, self._execute_python_analysis
                )
            elif task_type == "predictive_modeling":
                result = await predictive.process_predictive_modeling(task, self.llm_client)
            elif task_type == "data_visualization":
                result = await visualization.process_data_visualization(
                    task, self._execute_python_analysis
                )
            elif task_type == "time_series_analysis":
                result = await timeseries.process_time_series_analysis(
                    task, self._execute_python_analysis
                )
            elif task_type == "advanced_analytics":
                result = await general.process_advanced_analytics(task, self.llm_client)
            else:
                result = await general.process_general_analysis(task, self.llm_client)

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={"analysis_results": result},
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                logs=[f"Analysis task {task.id} processed by modular AnalyzerAgent"],
            )
        except Exception as e:
            logger.error(f"Error in AnalyzerAgent: {e}")
            return ExecutionResult(task_id=task.id, success=False, error_message=str(e))

    async def _execute_python_analysis(
        self, code: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code in secure sandbox"""
        if not self.sandbox_manager:
            return {"status": "error", "message": "Sandbox not initialized"}

        try:
            env = SandboxEnvironment(isolation_level=IsolationLevel.CONTAINER)
            result = await self.sandbox_manager.run_code(code, "python", env)
            return {
                "status": "success" if result.success else "error",
                "analysis_results": result.stdout,
                "error": result.stderr if not result.success else None,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
