"""
Optimized Prompt Templates for Agent Selection.

Provides:
- Structured prompts for agent routing
- Few-shot examples for common tasks
- Domain-specific prompt variations
- Template versioning and A/B testing support
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from jinja2 import Template

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """A versioned prompt template with metadata."""

    name: str
    version: str
    template: str
    description: str = ""
    examples: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    variables: list[str] = field(default_factory=list)

    def render(self, **kwargs: object) -> str:
        """Render the template with variables."""
        t = Template(self.template)
        # str(): jinja2 is voor mypy `Any` (staat in de ignore_missing_imports-lijst in
        # pyproject.toml), dus render() levert geen bewijsbare str op.
        return str(t.render(**kwargs))


class AgentSelectionTemplates:
    """
    Optimized prompt templates for agent selection and routing.

    These templates are designed to:
    - Minimize token usage
    - Maximize routing accuracy
    - Support few-shot learning
    - Handle edge cases
    """

    # --- Core Routing Template -------------------------------------------------

    ROUTING_V2 = PromptTemplate(
        name="agent_routing_v2",
        version="2.1.0",
        description="Optimized agent selection with structured output",
        template="""You are an expert task router. Select the best agent for this task.

TASK: {{ task_title }}
DESCRIPTION: {{ task_description }}
{% if capabilities %}
REQUIRED CAPABILITIES: {{ capabilities | join(', ') }}
{% endif %}

AVAILABLE AGENTS:
{% for agent in agents %}
- {{ agent.id }}: {{ agent.type }}
  Capabilities: {{ agent.capabilities | join(', ') }}
  Description: {{ agent.description }}
{% endfor %}

Analyze the task and select the best agent. Consider:
1. Capability match (most important)
2. Task complexity vs agent expertise
3. Historical performance

Respond with JSON:
{
  "selected_agent": "agent_id",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "fallback_agents": ["agent_id_2", "agent_id_3"]
}""",
        variables=["task_title", "task_description", "capabilities", "agents"],
        examples=[
            {
                "input": {
                    "task_title": "Review Python code",
                    "task_description": "Check for bugs and style issues",
                    "capabilities": ["code_review", "python"],
                },
                "output": {
                    "selected_agent": "code_reviewer_001",
                    "confidence": 0.95,
                    "reasoning": "Direct capability match for Python code review",
                    "fallback_agents": ["general_coder_001"],
                },
            }
        ],
    )

    # --- Few-Shot Routing Template ---------------------------------------------

    ROUTING_FEW_SHOT = PromptTemplate(
        name="agent_routing_few_shot",
        version="1.0.0",
        description="Few-shot routing with examples",
        template="""Route tasks to the most appropriate agent.

EXAMPLES:

Task: "Send email to marketing team"
Capabilities: ["email", "communication"]
Selected: communication_agent_001 (confidence: 0.92)

Task: "Generate quarterly sales report"
Capabilities: ["analytics", "reporting", "sales"]
Selected: sales_analyst_001 (confidence: 0.88)

Task: "Fix bug in authentication middleware"
Capabilities: ["coding", "security", "debugging"]
Selected: security_engineer_001 (confidence: 0.95)

---

NEW TASK: {{ task_title }}
DESCRIPTION: {{ task_description }}
{% if capabilities %}CAPABILITIES: {{ capabilities | join(', ') }}{% endif %}

AVAILABLE AGENTS:
{% for agent in agents %}
{{ loop.index }}. {{ agent.id }} - {{ agent.capabilities | join(', ') }}
{% endfor %}

Respond with JSON:
{
  "selected_agent": "agent_id",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence"
}""",
        variables=["task_title", "task_description", "capabilities", "agents"],
    )

    # --- Workflow Planning Template --------------------------------------------

    WORKFLOW_PLANNING = PromptTemplate(
        name="workflow_planning_v1",
        version="1.2.0",
        description="Decompose high-level goals into subtasks",
        template="""Decompose this goal into sequential subtasks.

GOAL: {{ goal }}
CONTEXT: {{ context }}
CONSTRAINTS: {{ constraints | default('none') }}

Create {{ max_subtasks }} or fewer subtasks that:
1. Are atomic and specific
2. Have clear dependencies
3. Can be assigned to specialized agents
4. Cover the complete goal

Respond with JSON:
{
  "subtasks": [
    {
      "id": "task_1",
      "title": "Clear task name",
      "description": "Specific instructions",
      "required_capabilities": ["cap1", "cap2"],
      "dependencies": [],
      "estimated_duration_minutes": 10
    }
  ],
  "parallelizable": true/false,
  "critical_path": ["task_1", "task_2"]
}""",
        variables=["goal", "context", "constraints", "max_subtasks"],
        examples=[
            {
                "input": {
                    "goal": "Create a marketing campaign",
                    "max_subtasks": 4,
                },
                "output": {
                    "subtasks": [
                        {
                            "id": "task_1",
                            "title": "Research target audience",
                            "description": "Analyze demographics and preferences",
                            "required_capabilities": ["research", "analytics"],
                            "dependencies": [],
                            "estimated_duration_minutes": 30,
                        },
                        {
                            "id": "task_2",
                            "title": "Create campaign content",
                            "description": "Write copy and design assets",
                            "required_capabilities": ["copywriting", "design"],
                            "dependencies": ["task_1"],
                            "estimated_duration_minutes": 60,
                        },
                    ],
                },
            }
        ],
    )

    # --- Capability Extraction Template ----------------------------------------

    CAPABILITY_EXTRACTION = PromptTemplate(
        name="capability_extraction",
        version="1.0.0",
        description="Extract required capabilities from task description",
        template="""Extract required capabilities from this task.

TASK: {{ task_title }}
DESCRIPTION: {{ task_description }}

AVAILABLE CAPABILITIES:
{{ capabilities | join(', ') }}

Instructions:
1. Analyze what skills are needed
2. Match against available capabilities
3. Return 1-5 most relevant capabilities
4. Include confidence score

Respond with JSON:
{
  "required_capabilities": [
    {"capability": "name", "confidence": 0.0-1.0, "reason": "why needed"}
  ],
  "complexity": "simple/medium/complex",
  "estimated_tokens": 100-5000
}""",
        variables=["task_title", "task_description", "capabilities"],
    )

    # --- Critique Template -----------------------------------------------------

    CRITIQUE_V1 = PromptTemplate(
        name="critique_v1",
        version="1.0.0",
        description="Critique agent output quality",
        template="""Critique this agent output for quality issues.

AGENT: {{ agent_name }}
TASK: {{ task_description }}

OUTPUT TO CRITIQUE:
{{ output }}

{% if error %}
ERROR OCCURRED: {{ error }}
{% endif %}

Evaluate on:
1. Completeness (did it address all requirements?)
2. Accuracy (are facts/statements correct?)
3. Format (is output well-structured?)
4. Efficiency (was it done optimally?)

Respond with JSON:
{
  "score": 0.0-1.0,
  "issues": [
    {"severity": "critical/warning/info", "category": "completeness/accuracy/format/performance", "message": "description"}
  ],
  "suggestions": ["improvement 1", "improvement 2"],
  "should_retry": true/false
}""",
        variables=["agent_name", "task_description", "output", "error"],
    )

    # --- Intent Classification Template ----------------------------------------

    INTENT_CLASSIFICATION = PromptTemplate(
        name="intent_classification",
        version="1.0.0",
        description="Classify user intent for routing",
        template="""Classify the user's intent to route to appropriate domain.

USER INPUT: "{{ user_input }}"

INTENT CATEGORIES:
- "technical": Coding, debugging, technical questions
- "analytical": Data analysis, reporting, research
- "creative": Writing, design, content creation
- "administrative": Scheduling, emails, documentation
- "strategic": Planning, decision making, strategy
- "support": Help, troubleshooting, guidance

Respond with JSON:
{
  "primary_intent": "category",
  "confidence": 0.0-1.0,
  "secondary_intents": ["category"],
  "urgency": "low/medium/high",
  "extracted_entities": {"key": "value"}
}""",
        variables=["user_input"],
    )


class PromptOptimizer:
    """
    Optimizes prompts for different scenarios.

    - Reduces token count while maintaining quality
    - Selects best template for task type
    - Handles context window limitations
    """

    def __init__(self) -> None:
        self.templates = AgentSelectionTemplates()
        self._token_estimates: dict[str, int] = {}

    def select_routing_template(
        self,
        agent_count: int,
        use_few_shot: bool = False,
        token_budget: int = 4000,
    ) -> PromptTemplate:
        """Select optimal routing template based on constraints."""

        if use_few_shot and agent_count < 20:
            # Few-shot works better with fewer agents
            return self.templates.ROUTING_FEW_SHOT

        # Default to structured template
        return self.templates.ROUTING_V2

    def optimize_agent_descriptions(
        self,
        agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        max_tokens: int = 2000,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Truncate agent descriptions to fit token budget.
        Preserves most important info (capabilities, type).
        """
        optimized: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        tokens_used = 0
        tokens_per_agent = max_tokens // len(agents) if agents else 0

        for agent in agents:
            # Always include ID and capabilities
            opt_agent = {
                "id": agent["id"],
                "type": agent.get("type", "unknown"),
                "capabilities": agent.get("capabilities", []),
            }

            # Add truncated description if room
            desc = agent.get("description", "")
            max_desc_tokens = tokens_per_agent - 50  # Reserve for other fields
            max_chars = max_desc_tokens * 4  # Rough estimate: 4 chars/token

            if len(desc) > max_chars:
                # Truncate to sentence boundary
                truncated = desc[:max_chars].rsplit(".", 1)[0] + "."
                opt_agent["description"] = truncated
            else:
                opt_agent["description"] = desc

            optimized.append(opt_agent)

        return optimized

    def build_routing_prompt(
        self,
        task_title: str,
        task_description: str,
        agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        capabilities: list[str] | None = None,
        use_few_shot: bool = False,
    ) -> str:
        """Build optimized routing prompt."""

        template = self.select_routing_template(
            agent_count=len(agents),
            use_few_shot=use_few_shot,
        )

        # Optimize agent list for token efficiency
        optimized_agents = self.optimize_agent_descriptions(agents)

        return template.render(
            task_title=task_title,
            task_description=task_description,
            agents=optimized_agents,
            capabilities=capabilities or [],
        )

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars/token average)."""
        return len(text) // 4


# Global template instances
templates = AgentSelectionTemplates()
optimizer = PromptOptimizer()


def get_routing_prompt(
    task_title: str,
    task_description: str,
    agents: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    capabilities: list[str] | None = None,
    use_few_shot: bool = False,
) -> str:
    """Convenience function for building routing prompts."""
    return optimizer.build_routing_prompt(
        task_title=task_title,
        task_description=task_description,
        agents=agents,
        capabilities=capabilities,
        use_few_shot=use_few_shot,
    )


def get_workflow_planning_prompt(goal: str, max_subtasks: int = 6, **kwargs: object) -> str:
    """Convenience function for workflow planning prompts."""
    return templates.WORKFLOW_PLANNING.render(
        goal=goal,
        max_subtasks=max_subtasks,
        **kwargs,
    )


def get_critique_prompt(
    agent_name: str,
    task_description: str,
    output: str,
    error: str | None = None,
) -> str:
    """Convenience function for critique prompts."""
    return templates.CRITIQUE_V1.render(
        agent_name=agent_name,
        task_description=task_description,
        output=output,
        error=error,
    )
