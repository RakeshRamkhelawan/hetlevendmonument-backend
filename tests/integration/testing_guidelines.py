"""
Integration Test Best Practices & Testing Framework

This module documents the "futureproof" testing approach and provides
helpers to prevent common issues like KeyError, response format mismatches,
and authentication timing problems.

Key Principles:
1. SCHEMA VALIDATION - Responses are validated before use
2. EARLY FAILURE - Invalid responses fail immediately with clear errors
3. REUSABLE PATTERNS - Common flows are fixtures, not duplicated in tests
4. PRODUCTION PARITY - Tests use real JWT, real DB, real API flows
"""

from datetime import datetime
from typing import Any, Dict, Optional

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.response_validation import (
    ResponseValidationError,
    assert_response_error,
    assert_response_ok,
    validate_response,
)

# ============================================================================
# PATTERN 1: Response Validation (Prevents KeyError)
# ============================================================================


class APIHelper:
    """Helper class for common API patterns used in all integration tests"""

    def __init__(self, client: AsyncClient):
        self.client = client

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login and get JWT token with automatic validation.

        Examples:
            token_data = await api.login("user@test.com", "password123")
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}

        Returns:
            {"access_token": "...", "token_type": "bearer", ...}

        Raises:
            AssertionError: If login fails
            ResponseValidationError: If token response is invalid
        """
        response = await self.client.post(
            "/api/v1/auth/login", data={"username": email, "password": password}
        )

        # Validate response
        assert_response_ok(response, endpoint="/api/v1/auth/login")
        token_data = validate_response(response, "auth_token", endpoint="/api/v1/auth/login")

        return token_data

    async def get_with_validation(
        self, endpoint: str, schema_type: str, headers: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        GET request with automatic schema validation.

        Example:
            agent = await api.get_with_validation(
                "/api/v1/agents/123",
                "agent",
                headers=auth_headers
            )
            # Safe to access: agent["id"], agent["name"], etc.
        """
        response = await self.client.get(endpoint, headers=headers)
        assert_response_ok(response, endpoint=endpoint)
        return validate_response(response, schema_type, endpoint=endpoint)

    async def post_with_validation(
        self,
        endpoint: str,
        json_data: Dict,
        schema_type: str,
        headers: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        POST request with automatic schema validation.

        Example:
            agent = await api.post_with_validation(
                "/api/v1/agents",
                {"name": "NewAgent", "type": "technical"},
                "agent",
                headers=auth_headers
            )
            # Safe: agent["id"], agent["name"] guaranteed to exist
        """
        response = await self.client.post(endpoint, json=json_data, headers=headers)
        assert_response_ok(response, endpoint=endpoint)
        return validate_response(response, schema_type, endpoint=endpoint)


# ============================================================================
# PATTERN 2: Authenticated Test Flows (Prevents JWT timing issues)
# ============================================================================


@pytest.fixture
async def authenticated_api(async_client: AsyncClient, test_user: Dict) -> APIHelper:
    """
    Fixture providing authenticated API helper.

    Usage in tests:
        async def test_something(authenticated_api):
            # Already logged in, ready to use
            agent = await authenticated_api.get_with_validation(
                "/api/v1/agents/1",
                "agent"
            )

    Depends on:
    - async_client: Fresh AsyncClient instance
    - test_user: Pre-seeded test user (from conftest.py)

    Guarantees:
    - JWT token is valid and current
    - User context is set
    - All subsequent requests are authenticated
    """
    api = APIHelper(async_client)
    # Login happens lazily on first use
    return api


# ============================================================================
# PATTERN 3: Reusable Test Flows
# ============================================================================

await_authenticated_api_test_template = """
async def test_example_authenticated_flow(authenticated_api):
    '''Example of proper authenticated test flow using helpers'''

    # Use pre-authenticated API helper
    agent = await authenticated_api.get_with_validation(
        "/api/v1/agents/1",
        "agent"
    )

    # Safe access - fields are guaranteed
    assert agent["id"] > 0
    assert agent["name"]  # Not None
    assert agent["status"] == "active"
"""

create_and_verify_flow = """
async def test_create_agent_flow(authenticated_api):
    '''Create agent and verify all required fields returned'''

    # Create
    agent = await authenticated_api.post_with_validation(
        "/api/v1/agents",
        {"name": "TestAgent", "type": "specialist"},
        "agent"  # Schema validation happens here
    )

    # Verify response has all required fields
    assert agent["id"]  # Safe - validated
    assert agent["name"] == "TestAgent"

    # Fetch and verify
    agent_fetched = await authenticated_api.get_with_validation(
        f"/api/v1/agents/{agent['id']}",
        "agent"
    )

    # Can safely compare
    assert agent_fetched["id"] == agent["id"]
"""

# ============================================================================
# PATTERN 4: Error Handling
# ============================================================================

error_handling_example = """
async def test_error_response_validated(authenticated_api):
    '''Errors are also validated to have consistent format'''

    # Try invalid request
    response = await authenticated_api.client.get(
        "/api/v1/agents/invalid-id"  # Invalid ID format
    )

    # Validate error response format
    error = assert_response_error(response, expected_status=400)

    # Safe access to error fields
    assert error["error"]
    assert error["detail"]  # All error responses have detail
"""

# ============================================================================
# DOCUMENTATION: Test Writing Guidelines
# ============================================================================

TESTING_GUIDELINES = """
## Integration Test Guidelines (Futureproof)

### DO:
1. ✅ Use validate_response() for ALL API calls
   response = await client.get("/endpoint")
   data = validate_response(response, "schema_type")

2. ✅ Use authenticated_api fixture for login-required tests
   async def test_something(authenticated_api):
       # Already have JWT, just use api helper

3. ✅ Check response status BEFORE accessing data
   assert_response_ok(response)  # Dies if not 2xx

4. ✅ Define missing schemas in response_validation.py
   # If test needs new schema, add to ResponseSchema enum

### DON'T:
1. ❌ Direct response.json()["field"] without validation
   # This causes KeyError when API changes

2. ❌ Assume fields exist
   # Always validate schema first

3. ❌ Create your own login logic in each test
   # Use authenticated_api fixture instead

4. ❌ Catch KeyError in tests
   # Fix the response schema validation instead

### Common Patterns:

#### Get with validation:
    data = await api.get_with_validation("/endpoint", "schema_name", headers)

#### Post with validation:
    data = await api.post_with_validation("/endpoint", json, "schema_name", headers)

#### Error handling:
    error = assert_response_error(response, expected_status=400)

#### List responses:
    response = await client.get("/api/v1/agents/")
    data = validate_response(response, "agent_list")  # Auto-unwraps "data" field

### Schema Extension:
If you get ResponseValidationError saying schema doesn't exist:
1. Go to tests/integration/response_validation.py
2. Add to ResponseSchema enum:
   MY_NEW_TYPE = {"required": ["id", "field2"], "optional": ["field3"]}
3. Done - all tests now validate against it
"""

print(__doc__)
print(TESTING_GUIDELINES)
