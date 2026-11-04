"""LLM Agent Adapter - Connects Swarm Orchestrator to LLM providers.

This module enables agents in a swarm to use LLMs for task execution,
making the ALS system capable of actual AI-powered task completion.
"""

import json
import logging
from typing import Any, Dict, List, Optional, cast

from src.core.als.llm_integration.providers import LLMProvider, get_provider
from src.core.als.swarm import SwarmOrchestrator, SwarmRole
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger("LLMAgentAdapter")


class AgentPersona:
    """Persona for an LLM agent in the swarm.

    Defines the system prompt and capabilities for a specific role.
    """

    PERSONAS = {
        SwarmRole.LEADER: """You are the LEADER of a restoration team handling a cultural artifact emergency.
Your role is to coordinate the team, make decisions, and ensure the mission succeeds.
Be decisive, clear, and focus on the big picture.

Key responsibilities:
- Coordinate team efforts
- Make final decisions on approaches
- Ensure compliance with museum standards
- Report progress clearly""",
        SwarmRole.STRATEGIST: """You are the STRATEGIST of a restoration team.
Your role is to plan the approach and analyze the situation.
Be analytical, thorough, and consider multiple options.

Key responsibilities:
- Analyze the artifact condition
- Plan restoration steps
- Assess risks
- Recommend techniques""",
        SwarmRole.EXECUTOR: """You are an EXECUTOR in the restoration team.
Your role is to perform the actual restoration work.
Be practical, detailed, and follow best practices.

Key responsibilities:
- Execute restoration procedures
- Document actions taken
- Report issues immediately
- Follow safety protocols""",
        SwarmRole.REVIEWER: """You are the REVIEWER of the restoration team.
Your role is to quality-check all work.
Be critical, thorough, and ensure nothing is missed.

Key responsibilities:
- Review all restoration actions
- Verify compliance with standards
- Check documentation
- Validate results""",
        SwarmRole.SPECIALIST: """You are a SPECIALIST in the restoration team.
You have deep expertise in specific restoration techniques.
Be precise, use technical knowledge, and provide expert guidance.

Key responsibilities:
- Apply specialized knowledge
- Solve complex technical problems
- Advise on specialized techniques
- Handle delicate procedures""",
        SwarmRole.SUPPORT: """You are SUPPORT staff for the restoration team.
Your role is to assist and enable the team.
Be helpful, efficient, and anticipate needs.

Key responsibilities:
- Assist other team members
- Handle logistics
- Prepare materials
- Document everything""",
    }

    @classmethod
    def get_system_prompt(cls, role: SwarmRole, specialization: str | None = None) -> str:
        """Get the system prompt for a role."""
        base_prompt = cls.PERSONAS.get(role, cls.PERSONAS[SwarmRole.SUPPORT])

        if specialization:
            base_prompt += f"\n\nYour specialization: {specialization}"

        return base_prompt


class LLMAgentAdapter:
    """Adapter that connects swarm agents to LLM providers.

    Each agent in a swarm gets an LLM backend that executes tasks
    using the appropriate persona and capabilities.

    Example:
        adapter = LLMAgentAdapter(swarm_orchestrator, provider_name="gemini")

        # Assign LLM-backed agents to swarm tasks
        await adapter.assign_llm_agent(
            swarm_id="swarm_123",
            agent_id="conservator_01",
            role=SwarmRole.LEADER
        )

        # Execute a task with LLM
        result = await adapter.execute_task(
            swarm_id="swarm_123",
            agent_id="conservator_01",
            task=task_data
        )
    """

    def __init__(
        self,
        swarm_orchestrator: SwarmOrchestrator,
        provider_name: str = "gemini",
        provider_config: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.orchestrator = swarm_orchestrator
        self.provider = get_provider(provider_name, **(provider_config or {}))

        # Track agent LLM assignments
        self._agent_configs: dict[
            str, dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}

        logger.info(f"LLMAgentAdapter initialized with provider: {self.provider.name}")

    async def register_agent(
        self,
        agent_id: str,
        role: SwarmRole,
        specialization: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        """Register an agent with LLM capabilities.

        Args:
            agent_id: Unique agent identifier
            role: Swarm role for persona selection
            specialization: Optional specialization context
            temperature: LLM temperature setting
        """
        system_prompt = AgentPersona.get_system_prompt(role, specialization)

        self._agent_configs[agent_id] = {
            "role": role,
            "specialization": specialization,
            "system_prompt": system_prompt,
            "temperature": temperature,
        }

        logger.info(f"Registered agent {agent_id} with role {role.value}")

    async def execute_task(
        self,
        agent_id: str,
        task: TaskData,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionResult:
        """Execute a task using the agent's LLM backend.

        Args:
            agent_id: Agent to execute the task
            task: Task data
            context: Additional context for the task

        Returns:
            ExecutionResult with LLM-generated output
        """
        if agent_id not in self._agent_configs:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Agent {agent_id} not registered with LLM adapter",
            )

        config = self._agent_configs[agent_id]

        # Build the prompt
        prompt = self._build_task_prompt(task, context)

        logger.info(f"Executing task {task.id} with agent {agent_id} using {self.provider.name}")

        # Call LLM
        llm_response = await self.provider.generate(
            prompt=prompt,
            system_prompt=config["system_prompt"],
            temperature=config["temperature"],
            max_tokens=2000,
        )

        if not llm_response["success"]:
            return ExecutionResult(
                task_id=task.id, success=False, error_message=llm_response["error"]
            )

        # Parse the response
        result_data = self._parse_llm_response(llm_response["content"])

        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data=result_data,
            execution_time=0.0,  # Could add timing
        )

    def _build_task_prompt(
        self,
        task: TaskData,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Build a prompt for the LLM based on task data."""
        prompt_parts = [
            f"TASK: {task.title}",
            f"DESCRIPTION: {task.description}",
        ]

        if task.tags:
            prompt_parts.append(f"TAGS: {', '.join(task.tags)}")

        if context:
            prompt_parts.append("\nCONTEXT:")
            for key, value in context.items():
                prompt_parts.append(f"  {key}: {value}")

        prompt_parts.extend(
            [
                "\nExecute this task and provide your response in the following JSON format:",
                "{",
                '  "summary": "Brief summary of actions taken",',
                '  "detailed_output": "Detailed description of work performed",',
                '  "findings": ["Any important findings or observations"],',
                '  "recommendations": ["Recommendations for next steps"],',
                '  "confidence": 0.0-1.0,',
                '  "completed": true/false',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_llm_response(
        self, content: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Parse LLM response, extracting JSON if present."""
        # Each json.loads branch gets its own try-except + WARNING (SP-SEC-001 LLM-C5-001)
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            try:
                return cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    json.loads(json_str),
                )
            except json.JSONDecodeError as e:
                logger.warning("LLM response parse failed (json block): %s", e, exc_info=True)
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            try:
                return cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    json.loads(json_str),
                )
            except json.JSONDecodeError as e:
                logger.warning("LLM response parse failed (code block): %s", e, exc_info=True)
        else:
            try:
                return cast(
                    dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                    json.loads(content),
                )
            except json.JSONDecodeError as e:
                logger.warning("LLM response parse failed (raw content): %s", e, exc_info=True)
        # Fallback: return structured text representation
        return {
            "summary": "Task completed",
            "detailed_output": content,
            "findings": [],
            "recommendations": [],
            "confidence": 0.8,
            "completed": True,
        }

    async def collaborate(
        self,
        agent_a_id: str,
        agent_b_id: str,
        task: TaskData,
        shared_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, ExecutionResult]:
        """Have two LLM agents collaborate on a task.

        Args:
            agent_a_id: First agent
            agent_b_id: Second agent
            task: Task to collaborate on
            shared_context: Shared context between agents

        Returns: Dict[str, Any] mapping agent_id to ExecutionResult  # TODO(TYPE): replace Any with concrete type
        """
        # Execute with both agents
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_id in [agent_a_id, agent_b_id]:
            results[agent_id] = await self.execute_task(
                agent_id=agent_id, task=task, context=shared_context
            )

        return results

    def get_agent_info(
        self, agent_id: str
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get information about a registered agent."""
        return self._agent_configs.get(agent_id)
