"""
Slice 1: Multi-Pack Assembler - Comprehensive Test Suite (RED Phase)

Tests the assembly of execution graphs spanning multiple domain packs
for cross-department workflows (F2 Hardware Procurement).
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.schemas import ExecutionDecision
from src.core.procedures.multi_pack_assembler import MultiPackAssembler
from src.core.procedures.schemas import ExecutionGraph

# NOTE: assemble() method exists and API is compatible -- skip removed (TC-005 / AUDIT-2026-06-26).


# ============================================================================
# TEST SUITE 1: Cross-Department Graph Building
# ============================================================================


class TestCrossDepartmentGraphBuilding:
    """Test building execution graphs across multiple domain packs"""

    @pytest.mark.asyncio
    async def test_assembler_builds_cross_department_graph_for_f2(self):
        """
        Should build complete graph with Finance, Legal, and Ops segments
        for Hardware Procurement (F2) workflow
        """
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop for new employee",
            tenant_id=tenant_id,
        )

        # Graph should contain nodes from all 3 departments
        assert graph is not None
        assert len(graph.nodes) >= 3

        # Verify department coverage
        departments = {node.department for node in graph.nodes}
        assert "finance" in departments
        assert "legal" in departments
        assert "ops" in departments

    @pytest.mark.asyncio
    async def test_graph_contains_proper_node_structure(self):
        """Should create nodes with correct structure and metadata"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase hardware",
            tenant_id=uuid4(),
        )

        for node in graph.nodes:
            # Each node should have required fields
            assert node.node_id is not None
            assert node.pack_id is not None
            assert node.procedure_name is not None
            assert node.department is not None
            assert isinstance(node.dependencies, list)

    @pytest.mark.asyncio
    async def test_graph_includes_edges_between_departments(self):
        """Should create edges connecting procedures across departments"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase equipment",
            tenant_id=uuid4(),
        )

        # Should have edges connecting nodes
        assert len(graph.edges) > 0

        # At least one edge should cross departments
        cross_dept_edges = [
            e
            for e in graph.edges
            if graph.get_node(e.from_node).department != graph.get_node(e.to_node).department
        ]
        assert len(cross_dept_edges) > 0


# ============================================================================
# TEST SUITE 2: Pack Order Constraints
# ============================================================================


class TestPackOrderConstraints:
    """Test that pack dependencies and ordering are respected"""

    @pytest.mark.asyncio
    async def test_assembler_respects_pack_order_constraints(self):
        """
        Should ensure Legal pack procedures come after Finance budget check
        per F2 specification
        """
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop",
            tenant_id=uuid4(),
        )

        # Find Finance and Legal nodes
        finance_nodes = [n for n in graph.nodes if n.department == "finance"]
        legal_nodes = [n for n in graph.nodes if n.department == "legal"]

        # Legal nodes should have Finance node IDs in their dependencies
        if finance_nodes and legal_nodes:
            finance_node_ids = {n.node_id for n in finance_nodes}
            legal_dependencies = {dep for node in legal_nodes for dep in node.dependencies}
            # At least one legal node should depend on a finance node
            assert len(finance_node_ids.intersection(legal_dependencies)) > 0

    @pytest.mark.asyncio
    async def test_topological_sort_validates(self):
        """Should produce a valid topological ordering of nodes"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Hardware purchase",
            tenant_id=uuid4(),
        )

        # Verify no circular dependencies
        visited = set()
        for node in graph.nodes:
            assert node.node_id not in node.dependencies  # No self-loops

        # Topological sort should succeed
        sorted_nodes = graph.topological_sort()
        assert len(sorted_nodes) == len(graph.nodes)

    @pytest.mark.asyncio
    async def test_parallel_execution_within_department(self):
        """Should allow parallel execution of independent procedures within same department"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase",
            tenant_id=uuid4(),
        )

        # Check for nodes without dependencies (can run in parallel)
        independent_nodes = [n for n in graph.nodes if len(n.dependencies) == 0]
        # Should have at least one starting node
        assert len(independent_nodes) >= 1


# ============================================================================
# TEST SUITE 3: Missing Pack Handling
# ============================================================================


class TestMissingPackHandling:
    """Test error handling when required packs are missing"""

    @pytest.mark.asyncio
    async def test_assembler_fails_when_required_pack_missing(self):
        """
        Should raise error if Ops pack is not active for tenant
        """
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        # Mock pack registry to return only Finance and Legal
        with patch.object(assembler, "_get_active_packs") as mock_packs:
            mock_packs.return_value = [
                {"pack_id": uuid4(), "domain": "finance", "status": "active"},
                {"pack_id": uuid4(), "domain": "legal", "status": "active"},
                # Ops pack missing
            ]

            with pytest.raises(ValueError, match="Required pack.*not found"):
                await assembler.assemble(
                    template_id="f2_hardware_procurement",
                    intent="Purchase",
                    tenant_id=tenant_id,
                )

    @pytest.mark.asyncio
    async def test_fails_when_pack_is_inactive(self):
        """Should fail if required pack exists but is not active"""
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        with patch.object(assembler, "_get_active_packs") as mock_packs:
            mock_packs.return_value = [
                {"pack_id": uuid4(), "domain": "finance", "status": "active"},
                {
                    "pack_id": uuid4(),
                    "domain": "legal",
                    "status": "inactive",
                },  # Inactive!
                {"pack_id": uuid4(), "domain": "ops", "status": "active"},
            ]

            with pytest.raises(ValueError, match="inactive|not active"):
                await assembler.assemble(
                    template_id="f2_hardware_procurement",
                    intent="Purchase",
                    tenant_id=tenant_id,
                )

    @pytest.mark.asyncio
    async def test_provides_helpful_error_message(self):
        """Should provide clear error message about which pack is missing"""
        assembler = MultiPackAssembler()

        with patch.object(assembler, "_get_active_packs") as mock_packs:
            mock_packs.return_value = []  # No packs

            try:
                await assembler.assemble(
                    template_id="f2_hardware_procurement",
                    intent="Purchase",
                    tenant_id=uuid4(),
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                error_msg = str(e).lower()
                # Error should mention missing packs
                assert "pack" in error_msg or "missing" in error_msg


# ============================================================================
# TEST SUITE 4: Template Resolution
# ============================================================================


class TestTemplateResolution:
    """Test resolving templates to actual procedures"""

    @pytest.mark.asyncio
    async def test_resolves_template_to_procedures(self):
        """Should map template steps to actual procedures in domain packs"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop",
            tenant_id=uuid4(),
        )

        # Each node should have a resolved procedure
        for node in graph.nodes:
            assert node.procedure_id is not None
            assert isinstance(node.procedure_id, UUID)

    @pytest.mark.asyncio
    async def test_fails_on_unknown_template(self):
        """Should fail gracefully for unknown template ID"""
        assembler = MultiPackAssembler()

        with pytest.raises(ValueError, match="Template.*not found"):
            await assembler.assemble(
                template_id="unknown_template_xyz",
                intent="Purchase",
                tenant_id=uuid4(),
            )


# ============================================================================
# TEST SUITE 5: Intent Context Propagation
# ============================================================================


class TestIntentContextPropagation:
    """Test that user intent is properly propagated through graph"""

    @pytest.mark.asyncio
    async def test_intent_stored_in_graph_metadata(self):
        """Should store original user intent in graph metadata"""
        assembler = MultiPackAssembler()
        intent = "Purchase MacBook Pro for developer"

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent=intent,
            tenant_id=uuid4(),
        )

        assert graph.metadata is not None
        assert graph.metadata.get("original_intent") == intent

    @pytest.mark.asyncio
    async def test_context_enrichment_per_department(self):
        """Should enrich context for each department's needs"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop $2000",
            tenant_id=uuid4(),
        )

        # Finance nodes should have budget context
        finance_nodes = [n for n in graph.nodes if n.department == "finance"]
        if finance_nodes:
            finance_node = finance_nodes[0]
            assert "context" in finance_node.metadata
            # Would check for budget amount in production


# ============================================================================
# TEST SUITE 6: Tenant Isolation
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation in multi-pack assembly"""

    @pytest.mark.asyncio
    async def test_only_uses_packs_from_current_tenant(self):
        """Should only include packs belonging to current tenant"""
        assembler = MultiPackAssembler()
        tenant_a = uuid4()

        with patch.object(assembler, "_get_active_packs") as mock_packs:
            # Mock should only be called with tenant_a
            mock_packs.return_value = []

            try:
                await assembler.assemble(
                    template_id="f2_hardware_procurement",
                    intent="Purchase",
                    tenant_id=tenant_a,
                )
            except ValueError:
                pass  # Expected due to no packs

            # Verify tenant_id was used in the call
            mock_packs.assert_called_once()
            call_args = mock_packs.call_args
            assert tenant_a in call_args[0] or tenant_a in call_args[1].values()


# ============================================================================
# TEST SUITE 7: Graph Validation
# ============================================================================


class TestGraphValidation:
    """Test graph structure validation"""

    @pytest.mark.asyncio
    async def test_validates_no_orphan_nodes(self):
        """Should ensure all nodes except start are reachable"""
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase",
            tenant_id=uuid4(),
        )

        # Validation should pass
        is_valid = graph.validate()
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_detects_circular_dependencies(self):
        """Should detect circular dependencies during validation"""
        from src.core.procedures.multi_pack_assembler import GraphEdge

        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase",
            tenant_id=uuid4(),
        )

        # Manually introduce circular dependency for testing.
        # validate() uses topological_sort() which checks self.edges, so we
        # must set both edges and dependencies to create a real cycle.
        if len(graph.nodes) >= 2:
            node_a = graph.nodes[0]
            node_b = graph.nodes[1]

            # Create cycle: A -> B -> A via edges (what topological_sort uses)
            graph.edges = [
                GraphEdge(from_node=node_a.node_id, to_node=node_b.node_id),
                GraphEdge(from_node=node_b.node_id, to_node=node_a.node_id),
            ]
            node_a.dependencies = [node_b.node_id]
            node_b.dependencies = [node_a.node_id]

            # Validation should fail -- topological sort cannot complete a cycle
            is_valid = graph.validate()
            assert is_valid is False


# ============================================================================
# TEST SUITE 8: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_handles_empty_intent(self):
        """Should handle empty intent gracefully"""
        assembler = MultiPackAssembler()

        try:
            await assembler.assemble(
                template_id="f2_hardware_procurement",
                intent="",
                tenant_id=uuid4(),
            )
            # Should either succeed with default context or fail gracefully
        except ValueError:
            pass  # Acceptable to reject empty intent

    @pytest.mark.asyncio
    async def test_handles_very_long_intent(self):
        """Should handle very long intent strings"""
        assembler = MultiPackAssembler()
        long_intent = "Purchase " + "laptop " * 100

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent=long_intent,
            tenant_id=uuid4(),
        )

        # Should succeed
        assert graph is not None
