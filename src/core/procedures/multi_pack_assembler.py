"""
Slice 1: Multi-Pack Assembler - GREEN Phase Implementation

Assembles execution graphs spanning multiple domain packs for cross-department
workflows (e.g., F2 Hardware Procurement across Finance, Legal, Ops).
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.core.company.context import AgentExecutionContext

from .domain_pack_orchestrator import DomainPackOrchestrator
from .schemas import ExecutionGraph as SegmentExecutionGraph
from .schemas import ExecutionStep, PackSegment


@dataclass
class GraphNode:
    """Legacy graph node shape kept for direct slice tests."""

    node_id: str
    pack_id: UUID
    procedure_id: UUID
    procedure_name: str
    department: str
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


@dataclass
class GraphEdge:
    """Legacy graph edge between two nodes."""

    from_node: str
    to_node: str


@dataclass
class ExecutionGraph:
    """Legacy execution graph with graph algorithms used by older tests."""

    graph_id: UUID
    tenant_id: UUID
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def get_node(self, node_id: str) -> GraphNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(f"Node not found: {node_id}")

    def topological_sort(self) -> list[GraphNode]:
        node_map = {node.node_id: node for node in self.nodes}
        in_degree = {node.node_id: 0 for node in self.nodes}
        adjacency: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}

        for edge in self.edges:
            adjacency.setdefault(edge.from_node, []).append(edge.to_node)
            in_degree[edge.to_node] = in_degree.get(edge.to_node, 0) + 1

        queue = deque(node_id for node_id, degree in in_degree.items() if degree == 0)
        ordered: list[GraphNode] = []

        while queue:
            node_id = queue.popleft()
            ordered.append(node_map[node_id])
            for neighbor in adjacency.get(node_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return ordered if len(ordered) == len(self.nodes) else []

    def validate(self) -> bool:
        if any(node.node_id in node.dependencies for node in self.nodes):
            return False
        return len(self.topological_sort()) == len(self.nodes)


class MultiPackAssembler:
    """
    Assembles execution graphs spanning multiple domain packs
    for cross-department workflows.
    """

    def __init__(self) -> None:
        self._templates = self._initialize_templates()
        self._orchestrator = DomainPackOrchestrator()

    async def assemble(
        self,
        template_id: str,
        intent: str,
        tenant_id: UUID,
    ) -> ExecutionGraph:
        """Build the legacy node/edge graph expected by older slice tests."""
        template = self._templates.get(template_id)
        if template is None:
            raise ValueError(f"Template not found: {template_id}")

        active_packs = self._get_active_packs(tenant_id)
        packs_by_domain = {pack["domain"]: pack for pack in active_packs}

        required_domains = [step["department"] for step in template["workflow"]]
        for domain in required_domains:
            pack = packs_by_domain.get(domain)
            if pack is None:
                raise ValueError(f"Required pack for domain '{domain}' not found")
            if pack.get("status") != "active":
                raise ValueError(f"Pack for domain '{domain}' is inactive")

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        domain_to_node_id: dict[str, str] = {}

        for index, step in enumerate(template["workflow"], start=1):
            domain = step["department"]
            pack = packs_by_domain[domain]
            node_id = f"{domain}_{index}"
            dependencies = [
                domain_to_node_id[dep]
                for dep in step.get("depends_on", [])
                if dep in domain_to_node_id
            ]

            node = GraphNode(
                node_id=node_id,
                pack_id=pack["pack_id"],
                procedure_id=uuid4(),
                procedure_name=step["procedure"],
                department=domain,
                dependencies=dependencies,
                metadata={
                    "context": self._build_context(domain, intent),
                    "original_intent": intent,
                },
            )
            nodes.append(node)
            domain_to_node_id[domain] = node_id

            for dependency in dependencies:
                edges.append(GraphEdge(from_node=dependency, to_node=node_id))

        return ExecutionGraph(
            graph_id=uuid4(),
            tenant_id=tenant_id,
            nodes=nodes,
            edges=edges,
            metadata={
                "template_id": template_id,
                "original_intent": intent,
                "template_name": template["name"],
            },
        )

    async def build_execution_graph(
        self,
        tenant_id: UUID,
        pack_configs: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> SegmentExecutionGraph:
        """
        Build execution graph from pack configurations.

        Args:
            tenant_id: Current tenant ID
            pack_configs: List[Any] of pack configurations with:  # TODO(TYPE): replace Any with concrete type
                - pack_id: UUID
                - domain: str (e.g., 'finance', 'legal')
                - order: int (execution order)
                - name: str (human-readable name)
                - depends_on: Optional[List[str]] (domain dependencies)
                - tenant_id: Optional[UUID] (for validation)

        Returns:
            ExecutionGraph with properly ordered segments

        Raises:
            ValueError: If pack config invalid or missing required fields
        """
        # Validate tenant isolation
        for config in pack_configs:
            if "tenant_id" in config and config["tenant_id"] != tenant_id:
                raise ValueError("Cross-tenant access not allowed")

        # Sort by order
        sorted_configs = sorted(pack_configs, key=lambda x: x.get("order", 999))

        # Build segments
        segments: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        total_duration = 0

        for config in sorted_configs:
            # Extract config fields
            pack_id = config.get("pack_id")
            domain = config.get("domain")
            order = config.get("order")
            name = config.get("name", domain) or ""
            depends_on = config.get("depends_on", [])

            # Validate required fields
            if not pack_id:
                raise ValueError("pack_id is required")
            if not domain:
                raise ValueError("domain is required")
            if order is None:
                raise ValueError("order is required")

            # Generate mock steps (in production, would come from DomainPack)
            steps = [
                ExecutionStep(
                    step_id=f"{domain}_step_1",
                    action=f"Execute {name} procedure",
                    estimated_duration_seconds=120,
                    requires_approval=False,
                    metadata={"domain": domain},
                )
            ]

            # Create segment
            segment = PackSegment(
                pack_id=pack_id,
                domain=domain,
                order=order,
                name=name,
                dependencies=depends_on,
                steps=steps,
                estimated_duration_minutes=2,  # Mock estimate
                requires_approval=False,
            )

            segments.append(segment)
            total_duration += segment.estimated_duration_minutes

        # Create graph
        graph = SegmentExecutionGraph(
            graph_id=uuid4(),
            tenant_id=tenant_id,
            segments=segments,
            estimated_duration_minutes=total_duration,
            created_at=datetime.now(timezone.utc),
        )

        return graph

    async def run_procedure(
        self,
        procedure: Any,  # TODO(TYPE): replace Any with concrete type
        context: AgentExecutionContext,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Execute a procedure with R1 goal alignment enforcement.

        Iterates through all steps in the procedure, validates each step
        against the goal chain using DomainPackOrchestrator, and executes
        only if alignment check passes.

        Args:
            procedure: Procedure object with steps attribute
            context: AgentExecutionContext with goal_chain for validation

        Returns:
            List[Any] of step execution results  # TODO(TYPE): replace Any with concrete type

        Raises:
            GoalMisalignmentError: If any step is misaligned with goal chain
        """
        results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        for step in procedure.steps:
            # R1 ENFORCEMENT: Validate goal alignment before execution
            await self._orchestrator.validate_step(step.action, context)

            # If validation passes, execute the step
            result = await self._execute_step(step, context)
            results.append(result)

        return results

    async def _execute_step(
        self,
        step: Any,  # TODO(TYPE): replace Any with concrete type
        context: AgentExecutionContext,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute a single step and return result.

        Args:
            step: Step object with action, step_id, etc.
            context: AgentExecutionContext

        Returns:
            Dict[Any, ...] with step execution result  # TODO(TYPE): replace Any with concrete type
        """
        # Build execution result with trace context
        trace_context = context.get_trace_context()

        return {
            "step_id": getattr(step, "step_id", str(uuid4())),
            "action": step.action,
            "status": "completed",
            "trace_id": trace_context.get("trace_id"),
            "tenant_id": trace_context.get("tenant_id"),
            "company_id": trace_context.get("company_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _initialize_templates(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Initialize workflow templates"""
        return {
            "f2_hardware_procurement": {
                "name": "Hardware Procurement",
                "departments": ["finance", "legal", "ops"],
                "workflow": [
                    {
                        "department": "finance",
                        "procedure": "budget_check",
                        "depends_on": [],
                    },
                    {
                        "department": "legal",
                        "procedure": "contract_review",
                        "depends_on": ["finance"],
                    },
                    {
                        "department": "ops",
                        "procedure": "procurement",
                        "depends_on": ["finance", "legal"],
                    },
                ],
            },
        }

    def _get_active_packs(self, tenant_id: UUID) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return active pack metadata for legacy assembly mode."""
        return [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "status": "active",
                "tenant_id": tenant_id,
            },
            {
                "pack_id": uuid4(),
                "domain": "legal",
                "status": "active",
                "tenant_id": tenant_id,
            },
            {
                "pack_id": uuid4(),
                "domain": "ops",
                "status": "active",
                "tenant_id": tenant_id,
            },
        ]

    def _build_context(self, domain: str, intent: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create lightweight per-domain context used by legacy tests."""
        return {
            "domain": domain,
            "intent": intent,
            "keywords": [token for token in intent.lower().split() if token],
        }


__all__ = [
    "ExecutionGraph",
    "GraphEdge",
    "GraphNode",
    "MultiPackAssembler",
]
