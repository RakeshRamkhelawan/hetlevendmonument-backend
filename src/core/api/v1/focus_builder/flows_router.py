"""
FocusBuilder Flow CRUD sub-router (ADR-033 Laag 1).

Routes:
- POST /flows
- GET /flows
- GET /flows/{flow_id}
- PUT /flows/{flow_id}
- DELETE /flows/{flow_id}
"""
# orphan:exempt reason: single-responsibility endpoint group, size driven by FastAPI verbose response schemas (ADR-033 S4)

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.flows.service import FocusBuilderService

from src.core.api.v1.focus_builder.shared import (
    _track_focus_builder_action,
    create_error_response,
    enrich_span,
    get_focus_builder_service,
    limiter,
)
from src.core.activepieces.stappencontrole import NietToegestaneStap
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency,
    require_resource_permission,
)
from src.core.focus_builder.validators import GraphValidationError
from src.domains.flows.models import FlowCreate, FlowRead, FlowUpdate

flows_router = APIRouter()


@flows_router.post("/flows", response_model=FlowRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_flow(
    request: Request,
    response: Response,
    flow_in: FlowCreate,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_resource_permission("workflows", "publish")),
) -> FlowRead:
    """
    Create a new automation flow.
    Rate limit: 10 requests per minute.
    """
    enrich_span(request, current_user.id, operation="create_flow", flow_name=flow_in.name)
    logger.info("create_flow_request", user_id=current_user.id, flow_name=flow_in.name)
    try:
        result = await service.create_flow(
            name=flow_in.name,
            graph=flow_in.react_flow_graph,
            description=flow_in.description,
            created_by=current_user.id,
        )
        enrich_span(request, current_user.id, flow_id=result.id)
        logger.info("create_flow_completed", user_id=current_user.id, flow_id=result.id)
        await _track_focus_builder_action(
            db=service.db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            session_id=request.headers.get("x-session-id", f"fb_{current_user.id}"),
            behavior_type="focus_builder.flow_created",
            context={"flow_id": result.id, "flow_name": flow_in.name},
        )
        return FlowRead.model_validate(result)
    except NietToegestaneStap as e:
        raise HTTPException(
            status_code=422, detail=create_error_response("STEP_NOT_ALLOWED", str(e))
        ) from e
    except GraphValidationError as e:
        logger.warning("create_flow_validation_error", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=400,
            detail=create_error_response("GRAPH_VALIDATION_ERROR", str(e)),
        )
    except ValueError as e:
        logger.warning("create_flow_value_error", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=400, detail=create_error_response("VALIDATION_ERROR", "Ongeldig verzoek.")
        )
    except Exception as e:
        logger.error("create_flow_unexpected_error", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=create_error_response("INTERNAL_ERROR", "An unexpected error occurred"),
        )


@flows_router.get("/flows", response_model=list[FlowRead])
@limiter.limit("30/minute")
async def list_flows(
    request: Request,
    response: Response,
    skip: int = 0,
    limit: int = 100,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> list[FlowRead]:
    """
    List all flows for current tenant.
    Rate limit: 30 requests per minute.
    """
    enrich_span(request, current_user.id, operation="list_flows")
    logger.debug("list_flows_request", user_id=current_user.id, skip=skip, limit=limit)
    try:
        flows = await service.repository.list(skip=skip, limit=limit)
        logger.info("list_flows_completed", user_id=current_user.id, count=len(flows))
        return [FlowRead.model_validate(f) for f in flows]
    except Exception as e:
        logger.error("list_flows_error", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=create_error_response("INTERNAL_ERROR", "Failed to list flows"),
        )


@flows_router.get("/flows/{flow_id}", response_model=FlowRead)
@limiter.limit("30/minute")
async def get_flow(
    request: Request,
    response: Response,
    flow_id: int,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> FlowRead:
    """
    Get a specific flow by ID.
    Rate limit: 30 requests per minute.
    """
    enrich_span(request, current_user.id, operation="get_flow", flow_id=flow_id)
    logger.debug("get_flow_request", user_id=current_user.id, flow_id=flow_id)
    flow = await service.repository.get(flow_id)
    if not flow:
        logger.warning("get_flow_not_found", user_id=current_user.id, flow_id=flow_id)
        raise HTTPException(
            status_code=404,
            detail=create_error_response("FLOW_NOT_FOUND", f"Flow {flow_id} not found"),
        )
    return FlowRead.model_validate(flow)


@flows_router.put("/flows/{flow_id}", response_model=FlowRead)
@limiter.limit("10/minute")
async def update_flow(
    request: Request,
    response: Response,
    flow_id: int,
    flow_in: FlowUpdate,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_resource_permission("workflows", "publish")),
) -> FlowRead:
    """
    Update an existing flow.
    Rate limit: 10 requests per minute.
    """
    enrich_span(request, current_user.id, operation="update_flow", flow_id=flow_id)
    logger.info("update_flow_request", user_id=current_user.id, flow_id=flow_id)
    try:
        result = await service.update_flow(flow_id, flow_in)
        if not result:
            logger.warning("update_flow_not_found", user_id=current_user.id, flow_id=flow_id)
            raise HTTPException(
                status_code=404,
                detail=create_error_response("FLOW_NOT_FOUND", f"Flow {flow_id} not found"),
            )
        logger.info("update_flow_completed", user_id=current_user.id, flow_id=flow_id)
        await _track_focus_builder_action(
            db=service.db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            session_id=request.headers.get("x-session-id", f"fb_{current_user.id}"),
            behavior_type="focus_builder.flow_updated",
            context={"flow_id": flow_id},
        )
        return FlowRead.model_validate(result)
    except NietToegestaneStap as e:
        raise HTTPException(
            status_code=422, detail=create_error_response("STEP_NOT_ALLOWED", str(e))
        ) from e
    except GraphValidationError as e:
        logger.warning(
            "update_flow_validation_error",
            user_id=current_user.id,
            flow_id=flow_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=400,
            detail=create_error_response("GRAPH_VALIDATION_ERROR", str(e)),
        )
    except ValueError as e:
        logger.warning(
            "update_flow_value_error",
            user_id=current_user.id,
            flow_id=flow_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=400, detail=create_error_response("VALIDATION_ERROR", "Ongeldig verzoek.")
        )


@flows_router.delete("/flows/{flow_id}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def delete_flow(
    request: Request,
    response: Response,
    flow_id: int,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_resource_permission("workflows", "publish")),
) -> None:
    """
    Delete a flow.
    Rate limit: 5 requests per minute.
    """
    enrich_span(request, current_user.id, operation="delete_flow", flow_id=flow_id)
    logger.info("delete_flow_request", user_id=current_user.id, flow_id=flow_id)
    success = await service.repository.delete(flow_id)
    if not success:
        logger.warning("delete_flow_not_found", user_id=current_user.id, flow_id=flow_id)
        raise HTTPException(
            status_code=404,
            detail=create_error_response("FLOW_NOT_FOUND", f"Flow {flow_id} not found"),
        )
    logger.info("delete_flow_completed", user_id=current_user.id, flow_id=flow_id)
    await _track_focus_builder_action(
        db=service.db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        session_id=request.headers.get("x-session-id", f"fb_{current_user.id}"),
        behavior_type="focus_builder.flow_deleted",
        context={"flow_id": flow_id},
    )
