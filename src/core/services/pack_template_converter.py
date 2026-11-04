"""
Pack Template Converter

Converts Domain Pack definitions into React Flow workflow graphs.
Also handles customizing templates based on user requirements.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.procedures.models import DomainPack
from src.domains.flows.models import ReactFlowEdge, ReactFlowGraph, ReactFlowNode

logger = logging.getLogger(__name__)


class NodePosition(BaseModel): # pydantic BaseModel untyped without mypy plugin
    x: float
    y: float


class PackTemplateConverter:
    """
    Converts Domain Packs into editable React Flow workflow templates.

    Each capability in a pack becomes a node in the workflow.
    Dependencies between capabilities become edges.
    """

    # Standard node dimensions
    NODE_WIDTH = 200
    NODE_HEIGHT = 80

    # Layout configuration
    HORIZONTAL_SPACING = 250
    VERTICAL_SPACING = 150
    START_X = 100
    START_Y = 100

    # Department colors for visual distinction
    DEPARTMENT_COLORS = {
        "hr": {"bg": "#3B82F6", "border": "#2563EB"},  # Blue
        "sales": {"bg": "#F59E0B", "border": "#D97706"},  # Amber
        "finance": {"bg": "#10B981", "border": "#059669"},  # Emerald
        "marketing": {"bg": "#EC4899", "border": "#DB2777"},  # Pink
        "it": {"bg": "#8B5CF6", "border": "#7C3AED"},  # Violet
        "operations": {"bg": "#F97316", "border": "#EA580C"},  # Orange
        "legal": {"bg": "#EF4444", "border": "#DC2626"},  # Red
    }

    # Capability type to node type mapping
    CAPABILITY_TO_NODE_TYPE = {
        "trigger": "trigger",
        "action": "action",
        "approval": "decision",
        "condition": "decision",
        "notification": "action",
        "integration": "action",
        "ai_analysis": "action",
        "data_transform": "action",
        "wait": "action",
    }

    # Default icons for capabilities
    CAPABILITY_ICONS = {
        "trigger": "Play",
        "action": "Bot",
        "approval": "CheckCircle",
        "condition": "GitBranch",
        "notification": "Bell",
        "integration": "Plug",
        "ai_analysis": "Brain",
        "data_transform": "Database",
        "wait": "Clock",
        "email": "Mail",
        "form": "FileText",
        "webhook": "Webhook",
        "schedule": "Calendar",
    }

    async def convert_pack_to_flow(
        self, pack: DomainPack, customizations: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Convert a Domain Pack to a React Flow workflow graph
        """
        logger.info(f"Converting pack '{pack.name}' to workflow template")

        nodes: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        edges: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        # Get pack capabilities
        capabilities = pack.capabilities or []

        if not capabilities:
            # Create a basic starter template if no capabilities defined
            logger.warning(f"Pack {pack.name} has no capabilities, creating starter template")
            nodes = self._create_starter_nodes(pack)
            edges = []
        else:
            # Convert capabilities to nodes
            nodes = self._capabilities_to_nodes(capabilities, pack)

            # Create edges between sequential nodes
            edges = self._create_sequential_edges(nodes)

        # Apply customizations if provided
        if customizations:
            nodes = self._apply_customizations(nodes, customizations)

        # Add pack metadata to the graph
        result = {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "source_pack_id": str(pack.id),
                "source_pack_name": pack.name,
                "department": pack.department,
                "version": pack.version,
                "is_template": True,
                "template_customizations": customizations or {},
            },
        }

        logger.info(f"Converted pack to {len(nodes)} nodes, {len(edges)} edges")
        return result

    def _capabilities_to_nodes(
        self, capabilities: list[str], pack: DomainPack
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Convert capability strings to React Flow nodes"""
        nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Get department color
        dept_colors = self.DEPARTMENT_COLORS.get(
            pack.department.lower(),
            {"bg": "#6B7280", "border": "#4B5563"},  # Default gray
        )

        for idx, capability in enumerate(capabilities):
            # Determine node type from capability
            node_type = self._infer_node_type(capability)

            # Determine icon
            icon = self._infer_icon(capability, node_type)

            # Calculate position (horizontal layout)
            position = {"x": self.START_X + (idx * self.HORIZONTAL_SPACING), "y": self.START_Y}

            # Create node
            node = {
                "id": f"node-{idx}-{uuid4().hex[:8]}",
                "type": node_type,
                "position": position,
                "data": {
                    "title": self._format_capability_name(capability),
                    "description": f"{pack.name} - {capability}",
                    "label": self._format_capability_name(capability),
                    "icon": icon,
                    "status": "pending",
                    "config": {},  # Empty config for user to fill
                    "phase": "create",
                    # Pack metadata for reference
                    "_source_pack_id": str(pack.id),
                    "_source_capability": capability,
                },
                "style": {
                    "background": dept_colors["bg"],
                    "borderColor": dept_colors["border"],
                    "borderWidth": 2,
                    "borderRadius": 8,
                },
            }

            nodes.append(node)

        return nodes

    def _create_sequential_edges(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Create edges connecting nodes sequentially"""
        edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i in range(len(nodes) - 1):
            edge = {
                "id": f"edge-{i}-{uuid4().hex[:8]}",
                "source": nodes[i]["id"],
                "target": nodes[i + 1]["id"],
                "type": "smoothstep",
                "animated": True,
                "style": {
                    "stroke": "#6B7280",
                    "strokeWidth": 2,
                },
            }
            edges.append(edge)

        return edges

    def _create_starter_nodes(self, pack: DomainPack) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Create a minimal starter template for packs without capabilities"""
        dept_colors = self.DEPARTMENT_COLORS.get(
            pack.department.lower(), {"bg": "#6B7280", "border": "#4B5563"}
        )

        return [
            {
                "id": f"trigger-{uuid4().hex[:8]}",
                "type": "trigger",
                "position": {"x": self.START_X, "y": self.START_Y},
                "data": {
                    "title": "Start",
                    "description": f"Trigger for {pack.name}",
                    "label": "Start",
                    "icon": "Play",
                    "status": "pending",
                    "phase": "discover",
                    "_source_pack_id": str(pack.id),
                },
                "style": {
                    "background": dept_colors["bg"],
                    "borderColor": dept_colors["border"],
                    "borderWidth": 2,
                },
            },
            {
                "id": f"action-{uuid4().hex[:8]}",
                "type": "action",
                "position": {"x": self.START_X + self.HORIZONTAL_SPACING, "y": self.START_Y},
                "data": {
                    "title": "Action",
                    "description": "Configure your action",
                    "label": "Action",
                    "icon": "Bot",
                    "status": "pending",
                    "phase": "create",
                    "_source_pack_id": str(pack.id),
                },
                "style": {
                    "background": dept_colors["bg"],
                    "borderColor": dept_colors["border"],
                    "borderWidth": 2,
                },
            },
        ]

    def _infer_node_type(self, capability: str) -> str:
        """Infer React Flow node type from capability name"""
        capability_lower = capability.lower()

        # Check for trigger keywords
        if any(
            word in capability_lower for word in ["trigger", "start", "when", "on_", "incoming"]
        ):
            return "trigger"

        # Check for decision/approval keywords
        if any(
            word in capability_lower
            for word in ["approve", "decision", "condition", "if_", "check", "validate"]
        ):
            return "decision"

        # Default to action
        return "action"

    def _infer_icon(self, capability: str, node_type: str) -> str:
        """Infer appropriate icon for capability"""
        capability_lower = capability.lower()

        # Check for specific patterns
        if "email" in capability_lower or "mail" in capability_lower:
            return "Mail"
        if "form" in capability_lower or "input" in capability_lower:
            return "FileText"
        if "webhook" in capability_lower or "api" in capability_lower:
            return "Webhook"
        if (
            "schedule" in capability_lower
            or "cron" in capability_lower
            or "timer" in capability_lower
        ):
            return "Calendar"
        if "notify" in capability_lower or "alert" in capability_lower:
            return "Bell"
        if (
            "database" in capability_lower
            or "store" in capability_lower
            or "save" in capability_lower
        ):
            return "Database"

        # Fall back to node type default
        return self.CAPABILITY_ICONS.get(node_type, "Bot")

    def _format_capability_name(self, capability: str) -> str:
        """Convert capability string to human-readable title"""
        # Replace underscores with spaces
        name = capability.replace("_", " ").replace("-", " ")
        # Capitalize each word
        return name.title()

    def _apply_customizations(
        self, nodes: list[dict[str, Any]], customizations: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Apply user customizations to the template nodes"""
        customized_nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for node in nodes:
            node_id = node["id"]

            # Check if this node has customizations
            if node_id in customizations:
                node_custom = customizations[node_id]

                # Apply title customization
                if "title" in node_custom:
                    node["data"]["title"] = node_custom["title"]
                    node["data"]["label"] = node_custom["title"]

                # Apply description customization
                if "description" in node_custom:
                    node["data"]["description"] = node_custom["description"]

                # Apply config customization
                if "config" in node_custom:
                    node["data"]["config"].update(node_custom["config"])

                # Mark as customized
                node["data"]["_customized"] = True

            customized_nodes.append(node)

        return customized_nodes

    async def customize_template_with_llm(
        self, pack: DomainPack, user_requirements: str, base_template: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Use LLM to customize a pack template based on user requirements
        """
        from src.core.llm.llm_service import get_llm_service

        llm = await get_llm_service()

        system_prompt = f"""You are a Workflow Customization AI.

You have a base workflow template from the "{pack.name}" pack.
The user has specific requirements they want to add or modify.

Your task:
1. Analyze the base template nodes
2. Identify what needs to change based on user requirements
3. Generate customization instructions for each affected node

Base Template:
{json.dumps(base_template, indent=2)}

User Requirements:
{user_requirements}

Output JSON with customization instructions:
{{
  "node_customizations": {{
    "node-id-1": {{
      "title": "New title",
      "description": "New description",
      "config": {{"key": "value"}}
    }}
  }},
  "reasoning": "Explanation of changes"
}}"""

        response = await llm.generate_response(
            prompt=user_requirements,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_requirements},
            ],
            provider=None,
            response_format={"type": "json_object"},
        )

        if not response.get("success"):
            logger.error(f"Template customization failed: {response.get('error')}")
            return base_template

        try:
            content = response.get("content", "")
            customizations = json.loads(content)

            # Apply the LLM-generated customizations
            node_customs = customizations.get("node_customizations", {})
            customized_nodes = self._apply_customizations(base_template["nodes"], node_customs)

            result = {
                "nodes": customized_nodes,
                "edges": base_template["edges"],
                "metadata": {
                    **base_template.get("metadata", {}),
                    "ai_customized": True,
                    "customization_reasoning": customizations.get("reasoning", ""),
                },
            }

            return result

        except Exception as e:
            logger.error(f"Failed to apply AI customizations: {e}")
            return base_template


# Singleton instance
_template_converter: PackTemplateConverter | None = None


async def get_template_converter() -> PackTemplateConverter:
    """Get or create singleton PackTemplateConverter instance"""
    global _template_converter
    if _template_converter is None:
        _template_converter = PackTemplateConverter()
    return _template_converter
