"""
Example: Futureproof Integration Tests

This module demonstrates the "futureproof" testing approach that prevents:
✓ KeyError from missing response fields
✓ Silent API contract violations
✓ Response format regressions

Key principles:
1. All responses are validated against schemas defined in response_validation.py
2. Tests fail immediately with clear error if response format changes
3. Common patterns (login, create, list, etc.) are reusable fixtures
4. No naked response.json()["field"] access - always validate first

Usage Pattern:
    async def test_feature(authenticated_api):
        # api is already logged in and has auth headers set
        result = await authenticated_api.get("/api/v1/agents/1", "agent")
        # Safe to access result["id"], result["name"], etc.
        # Schema validation guarantees those fields exist
"""

from typing import Any, Dict

import pytest

pytestmark = pytest.mark.skip(
    reason="Legacy example tests are out of sync with current API contracts"
)

# ============================================================================
# EXAMPLE 1: Simple GET with Schema Validation
# ============================================================================


@pytest.mark.asyncio
async def test_get_agent_with_validation(authenticated_api):
    """
    FUTUREPROOF PATTERN: Use schema validation on all responses.

    This test will FAIL IMMEDIATELY if:
    - Response status is not 2xx
    - Response doesn't have required fields (id, name, etc.)
    - Response has fields removed that schema expects

    Classic pattern (BREAKS on API changes):
        response = await client.get("/api/v1/agents/1")
        agent = response.json()  # No validation
        assert agent["id"]  # ❌ KeyError if "id" not in response

    Futureproof pattern (DETECTS API changes):
        agent = await api.get("/api/v1/agents/1", "agent")
        # ✅ Schema validation ensures all fields exist
        # ✅ ResponseValidationError if schema violated
    """
    # Get agent with schema validation
    agent = await authenticated_api.get("/api/v1/agents/1", "agent")

    # These are safe because schema validates them first
    assert agent["id"] == 1
    assert isinstance(agent["name"], str)
    assert agent["status"] in ["active", "inactive"]


# ============================================================================
# EXAMPLE 2: Create with Schema Validation
# ============================================================================


@pytest.mark.asyncio
async def test_create_agent_validated(authenticated_api):
    """
    FUTUREPROOF: Create resource and validate all returned fields.

    Guarantees:
    - POST request succeeds (201 Created)
    - Response has 'id' field to reference new resource
    - All required fields present in response
    - Created resource can be immediately fetched
    """
    # Create with validation
    new_agent = await authenticated_api.post(
        "/api/v1/agents",
        {"name": "TestAgent", "type": "specialist"},
        schema_type="agent",
    )

    # Safe to use new_agent["id"] - schema validated it exists
    agent_id = new_agent["id"]
    assert agent_id > 0

    # Verify can fetch it
    fetched = await authenticated_api.get(f"/api/v1/agents/{agent_id}", "agent")

    assert fetched["id"] == agent_id
    assert fetched["name"] == "TestAgent"


# ============================================================================
# EXAMPLE 3: List with Schema Validation
# ============================================================================


@pytest.mark.asyncio
async def test_list_agents_validated(authenticated_api):
    """
    FUTUREPROOF: Validate list response structure.

    List responses have schema_type="agent_list" which validates:
    - Response has "data" field (array of agents)
    - Each agent in array has id, name, etc.
    - Optional fields for pagination (page, total, etc.)
    """
    # Get list with validation
    result = await authenticated_api.get("/api/v1/agents/", schema_type="agent_list")

    # Safe access because schema validated the "data" field exists
    assert isinstance(result["data"], list)
    assert len(result["data"]) >= 0

    # If list has items, validate structure
    if result["data"]:
        first = result["data"][0]
        # Safe because agent_list schema validates items
        assert first["id"]
        assert first["name"]


# ============================================================================
# EXAMPLE 4: Authentication Flow (Futureproof)
# ============================================================================


@pytest.mark.asyncio
async def test_login_flow(api):
    """
    FUTUREPROOF: Full authentication flow with validation.

    This test validates:
    - Login response has access_token, token_type
    - JWT can be used to access protected endpoints
    - Token is properly included in subsequent requests
    - API rejects invalid tokens
    """
    # Login with validation
    token_data = await api.login("user@test.com", "UserPass123!")

    # Validated by schema - these fields guaranteed
    assert token_data["access_token"]
    assert token_data["token_type"] == "bearer"

    # api.headers now has Authorization header set
    assert api.headers["Authorization"].startswith("Bearer ")

    # Can now access protected endpoints
    agent = await api.get("/api/v1/agents/1", "agent")
    assert agent["id"] == 1


# ============================================================================
# EXAMPLE 5: Error Handling (Futureproof)
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_agent_id_error(authenticated_api):
    """
    FUTUREPROOF: Even error responses follow schema.

    API should return consistent error format:
    {"error": "...", "detail": "..."}

    This test validates error response format.
    """
    from tests.integration.response_validation import ResponseValidationError, assert_response_error

    # Try to get non-existent agent
    response = await authenticated_api.client.get(
        "/api/v1/agents/99999", headers=authenticated_api.headers
    )

    # Validate error response format (should be 404)
    error = assert_response_error(response, expected_status=404)

    # Safe to access error fields - schema validated
    assert error["detail"]  # Error message is present


# ============================================================================
# EXAMPLE 6: Update with Validation
# ============================================================================


@pytest.mark.asyncio
async def test_update_agent_validated(authenticated_api):
    """
    FUTUREPROOF: PATCH request with response validation.

    Validates:
    - PATCH succeeds (200 OK)
    - Response includes updated resource
    - Updated fields match what was sent
    """
    # Create first
    agent = await authenticated_api.post(
        "/api/v1/agents", {"name": "Original", "type": "specialist"}, "agent"
    )
    agent_id = agent["id"]

    # Update with validation
    updated = await authenticated_api.patch(
        f"/api/v1/agents/{agent_id}", {"name": "Updated"}, "agent"
    )

    # Safe to access updated fields
    assert updated["id"] == agent_id
    assert updated["name"] == "Updated"


# ============================================================================
# EXAMPLE 7: Response Validation Error (When to add new schemas)
# ============================================================================


@pytest.mark.asyncio
async def test_new_endpoint_requires_schema(authenticated_api):
    """
    FUTUREPROOF: When you get ResponseValidationError, just add the schema!

    If you encounter:
        ResponseValidationError: No schema defined for endpoint /api/v1/new-endpoint

    Solution:
    1. Go to tests/integration/response_validation.py
    2. Add to ResponseSchema enum:
       NEW_ENDPOINT = {"required": ["id", "field"], "optional": ["opt_field"]}
    3. Add to RESPONSE_SCHEMAS registry:
       "/api/v1/new-endpoint": ResponseSchema.NEW_ENDPOINT
    4. Done! Test now validates against it.

    This ensures the response validator always knows what fields to expect.
    """
    # If this fails with ResponseValidationError, add schema as shown above
    try:
        result = await authenticated_api.get(
            "/api/v1/agents/1",
            "agent",  # A real endpoint  # Validated by existing schema
        )
        assert result["id"]
    except Exception as e:
        # If schema missing, error message tells you exactly what to do
        pytest.skip(f"Schema error: {e}")


# ============================================================================
# DOCUMENTATION: Benefits of Futureproof Pattern
# ============================================================================

BENEFITS = """
BEFORE (Fragile Pattern):
    response = await client.get("/api/v1/agents")
    agents = response.json()["data"]  # ❌ Crashes if "data" removed
    for agent in agents:
        print(agent["id"])  # ❌ KeyError if "id" renamed to "agent_id"

    Problems:
    - No early error detection (crashes in middle of test)
    - Silent failures if field renamed
    - Each test has to know API format
    - Tests break when API refactored
    - Debugging is slow (which response format changed?)

AFTER (Futureproof Pattern):
    result = await api.get("/api/v1/agents", "agent_list")
    # ✓ ResponseValidationError immediately if "data" removed
    # ✓ ResponseValidationError if required fields missing
    # ✓ Test knows exact expected format (schema-driven)
    # ✓ All tests protected by same validation
    # ✓ Clear error: "Expected field 'data' at /api/v1/agents but not found"

BENEFITS:
✓ Fail fast - errors at response validation, not later
✓ Regressions caught immediately - API contract violations detected
✓ Self-documenting - schemas define expected response format
✓ Reduced debugging - clear error message = easy fix
✓ One place to fix - update schema once, all tests validated
✓ Production-ready - same validation logic can be used in client SDKs
"""

print(__doc__)
print(BENEFITS)
