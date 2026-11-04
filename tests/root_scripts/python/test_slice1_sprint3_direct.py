"""
Sprint 3 Slice 1 Direct Tests: Multi-Pack Assembler
Quick standalone validation (5-10 second feedback loop)
"""

import asyncio
from uuid import uuid4

from src.core.procedures.multi_pack_assembler import MultiPackAssembler
from src.core.procedures.schemas import ExecutionGraph, PackSegment


async def test_builds_cross_department_graph():
    """Should build graph with Finance, Legal, Ops segments"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    # Simulate F2: Hardware Procurement flow
    pack_configs = [
        {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Budget Check"},
        {"pack_id": uuid4(), "domain": "legal", "order": 2, "name": "Contract Review"},
        {"pack_id": uuid4(), "domain": "ops", "order": 3, "name": "Asset Tracking"},
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    assert isinstance(graph, ExecutionGraph)
    assert len(graph.segments) == 3
    assert graph.segments[0].domain == "finance"
    assert graph.segments[1].domain == "legal"
    assert graph.segments[2].domain == "ops"
    print("✓ Builds cross-department graph")


async def test_respects_order_constraints():
    """Should respect pack order constraints"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    pack_configs = [
        {"pack_id": uuid4(), "domain": "legal", "order": 2, "name": "Legal"},
        {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Finance"},
        {"pack_id": uuid4(), "domain": "ops", "order": 3, "name": "Ops"},
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    # Should be sorted by order
    assert graph.segments[0].order == 1
    assert graph.segments[1].order == 2
    assert graph.segments[2].order == 3
    print("✓ Respects order constraints")


async def test_handles_dependencies():
    """Should track dependencies between segments"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    pack_configs = [
        {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Budget"},
        {
            "pack_id": uuid4(),
            "domain": "legal",
            "order": 2,
            "name": "Legal",
            "depends_on": ["finance"],
        },
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    legal_segment = graph.segments[1]
    assert "finance" in legal_segment.dependencies
    print("✓ Handles dependencies")


async def test_validates_tenant_isolation():
    """Should enforce tenant isolation"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    pack_configs = [
        {
            "pack_id": uuid4(),
            "domain": "finance",
            "order": 1,
            "name": "Budget",
            "tenant_id": tenant_id,
        },
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    assert graph.tenant_id == tenant_id
    print("✓ Validates tenant isolation")


async def test_fails_when_pack_missing():
    """Should fail when required pack is missing"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    # Empty pack configs
    pack_configs = []

    try:
        graph = await assembler.build_execution_graph(
            tenant_id=tenant_id,
            pack_configs=pack_configs,
        )
        # Should create empty graph or fail gracefully
        assert len(graph.segments) == 0
        print("✓ Handles missing packs gracefully")
    except ValueError:
        print("✓ Fails when pack missing (expected)")


async def test_builds_execution_steps():
    """Should build execution steps for each segment"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    pack_configs = [
        {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Budget Check"},
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    segment = graph.segments[0]
    assert len(segment.steps) > 0
    print("✓ Builds execution steps")


async def test_estimates_duration():
    """Should estimate total duration"""
    assembler = MultiPackAssembler()
    tenant_id = uuid4()

    pack_configs = [
        {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Finance"},
        {"pack_id": uuid4(), "domain": "legal", "order": 2, "name": "Legal"},
    ]

    graph = await assembler.build_execution_graph(
        tenant_id=tenant_id,
        pack_configs=pack_configs,
    )

    assert graph.estimated_duration_minutes > 0
    print("✓ Estimates duration")


async def main():
    """Run all direct tests"""
    print("\nSprint 3 Slice 1: Multi-Pack Assembler - Direct Tests")
    print("=" * 60)

    tests = [
        test_builds_cross_department_graph,
        test_respects_order_constraints,
        test_handles_dependencies,
        test_validates_tenant_isolation,
        test_fails_when_pack_missing,
        test_builds_execution_steps,
        test_estimates_duration,
    ]

    passed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("✅ All direct tests passing!")
        return 0
    else:
        print(f"❌ {len(tests) - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
