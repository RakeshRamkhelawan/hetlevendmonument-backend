"""
API Response Validation Layer for Integration Tests

This module provides schema-based response validation to prevent:
- KeyError exceptions on missing fields
- API contract violations during testing
- Response format regressions

Usage:
    response = await async_client.get("/api/v1/agents")
    agent_data = validate_response(response, "agent")  # Auto-validates schema

    list_response = await async_client.get("/api/v1/agents/")
    agents = validate_response(response, "agent_list")
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Type


class ResponseSchema(Enum):
    """Define expected response schemas for each API endpoint type"""

    # Agent endpoints
    AGENT = {
        "required": ["id", "name"],
        "optional": [
            "type",
            "status",
            "category",
            "capabilities",
            "created_at",
            "tenant_id",
            "model",
            "description",
        ],
    }
    AGENT_CREATION = {
        "required": ["id", "agent_id", "success", "message"],
        "optional": ["timestamp"],
    }
    AGENT_LIST = {
        "required": ["agents"],
        "optional": ["total", "page", "limit", "total_count", "data"],
    }

    # Workflow endpoints
    WORKFLOW = {
        "required": ["id", "name"],
        "optional": ["status", "created_by", "created_at", "steps", "description"],
    }
    WORKFLOW_LIST = {"required": ["data"], "optional": ["total", "page", "limit"]}

    # User endpoints
    USER = {
        "required": ["id", "email"],
        "optional": ["tenant_id", "roles", "is_active", "created_at", "full_name"],
    }
    USER_LIST = {"required": ["data"], "optional": ["total", "page", "limit"]}

    # Tool/Resource endpoints
    TOOL = {
        "required": ["id", "name"],
        "optional": ["type", "status", "capabilities", "created_at"],
    }
    TOOL_LIST = {"required": ["data"], "optional": ["total", "page", "limit"]}

    # Tenant endpoints
    TENANT = {
        "required": ["id", "name"],
        "optional": ["subdomain", "contact_email", "created_at"],
    }
    TENANT_LIST = {"required": ["data"], "optional": ["total", "page", "limit"]}

    # Execution/Task results
    EXECUTION_RESULT = {
        "required": ["status"],
        "optional": [
            "result",
            "response",
            "session_id",
            "execution_id",
            "error",
            "workflow_id",
            "message",
            "input_data",
            "output_data",
            "start_time",
            "end_time",
            "duration",
            "tasks_completed",
            "tasks_failed",
            "tasks_total",
            "error_message",
        ],
    }

    # Routing/Query results (old agent routing)
    ROUTING_RESULT = {
        "required": ["selected_agent"],
        "optional": ["confidence", "reason"],
    }

    # Agentic routing decision (new /agentic/route endpoint)
    AGENTIC_ROUTING = {
        "required": ["category", "priority", "suggested_model", "reasoning"],
        "optional": [],
    }

    # Agentic execution result (new /agentic/request endpoint)
    AGENTIC_EXECUTION = {
        "required": ["query", "decision", "result", "executed_by"],
        "optional": [],
    }

    # Error & Success responses
    ERROR = {"required": ["error", "detail"], "optional": ["status_code", "request_id"]}
    SUCCESS = {"required": ["message"], "optional": ["data", "code"]}

    # Authentication responses
    AUTH_TOKEN = {
        "required": ["access_token", "token_type"],
        "optional": ["refresh_token", "expires_in", "user", "scope"],
    }


@dataclass
class ResponseValidationError(Exception):
    """Raised when response doesn't match expected schema"""

    endpoint: str
    expected_schema: str
    actual_response: Dict
    missing_fields: List[str]
    extra_fields: List[str]

    def __str__(self) -> str:
        msg = f"\n{'='*70}\n"
        msg += "❌ RESPONSE VALIDATION FAILED\n"
        msg += f"Endpoint: {self.endpoint}\n"
        msg += f"Expected Schema: {self.expected_schema}\n\n"

        if self.missing_fields:
            msg += f"❌ MISSING REQUIRED FIELDS: {self.missing_fields}\n"

        if self.extra_fields:
            msg += f"⚠️  UNEXPECTED FIELDS (may cause KeyError): {self.extra_fields}\n"

        msg += f"\nActual Response:\n{json.dumps(self.actual_response, indent=2)}\n"
        msg += f"{'='*70}\n"
        return msg


def validate_response(
    response: Any, schema_type: str, endpoint: str = "unknown", strict: bool = True
) -> Dict:
    """
    Validate API response against expected schema.

    Args:
        response: httpx.Response object
        schema_type: ResponseSchema enum name (e.g., "agent", "user_list")
        endpoint: API endpoint path (for error reporting)
        strict: If True, fail on extra fields; if False, only warn

    Returns:
        Parsed JSON response if valid

    Raises:
        ResponseValidationError: If response doesn't match schema

    Example:
        response = await client.get("/api/v1/agents/123")
        agent = validate_response(response, "agent", endpoint="/api/v1/agents/123")
        assert agent["id"] == 123  # Safe - field validated
    """

    # Get response data
    try:
        response_data = response.json()
    except json.JSONDecodeError as e:
        raise ResponseValidationError(
            endpoint=endpoint,
            expected_schema=schema_type,
            actual_response={"error": f"Invalid JSON: {str(e)}"},
            missing_fields=[],
            extra_fields=[],
        )

    # Handle list responses (unwrap if needed)
    if isinstance(response_data, list):
        response_data = {"data": response_data}

    # Get schema definition
    schema_name = schema_type.upper()
    if not hasattr(ResponseSchema, schema_name):
        raise ValueError(
            f"Unknown schema type: {schema_type}. Must be one of {[e.name.lower() for e in ResponseSchema]}"
        )

    schema = getattr(ResponseSchema, schema_name).value
    required_fields = schema.get("required", [])
    optional_fields = schema.get("optional", [])
    allowed_fields = set(required_fields + optional_fields)

    # Validate required fields
    missing = [f for f in required_fields if f not in response_data]
    if missing:
        raise ResponseValidationError(
            endpoint=endpoint,
            expected_schema=schema_type,
            actual_response=response_data,
            missing_fields=missing,
            extra_fields=[],
        )

    # Check for unexpected fields
    actual_fields = set(response_data.keys())
    extra = list(actual_fields - allowed_fields)

    if strict and extra:
        # Strict mode: fail on extra fields
        raise ResponseValidationError(
            endpoint=endpoint,
            expected_schema=schema_type,
            actual_response=response_data,
            missing_fields=[],
            extra_fields=extra,
        )
    elif extra:
        # Warning mode: log but don't fail
        print(f"⚠️  [VALIDATE] Unexpected fields in {schema_type} response: {extra}")

    return response_data


def assert_response_ok(response: Any, endpoint: str = "unknown") -> Dict:
    """
    Quick validation that response is 2xx and contains valid JSON.

    Args:
        response: httpx.Response object
        endpoint: API endpoint path (for error reporting)

    Returns:
        Parsed JSON response
    """
    assert (
        response.status_code >= 200 and response.status_code < 300
    ), f"Expected 2xx status, got {response.status_code} from {endpoint}\n{response.text}"

    try:
        return response.json()
    except json.JSONDecodeError:
        raise AssertionError(f"Response is not valid JSON from {endpoint}\n{response.text}")


def assert_response_error(
    response: Any, expected_status: int = 400, endpoint: str = "unknown"
) -> Dict:
    """
    Validate that response is an error with expected status.

    Args:
        response: httpx.Response object
        expected_status: Expected HTTP error status
        endpoint: API endpoint path (for error reporting)

    Returns:
        Parsed error response
    """
    assert (
        response.status_code == expected_status
    ), f"Expected {expected_status}, got {response.status_code} from {endpoint}"

    error_data = validate_response(response, "error", endpoint=endpoint, strict=False)
    return error_data


# ============================================================================
# Schema Registry - Extensible for new endpoints
# ============================================================================

RESPONSE_SCHEMAS = {
    # Auth endpoints
    "/api/v1/auth/login": ResponseSchema.AUTH_TOKEN,
    "/api/v1/auth/token": ResponseSchema.AUTH_TOKEN,
    "/api/v1/auth/refresh": ResponseSchema.AUTH_TOKEN,
    # Agent endpoints
    "/api/v1/agents": ResponseSchema.AGENT_LIST,
    "/api/v1/agents/": ResponseSchema.AGENT_LIST,
    "/api/v1/agents/{agent_id}": ResponseSchema.AGENT,
    "/api/v1/agents/route": ResponseSchema.ROUTING_RESULT,
    "/api/v1/agents/execute": ResponseSchema.EXECUTION_RESULT,
    # Workflow endpoints
    "/api/v1/workflows": ResponseSchema.WORKFLOW_LIST,
    "/api/v1/workflows/": ResponseSchema.WORKFLOW_LIST,
    "/api/v1/workflows/{workflow_id}": ResponseSchema.WORKFLOW,
    # User endpoints
    "/api/v1/users": ResponseSchema.USER_LIST,
    "/api/v1/users/": ResponseSchema.USER_LIST,
    "/api/v1/users/{user_id}": ResponseSchema.USER,
    # Tenant endpoints
    "/api/v1/tenants": ResponseSchema.TENANT_LIST,
    "/api/v1/tenants/": ResponseSchema.TENANT_LIST,
    "/api/v1/tenants/{tenant_id}": ResponseSchema.TENANT,
}


def get_expected_schema(endpoint: str) -> Optional[str]:
    """Get expected response schema for an endpoint pattern"""
    # Try exact match first
    if endpoint in RESPONSE_SCHEMAS:
        return RESPONSE_SCHEMAS[endpoint].name.lower()

    # Try pattern match (e.g., /api/v1/agents/{id})
    for pattern, schema in RESPONSE_SCHEMAS.items():
        if pattern.replace("{", "").replace("}", "").replace("_id", "") in endpoint:
            return schema.name.lower()

    return None
