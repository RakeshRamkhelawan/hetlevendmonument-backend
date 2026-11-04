"""
Workflow Orchestrator Agent - Agentic Workflow Refinement System
==================================================================

AI-powered agent that analyzes workflows and suggests improvements.

Capabilities:
- Workflow structure analysis using LLM (detect bottlenecks, missing nodes)
- Smart agent assignment recommendations
- Error handling injection with LLM reasoning
- Performance optimization suggestions
- Workflow validation and integrity checking

Uses DeepSeek/OpenAI/Claude LLM to understand user intent and generate actionable improvements.
"""

import json
import logging
import uuid
from typing import Any, cast, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from src.core.workflow.schemas import WorkflowDefinition, RefinementSuggestion

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import LLMMessage

logger = logging.getLogger(__name__)


class WorkflowOrchestratorAgent:
    """
    Agentic orchestrator for workflow analysis and refinement.

    Uses LLM to understand user intent and generate intelligent workflow improvements.
    """

    def __init__(self, tenant_id: int, user_id: int) -> None:
        """
        Initialize the workflow orchestrator agent.

        Het taalmodel is de keuze van de TENANT (ADR-041 B14); er is geen `llm_provider` meer. Hier stond
        `deepseek` als standaard en bij een fout stil een namaakmodel.

        Args:
            tenant_id: Tenant ID for multi-tenant isolation
            user_id: User ID for audit logging
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.conversation_id = str(uuid.uuid4())

        self.llm_client = TenantTaalmodel(tenant_id)
        logger.info(
            "[ROBOT] WorkflowOrchestratorAgent initialized",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": self.conversation_id,
            },
        )

    async def analyze_and_suggest(
        self,
        message: str,
        workflow: "WorkflowDefinition",
    ) -> dict[str, object]:
        """
        Analyze a workflow and generate suggestions based on user message.

        Uses LLM to understand user intent and generate intelligent suggestions.

        Args:
            message: User's request/question about the workflow
            workflow: WorkflowDefinition object with nodes and edges

        Returns: Dictionary with:
            - analysis: AI analysis of the workflow
            - suggestions: List of RefinementSuggestion dicts
            - conversation_id: Conversation tracking ID
        """

        logger.info(
            f"[SEARCH] Analyzing workflow with LLM: {message[:100]}",
            extra={
                "tenant_id": self.tenant_id,
                "nodes": len(workflow.nodes),
                "edges": len(workflow.edges),
            },
        )

        try:
            # Step 1: Build workflow context for LLM
            workflow_context = self._build_workflow_context(workflow)

            # Step 2: Call LLM to analyze and suggest
            suggestions = await self._generate_suggestions_with_llm(
                message=message,
                workflow_context=workflow_context,
            )

            # Step 3: Validate suggestions
            validated_suggestions = self._validate_suggestions(
                suggestions=suggestions,
                workflow=workflow,
            )

            # Step 4: Generate analysis summary
            analysis = self._generate_analysis_summary(
                message=message,
                suggestions=validated_suggestions,
            )

            logger.info(
                f"[OK] Generated {len(validated_suggestions)} suggestions",
                extra={
                    "tenant_id": self.tenant_id,
                    "conversation_id": self.conversation_id,
                },
            )

            return {
                "analysis": analysis,
                "suggestions": validated_suggestions,
                "conversation_id": self.conversation_id,
            }

        except Exception as e:
            logger.error(
                f"[FAIL] Analysis failed: {str(e)}",
                extra={"tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    async def apply_refinement(
        self,
        refinement: "RefinementSuggestion",
        workflow: "WorkflowDefinition",
    ) -> "WorkflowDefinition":
        """
        Apply a refinement suggestion to a workflow.

        Args:
            refinement: RefinementSuggestion object to apply
            workflow: Current WorkflowDefinition

        Returns:
            Updated WorkflowDefinition
        """

        logger.info(
            f"[HAMMER] Applying refinement: {refinement.type}",
            extra={
                "tenant_id": self.tenant_id,
                "refinement_type": refinement.type,
            },
        )

        try:
            # Copy workflow to avoid mutations
            updated_workflow = self._copy_workflow(workflow)

            # Apply the refinement based on type
            if refinement.type == "add_node":
                updated_workflow = self._apply_add_node(updated_workflow, refinement.action_data)

            elif refinement.type == "remove_node":
                updated_workflow = self._apply_remove_node(updated_workflow, refinement.action_data)

            elif refinement.type == "update_node":
                updated_workflow = self._apply_update_node(updated_workflow, refinement.action_data)

            elif refinement.type == "add_edge":
                updated_workflow = self._apply_add_edge(updated_workflow, refinement.action_data)

            elif refinement.type == "optimize":
                updated_workflow = await self._apply_optimization(
                    updated_workflow, refinement.action_data
                )

            # Validate updated workflow
            self._validate_workflow_integrity(updated_workflow)

            logger.info(
                "[OK] Refinement applied successfully",
                extra={
                    "tenant_id": self.tenant_id,
                    "nodes": len(updated_workflow.nodes),
                },
            )

            return updated_workflow

        except Exception as e:
            logger.error(
                f"[FAIL] Refinement failed: {str(e)}",
                extra={"tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _build_workflow_context(self, workflow: "WorkflowDefinition") -> str:
        """Build a human-readable context of the workflow for LLM."""

        nodes_desc: list[str] = []
        for node in workflow.nodes:
            agent_info = node.data.get("agent", "unassigned")
            nodes_desc.append(
                f"  - {node.id}: {node.name} (type: {node.type}, agent: {agent_info})"
            )

        edges_desc: list[str] = []
        for edge in workflow.edges:
            edges_desc.append(f"  - {edge.source} -> {edge.target}")

        return f"""
Workflow Structure:

Nodes ({len(workflow.nodes)} total):
{chr(10).join(nodes_desc) if nodes_desc else "  (No nodes)"}

Connections ({len(workflow.edges)} total):
{chr(10).join(edges_desc) if edges_desc else "  (No connections)"}
"""

    async def _generate_suggestions_with_llm(
        self,
        message: str,
        workflow_context: str,
    ) -> list[dict[str, object]]:
        """
        Call LLM to generate intelligent refinement suggestions.

        Uses prompt engineering to understand user intent and generate
        specific, actionable workflow improvements.
        """

        # Build the prompt
        system_prompt = """You are an expert workflow architect. Analyze the given workflow and user request,
then suggest specific, actionable improvements.

For each suggestion, provide:
1. type: one of [add_node, remove_node, update_node, add_edge, optimize]
2. title: short summary (max 50 chars)
3. description: detailed explanation
4. reasoning: why this improves the workflow
5. impact: low/medium/high
6. action_data: specific parameters to implement

Return ONLY valid JSON array of suggestions."""

        user_prompt = f"""
{workflow_context}

User Request: {message}

Provide up to 3 specific, actionable suggestions to improve this workflow based on the user's request.
Return valid JSON array only, no other text."""

        try:
            # Call LLM
            response = await self.llm_client.async_prompt(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            # Parse response
            content = response.content.strip()

            # Try to extract JSON from response
            json_match = None
            if content.startswith("["):
                json_match = content
            else:
                # Try to find JSON in response
                start_idx = content.find("[")
                end_idx = content.rfind("]") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_match = content[start_idx:end_idx]

            if json_match:
                suggestions = cast(list[dict[str, object]], json.loads(json_match))
                logger.info(f"[OK] LLM generated {len(suggestions)} suggestions")
                return suggestions
            else:
                logger.warning("[WARN]  LLM response didn't contain valid JSON, using fallback")
                return self._fallback_suggestions(message)

        except Exception as e:
            logger.error(
                f"[FAIL] LLM call failed: {str(e)}. Using fallback suggestions.",
                exc_info=True,
            )
            return self._fallback_suggestions(message)

    def _fallback_suggestions(self, message: str) -> list[dict[str, object]]:
        """
        Generate rule-based fallback suggestions if LLM fails.

        Useful for demo/testing when LLM is unavailable.
        """

        suggestions: list[dict[str, object]] = []
        # Analyze message keywords
        keywords = message.lower().split()

        if any(word in keywords for word in ["error", "fail", "robust", "reliable"]):
            suggestions.append(
                {
                    "type": "add_node",
                    "title": "Add error handling node",
                    "description": "Add dedicated error handler to improve reliability",
                    "reasoning": "Workflows need graceful error handling",
                    "impact": "high",
                    "action_data": {
                        "node_name": "Error Handler",
                        "node_type": "process",
                    },
                }
            )

        if any(word in keywords for word in ["timeout", "slow", "fast", "optimize"]):
            suggestions.append(
                {
                    "type": "optimize",
                    "title": "Add operation timeouts",
                    "description": "Prevent hanging operations with timeout limits",
                    "reasoning": "Timeouts improve reliability and resource usage",
                    "impact": "medium",
                    "action_data": {
                        "timeout_seconds": 30,
                    },
                }
            )

        if any(word in keywords for word in ["agent", "assign", "who"]):
            suggestions.append(
                {
                    "type": "update_node",
                    "title": "Optimize agent assignments",
                    "description": "Assign specialized agents for better performance",
                    "reasoning": "Right agent for each task = better results",
                    "impact": "medium",
                    "action_data": {},
                }
            )

        # Default if no keywords matched
        if not suggestions:
            suggestions.append(
                {
                    "type": "add_node",
                    "title": "Add input validation",
                    "description": "Validate inputs before processing",
                    "reasoning": "Prevents downstream errors",
                    "impact": "medium",
                    "action_data": {
                        "node_name": "Input Validator",
                        "node_type": "process",
                    },
                }
            )

        return suggestions

    def _validate_suggestions(
        self,
        suggestions: list[dict[str, object]],
        workflow: "WorkflowDefinition",
    ) -> list[dict[str, object]]:
        """Validate and filter suggestions for feasibility."""

        validated: list[dict[str, object]] = []
        valid_types = ["add_node", "remove_node", "update_node", "add_edge", "optimize"]

        for suggestion in suggestions:
            # Validate structure
            if not isinstance(suggestion, dict):
                continue

            if suggestion.get("type") not in valid_types:
                logger.warning(f"Skipping invalid type: {suggestion.get('type')}")
                continue

            # Ensure required fields
            if not suggestion.get("title") or not suggestion.get("description"):
                continue

            # Set defaults
            if not suggestion.get("action_data"):
                suggestion["action_data"] = {}
            if not suggestion.get("reasoning"):
                suggestion["reasoning"] = ""
            if not suggestion.get("impact"):
                suggestion["impact"] = "medium"

            validated.append(suggestion)

        return validated

    def _generate_analysis_summary(
        self,
        message: str,
        suggestions: list[dict[str, object]],
    ) -> str:
        """Generate a summary analysis of the workflow."""

        summary = f"""
## Workflow Analysis

**Your Request:** {message}

**Findings:**
- Analyzed current workflow structure
- Generated {len(suggestions)} actionable recommendations

**Recommended Improvements:**
"""
        for i, sugg in enumerate(suggestions, 1):
            summary += f"\n{i}. **{sugg.get('title', 'Improvement')}**\n   {sugg.get('description', 'No description')}"

        return summary

    def _apply_add_node(
        self, workflow: "WorkflowDefinition", action_data: dict[str, object]
    ) -> "WorkflowDefinition":
        """Add a new node to the workflow."""

        from src.core.workflow.schemas import WorkflowNode

        node_id = cast(str, action_data.get("node_id", f"node_{len(workflow.nodes) + 1}"))
        node_name = cast(str, action_data.get("node_name", "New Node"))
        node_type = cast(str, action_data.get("node_type", "process"))

        new_node = WorkflowNode(
            id=node_id,
            name=node_name,
            type=node_type,
            x=cast(float, action_data.get("x", 300.0)),
            y=cast(float, action_data.get("y", float(len(workflow.nodes) * 100))),
            data=cast(dict[str, Any], action_data.get("data", {})),  # TODO(TYPE): cast to Any
        )

        workflow.nodes.append(new_node)
        logger.info(f"[OK] Added node: {node_id}")
        return workflow

    def _apply_remove_node(
        self, workflow: "WorkflowDefinition", action_data: dict[str, object]
    ) -> "WorkflowDefinition":
        """Remove a node from the workflow."""

        node_id = action_data.get("node_id")
        if not node_id:
            raise ValueError("node_id required for remove_node")

        workflow.nodes = [n for n in workflow.nodes if n.id != node_id]
        workflow.edges = [e for e in workflow.edges if e.source != node_id and e.target != node_id]

        logger.info(f"[OK] Removed node: {node_id}")
        return workflow

    def _apply_update_node(
        self, workflow: "WorkflowDefinition", action_data: dict[str, object]
    ) -> "WorkflowDefinition":
        """Update a node's properties."""

        node_id = action_data.get("node_id")
        if not node_id:
            raise ValueError("node_id required for update_node")

        for node in workflow.nodes:
            if node.id == node_id:
                if "name" in action_data:
                    node.name = cast(str, action_data["name"])
                if "data" in action_data:
                    node.data.update(
                        cast(dict[str, Any], action_data["data"])
                    )  # TODO(TYPE): cast to Any
                if "type" in action_data:
                    node.type = cast(str, action_data["type"])
                break

        logger.info(f"[OK] Updated node: {node_id}")
        return workflow

    def _apply_add_edge(
        self, workflow: "WorkflowDefinition", action_data: dict[str, object]
    ) -> "WorkflowDefinition":
        """Add a new edge/connection to the workflow."""

        from src.core.workflow.schemas import WorkflowEdge

        source = cast(str, action_data.get("source"))
        target = cast(str, action_data.get("target"))

        if not source or not target:
            raise ValueError("source and target required for add_edge")

        edge_id = f"{source}-{target}"

        if any(e.id == edge_id for e in workflow.edges):
            logger.warning(f"Edge already exists: {edge_id}")
            return workflow

        new_edge = WorkflowEdge(id=edge_id, source=source, target=target, type="smoothstep")

        workflow.edges.append(new_edge)
        logger.info(f"[OK] Added edge: {edge_id}")
        return workflow

    async def _apply_optimization(
        self, workflow: "WorkflowDefinition", action_data: dict[str, object]
    ) -> "WorkflowDefinition":
        """Apply optimization improvements to the workflow."""

        timeout = action_data.get("timeout_seconds", 30)

        for node in workflow.nodes:
            if "timeout" not in node.data:
                node.data["timeout"] = timeout
                logger.info(f"[TIMER]  Added timeout to {node.id}")

        return workflow

    def _validate_workflow_integrity(self, workflow: "WorkflowDefinition") -> None:
        """Validate that the workflow structure is still valid."""

        node_ids = {n.id for n in workflow.nodes}

        for edge in workflow.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"Invalid edge: {edge.source} -> {edge.target} (nodes not found)")

        logger.info("[OK] Workflow integrity validated")

    def _copy_workflow(self, workflow: "WorkflowDefinition") -> "WorkflowDefinition":
        """Create a deep copy of the workflow."""

        from src.core.workflow.schemas import (
            WorkflowDefinition,
            WorkflowEdge,
            WorkflowNode,
        )

        new_nodes = [
            WorkflowNode(
                id=n.id,
                name=n.name,
                type=n.type,
                x=n.x,
                y=n.y,
                data=dict(n.data),
            )
            for n in workflow.nodes
        ]

        new_edges = [
            WorkflowEdge(
                id=e.id,
                source=e.source,
                target=e.target,
                type=e.type,
            )
            for e in workflow.edges
        ]

        return WorkflowDefinition(nodes=new_nodes, edges=new_edges)
