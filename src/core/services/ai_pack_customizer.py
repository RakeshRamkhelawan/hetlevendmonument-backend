"""
AI Pack Customizer Service

Uses LLM to automatically customize pack templates based on user requirements.
Can save customized packs to the global repository for reuse.
"""

import json
import logging
from typing import Any, Dict, List, Optional, cast
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.llm.llm_service import LLMService, get_llm_service
from src.core.procedures.models import DomainPack
from src.core.services.pack_template_converter import PackTemplateConverter
from src.domains.flows.models import ReactFlowGraph

logger = logging.getLogger(__name__)


class CustomizationRequest(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Request to customize a pack"""

    original_prompt: str
    user_requirements: str
    pack_template: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    pack_name: str
    department: str


class CustomizationResult(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Result of AI customization"""

    success: bool
    customized_flow: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    changes_made: list[str]
    new_pack_name: str | None = None
    new_pack_description: str | None = None
    suggested_capabilities: list[str]
    suggested_intent_tags: list[str]
    error_message: str | None = None


class AIPackCustomizer:
    """
    Uses LLM to customize pack templates based on specific user requirements.

    Capabilities:
    1. Analyze difference between generic pack and specific requirements
    2. Modify node configurations (titles, descriptions, configs)
    3. Add/remove nodes as needed
    4. Adjust connections
    5. Generate metadata for new pack (name, description, tags)
    """

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm = llm_service
        self._converter = PackTemplateConverter()

    async def _get_llm(self) -> LLMService:
        if not self._llm:
            self._llm = await get_llm_service()
        return self._llm

    async def customize_pack(
        self,
        pack: DomainPack,
        original_prompt: str,
        user_requirements: str,
        save_to_global: bool = False,
        contributed_by: str | None = None,
    ) -> CustomizationResult:
        """
        Customize a pack template based on user requirements

        Args:
            pack: The original Domain Pack
            original_prompt: The original user prompt
            user_requirements: Specific customizations needed
            save_to_global: Whether to save to global repository
            contributed_by: User ID if saving to global

        Returns:
            CustomizationResult with the customized flow
        """
        logger.info(f"Customizing pack '{pack.name}' for requirements: {user_requirements[:50]}...")

        # Get base template
        base_flow = await self._converter.convert_pack_to_flow(pack)

        # Use LLM to customize
        customization = await self._generate_customization(
            original_prompt=original_prompt,
            user_requirements=user_requirements,
            base_template=base_flow,
            pack_name=pack.name,
            department=pack.department,
        )

        if not customization.success:
            return customization

        # Save to global repository if requested
        if save_to_global and customization.success:
            await self._save_to_global_repository(
                customization=customization, source_pack=pack, contributed_by=contributed_by
            )

        return customization

    async def _generate_customization(
        self,
        original_prompt: str,
        user_requirements: str,
        base_template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        pack_name: str,
        department: str,
    ) -> CustomizationResult:
        """Use LLM to generate customization"""

        system_prompt = f"""You are an AI Pack Customizer.

Your task: Customize a workflow template based on specific user requirements.

ORIGINAL PACK: {pack_name}
DEPARTMENT: {department}

BASE TEMPLATE:
{json.dumps(base_template, indent=2)}

ORIGINAL USER REQUEST: {original_prompt}
SPECIFIC CUSTOMIZATIONS NEEDED: {user_requirements}

Your job:
1. Identify what needs to change in the base template
2. Modify node configurations (titles, descriptions, config values)
3. Keep the overall structure but adapt to specific needs
4. Generate new pack metadata (name, description, intent tags)

OUTPUT FORMAT (JSON):
{{
  "customized_nodes": [
    {{
      "id": "original_node_id",
      "changes": {{
        "title": "New title",
        "description": "New description",
        "config": {{"key": "value"}}
      }}
    }}
  ],
  "nodes_to_add": [
    {{
      "type": "action|trigger|decision",
      "title": "Node title",
      "description": "Description",
      "position": {{"x": 100, "y": 100}},
      "config": {{}}
    }}
  ],
  "nodes_to_remove": ["node_id_1", "node_id_2"],
  "changes_made": [
    "Changed email subject to be more personalized",
    "Added delay between steps",
    "Removed approval step per user request"
  ],
  "new_pack_name": "Personalized Lead Nurturing",
  "new_pack_description": "Customized lead nurturing with personalized emails and dynamic scoring",
  "suggested_capabilities": ["personalized_email", "dynamic_scoring", "smart_scheduling"],
  "suggested_intent_tags": ["lead_nurturing", "personalization", "b2b_sales"]
}}"""

        llm = await self._get_llm()

        response = await llm.generate_response(
            prompt=user_requirements,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Customize this pack: {user_requirements}"},
            ],
            provider=None,
            response_format={"type": "json_object"},
        )

        if not response.get("success"):
            return CustomizationResult(
                success=False,
                customized_flow=None,
                changes_made=[],
                suggested_capabilities=[],
                suggested_intent_tags=[],
                error_message=f"LLM customization failed: {response.get('error')}",
            )

        try:
            content = json.loads(response.get("content", ""))

            # Apply customizations to base template
            customized_flow = await self._apply_llm_customizations(base_template, content)

            return CustomizationResult(
                success=True,
                customized_flow=customized_flow,
                changes_made=content.get("changes_made", []),
                new_pack_name=content.get("new_pack_name"),
                new_pack_description=content.get("new_pack_description"),
                suggested_capabilities=content.get("suggested_capabilities", []),
                suggested_intent_tags=content.get("suggested_intent_tags", []),
            )

        except Exception as e:
            logger.error(f"Failed to apply customization: {e}")
            return CustomizationResult(
                success=False,
                customized_flow=None,
                changes_made=[],
                suggested_capabilities=[],
                suggested_intent_tags=[],
                error_message=str(e),
            )

    async def _apply_llm_customizations(
        self,
        base_template: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        customization_spec: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Apply LLM-generated customizations to base template"""

        # Deep copy the template
        customized = json.loads(json.dumps(base_template))
        nodes = customized["nodes"]
        edges = customized["edges"]

        # Apply node changes
        node_changes = {
            c["id"]: c.get("changes", {}) for c in customization_spec.get("customized_nodes", [])
        }

        for node in nodes:
            if node["id"] in node_changes:
                changes = node_changes[node["id"]]
                if "title" in changes:
                    node["data"]["title"] = changes["title"]
                    node["data"]["label"] = changes["title"]
                if "description" in changes:
                    node["data"]["description"] = changes["description"]
                if "config" in changes:
                    node["data"]["config"].update(changes["config"])
                node["data"]["_customized_by_ai"] = True

        # Add new nodes
        nodes_to_add = customization_spec.get("nodes_to_add", [])
        for new_node_spec in nodes_to_add:
            new_node = {
                "id": f"ai_added_{uuid4().hex[:8]}",
                "type": new_node_spec.get("type", "action"),
                "position": new_node_spec.get("position", {"x": 400, "y": 100}),
                "data": {
                    "title": new_node_spec.get("title", "New Step"),
                    "description": new_node_spec.get("description", ""),
                    "icon": "Bot",
                    "status": "pending",
                    "config": new_node_spec.get("config", {}),
                    "_ai_generated": True,
                },
            }
            nodes.append(new_node)

        # Remove nodes
        nodes_to_remove = set(customization_spec.get("nodes_to_remove", []))
        nodes = [n for n in nodes if n["id"] not in nodes_to_remove]

        # Remove edges connected to removed nodes
        edges = [
            e
            for e in edges
            if e["source"] not in nodes_to_remove and e["target"] not in nodes_to_remove
        ]

        customized["nodes"] = nodes
        customized["edges"] = edges
        customized["metadata"]["ai_customized"] = True
        customized["metadata"]["customization_timestamp"] = str(uuid4())

        return cast(dict[str, Any], customized)  # TODO(TYPE): replace Any with concrete type

    async def _save_to_global_repository(
        self,
        customization: CustomizationResult,
        source_pack: DomainPack,
        contributed_by: str | None = None,
    ) -> None:
        """Save customized pack to global repository"""
        # TODO(SP-VOLGENDE): global_pack_repo singleton verwijderd in SP-A02 (2026-05-28).
        # Gebruik GlobalPack ORM model via src.core.governance.models.GlobalPack + db session.
        # Methode is tijdelijk uitgeschakeld totdat de fix geimplementeerd is.
        if not customization.customized_flow:
            return
        logger.warning("_save_customized_to_global not yet migrated to ORM; skipping global save")

    async def generate_pack_from_scratch(
        self,
        prompt: str,
        department: str,
        save_to_global: bool = False,
        contributed_by: str | None = None,
    ) -> CustomizationResult:
        """
        Generate a completely new pack from scratch using AI

        This is used when no existing pack matches the requirements
        """
        logger.info(f"Generating new pack from scratch for: {prompt[:50]}...")

        system_prompt = f"""You are an AI Pack Generator.

Create a new workflow pack from scratch based on user requirements.

USER REQUEST: {prompt}
DEPARTMENT: {department}

Generate:
1. A complete workflow with 3-7 nodes
2. Each node should have: type, title, description, config
3. Connections between nodes
4. Pack metadata (name, description, capabilities, intent tags)

OUTPUT FORMAT (JSON):
{{
  "pack_name": "Descriptive Name",
  "pack_description": "What this pack does",
  "nodes": [
    {{
      "id": "node_1",
      "type": "trigger|action|decision",
      "title": "Node Title",
      "description": "What this node does",
      "position": {{"x": 100, "y": 100}},
      "config": {{}}
    }}
  ],
  "edges": [
    {{"source": "node_1", "target": "node_2"}}
  ],
  "capabilities": ["capability_1", "capability_2"],
  "intent_tags": ["tag1", "tag2", "tag3"]
}}"""

        llm = await self._get_llm()

        response = await llm.generate_response(
            prompt=prompt,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Create a new pack for: {prompt}"},
            ],
            provider=None,
            response_format={"type": "json_object"},
        )

        if not response.get("success"):
            return CustomizationResult(
                success=False,
                customized_flow=None,
                changes_made=[],
                suggested_capabilities=[],
                suggested_intent_tags=[],
                error_message=f"Pack generation failed: {response.get('error')}",
            )

        try:
            content = json.loads(response.get("content", ""))

            # Construct the flow
            flow = {
                "nodes": content.get("nodes", []),
                "edges": content.get("edges", []),
                "metadata": {
                    "ai_generated": True,
                    "source_prompt": prompt,
                    "department": department,
                },
            }

            result = CustomizationResult(
                success=True,
                customized_flow=flow,
                changes_made=["Generated from scratch by AI"],
                new_pack_name=content.get("pack_name"),
                new_pack_description=content.get("pack_description"),
                suggested_capabilities=content.get("capabilities", []),
                suggested_intent_tags=content.get("intent_tags", []),
            )

            # Save to global if requested
            if save_to_global:
                await self._save_generated_to_global(result, department, contributed_by)

            return result

        except Exception as e:
            logger.error(f"Failed to parse generated pack: {e}")
            return CustomizationResult(
                success=False,
                customized_flow=None,
                changes_made=[],
                suggested_capabilities=[],
                suggested_intent_tags=[],
                error_message=str(e),
            )

    async def _save_generated_to_global(
        self, result: CustomizationResult, department: str, contributed_by: str | None
    ) -> None:
        """Save AI-generated pack to global repository"""
        # TODO(SP-VOLGENDE): global_pack_repo singleton verwijderd in SP-A02 (2026-05-28).
        # Gebruik GlobalPack ORM model via src.core.governance.models.GlobalPack + db session.
        # Methode is tijdelijk uitgeschakeld totdat de fix geimplementeerd is.
        if not result.customized_flow:
            return
        logger.warning("_save_generated_to_global not yet migrated to ORM; skipping global save")


# Singleton
_ai_pack_customizer: AIPackCustomizer | None = None


async def get_ai_pack_customizer() -> AIPackCustomizer:
    """Get or create singleton AIPackCustomizer"""
    global _ai_pack_customizer
    if _ai_pack_customizer is None:
        _ai_pack_customizer = AIPackCustomizer()
    return _ai_pack_customizer
