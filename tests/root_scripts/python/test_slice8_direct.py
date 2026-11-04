"""
Slice 8 Direct Tests: AgentRegistry
Quick standalone validation (5-10 second feedback loop)
"""

import asyncio
from uuid import uuid4

from src.core.agents.capabilities.agent_registry import AgentRegistry
from src.core.agents.capabilities.schemas import AgentRegistration, AgentStatus


async def test_registers_and_retrieves_agent():
    """Should register and retrieve an agent"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register
    reg = AgentRegistration(
        agent_type="planner",
        agent_name="PlannerAgent",
        version="1.0.0",
        capabilities=["planning", "orchestration"],
        tenant_id=tenant_id,
        description="Test planner",
    )
    result = await registry.register_agent(reg)

    # Verify registration
    assert result.agent_id is not None
    assert result.agent_type == "planner"
    assert result.status == AgentStatus.ACTIVE

    # Retrieve
    agent = await registry.get_agent(result.agent_id, tenant_id)
    assert agent is not None
    assert agent.agent_id == result.agent_id
    print("✓ Agent registration and retrieval")


async def test_finds_by_capability():
    """Should find agents by capability"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register executor
    reg = AgentRegistration(
        agent_type="executor",
        agent_name="ExecutorAgent",
        version="1.0.0",
        capabilities=["execution", "retry"],
        tenant_id=tenant_id,
    )
    await registry.register_agent(reg)

    # Find by capability
    agents = await registry.find_agents_by_capability("execution", tenant_id)

    assert len(agents) > 0
    assert all("execution" in a.capabilities for a in agents)
    print("✓ Capability-based discovery")


async def test_tenant_isolation():
    """Should enforce tenant isolation"""
    registry = AgentRegistry()
    tenant_a = uuid4()
    tenant_b = uuid4()

    # Register for tenant A
    reg = AgentRegistration(
        agent_type="compliance",
        agent_name="ComplianceAgent",
        version="1.0.0",
        capabilities=["compliance"],
        tenant_id=tenant_a,
    )
    registered = await registry.register_agent(reg)

    # Try to access from tenant B
    agent = await registry.get_agent(registered.agent_id, tenant_b)

    assert agent is None
    print("✓ Tenant isolation enforced")


async def test_lists_all_agents():
    """Should list all agents for tenant"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register 3 agents
    for i in range(3):
        reg = AgentRegistration(
            agent_type=f"type_{i}",
            agent_name=f"Agent{i}",
            version="1.0.0",
            capabilities=["test"],
            tenant_id=tenant_id,
        )
        await registry.register_agent(reg)

    # List all
    agents = await registry.list_agents(tenant_id)

    assert len(agents) == 3
    print("✓ Agent listing")


async def test_status_updates():
    """Should update agent status"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register
    reg = AgentRegistration(
        agent_type="retriever",
        agent_name="RetrieverAgent",
        version="1.0.0",
        capabilities=["retrieval"],
        tenant_id=tenant_id,
    )
    registered = await registry.register_agent(reg)

    # Update status
    updated = await registry.update_agent_status(
        registered.agent_id,
        AgentStatus.INACTIVE,
        tenant_id,
    )

    assert updated.status == AgentStatus.INACTIVE
    print("✓ Status updates")


async def test_filters_by_status():
    """Should filter agents by status"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register and mark inactive
    reg = AgentRegistration(
        agent_type="test",
        agent_name="TestAgent",
        version="1.0.0",
        capabilities=["test"],
        tenant_id=tenant_id,
    )
    registered = await registry.register_agent(reg)
    await registry.update_agent_status(
        registered.agent_id,
        AgentStatus.INACTIVE,
        tenant_id,
    )

    # Get only active
    active = await registry.list_agents(tenant_id, status_filter=AgentStatus.ACTIVE)

    # Inactive agent should not appear
    assert registered.agent_id not in [a.agent_id for a in active]
    print("✓ Status filtering")


async def test_multiple_versions():
    """Should support multiple versions of same agent"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register v1
    reg_v1 = AgentRegistration(
        agent_type="planner",
        agent_name="PlannerAgent",
        version="1.0.0",
        capabilities=["planning"],
        tenant_id=tenant_id,
    )
    await registry.register_agent(reg_v1)

    # Register v2
    reg_v2 = AgentRegistration(
        agent_type="planner",
        agent_name="PlannerAgent",
        version="2.0.0",
        capabilities=["planning", "advanced"],
        tenant_id=tenant_id,
    )
    await registry.register_agent(reg_v2)

    # Both should exist
    agents = await registry.find_agents_by_type("planner", tenant_id)
    versions = [a.version for a in agents]

    assert "1.0.0" in versions
    assert "2.0.0" in versions
    print("✓ Multiple agent versions")


async def test_unregisters_agent():
    """Should unregister an agent"""
    registry = AgentRegistry()
    tenant_id = uuid4()

    # Register
    reg = AgentRegistration(
        agent_type="executor",
        agent_name="ExecutorAgent",
        version="1.0.0",
        capabilities=["execution"],
        tenant_id=tenant_id,
    )
    registered = await registry.register_agent(reg)

    # Unregister
    success = await registry.unregister_agent(registered.agent_id, tenant_id)
    assert success is True

    # Should not be retrievable
    agent = await registry.get_agent(registered.agent_id, tenant_id)
    assert agent is None
    print("✓ Agent unregistration")


async def test_prevents_cross_tenant_unregistration():
    """Should prevent cross-tenant unregistration"""
    registry = AgentRegistry()
    tenant_a = uuid4()
    tenant_b = uuid4()

    # Register for tenant A
    reg = AgentRegistration(
        agent_type="planner",
        agent_name="PlannerAgent",
        version="1.0.0",
        capabilities=["planning"],
        tenant_id=tenant_a,
    )
    registered = await registry.register_agent(reg)

    # Try to unregister from tenant B
    success = await registry.unregister_agent(registered.agent_id, tenant_b)

    assert success is False
    print("✓ Cross-tenant unregistration prevented")


async def test_validation():
    """Should validate required fields"""
    registry = AgentRegistry()

    # Empty agent_type
    try:
        reg = AgentRegistration(
            agent_type="",
            agent_name="Test",
            version="1.0.0",
            capabilities=[],
            tenant_id=uuid4(),
        )
        await registry.register_agent(reg)
        assert False, "Should have raised error"
    except (ValueError, TypeError):
        print("✓ Field validation")


async def main():
    """Run all direct tests"""
    print("\nSlice 8: AgentRegistry - Direct Tests")
    print("=" * 50)

    tests = [
        test_registers_and_retrieves_agent,
        test_finds_by_capability,
        test_tenant_isolation,
        test_lists_all_agents,
        test_status_updates,
        test_filters_by_status,
        test_multiple_versions,
        test_unregisters_agent,
        test_prevents_cross_tenant_unregistration,
        test_validation,
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

    print("\n" + "=" * 50)
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
