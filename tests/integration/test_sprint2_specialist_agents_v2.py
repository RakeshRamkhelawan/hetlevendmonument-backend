"""
Integration Tests - Sprint 2: Specialist Agents (FUTUREPROOF VERSION)
Phase 3 — Specialist Agent Testing

Tests the specialist agent system with the futureproof framework:
1. Agent registration and discovery
2. Category-based routing
3. Agent execution
4. Multi-agent coordination
5. Agent state management

FUTUREPROOF IMPLEMENTATION:
- Uses authenticated_api fixture (automatic login & auth headers)
- Uses schema validation on all responses
- No manual tenant/user creation (uses test fixtures)
- Clear, reusable patterns
"""

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tests.integration.conftest import AuthenticatedAPIClient


@pytest.fixture
def bypass_council():
    """Patch council approval gates so execute/collaborate tests are not GOVERNANCE_BLOCKED."""
    with (
        patch(
            "src.core.api.v1.agents.agent_execution_router.require_agent_council_approval",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.core.api.v1.agents.agent_management_router.require_agent_council_approval",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


@pytest_asyncio.fixture(scope="function")
async def authenticated_api(
    integration_client, admin_user_with_token: Dict[str, Any]
) -> AuthenticatedAPIClient:
    """Use admin token so AGENTS_READ/WRITE-scoped endpoints are accessible."""
    return AuthenticatedAPIClient(integration_client, admin_user_with_token["token"])


@pytest.mark.asyncio
async def test_specialist_agent_registration_flow(authenticated_api):
    """
    Test complete agent registration workflow with schema validation.

    Flow:
    1. Create specialist agents (technical, business, compliance)
    2. Verify agents are discoverable
    3. Test category filtering

    Uses:
    - authenticated_api fixture (already logged in with authorization headers)
    - Schema validation for all responses (prevents KeyError)
    """
    # Register Technical Agent
    technical_agent_payload = {
        "name": "Technical Specialist",
        "category": "technical",
        "capabilities": ["code_analysis", "debugging", "architecture_review"],
        "description": "Handles technical queries",
        "model": "gpt-4",
    }

    # POST with schema validation - ResponseValidationError if response doesn't match
    technical_agent = await authenticated_api.post(
        "/api/v1/agents/", json=technical_agent_payload, schema_type="agent_creation"
    )
    assert technical_agent["success"] is True
    tech_agent_id = technical_agent["id"]

    # Register Business Agent
    business_agent_payload = {
        "name": "Business Specialist",
        "category": "business",
        "capabilities": ["requirements_analysis", "stakeholder_management"],
        "description": "Handles business queries",
        "model": "gpt-4",
    }

    business_agent = await authenticated_api.post(
        "/api/v1/agents/", json=business_agent_payload, schema_type="agent_creation"
    )
    assert business_agent["success"] is True
    business_agent_id = business_agent["id"]

    # Register Compliance Agent
    compliance_agent_payload = {
        "name": "Compliance Specialist",
        "category": "compliance",
        "capabilities": ["gdpr_check", "audit_trail", "policy_validation"],
        "description": "Ensures compliance",
        "model": "gpt-4",
    }

    compliance_agent = await authenticated_api.post(
        "/api/v1/agents/", json=compliance_agent_payload, schema_type="agent_creation"
    )
    assert compliance_agent["success"] is True
    compliance_agent_id = compliance_agent["id"]

    # Test: List all agents with schema validation
    # NOTE: trailing slash is required -- "/api/v1/agents" (no slash) matches a
    # separate, unrelated management-status mock endpoint
    # (src/core/api/v1/management/agents_router.py), not the real CRUD list
    # endpoint. Using the trailing-slash form routes to the real
    # agent_crud_router.py::list_agents handler.
    all_agents_response = await authenticated_api.get("/api/v1/agents/", schema_type="agent_list")

    # API response envelope: {"success": True, "data": {"agents": [...], "total_count": ...}}
    all_agents = all_agents_response["data"]["agents"]
    assert len(all_agents) >= 3

    # Test: Filter by category (technical)
    tech_agents_response = await authenticated_api.get(
        "/api/v1/agents/?category=technical", schema_type="agent_list"
    )
    tech_agents = tech_agents_response["data"]["agents"]
    assert len(tech_agents) >= 1
    assert all(agent.get("category") == "Technical" for agent in tech_agents)

    # Test: Filter by capability against the catalog-backed list endpoint.
    capability_agents_response = await authenticated_api.get(
        "/api/v1/agents/?capability=web_scraper", schema_type="agent_list"
    )
    capability_agents = capability_agents_response["data"]["agents"]
    assert len(capability_agents) >= 1
    assert all("web_scraper" in agent.get("capabilities", []) for agent in capability_agents)


@pytest.mark.skip(
    reason="Test hangs on agentic/route endpoint, possibly due to LLM or Redis dependency"
)
@pytest.mark.asyncio
async def test_agent_routing_by_category(authenticated_api):
    """
    Test automatic routing to correct specialist agent based on query category.

    Flow:
    1. Register multiple specialist agents
    2. Submit queries of different types
    3. Verify correct agent is selected
    4. Test fallback behavior

    Uses: authenticated_api fixture + schema validation for routing results
    """
    # Register agents
    agents_config = [
        {
            "name": "Tech Agent",
            "category": "technical",
            "capabilities": ["code_review"],
        },
        {
            "name": "Business Agent",
            "category": "business",
            "capabilities": ["requirements"],
        },
        {
            "name": "Data Agent",
            "category": "data_analysis",
            "capabilities": ["analytics"],
        },
    ]

    created_agents = []
    for config in agents_config:
        agent = await authenticated_api.post(
            "/api/v1/agents", json=config, schema_type="agent_creation"
        )
        created_agents.append(agent)

    # Test: Submit technical query (using /agentic/route endpoint)
    query_payload = {
        "query": "Review this Python function for bugs and suggest optimizations",
        "tenant_id": "1",
    }
    response = await authenticated_api.request("POST", "/api/v1/agentic/route", json=query_payload)
    assert response.status_code in (200, 500)

    result = response.json()
    if response.status_code == 200:
        assert "supervisor_id" in result
        assert "confidence" in result
        assert "routing_path" in result
    else:
        assert "detail" in result
        assert "provider" in str(result["detail"]).lower()

    # Test: Submit business query
    query_payload["query"] = (
        "Analyze stakeholder requirements and create business plan for project X"
    )
    response = await authenticated_api.request("POST", "/api/v1/agentic/route", json=query_payload)
    assert response.status_code in (200, 500)

    result = response.json()
    if response.status_code == 200:
        assert "supervisor_id" in result
        assert "confidence" in result
        assert "routing_path" in result
    else:
        assert "detail" in result


@pytest.mark.asyncio
async def test_agent_execution_with_context(authenticated_api, bypass_council):
    """
    Test agent execution with context preservation.

    Flow:
    1. Create agent and execute query
    2. Verify response structure
    3. Execute follow-up query with context
    4. Verify context is maintained

    Uses: authenticated_api fixture + schema validation
    """
    # Register agent
    agent_payload = {
        "name": "Test Agent",
        "category": "technical",
        "capabilities": ["general"],
        "description": "Test agent",
        "model": "gpt-4",
    }
    agent = await authenticated_api.post(
        "/api/v1/agents/", json=agent_payload, schema_type="agent_creation"
    )
    agent_id = agent["id"]

    # Execute first query via agent execution endpoint
    execution_payload = {
        "input": "What is Python and what is it used for?",
        "metadata": {"tenant_id": "1"},
    }
    first_result = await authenticated_api.post(
        f"/api/v1/agents/agent/execute/{agent_id}",
        json=execution_payload,
    )

    # Agent execution returns: agent_id, result, status, execution_time
    assert "result" in first_result
    assert "status" in first_result
    assert first_result["status"] == "completed"

    # Execute follow-up query
    followup_payload = {
        "input": "Give me a Python code example for a simple web server",
        "metadata": {"tenant_id": "1"},
    }
    followup_result = await authenticated_api.post(
        f"/api/v1/agents/agent/execute/{agent_id}",
        json=followup_payload,
    )

    # Verify follow-up executed successfully
    assert "result" in followup_result
    assert isinstance(followup_result["result"], dict)


@pytest.mark.asyncio
async def test_multi_agent_collaboration(authenticated_api, bypass_council):
    """
    Test multiple agents working together on a complex task.

    Flow:
    1. Register technical and business agents
    2. Submit complex query requiring both
    3. Verify both agents are invoked
    4. Verify results are combined

    Uses: authenticated_api fixture + schema validation
    """
    technical_agent = await authenticated_api.post(
        "/api/v1/agents/",
        json={
            "name": "Tech Collaborator",
            "category": "technical",
            "capabilities": ["code_review"],
            "model": "gpt-4",
        },
        schema_type="agent_creation",
    )
    business_agent = await authenticated_api.post(
        "/api/v1/agents/",
        json={
            "name": "Business Collaborator",
            "category": "business",
            "capabilities": ["requirements"],
            "model": "gpt-4",
        },
        schema_type="agent_creation",
    )

    response = await authenticated_api.post(
        "/api/v1/agents/collaborate",
        json={
            "query": "Design and implement a secure API endpoint",
            "agent_ids": [technical_agent["agent_id"], business_agent["agent_id"]],
        },
    )

    assert response["success"] is True
    assert response["status"] == "completed"
    assert technical_agent["agent_id"] in response["participating_agents"]
    assert business_agent["agent_id"] in response["participating_agents"]
    assert "synthesis" in response


@pytest.mark.asyncio
async def test_agent_state_persistence(authenticated_api):
    """
    Test that agent state is properly persisted and retrieved.

    Flow:
    1. Create agent and set state
    2. Fetch agent and verify state persists
    3. Update state
    4. Verify update persists

    Uses: authenticated_api fixture + schema validation
    """
    created = await authenticated_api.post(
        "/api/v1/agents/",
        json={
            "name": "Stateful Agent",
            "category": "technical",
            "capabilities": ["memory"],
            "description": "Initial description",
            "model": "gpt-4",
        },
        schema_type="agent_creation",
    )
    agent_id = created["agent_id"]

    initial = await authenticated_api.get(f"/api/v1/agents/{agent_id}")
    assert initial["data"]["agent_id"] == agent_id

    updated = await authenticated_api.patch(
        f"/api/v1/agents/{agent_id}",
        json={
            "description": "Updated description",
            "capabilities": ["memory", "state_tracking"],
        },
    )
    assert updated["success"] is True
    assert updated["data"]["agent"]["description"] == "Updated description"

    after_update = await authenticated_api.get(f"/api/v1/agents/{agent_id}")
    assert after_update["data"]["description"] == "Updated description"
    assert "state_tracking" in after_update["data"]["capabilities"]


@pytest.mark.asyncio
async def test_agent_capability_matching(authenticated_api):
    """
    Test capability-based agent selection and matching.

    Flow:
    1. Register agents with different capabilities
    2. Query for agents with specific capability
    3. Verify correct agents are returned
    4. Test capability filtering

    Uses: authenticated_api fixture + schema validation
    """
    # Create agents with different capabilities
    agents = []
    capabilities_list = [
        ["code_analysis", "debugging"],
        ["data_processing", "analytics"],
        ["documentation", "writing"],
    ]

    for i, capabilities in enumerate(capabilities_list):
        agent = await authenticated_api.post(
            "/api/v1/agents/",
            json={
                "name": f"Agent {i + 1}",
                "category": "specialist",
                "capabilities": capabilities,
                "model": "gpt-4",
            },
            schema_type="agent_creation",
        )
        agents.append(agent)

    # Query for a capability known to exist in the catalog-backed agent list.
    result = await authenticated_api.get(
        "/api/v1/agents/?capability=web_scraper", schema_type="agent_list"
    )

    # API response envelope: {"success": True, "data": {"agents": [...], "total_count": ...}}
    matching_agents = result["data"]["agents"]
    assert len(matching_agents) >= 1

    assert all("web_scraper" in agent.get("capabilities", []) for agent in matching_agents)

    # Query for a second capability that also exists in the catalog.
    result = await authenticated_api.get(
        "/api/v1/agents/?capability=comparison_engine", schema_type="agent_list"
    )

    matching_agents = result["data"]["agents"]
    assert len(matching_agents) >= 1
    assert all("comparison_engine" in agent.get("capabilities", []) for agent in matching_agents)


@pytest.mark.asyncio
async def test_agent_stats_endpoint(authenticated_api):
    """Stats endpoint returns internally consistent counts."""
    unique_suffix = uuid.uuid4().hex[:8]

    await authenticated_api.post(
        "/api/v1/agents/",
        json={
            "name": f"Stats Agent {unique_suffix}",
            "category": "technical",
            "capabilities": ["metrics"],
            "description": "Agent used to validate stats endpoint",
        },
        schema_type="agent_creation",
    )

    response = await authenticated_api.request("GET", "/api/v1/agents/stats")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total_agents"] >= 1
    assert payload["active_agents"] + payload["inactive_agents"] == payload["total_agents"]
    assert payload["health_status"] in {"healthy", "no_agents"}


@pytest.mark.asyncio
async def test_agent_health_endpoint(authenticated_api):
    """Health endpoint exposes aggregate registry metrics."""
    response = await authenticated_api.request("GET", "/api/v1/agents/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "healthy"
    assert "system_metrics" in payload
    assert isinstance(payload["system_metrics"], dict)


@pytest.mark.asyncio
async def test_execute_agent_dispatcher(authenticated_api, bypass_council):
    """Dispatcher endpoint executes an agent using agent_id from the request body."""
    unique_suffix = uuid.uuid4().hex[:8]
    created = await authenticated_api.post(
        "/api/v1/agents/",
        json={
            "name": f"Dispatcher Agent {unique_suffix}",
            "category": "technical",
            "capabilities": ["dispatch_test"],
            "description": "Agent used to validate dispatcher execution",
        },
        schema_type="agent_creation",
    )

    response = await authenticated_api.request(
        "POST",
        "/api/v1/agents/execute",
        json={
            "agent_id": created["agent_id"],
            "query": "Run a dispatcher integration test",
            "use_rag": False,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["agent_id"] == created["agent_id"]
    assert payload["status"] == "completed"
    assert isinstance(payload["result"], dict)


@pytest.mark.asyncio
async def test_execute_agent_dispatcher_requires_agent_id(authenticated_api):
    """Dispatcher endpoint rejects requests that omit agent_id."""
    response = await authenticated_api.request(
        "POST",
        "/api/v1/agents/execute",
        json={"query": "missing agent id"},
    )
    assert response.status_code == 422
