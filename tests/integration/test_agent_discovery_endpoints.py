"""Integration tests for Phase 0a: Agent Discovery API Endpoints

Tests validate:
- All 6 discovery endpoints work correctly with auth (FA-SEC-001)
- Department and function filtering returns correct agents
- Pagination works correctly with limit/offset
- Tenant isolation is enforced via require_tenant_id
- 404 responses for invalid departments/functions
- Response schemas match expected Pydantic models
"""

import pytest
from httpx import AsyncClient

from src.core.api.v1.agentic.agent_discovery import (
    AgentDiscoveryItem,
    AgentDiscoveryResponse,
    DepartmentAgentsResponse,
    DepartmentInfo,
    FunctionAgentsResponse,
    FunctionCapability,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDiscoveryEndpoints:
    """Integration tests for all agent discovery endpoints (require auth per FA-SEC-001)."""

    async def test_list_all_departments_returns_10_departments(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/departments should return all 10 departments with agent counts."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/departments", headers=headers)

        assert response.status_code == 200
        departments = response.json()
        assert isinstance(departments, list)
        assert len(departments) == 10

        for dept in departments:
            DepartmentInfo(**dept)
            assert "name" in dept
            assert "value" in dept
            assert "description" in dept
            assert "agent_count" in dept
            assert isinstance(dept["agent_count"], int)
            assert dept["agent_count"] >= 0

    async def test_list_all_departments_includes_all_standard_depts(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """Verify all 10 standard departments are present in the list."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/departments", headers=headers)
        departments = response.json()

        expected_departments = {
            "DATA_AI_GOVERNANCE",
            "OPERATIONS",
            "CUSTOMER_EXPERIENCE",
            "SALES_MARKETING",
            "IT_SECURITY",
            "LEGAL_COMPLIANCE",
            "HR",
            "FINANCE",
            "PRODUCT_INNOVATION",
            "STRATEGY",
        }

        dept_values = {d["value"] for d in departments}
        assert dept_values == expected_departments

    async def test_list_all_functions_returns_functions_with_counts(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/functions should return all unique functions with agent counts."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/functions", headers=headers)

        assert response.status_code == 200
        functions = response.json()
        assert isinstance(functions, list)
        assert len(functions) > 0

        for func in functions:
            FunctionCapability(**func)
            assert "name" in func
            assert "description" in func
            assert "agent_count" in func
            assert func["agent_count"] > 0

    async def test_list_all_functions_includes_known_capabilities(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """Verify common capabilities are present in functions list."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/functions", headers=headers)
        functions = response.json()

        function_names = {f["name"] for f in functions}
        known_capabilities = {
            "ai",
            "data",
            "cloud",
            "security",
            "deployment",
            "sales",
            "marketing",
            "hr",
        }

        assert known_capabilities.issubset(function_names)

    async def test_discover_agents_returns_all_agents_with_pagination(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery should return agents with pagination."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery", headers=headers)

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryResponse(**data)

        assert "agents" in data
        assert isinstance(data["agents"], list)
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] >= 10

    async def test_discover_agents_filter_by_department(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?department=DATA_AI_GOVERNANCE should return only matching agents."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"department": "DATA_AI_GOVERNANCE"},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryResponse(**data)

        assert len(data["agents"]) > 0
        for agent in data["agents"]:
            assert agent["department"] == "DATA_AI_GOVERNANCE"

        assert data["filtered_by_department"] == "DATA_AI_GOVERNANCE"

    async def test_discover_agents_filter_by_function(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?function=ai should return only agents with ai function."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"function": "ai"},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryResponse(**data)

        assert len(data["agents"]) > 0
        for agent in data["agents"]:
            assert "ai" in agent["functions"]

        assert data["filtered_by_function"] == "ai"

    async def test_discover_agents_filter_by_status(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?status=active should return active agents."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"status": "active"},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryResponse(**data)

        assert len(data["agents"]) > 0
        for agent in data["agents"]:
            assert agent["status"] == "active"

    async def test_discover_agents_combined_filters(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery with multiple filters should apply all filters."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={
                "department": "OPERATIONS",
                "function": "infrastructure",
                "status": "active",
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryResponse(**data)

        for agent in data["agents"]:
            assert agent["department"] == "OPERATIONS"
            assert "infrastructure" in agent["functions"]
            assert agent["status"] == "active"

    async def test_discover_agents_pagination_limit(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?limit=5 should return max 5 agents per page."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"limit": 5},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["agents"]) <= 5
        assert data["limit"] == 5

    async def test_discover_agents_pagination_offset(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?offset=5&limit=3 should skip 5 agents, return next 3."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        all_response = await client.get("/api/v1/agentic/discovery?limit=100", headers=headers)
        all_agents = all_response.json()["agents"]

        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"offset": 5, "limit": 3},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["agents"]) == 3
        assert data["offset"] == 5
        assert data["limit"] == 3

        for i, agent in enumerate(data["agents"]):
            assert agent == all_agents[5 + i]

    async def test_discover_agents_limit_constraint_max_1000(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery?limit=2000 should be clamped to max 1000."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery",
            params={"limit": 2000},
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            assert data["limit"] <= 1000 or response.status_code == 422

    async def test_get_agents_by_department_returns_department_agents(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-department/SALES_MARKETING should return matching agents."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-department/SALES_MARKETING", headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        DepartmentAgentsResponse(**data)

        assert data["department"] == "SALES_MARKETING"
        assert "agents" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        for agent in data["agents"]:
            assert agent["department"] == "SALES_MARKETING"

    async def test_get_agents_by_department_404_invalid_department(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-department/INVALID should return 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-department/INVALID_DEPT", headers=headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_agents_by_department_pagination(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-department/OPERATIONS?limit=2 should paginate agents."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-department/OPERATIONS",
            params={"limit": 2, "offset": 0},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["agents"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    async def test_get_agents_by_function_returns_function_agents(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-function/deployment should return agents with that function."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-function/deployment", headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        FunctionAgentsResponse(**data)

        assert data["function"] == "deployment"
        assert "agents" in data
        assert "total" in data

        for agent in data["agents"]:
            assert "deployment" in agent["functions"]

    async def test_get_agents_by_function_404_invalid_function(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-function/nonexistent should return 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-function/nonexistent_function_xyz",
            headers=headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_agents_by_function_pagination(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/by-function/data?limit=2 should paginate agents."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-function/data",
            params={"limit": 2, "offset": 0},
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["agents"]) <= 2
        assert data["limit"] == 2

    async def test_get_agent_details_returns_full_agent_info(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/agent/ai-engineer should return full agent details."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/agent/ai-engineer", headers=headers)

        assert response.status_code == 200
        data = response.json()
        AgentDiscoveryItem(**data)

        assert data["agent_id"] == "ai-engineer"
        assert data["name"] == "AI Engineer"
        assert data["department"] == "DATA_AI_GOVERNANCE"
        assert "ai" in data["functions"]
        assert "ai-engineering" in data["functions"]
        assert data["status"] == "active"

    async def test_get_agent_details_404_invalid_agent_id(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """GET /discovery/agent/invalid-id should return 404."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/agent/nonexistent-agent-xyz", headers=headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_get_agent_details_multiple_agents(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """Verify multiple agents are individually retrievable."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        agent_ids = ["ai-engineer", "cloud-architect", "legal-advisor", "hr-pro"]

        for agent_id in agent_ids:
            response = await client.get(
                f"/api/v1/agentic/discovery/agent/{agent_id}", headers=headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == agent_id
            AgentDiscoveryItem(**data)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.multi_tenant
class TestDiscoveryTenantIsolation:
    """FA-SEC-001: discovery endpoints require auth -- unauthenticated requests must be rejected."""

    async def test_list_departments_requires_auth(self, client_no_auth: AsyncClient) -> None:
        """GET /discovery/departments without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery/departments")

        assert response.status_code == 401

    async def test_list_functions_requires_auth(self, client_no_auth: AsyncClient) -> None:
        """GET /discovery/functions without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery/functions")

        assert response.status_code == 401

    async def test_discover_agents_requires_auth(self, client_no_auth: AsyncClient) -> None:
        """GET /discovery without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery")

        assert response.status_code == 401

    async def test_get_agents_by_department_requires_auth(
        self, client_no_auth: AsyncClient
    ) -> None:
        """GET /discovery/by-department/{x} without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery/by-department/OPERATIONS")

        assert response.status_code == 401

    async def test_get_agents_by_function_requires_auth(self, client_no_auth: AsyncClient) -> None:
        """GET /discovery/by-function/{x} without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery/by-function/ai")

        assert response.status_code == 401

    async def test_get_agent_details_requires_auth(self, client_no_auth: AsyncClient) -> None:
        """GET /discovery/agent/{x} without auth must return 401 (FA-SEC-001)."""
        response = await client_no_auth.get("/api/v1/agentic/discovery/agent/ai-engineer")

        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
class TestDiscoveryResponseSchemas:
    """Verify all responses match expected Pydantic schemas (require auth per FA-SEC-001)."""

    async def test_department_info_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """DepartmentInfo should validate all required fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/departments", headers=headers)
        departments = response.json()

        for dept in departments:
            validated = DepartmentInfo(**dept)
            assert validated.name
            assert validated.value
            assert validated.description
            assert validated.agent_count >= 0

    async def test_function_capability_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """FunctionCapability should validate all required fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/functions", headers=headers)
        functions = response.json()

        for func in functions:
            validated = FunctionCapability(**func)
            assert validated.name
            assert validated.description
            assert validated.agent_count > 0

    async def test_agent_discovery_item_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """AgentDiscoveryItem should validate all required fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery", headers=headers)
        data = response.json()

        for agent in data["agents"]:
            validated = AgentDiscoveryItem(**agent)
            assert validated.agent_id
            assert validated.name
            assert validated.status in ["active", "inactive"]

    async def test_agent_discovery_response_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """AgentDiscoveryResponse should validate all fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery", headers=headers)
        AgentDiscoveryResponse(**response.json())

    async def test_department_agents_response_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """DepartmentAgentsResponse should validate all fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get(
            "/api/v1/agentic/discovery/by-department/OPERATIONS", headers=headers
        )
        DepartmentAgentsResponse(**response.json())

    async def test_function_agents_response_schema_validation(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """FunctionAgentsResponse should validate all fields."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/api/v1/agentic/discovery/by-function/cloud", headers=headers)
        FunctionAgentsResponse(**response.json())
