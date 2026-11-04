"""
Sprint 3 Slice 1: Multi-Pack Assembler - Direct Tests

Quick validation script for rapid feedback during development.
Run this with: python test_slice_s3_1_direct.py
"""

import asyncio
import sys
from uuid import uuid4

# Add src to path for direct execution
sys.path.insert(0, "src")

from src.core.procedures.multi_pack_assembler import ExecutionGraph, GraphNode, MultiPackAssembler


def print_result(test_name: str, passed: bool, error: str = ""):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {test_name}")
    if error:
        print(f"    Error: {error}")


async def test_assembler_creates_graph():
    """Should create execution graph for F2 template"""
    try:
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop for new employee",
            tenant_id=tenant_id,
        )

        assert graph is not None
        assert isinstance(graph, ExecutionGraph)
        assert len(graph.nodes) > 0

        print_result("assembler_creates_graph", True)
        return True
    except Exception as e:
        print_result("assembler_creates_graph", False, str(e))
        return False


async def test_graph_contains_three_departments():
    """Should have nodes from Finance, Legal, and Ops"""
    try:
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase hardware",
            tenant_id=uuid4(),
        )

        departments = {node.department for node in graph.nodes}

        assert "finance" in departments
        assert "legal" in departments
        assert "ops" in departments

        print_result("graph_contains_three_departments", True)
        return True
    except Exception as e:
        print_result("graph_contains_three_departments", False, str(e))
        return False


async def test_legal_depends_on_finance():
    """Should enforce Legal comes after Finance"""
    try:
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase laptop",
            tenant_id=uuid4(),
        )

        finance_nodes = [n for n in graph.nodes if n.department == "finance"]
        legal_nodes = [n for n in graph.nodes if n.department == "legal"]

        assert len(finance_nodes) > 0
        assert len(legal_nodes) > 0

        # Legal should depend on Finance
        finance_node_ids = {n.node_id for n in finance_nodes}
        legal_has_finance_dep = any(
            dep in finance_node_ids for legal_node in legal_nodes for dep in legal_node.dependencies
        )

        assert legal_has_finance_dep, "Legal should depend on Finance"

        print_result("legal_depends_on_finance", True)
        return True
    except Exception as e:
        print_result("legal_depends_on_finance", False, str(e))
        return False


async def test_fails_on_unknown_template():
    """Should raise ValueError for unknown template"""
    try:
        assembler = MultiPackAssembler()

        try:
            await assembler.assemble(
                template_id="unknown_template_xyz",
                intent="Purchase",
                tenant_id=uuid4(),
            )
            print_result("fails_on_unknown_template", False, "Should have raised ValueError")
            return False
        except ValueError:
            # Expected
            print_result("fails_on_unknown_template", True)
            return True

    except Exception as e:
        print_result("fails_on_unknown_template", False, str(e))
        return False


async def test_intent_stored_in_metadata():
    """Should store original intent in graph metadata"""
    try:
        assembler = MultiPackAssembler()
        intent = "Purchase MacBook Pro for developer"

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent=intent,
            tenant_id=uuid4(),
        )

        assert graph.metadata is not None
        assert graph.metadata.get("original_intent") == intent

        print_result("intent_stored_in_metadata", True)
        return True
    except Exception as e:
        print_result("intent_stored_in_metadata", False, str(e))
        return False


async def test_topological_sort_works():
    """Should produce valid topological ordering"""
    try:
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Hardware purchase",
            tenant_id=uuid4(),
        )

        sorted_nodes = graph.topological_sort()

        assert len(sorted_nodes) == len(graph.nodes)

        # Finance should come before Legal in sorted order
        finance_idx = next(
            (i for i, n in enumerate(sorted_nodes) if n.department == "finance"), None
        )
        legal_idx = next((i for i, n in enumerate(sorted_nodes) if n.department == "legal"), None)

        if finance_idx is not None and legal_idx is not None:
            assert finance_idx < legal_idx, "Finance should come before Legal"

        print_result("topological_sort_works", True)
        return True
    except Exception as e:
        print_result("topological_sort_works", False, str(e))
        return False


async def test_graph_validation_passes():
    """Should validate graph has no cycles"""
    try:
        assembler = MultiPackAssembler()

        graph = await assembler.assemble(
            template_id="f2_hardware_procurement",
            intent="Purchase",
            tenant_id=uuid4(),
        )

        is_valid = graph.validate()

        assert is_valid is True

        print_result("graph_validation_passes", True)
        return True
    except Exception as e:
        print_result("graph_validation_passes", False, str(e))
        return False


async def test_context_enrichment():
    """Should enrich context for department needs"""
    try:
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
            # Check metadata exists and has context
            assert isinstance(finance_node.metadata["context"], dict)

        print_result("context_enrichment", True)
        return True
    except Exception as e:
        print_result("context_enrichment", False, str(e))
        return False


async def main():
    """Run all direct tests"""
    print()
    print("Sprint 3 Slice 1: Multi-Pack Assembler - Direct Tests")
    print("=" * 50)

    tests = [
        test_assembler_creates_graph,
        test_graph_contains_three_departments,
        test_legal_depends_on_finance,
        test_fails_on_unknown_template,
        test_intent_stored_in_metadata,
        test_topological_sort_works,
        test_graph_validation_passes,
        test_context_enrichment,
    ]

    results = []
    for test in tests:
        result = await test()
        results.append(result)

    print()
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
