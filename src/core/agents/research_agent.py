"""
Research Agent Implementation
Specialist agent for data analysis, research, and information processing
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.sandbox.sandbox_manager import BaseSandboxManager, SandboxManagerFactory
from src.core.shared.interfaces import (
    AgentCapability,
    ExecutionResult,
    SandboxEnvironment,
    TaskData,
)
from src.core.types import AgentType, IsolationLevel
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel, LLMMessage

logger = logging.getLogger(__name__)


class ResearchAgent(CriticMixin, EnhancedBaseAgent):
    """Specialist agent for research, data analysis, and information processing"""

    def __init__(
        self,
        agent_id: str = "research_agent_001",
        tenant_id: int | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id if tenant_id is not None else 0,
        )
        self.__init_critic__(mode=CriticMode.ADVISORY)

        # Research-specific configuration
        self.specialization = "research_analysis"
        self.research_domains = [
            "data_analysis",
            "market_research",
            "technical_documentation",
            "competitive_analysis",
            "trend_analysis",
            "feasibility_studies",
        ]

        # Initialize LLM client for research tasks
        self.llm_client: ChatTaalmodel | None = None

        # Initialize sandbox for safe code execution
        self.sandbox_manager: BaseSandboxManager | None = None

        logger.info(f"ResearchAgent {agent_id} initialized")

    async def initialize(self) -> bool:
        """Initialize the research agent"""
        try:
            # Initialize LLM client
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).
            self.llm_client = TenantTaalmodel(self.tenant_id)

            # Initialize sandbox manager
            self.sandbox_manager = SandboxManagerFactory.create_manager(IsolationLevel.CONTAINER)

            logger.info(f"ResearchAgent {self.agent_id} fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ResearchAgent {self.agent_id}: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get research agent capabilities"""
        return [
            AgentCapability(
                name="data_analysis",
                description="Analyze datasets and generate insights",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="research_synthesis",
                description="Synthesize research from multiple sources",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="market_research",
                description="Conduct market research and competitive analysis",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="trend_analysis",
                description="Identify and analyze market/technology trends",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="feasibility_analysis",
                description="Assess feasibility of projects and initiatives",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="python_analysis",
                description="Execute Python code for data analysis",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process research-related tasks"""
        start_time = datetime.now(timezone.utc)

        try:
            task_type = task.metadata.get("type", "general_research")

            logger.info(f"ResearchAgent processing task: {task.id} (type: {task_type})")

            # Route to appropriate research method
            if task_type == "data_analysis":
                result = await self._process_data_analysis(task)
            elif task_type == "market_research":
                result = await self._process_market_research(task)
            elif task_type == "trend_analysis":
                result = await self._process_trend_analysis(task)
            elif task_type == "feasibility_study":
                result = await self._process_feasibility_study(task)
            elif task_type == "python_analysis":
                result = await self._process_python_analysis(task)
            else:
                result = await self._process_general_research(task)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "agent_type": "research_agent",
                    "specialization": self.specialization,
                    "analysis_results": result,
                    "domains_utilized": self.research_domains,
                    "methodology": task_type,
                },
                execution_time=execution_time,
                logs=[
                    f"Research task {task.id} processed by ResearchAgent",
                    f"Task type: {task_type}",
                    f"Execution time: {execution_time:.2f}s",
                ],
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"ResearchAgent error processing task {task.id}: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Research processing failed: {e}",
                execution_time=execution_time,
                logs=[f"ResearchAgent error: {e}"],
            )

    async def _process_data_analysis(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process data analysis tasks"""

        # Extract data parameters
        data_source = task.metadata.get("data_source", "provided")
        analysis_type = task.metadata.get("analysis_type", "descriptive")

        if "code" in task.metadata:
            # Execute Python analysis code in sandbox
            return await self._execute_python_analysis(task.metadata["code"])

        # Generate analysis based on task description
        analysis_prompt = f"""
        As a data analysis specialist, analyze the following research request:

        Task: {task.title}
        Description: {task.description}
        Data Source: {data_source}
        Analysis Type: {analysis_type}

        Provide a comprehensive data analysis including:
        1. Key findings and insights
        2. Statistical summary
        3. Trends and patterns identified
        4. Recommendations based on analysis
        5. Data quality assessment

        Format the response as structured JSON with clear categories.
        """

        if self.llm_client is None:
            return {
                "error": "LLM client not initialized",
                "status": "failed",
                "analysis_type": analysis_type,
            }

        messages = [LLMMessage(role="user", content=analysis_prompt)]

        response = await self.llm_client.chat_completion(messages)

        try:
            # Try to parse as JSON
            analysis_result = json.loads(response.content)
        except json.JSONDecodeError:
            # If not JSON, structure the response
            analysis_result = {
                "analysis_type": analysis_type,
                "findings": response.content,
                "methodology": "llm_analysis",
                "confidence_level": 0.85,
                "recommendations": [
                    "Further validation recommended",
                    "Consider additional data sources",
                ],
            }

        return cast(dict[str, Any], analysis_result)  # TODO(TYPE): replace Any with concrete type

    async def _process_market_research(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process market research tasks"""

        market = task.metadata.get("market", "general")
        competitors = task.metadata.get("competitors", [])

        research_prompt = f"""
        Conduct comprehensive market research for:

        Market: {market}
        Task: {task.title}
        Focus: {task.description}
        Competitors: {", ".join(competitors) if competitors else "To be identified"}

        Provide market research including:
        1. Market size and growth potential
        2. Key market segments
        3. Competitive landscape analysis
        4. Market trends and drivers
        5. Opportunities and threats
        6. Strategic recommendations

        Present findings in a structured business format.
        """

        if self.llm_client is None:
            return {
                "error": "LLM client not initialized",
                "status": "failed",
                "market": market,
            }

        messages = [LLMMessage(role="user", content=research_prompt)]
        response = await self.llm_client.chat_completion(messages)

        return {
            "market": market,
            "research_findings": response.content,
            "methodology": "market_analysis",
            "research_date": datetime.now(timezone.utc).isoformat(),
            "confidence_level": 0.80,
            "next_steps": [
                "Validate findings with primary research",
                "Update analysis quarterly",
                "Monitor competitor activities",
            ],
        }

    async def _process_trend_analysis(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process trend analysis tasks"""

        domain = task.metadata.get("domain", "technology")
        timeframe = task.metadata.get("timeframe", "next_2_years")

        trend_prompt = f"""
        Analyze trends in {domain} for the {timeframe}:

        Focus Area: {task.title}
        Analysis Request: {task.description}

        Provide comprehensive trend analysis:
        1. Emerging trends identification
        2. Trend drivers and catalysts
        3. Impact assessment (high/medium/low)
        4. Timeline predictions
        5. Strategic implications
        6. Recommended actions

        Structure the analysis with clear trend categories and priorities.
        """

        if self.llm_client is None:
            return {
                "error": "LLM client not initialized",
                "status": "failed",
                "domain": domain,
            }

        messages = [LLMMessage(role="user", content=trend_prompt)]
        response = await self.llm_client.chat_completion(messages)

        return {
            "domain": domain,
            "timeframe": timeframe,
            "trend_analysis": response.content,
            "methodology": "trend_forecasting",
            "analysis_date": datetime.now(timezone.utc).isoformat(),
            "reliability_score": 0.75,
            "update_frequency": "monthly",
        }

    async def _process_feasibility_study(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process feasibility study tasks"""

        project_type = task.metadata.get("project_type", "general")
        budget_range = task.metadata.get("budget_range", "not_specified")

        feasibility_prompt = f"""
        Conduct a feasibility study for:

        Project: {task.title}
        Description: {task.description}
        Type: {project_type}
        Budget Range: {budget_range}

        Analyze feasibility across key dimensions:
        1. Technical feasibility
        2. Economic feasibility
        3. Operational feasibility
        4. Market feasibility
        5. Risk assessment
        6. Resource requirements
        7. Timeline estimation
        8. Success probability

        Provide clear recommendations: Go/No-Go/Conditional
        """

        if self.llm_client is None:
            return {
                "error": "LLM client not initialized",
                "status": "failed",
                "project_type": project_type,
            }

        messages = [LLMMessage(role="user", content=feasibility_prompt)]
        response = await self.llm_client.chat_completion(messages)

        return {
            "project_type": project_type,
            "feasibility_assessment": response.content,
            "methodology": "multi_criteria_analysis",
            "assessment_date": datetime.now(timezone.utc).isoformat(),
            "confidence_level": 0.82,
            "review_recommendation": "quarterly_update",
        }

    async def _process_python_analysis(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code for data analysis"""

        code = task.metadata.get("code", "")
        if not code:
            return {"error": "No Python code provided for analysis", "status": "failed"}

        return await self._execute_python_analysis(code)

    async def _execute_python_analysis(
        self, code: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute Python analysis code in Docker sandbox"""
        try:
            if not self.sandbox_manager:
                return {"error": "Sandbox manager not initialized", "status": "failed"}

            # Create sandbox for Python analysis
            sandbox_config = SandboxEnvironment(
                isolation_level=IsolationLevel.CONTAINER,
                resource_limits={"memory": "512m", "cpu": "1.0", "timeout": 120},
                allowed_capabilities=["file_read", "file_write", "compute"],
                network_access=False,
            )

            sandbox_id = await self.sandbox_manager.create_sandbox(sandbox_config)

            try:
                # Create analysis task
                analysis_task = TaskData(
                    id=f"research_analysis_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    title="Python Data Analysis",
                    description="Execute research analysis code",
                    metadata={
                        "type": "python_code",
                        "code": f"""
import numpy as np
import pandas as pd
import json
from datetime import datetime, timezone
# Research analysis code
{code}

# Ensure output is JSON serializable
print("ANALYSIS_COMPLETE")
""",
                    },
                )

                # Execute in sandbox
                result = await self.sandbox_manager.execute_in_sandbox(sandbox_id, analysis_task)

                if result.success and result.result_data:
                    output = result.result_data.get("output", "")

                    return {
                        "analysis_results": output,
                        "execution_time": result.execution_time,
                        "status": "success",
                        "sandbox_type": "docker_research",
                        "resource_usage": result.resource_usage,
                    }
                else:
                    return {
                        "error": result.error_message or "Analysis execution failed",
                        "status": "failed",
                        "execution_time": result.execution_time,
                    }

            finally:
                # Clean up sandbox
                await self.sandbox_manager.destroy_sandbox(sandbox_id)

        except Exception as e:
            logger.error(f"Python analysis execution error: {e}")
            return {"error": f"Execution error: {e}", "status": "failed"}

    async def _process_general_research(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process general research tasks"""

        research_prompt = f"""
        Conduct comprehensive research on:

        Topic: {task.title}
        Requirements: {task.description}

        Provide thorough research including:
        1. Executive summary
        2. Key findings
        3. Supporting evidence
        4. Analysis and insights
        5. Conclusions
        6. Recommendations for next steps

        Structure the response professionally for business use.
        """

        if self.llm_client is None:
            return {
                "error": "LLM client not initialized",
                "status": "failed",
                "research_topic": task.title,
            }

        messages = [LLMMessage(role="user", content=research_prompt)]
        response = await self.llm_client.chat_completion(messages)

        return {
            "research_topic": task.title,
            "research_findings": response.content,
            "methodology": "comprehensive_research",
            "completion_date": datetime.now(timezone.utc).isoformat(),
            "quality_score": 0.88,
            "follow_up_recommended": True,
        }


# Factory function
async def create_research_agent(
    agent_id: str | None = None,
    tenant_id: int | None = None,
) -> ResearchAgent:
    """Create and initialize a research agent"""
    if agent_id is None:
        agent_id = f"research_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    agent = ResearchAgent(agent_id, tenant_id=tenant_id)

    # Initialize the agent
    await agent.initialize()

    return agent
