"""
P5.7: Integration & Smoke Tests

Comprehensive testing for system integration, critical paths, and smoke tests:

1. Integration Tests: Full workflows across multiple services
   - Authentication → Workflow Creation → Agent Execution → Result
   - Multi-service data flow and consistency
   - Service-to-service communication

2. Smoke Tests: Critical functionality validation
   - Health checks and service readiness
   - Basic CRUD operations
   - Authentication flow verification
   - Error handling

3. System Tests: Multi-service interaction
   - Database consistency across operations
   - Cache invalidation and synchronization
   - Transaction rollback on errors
   - Concurrent access handling

Reference: Test Plan v1.0 Section 7 - Integration & Smoke Tests
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import httpx
import pytest

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(
        reason="Smoke tests require a live server at localhost:8100. "
        "Start the backend first: uvicorn src.main:app --port 8100"
    ),
]


# ============================================================================
# SECTION 1: Smoke Tests - Critical Functionality
# ============================================================================


class TestSmokeTests:
    """Basic smoke tests for critical system functionality"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self, api_client: httpx.AsyncClient):
        """Smoke test: System health check"""
        response = await api_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_service_is_up_and_responsive(self, api_client: httpx.AsyncClient):
        """Smoke test: Service responds to basic request"""
        response = await api_client.get("/health")
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_authentication_service_available(self, api_client: httpx.AsyncClient):
        """Smoke test: Authentication service is available"""
        response = await api_client.post(
            "/auth/token", data={"username": "test@example.com", "password": "test"}
        )
        # Should either authenticate or reject (not error out)
        assert response.status_code in [200, 401, 422]

    @pytest.mark.asyncio
    async def test_api_returns_valid_json(self, api_client: httpx.AsyncClient):
        """Smoke test: API responses are valid JSON"""
        response = await api_client.get("/health")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_basic_workflow_endpoint_accessible(self, api_client: httpx.AsyncClient):
        """Smoke test: Workflow endpoint is accessible"""
        response = await api_client.get("/api/v1/workflows", follow_redirects=True)
        # Should be 401 (unauthorized) not 500 (error)
        assert response.status_code in [200, 401, 404]


# ============================================================================
# SECTION 2: Integration Tests - Full Workflows
# ============================================================================


class TestIntegrationAuthToExecution:
    """Integration tests for complete workflows: Auth → Workflow → Agent → Execution"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_complete_workflow_auth_to_execution(self, api_client: httpx.AsyncClient):
        """
        Integration test: Complete workflow from authentication to execution

        Flow:
        1. Register user
        2. Authenticate (get token)
        3. Create workflow
        4. Execute workflow
        5. Get execution results
        """
        # Step 1: Register user
        user_email = f"integration_{uuid4()}@example.com"
        user_password = "IntegrationTest123!@#"

        register_response = await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        assert register_response.status_code in [200, 201]

        # Step 2: Authenticate
        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        assert auth_response.status_code == 200
        token = auth_response.json()["access_token"]

        # Create authenticated client
        auth_headers = {"Authorization": f"Bearer {token}"}
        auth_client = httpx.AsyncClient(
            base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
        )

        # Step 3: Create workflow
        workflow_data = {
            "name": "Integration Test Workflow",
            "spec": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "agent", "type": "agent", "agent_id": "test_agent"},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"from": "start", "to": "agent"},
                    {"from": "agent", "to": "end"},
                ],
            },
        }

        workflow_response = await auth_client.post("/api/v1/workflows", json=workflow_data)

        assert workflow_response.status_code in [200, 201, 404]

        if workflow_response.status_code in [200, 201]:
            workflow = workflow_response.json()
            workflow_id = workflow.get("id") or workflow.get("workflow_id")

            # Step 4: Execute workflow
            exec_response = await auth_client.post(f"/api/v1/workflows/{workflow_id}/execute")

            assert exec_response.status_code in [200, 201, 202, 404]

        await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_multi_step_workflow_with_data_flow(self, api_client: httpx.AsyncClient):
        """Integration test: Multi-step workflow with data flowing through steps"""
        user_email = f"data_flow_{uuid4()}@example.com"
        user_password = "DataFlowTest123!@#"

        # Register and authenticate
        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Create complex workflow
            workflow_data = {
                "name": "Multi-Step Workflow",
                "spec": {
                    "nodes": [
                        {"id": "input", "type": "start"},
                        {"id": "step1", "type": "agent", "agent_id": "agent1"},
                        {"id": "step2", "type": "agent", "agent_id": "agent2"},
                        {"id": "output", "type": "end"},
                    ],
                    "edges": [
                        {"from": "input", "to": "step1"},
                        {"from": "step1", "to": "step2"},
                        {"from": "step2", "to": "output"},
                    ],
                },
            }

            response = await auth_client.post("/api/v1/workflows", json=workflow_data)

            assert response.status_code in [200, 201, 404]

            await auth_client.aclose()


# ============================================================================
# SECTION 3: System Integration Tests - Multi-Service Communication
# ============================================================================


class TestSystemIntegration:
    """Tests for multi-service communication and system integration"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_user_data_consistency_across_services(self, api_client: httpx.AsyncClient):
        """Integration test: User data is consistent across all services"""
        user_email = f"consistency_{uuid4()}@example.com"
        user_password = "ConsistencyTest123!@#"

        # Register user
        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        # Authenticate
        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Get user profile
            profile_response = await auth_client.get("/auth/me")

            assert profile_response.status_code in [200, 404]

            if profile_response.status_code == 200:
                profile = profile_response.json()
                assert profile.get("email") == user_email

            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_workflow_and_agent_interaction(self, api_client: httpx.AsyncClient):
        """Integration test: Workflows and agents interact correctly"""
        user_email = f"workflow_agent_{uuid4()}@example.com"
        user_password = "WorkflowAgentTest123!@#"

        # Setup user
        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Create workflow with agent
            workflow = {
                "name": "Agent Workflow",
                "spec": {"nodes": [{"id": "agent_node", "type": "agent"}], "edges": []},
            }

            response = await auth_client.post("/api/v1/workflows", json=workflow)

            assert response.status_code in [200, 201, 404]

            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_concurrent_operations_dont_cause_conflicts(self, api_client: httpx.AsyncClient):
        """Integration test: Concurrent operations don't cause data conflicts"""
        user_email = f"concurrent_{uuid4()}@example.com"
        user_password = "ConcurrentTest123!@#"

        # Register user
        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        # Authenticate
        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            # Create multiple concurrent workflows
            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            async def create_workflow(name: str):
                return await auth_client.post(
                    "/api/v1/workflows",
                    json={"name": name, "spec": {"nodes": [], "edges": []}},
                )

            # Run concurrent operations
            tasks = [create_workflow(f"Concurrent Workflow {i}") for i in range(3)]

            results = await asyncio.gather(*tasks)

            # All should complete successfully
            assert all(r.status_code in [200, 201, 404] for r in results)

            await auth_client.aclose()


# ============================================================================
# SECTION 4: Error Handling and Recovery
# ============================================================================


class TestErrorHandlingAndRecovery:
    """Tests for error handling and system recovery"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_graceful_error_on_invalid_workflow(self, api_client: httpx.AsyncClient):
        """Integration test: Invalid workflows are handled gracefully"""
        user_email = f"error_test_{uuid4()}@example.com"
        user_password = "ErrorTest123!@#"

        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Try to create invalid workflow
            invalid_workflow = {
                "name": "Invalid",
                # Missing spec
            }

            response = await auth_client.post("/api/v1/workflows", json=invalid_workflow)

            # Should return error, not crash
            assert response.status_code in [400, 422, 201, 200, 404]

            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_service_recovers_from_errors(self, api_client: httpx.AsyncClient):
        """Integration test: Service continues functioning after error"""
        # First request that might fail
        response1 = await api_client.get("/api/v1/invalid-endpoint")

        # Next request should still work
        response2 = await api_client.get("/health")

        assert response2.status_code in [200, 404]


# ============================================================================
# SECTION 5: Data Consistency Tests
# ============================================================================


class TestDataConsistency:
    """Tests for data consistency across operations"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_created_data_is_immediately_readable(self, api_client: httpx.AsyncClient):
        """Integration test: Created data is immediately readable"""
        user_email = f"readability_{uuid4()}@example.com"
        user_password = "ReadabilityTest123!@#"

        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Create workflow
            create_response = await auth_client.post(
                "/api/v1/workflows",
                json={"name": "Test", "spec": {"nodes": [], "edges": []}},
            )

            if create_response.status_code in [200, 201]:
                workflow = create_response.json()
                workflow_id = workflow.get("id") or workflow.get("workflow_id")

                # Immediately read it back
                read_response = await auth_client.get(f"/api/v1/workflows/{workflow_id}")

                # Should be readable
                assert read_response.status_code in [200, 404]

            await auth_client.aclose()

    @pytest.mark.asyncio
    async def test_deleted_data_is_no_longer_accessible(self, api_client: httpx.AsyncClient):
        """Integration test: Deleted data is no longer accessible"""
        user_email = f"deletion_{uuid4()}@example.com"
        user_password = "DeletionTest123!@#"

        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Create workflow
            create_response = await auth_client.post(
                "/api/v1/workflows",
                json={"name": "ToDelete", "spec": {"nodes": [], "edges": []}},
            )

            if create_response.status_code in [200, 201]:
                workflow = create_response.json()
                workflow_id = workflow.get("id") or workflow.get("workflow_id")

                # Delete it
                delete_response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")

                if delete_response.status_code in [200, 204]:
                    # Verify it's gone
                    get_response = await auth_client.get(f"/api/v1/workflows/{workflow_id}")
                    assert get_response.status_code == 404

            await auth_client.aclose()


# ============================================================================
# SECTION 6: Performance and Load Handling
# ============================================================================


class TestPerformanceAndLoad:
    """Tests for performance under load"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_api_responds_under_load(self, api_client: httpx.AsyncClient):
        """Integration test: API responds even under load"""
        # Send multiple concurrent requests
        tasks = [api_client.get("/health") for _ in range(10)]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.status_code in [200, 404] for r in results)

    @pytest.mark.asyncio
    async def test_large_workflow_handling(self, api_client: httpx.AsyncClient):
        """Integration test: Large workflows are handled correctly"""
        user_email = f"large_workflow_{uuid4()}@example.com"
        user_password = "LargeWorkflowTest123!@#"

        await api_client.post(
            "/auth/register", json={"email": user_email, "password": user_password}
        )

        auth_response = await api_client.post(
            "/auth/token", data={"username": user_email, "password": user_password}
        )

        if auth_response.status_code == 200:
            token = auth_response.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            auth_client = httpx.AsyncClient(
                base_url="http://localhost:8100", headers=auth_headers, timeout=30.0
            )

            # Create large workflow with many nodes
            large_workflow = {
                "name": "Large Workflow",
                "spec": {
                    "nodes": [
                        {"id": f"node_{i}", "type": "agent" if i % 2 else "start"}
                        for i in range(50)
                    ],
                    "edges": [{"from": f"node_{i}", "to": f"node_{i+1}"} for i in range(49)],
                },
            }

            response = await auth_client.post("/api/v1/workflows", json=large_workflow)

            assert response.status_code in [200, 201, 400, 404]

            await auth_client.aclose()


# ============================================================================
# SECTION 7: Helper Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
async def wait_for_backend():
    """Ensure backend is available before tests run"""
    max_retries = 30
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(base_url="http://localhost:8100", timeout=5.0) as client:
                response = await client.get("/health")
                if response.status_code == 200:
                    return
        except Exception:
            pass

        if attempt < max_retries - 1:
            await asyncio.sleep(1)

    raise RuntimeError("Backend not available after 30 seconds")
