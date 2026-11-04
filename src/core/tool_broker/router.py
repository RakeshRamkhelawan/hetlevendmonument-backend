#!/usr/bin/env python3
"""
Tool Broker Router with JWT Authentication and Resilience

Provides endpoints for:
- Tool execution (protected)
- Health checks
- Resilience monitoring (circuit breaker, retry stats)
- Token generation (for development/testing)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database.database import get_db
from src.core.tool_broker.hitl_repository import HITLTicketRepository
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.auth.dependencies import get_optional_user_dependency as get_optional_user
from src.core.tool_broker.exceptions import (
    ToolExecutionException,
    ToolNotFoundException,
    ValidationException,
)
from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel
from src.core.tool_broker.schemas import (
    ErrorResponse,
    HealthCheckResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolHITLRequest,
)
from src.core.tool_broker.dependencies import get_tool_broker_service
from src.core.tool_broker.service import ToolBrokerService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tools",
    tags=["Tool Broker"],
)


@router.post(
    "/execute",
    response_model=ToolExecutionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid tool or parameters"},
        401: {
            "model": ErrorResponse,
            "description": "Unauthorized - invalid or missing token",
        },
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - insufficient permissions",
        },
        404: {"model": ErrorResponse, "description": "Tool not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "External service unavailable"},
        504: {"model": ErrorResponse, "description": "External service timeout"},
    },
)
async def execute_tool(
    request: ToolExecutionRequest,
    service: ToolBrokerService = Depends(get_tool_broker_service),
    current_user: UserResponse = Depends(get_current_user),
) -> ToolExecutionResponse:
    """
    Execute a tool via the Tool Broker Service

    **Security:**
    - Requires valid JWT token in Authorization header
    - Requires 'tool:execute' scope
    - User must be authenticated

    **Resilience:**
    - Automatic retry with exponential backoff (3 attempts)
    - Circuit breaker protection for cascading failures
    - Graceful error handling with detailed status codes

    **Parameters:**
    - tool_name: Either 'serena' or 'sequential_thinking'
    - sub_tool: Specific tool name (e.g., 'find_symbol')
    - params: Tool-specific parameters
    - timeout_seconds: Optional execution timeout
    - request_id: Optional tracing ID

    **Returns:**
    - ToolExecutionResponse with execution result or error details

    **Example Request:**
    ```json
    {
        "tool_name": "serena",
        "sub_tool": "find_symbol",
        "params": {"name": "my_function", "file": "main.py"},
        "timeout_seconds": 30,
        "request_id": "req_12345"
    }
    ```
    """
    start_time = time.time()
    request_id = request.request_id or f"req_{int(time.time() * 1000)}"

    try:
        # Log tool execution attempt
        logger.info(
            f"Tool execution requested: {request.tool_name.value}__{request.sub_tool}",
            extra={
                "request_id": request_id,
                "user": current_user.email,
                "tool": request.tool_name.value,
                "sub_tool": request.sub_tool,
            },
        )

        # Validate user has tool execution permission
        if "tool:execute" not in current_user.scopes:
            logger.warning(
                f"User {current_user.email} attempted tool execution without permission",
                extra={
                    "request_id": request_id,
                    "available_scopes": current_user.scopes,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required scope: tool:execute",
            )

        # Construct full tool name: tool_name__sub_tool (e.g., serena__find_symbol)
        full_tool_name = f"{request.tool_name.value}__{request.sub_tool}"

        # Execute tool
        result = await service.execute_tool(
            full_tool_name, request.params, timeout_seconds=request.timeout_seconds
        )

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Tool execution successful",
            extra={
                "request_id": request_id,
                "tool": request.tool_name.value,
                "execution_time_ms": execution_time_ms,
            },
        )

        return ToolExecutionResponse(
            success=True,
            result=result,
            execution_time_ms=execution_time_ms,
            request_id=request_id,
        )

    except ToolNotFoundException as e:
        logger.error(f"Tool not found: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))

    except ValidationException as e:
        logger.warning(f"Validation error: {str(e)}", extra={"request_id": request_id})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e.detail))

    except ToolExecutionException as e:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(
            f"Tool execution failed: {str(e)}",
            extra={"request_id": request_id, "execution_time_ms": execution_time_ms},
        )
        status_code = getattr(e, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        raise HTTPException(status_code=status_code, detail=str(e.detail))

    except HTTPException:
        raise

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(
            f"Unexpected error: {str(e)}",
            extra={"request_id": request_id, "execution_time_ms": execution_time_ms},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during tool execution",
        )


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
)
async def health_check(
    current_user: UserResponse | None = Depends(get_optional_user),
) -> HealthCheckResponse:
    """
    Health check endpoint for monitoring

    **Security:**
    - Optional authentication (works with or without token)
    - Can be used by monitoring systems

    **Returns:**
    - Service status and component health
    """
    logger.debug(
        "Health check requested",
        extra={"user": current_user.username if current_user else "anonymous"},  # type: ignore[attr-defined]
    )

    components = {
        "serena_client": "operational",
        "sequential_thinking_client": "operational",
        "jwt_handler": "operational",
        "error_handling": "operational",
        "authentication": "operational",
        "resilience_patterns": "operational",
    }

    all_healthy = all(v == "operational" for v in components.values())
    status_str = "healthy" if all_healthy else "degraded"

    return HealthCheckResponse(
        status=status_str,
        service_name="Tool Broker Service",
        version="2.1.0",
        components=components,
    )


@router.get(
    "/status",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    tags=["Health"],
    dependencies=[Depends(get_optional_user)],
)
async def status_endpoint() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Detailed status endpoint

    Returns comprehensive service status information including
    component health and basic resilience information.
    """
    return {
        "service": "Tool Broker",
        "version": "2.1.0",
        "phase": "2.4",
        "status": "operational",
        "timestamp": time.time(),
        "features": [
            "JWT Authentication",
            "Scope-based Authorization",
            "Comprehensive Error Handling",
            "Request Tracing",
            "Health Monitoring",
            "Circuit Breaker Pattern",
            "Exponential Backoff Retry",
            "Graceful Degradation",
        ],
    }


@router.get(
    "/resilience/status",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    tags=["Resilience", "Monitoring"],
    dependencies=[Depends(get_optional_user)],
)
async def get_resilience_status(
    service: ToolBrokerService = Depends(get_tool_broker_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get detailed resilience status

    **Returns:**
    - Circuit breaker states for each client
    - Resilience metrics (retries, successes, failures)
    - Service health information

    **Example Response:**
    ```json
    {
        "resilience_enabled": True,
        "circuit_breakers": {
            "serena_client": {
                "name": "serena_client",
                "state": "closed",
                "failure_count": 0,
                "success_count": 42
            },
            "sequential_thinking_client": {
                "name": "sequential_thinking_client",
                "state": "closed",
                "failure_count": 0,
                "success_count": 38
            }
        },
        "resilience_metrics": {
            "total_calls": 80,
            "successful_calls": 80,
            "failed_calls": 0,
            "success_rate": 1.0,
            "total_retry_attempts": 2,
            "successful_retries": 2
        },
        "service_health": {
            "overall_health": "healthy",
            "is_running": True,
            "components_total": 2,
            "components_healthy": 2,
            "components_degraded": 0
        }
    }
    ```
    """
    logger.debug("Resilience status requested")
    return service.get_resilience_status()


@router.get(
    "/resilience/circuit-breakers",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    tags=["Resilience", "Monitoring"],
    dependencies=[Depends(get_optional_user)],
)
async def get_circuit_breaker_status(
    service: ToolBrokerService = Depends(get_tool_broker_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get circuit breaker states for all clients

    **Returns:**
    - State of each circuit breaker (closed, open, half-open)
    - Failure counts and thresholds
    - State change times

    **Possible States:**
    - `closed`: Normal operation, requests pass through
    - `open`: Service failing, requests rejected immediately
    - `half_open`: Testing if service recovered, limited requests allowed

    **Example Response:**
    ```json
    {
        "serena_client": {
            "name": "serena_client",
            "state": "closed",
            "failure_count": 0,
            "success_count": 42,
            "state_change_time": "2024-01-15T10:30:00"
        },
        "sequential_thinking_client": {
            "name": "sequential_thinking_client",
            "state": "closed",
            "failure_count": 0,
            "success_count": 38,
            "state_change_time": "2024-01-15T10:25:00"
        }
    }
    ```
    """
    logger.debug("Circuit breaker status requested")
    breaker_states: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for breaker_name in ["serena_client", "sequential_thinking_client"]:
        state = service.get_circuit_breaker_state(breaker_name)
        if state:
            breaker_states[breaker_name] = state

    return breaker_states


@router.get(
    "/resilience/metrics",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    tags=["Resilience", "Monitoring"],
    dependencies=[Depends(get_optional_user)],
)
async def get_resilience_metrics(
    service: ToolBrokerService = Depends(get_tool_broker_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get resilience metrics and statistics

    **Returns:**
    - Total call counts (successful, failed)
    - Success rate percentage
    - Retry statistics
    - Circuit breaker activity

    **Example Response:**
    ```json
    {
        "total_calls": 80,
        "successful_calls": 80,
        "failed_calls": 0,
        "success_rate": 1.0,
        "circuit_breaker_opens": 0,
        "circuit_breaker_resets": 0,
        "total_retry_attempts": 2,
        "successful_retries": 2,
        "retry_success_rate": 1.0
    }
    ```
    """
    logger.debug("Resilience metrics requested")
    resilience_status = service.get_resilience_status()
    return cast(dict[str, Any], resilience_status["resilience_metrics"])  # TODO(TYPE): replace Any with concrete type


# ---------------------------------------------------------------------------
# HITL (Human-in-the-Loop) endpoints
# ---------------------------------------------------------------------------

_risk_classifier = ToolRiskClassifier()


@router.post(
    "/hitl/request",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Tool is not HIGH risk"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def create_hitl_request(
    request: ToolHITLRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a HITL approval ticket for a HIGH-risk tool.

    Returns the ticket_ref that must be included in the tool execution payload
    once approved.
    """
    risk = _risk_classifier.classify(request.tool_name)
    if risk != ToolRiskLevel.HIGH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool '{request.tool_name}' is {risk.value} risk; HITL only required for HIGH risk tools",
        )

    from src.core.tool_broker.hitl_repository import generate_ticket_ref
    ticket_ref = generate_ticket_ref()
    
    # Store requested_by in payload as extra metadata, since the db columns are fixed
    payload_metadata = {
        **(request.tool_input or {}),
        # Het user-id, net als `HITLTicketRepository.create_hitl_request`: de vier-ogencontrole
        # (`hitl_router._refuse_self_approval`) vergelijkt met `str(current_user.id)`. Met het
        # e-mailadres hier werd een zelfgoedkeuring via dit pad nooit herkend.
        "_requested_by": str(current_user.id),
        "_requester_kind": "user",
        "_requested_at": datetime.now(timezone.utc).isoformat(),
        "_reason": request.reason,
        "_agent_id": request.agent_id,
        "_task_id": request.task_id,
    }

    repo = HITLTicketRepository(db)
    await repo.create(
        ticket_ref=ticket_ref,
        tenant_id=current_user.tenant_id,
        tool_name=request.tool_name,
        payload=payload_metadata,
        risk_level="HIGH",
    )
    await db.commit()

    logger.info(
        "HITL ticket created",
        extra={
            "ticket_ref": ticket_ref,
            "tool_name": request.tool_name,
            "agent_id": request.agent_id,
            "tenant_id": current_user.tenant_id,
            "user": current_user.email,
        },
    )

    # De live melding gaat na de commit hierboven vanzelf, vanuit `HITLTicketRepository.create`
    # (`_meld_na_commit`). Hier niet nog eens melden: dan krijgt de client hem twee keer.

    return {"success": True, "data": {"ticket_ref": ticket_ref, "status": "pending"}}
