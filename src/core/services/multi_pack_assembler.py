"""
Multi-Pack Assembler Service

Combines multiple Domain Packs into a single cohesive workflow.
Supports different assembly strategies: sequential, parallel, or conditional.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, cast
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.database.database import db_manager
from src.core.procedures.domain_pack_repository import DomainPackRepository
from src.core.procedures.models import DomainPack
from src.core.services.pack_template_converter import PackTemplateConverter

logger = logging.getLogger(__name__)


class AssemblyStrategy(str, Enum):
    """Strategy for combining multiple packs"""

    SEQUENTIAL = "sequential"  # Pack A -> Pack B -> Pack C
    PARALLEL = "parallel"  # All packs run simultaneously
    CONDITIONAL = "conditional"  # Based on conditions


@dataclass
class PackAssemblyResult:
    """Result of assembling multiple packs"""

    success: bool
    nodes: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    edges: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    assembly_log: list[str]
    error_message: str | None = None
    combined_capabilities: list[str] | None = None


class PackCompatibility(BaseModel):  # pydantic BaseModel untyped without mypy plugin
    """Compatibility analysis between two packs"""

    pack_a_id: str
    pack_b_id: str
    compatible: bool
    shared_inputs: list[str]
    shared_outputs: list[str]
    conflicts: list[str]
    suggested_connections: list[dict[str, str]]


class MultiPackAssembler:
    """
    Assembles multiple Domain Packs into a single workflow.

    Capabilities:
    - Sequential: Chain packs together (e.g., HR Onboarding -> IT Setup)
    - Parallel: Run packs simultaneously (e.g., Sales + Marketing actions)
    - Conditional: Branch based on conditions (e.g., if approved, do Pack B)
    """

    def __init__(self) -> None:
        self._converter = PackTemplateConverter()
        self._pack_repo: DomainPackRepository | None = None

    async def _get_pack_repo(self) -> DomainPackRepository:
        if not self._pack_repo:
            async with db_manager.get_session() as session:
                self._pack_repo = DomainPackRepository(session)
        return self._pack_repo

    async def assemble_packs(
        self,
        tenant_id: int,
        pack_ids: list[str],
        strategy: AssemblyStrategy = AssemblyStrategy.SEQUENTIAL,
        custom_connections: list[dict[str, str]] | None = None,
        condition: str | None = None,
    ) -> PackAssemblyResult:
        """
        Assemble multiple packs into a single workflow

        Args:
            tenant_id: The tenant ID
            pack_ids: List[Any] of pack IDs to assemble  # TODO(TYPE): replace Any with concrete type
            strategy: How to combine the packs
            custom_connections: Optional custom connections between packs
            condition: Condition for conditional strategy

        Returns:
            PackAssemblyResult with combined workflow
        """
        if len(pack_ids) < 2:
            return PackAssemblyResult(
                success=False,
                nodes=[],
                edges=[],
                assembly_log=["Need at least 2 packs to assemble"],
                error_message="Need at least 2 packs to assemble",
            )

        logger.info(f"Assembling {len(pack_ids)} packs with strategy {strategy}")

        # Load all packs
        packs = await self._load_packs(tenant_id, pack_ids)
        if len(packs) != len(pack_ids):
            missing = set(pack_ids) - {str(p.id) for p in packs}
            return PackAssemblyResult(
                success=False,
                nodes=[],
                edges=[],
                assembly_log=[f"Could not find packs: {missing}"],
                error_message=f"Could not find all packs. Missing: {missing}",
            )

        # Check compatibility
        compatibility_log: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i in range(len(packs) - 1):
            compat = await self._check_compatibility(packs[i], packs[i + 1])
            compatibility_log.append(
                f"{packs[i].name} -> {packs[i + 1].name}: "
                f"{'Compatible' if compat.compatible else 'Incompatible'}"
            )
            if not compat.compatible:
                logger.warning(f"Pack compatibility issue: {packs[i].name} and {packs[i + 1].name}")

        # Assemble based on strategy
        if strategy == AssemblyStrategy.SEQUENTIAL:
            return await self._assemble_sequential(packs, custom_connections)
        elif strategy == AssemblyStrategy.PARALLEL:
            return await self._assemble_parallel(packs)
        elif strategy == AssemblyStrategy.CONDITIONAL:
            return await self._assemble_conditional(packs, condition)
        else:
            return PackAssemblyResult(
                success=False,
                nodes=[],
                edges=[],
                assembly_log=["Unknown assembly strategy"],
                error_message="Unknown assembly strategy",
            )

    async def _load_packs(self, tenant_id: int, pack_ids: list[str]) -> list[DomainPack]:
        """Load packs from repository"""
        pack_repo = await self._get_pack_repo()
        packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pack_id in pack_ids:
            pack = await pack_repo.get_by_id(UUID(str(tenant_id)), UUID(pack_id))  # type: ignore[arg-type]
            if pack:
                packs.append(pack)
            else:
                logger.warning(f"Pack {pack_id} not found for tenant {tenant_id}")

        return packs

    async def _assemble_sequential(
        self, packs: list[DomainPack], custom_connections: list[dict[str, str]] | None = None
    ) -> PackAssemblyResult:
        """
        Assemble packs sequentially: Pack A -> Pack B -> Pack C

        The output of Pack A connects to the input of Pack B, etc.
        """
        all_nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        all_edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        assembly_log = [f"Sequential assembly of {len(packs)} packs"]
        combined_capabilities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        x_offset = 100
        y_offset = 100
        horizontal_spacing = 300

        previous_pack_last_node_id = None

        for idx, pack in enumerate(packs):
            # Convert pack to flow
            flow = await self._converter.convert_pack_to_flow(pack)
            pack_nodes = flow["nodes"]
            pack_edges = flow["edges"]

            # Offset positions based on pack index
            for node in pack_nodes:
                node["position"]["x"] += x_offset + (idx * horizontal_spacing)
                node["position"]["y"] += y_offset
                # Add pack prefix to node ID to avoid conflicts
                old_id = node["id"]
                new_id = f"{pack.id}_{old_id}"
                node["id"] = new_id

                # Update edges to use new IDs
                for edge in pack_edges:
                    if edge["source"] == old_id:
                        edge["source"] = new_id
                    if edge["target"] == old_id:
                        edge["target"] = new_id

            all_nodes.extend(pack_nodes)
            all_edges.extend(pack_edges)
            combined_capabilities.extend(pack.capabilities or [])

            # Connect to previous pack
            if previous_pack_last_node_id and pack_nodes:
                # Find the first node of this pack (usually the trigger)
                first_node_id = pack_nodes[0]["id"]

                connection = {
                    "id": f"bridge_{idx}_{pack.id}",
                    "source": previous_pack_last_node_id,
                    "target": first_node_id,
                    "type": "smoothstep",
                    "animated": True,
                    "label": "next",
                    "style": {"stroke": "#8B5CF6", "strokeWidth": 2, "strokeDasharray": "5,5"},
                }
                all_edges.append(connection)
                assembly_log.append(f"Connected {packs[idx - 1].name} to {pack.name}")

            # Remember last node for next connection
            if pack_nodes:
                # Find the last node (no outgoing edges)
                outgoing = {e["source"] for e in pack_edges}
                all_node_ids = {n["id"] for n in pack_nodes}
                terminal_nodes = all_node_ids - outgoing
                if terminal_nodes:
                    previous_pack_last_node_id = list(terminal_nodes)[0]
                else:
                    previous_pack_last_node_id = pack_nodes[-1]["id"]

        return PackAssemblyResult(
            success=True,
            nodes=all_nodes,
            edges=all_edges,
            assembly_log=assembly_log,
            combined_capabilities=combined_capabilities,
        )

    async def _assemble_parallel(self, packs: list[DomainPack]) -> PackAssemblyResult:
        """
        Assemble packs in parallel: All packs run simultaneously

        Adds a trigger node that fans out to all packs
        """
        all_nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        all_edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        assembly_log = [f"Parallel assembly of {len(packs)} packs"]
        combined_capabilities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Create a master trigger node
        trigger_id = "parallel_trigger"
        trigger_node = {
            "id": trigger_id,
            "type": "trigger",
            "position": {"x": 100, "y": 250},
            "data": {
                "title": "Start Parallel Execution",
                "description": f"Triggers {len(packs)} workflows simultaneously",
                "icon": "Play",
                "status": "pending",
            },
        }
        all_nodes.append(trigger_node)

        # Position each pack vertically
        y_offset = 100
        vertical_spacing = 150
        x_position = 400

        for idx, pack in enumerate(packs):
            # Convert pack to flow
            flow = await self._converter.convert_pack_to_flow(pack)
            pack_nodes = flow["nodes"]
            pack_edges = flow["edges"]

            # Offset positions
            for node in pack_nodes:
                node["position"]["x"] = x_position
                node["position"]["y"] += y_offset + (idx * vertical_spacing)

                # Add pack prefix
                old_id = node["id"]
                new_id = f"{pack.id}_{old_id}"
                node["id"] = new_id

                for edge in pack_edges:
                    if edge["source"] == old_id:
                        edge["source"] = new_id
                    if edge["target"] == old_id:
                        edge["target"] = new_id

            # Connect trigger to first node of this pack
            if pack_nodes:
                connection = {
                    "id": f"parallel_conn_{idx}",
                    "source": trigger_id,
                    "target": pack_nodes[0]["id"],
                    "type": "smoothstep",
                    "animated": True,
                    "style": {"stroke": "#10B981", "strokeWidth": 2},
                }
                all_edges.append(connection)

            all_nodes.extend(pack_nodes)
            all_edges.extend(pack_edges)
            combined_capabilities.extend(pack.capabilities or [])
            assembly_log.append(f"Added {pack.name} as parallel branch")

        return PackAssemblyResult(
            success=True,
            nodes=all_nodes,
            edges=all_edges,
            assembly_log=assembly_log,
            combined_capabilities=combined_capabilities,
        )

    async def _assemble_conditional(
        self, packs: list[DomainPack], condition: str | None = None
    ) -> PackAssemblyResult:
        """
        Assemble packs with conditional branching

        Pack A runs first, then based on condition:
        - True -> Pack B
        - False -> Pack C
        """
        if len(packs) != 2:
            return PackAssemblyResult(
                success=False,
                nodes=[],
                edges=[],
                assembly_log=["Conditional assembly requires exactly 2 packs"],
                error_message="Conditional assembly requires exactly 2 packs",
            )

        all_nodes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        all_edges: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        assembly_log = [f"Conditional assembly with condition: {condition}"]
        combined_capabilities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Pack 1 is the decision maker
        pack1_flow = await self._converter.convert_pack_to_flow(packs[0])
        pack1_nodes = pack1_flow["nodes"]
        pack1_edges = pack1_flow["edges"]

        # Add pack prefix
        for node in pack1_nodes:
            old_id = node["id"]
            new_id = f"pack1_{old_id}"
            node["id"] = new_id
            for edge in pack1_edges:
                if edge["source"] == old_id:
                    edge["source"] = new_id
                if edge["target"] == old_id:
                    edge["target"] = new_id

        all_nodes.extend(pack1_nodes)
        all_edges.extend(pack1_edges)
        combined_capabilities.extend(packs[0].capabilities or [])

        # Add decision node after Pack 1
        decision_id = "conditional_decision"
        # Find last node of pack 1
        outgoing = {e["source"] for e in pack1_edges}
        all_p1_ids = {n["id"] for n in pack1_nodes}
        terminal_p1 = list(all_p1_ids - outgoing)

        decision_node = {
            "id": decision_id,
            "type": "decision",
            "position": {"x": 500, "y": 200},
            "data": {
                "title": "Decision",
                "description": condition or "Check condition",
                "icon": "GitBranch",
                "status": "pending",
                "condition": condition,
            },
        }
        all_nodes.append(decision_node)

        # Connect pack 1 to decision
        if terminal_p1:
            all_edges.append(
                {
                    "id": "p1_to_decision",
                    "source": terminal_p1[0],
                    "target": decision_id,
                    "type": "smoothstep",
                }
            )

        # Pack 2 is the "true" branch (lower position)
        pack2_flow = await self._converter.convert_pack_to_flow(packs[1])
        pack2_nodes = pack2_flow["nodes"]
        pack2_edges = pack2_flow["edges"]

        for node in pack2_nodes:
            old_id = node["id"]
            new_id = f"pack2_{old_id}"
            node["id"] = new_id
            node["position"]["x"] += 600
            node["position"]["y"] += 300  # Lower branch
            for edge in pack2_edges:
                if edge["source"] == old_id:
                    edge["source"] = new_id
                if edge["target"] == old_id:
                    edge["target"] = new_id

        all_nodes.extend(pack2_nodes)
        all_edges.extend(pack2_edges)
        combined_capabilities.extend(packs[1].capabilities or [])

        # Connect decision to pack 2 (true branch)
        if pack2_nodes:
            all_edges.append(
                {
                    "id": "decision_true",
                    "source": decision_id,
                    "target": pack2_nodes[0]["id"],
                    "type": "smoothstep",
                    "label": "Yes",
                    "style": {"stroke": "#10B981", "strokeWidth": 2},
                }
            )

        assembly_log.append(f"Added conditional branch: {packs[1].name}")

        return PackAssemblyResult(
            success=True,
            nodes=all_nodes,
            edges=all_edges,
            assembly_log=assembly_log,
            combined_capabilities=combined_capabilities,
        )

    async def _check_compatibility(
        self, pack_a: DomainPack, pack_b: DomainPack
    ) -> PackCompatibility:
        """
        Check if two packs are compatible for sequential assembly
        """
        a_outputs = set(pack_a.output_contracts.keys())
        b_inputs = set(pack_b.input_contracts.keys())

        shared_outputs_inputs = a_outputs & b_inputs

        # Check for conflicts
        conflicts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for key in a_outputs:
            if key in b_inputs:
                a_type = pack_a.output_contracts[key].get("type")
                b_type = pack_b.input_contracts[key].get("type")
                if a_type and b_type and a_type != b_type:
                    conflicts.append(f"Type mismatch for {key}: {a_type} vs {b_type}")

        # Suggest connections
        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for shared in shared_outputs_inputs:
            suggestions.append(
                {
                    "from": f"{pack_a.name}.{shared}",
                    "to": f"{pack_b.name}.{shared}",
                    "field": shared,
                }
            )

        return PackCompatibility(
            pack_a_id=str(pack_a.id),
            pack_b_id=str(pack_b.id),
            compatible=len(conflicts) == 0,
            shared_inputs=list(b_inputs),
            shared_outputs=list(a_outputs),
            conflicts=conflicts,
            suggested_connections=suggestions,
        )

    async def suggest_multi_pack_combinations(
        self, tenant_id: int, prompt: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Suggest pack combinations based on user prompt

        Uses LLM to identify which packs work well together
        """
        from src.core.llm.llm_service import get_llm_service

        # Get available packs
        pack_repo = await self._get_pack_repo()
        packs = await pack_repo.list_by_tenant(UUID(str(tenant_id)))  # type: ignore[arg-type]

        if len(packs) < 2:
            return []

        # Build context for LLM
        packs_context = [
            {
                "id": str(p.id),
                "name": p.name,
                "department": p.department,
                "capabilities": p.capabilities or [],
            }
            for p in packs
        ]

        system_prompt = f"""You are a Pack Combination Advisor.

Available packs:
{json.dumps(packs_context, indent=2)}

User request: "{prompt}"

Suggest 1-3 combinations of packs that would work well together.
Consider:
- Department synergies (e.g., HR + IT for onboarding)
- Sequential workflows (output of A -> input of B)
- Common business processes

Output JSON:
{{
  "suggestions": [
    {{
      "pack_ids": ["id1", "id2"],
      "strategy": "sequential",
      "reasoning": "Why these packs work together",
      "use_case": "Brief description"
    }}
  ]
}}"""

        llm = await get_llm_service()
        response = await llm.generate_response(
            prompt=prompt,
            messages=[{"role": "system", "content": system_prompt}],
            provider=None,
            response_format={"type": "json_object"},
        )

        if not response.get("success"):
            return []

        try:
            content = json.loads(response.get("content", ""))
            return cast(
                list[dict[str, Any]], content.get("suggestions", [])
            )  # TODO(TYPE): replace Any with concrete type
        except Exception as e:
            logger.error(f"Failed to parse multi-pack suggestions: {e}")
            return []


# Singleton
_multi_pack_assembler: MultiPackAssembler | None = None


async def get_multi_pack_assembler() -> MultiPackAssembler:
    """Get or create singleton MultiPackAssembler"""
    global _multi_pack_assembler
    if _multi_pack_assembler is None:
        _multi_pack_assembler = MultiPackAssembler()
    return _multi_pack_assembler
