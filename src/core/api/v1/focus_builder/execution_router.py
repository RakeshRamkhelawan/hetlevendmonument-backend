"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
FocusBuilder Flow Execution sub-router (ADR-033 Laag 1).

Routes:
- POST /flows/{flow_id}/execute
- GET /flows/{flow_id}/runs/latest
- GET /runs/{run_id}
"""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

if TYPE_CHECKING:
    from src.core.api.v1.focus_builder.dependencies import AgentCouncil  # own-domain -- ADR-033
    from src.domains.flows.service import FocusBuilderService
from loguru import logger

from src.core.api.v1.focus_builder.shared import (
    _track_focus_builder_action,
    create_error_response,
    enrich_span,
    get_focus_builder_service,
    limiter,
)
from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
from src.core.activepieces.stappencontrole import NietToegestaneStap
from src.core.exceptions.exceptions import SanskritiError
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency,
    require_resource_permission,
)

execution_router = APIRouter()


@execution_router.post("/flows/{flow_id}/execute", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def execute_flow(
    request: Request,
    response: Response,
    flow_id: int,
    payload: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
    council: "AgentCouncil" = Depends(get_focus_builder_council),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Execute a flow via ActivePieces.

    Passes through an AgentCouncil governance check before delegating to
    ActivePieces. Blocked or policy-violating flows return HTTP 403.
    Rate limit: 5 requests per minute (resource-intensive).
    """
    enrich_span(request, current_user.id, operation="execute_flow", flow_id=flow_id)
    logger.info("execute_flow_request", user_id=current_user.id, flow_id=flow_id)

    from src.core.api.v1.focus_builder.dependencies import (  # own-domain -- ADR-033
        DataClassification,
        DecisionVerdict,
        Proposal,
        ProposalTrigger,
    )

    inputs = payload or {}
    proposal = Proposal(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="focus_builder.execute_flow",
        action_params={
            "flow_id": str(flow_id),
            "input_keys": list(inputs.keys()),
        },
        reasoning="User requested flow execution via Focus Builder UI.",
        data_classification=DataClassification.INTERNAL,
        confidence=1.0,
        model_id="focus_builder",
        model_version="1.0",
        context_snapshot={"flow_id": str(flow_id)},
    )
    try:
        decision = await council.deliberate(proposal)
    except Exception as council_error:
        logger.error(
            "execute_flow.council_error: %s: %s",
            type(council_error).__name__,
            council_error,
            exc_info=True,
            extra={"tenant_id": current_user.tenant_id, "flow_id": flow_id},
        )
        raise HTTPException(
            status_code=500,
            detail=create_error_response("COUNCIL_UNAVAILABLE", "Governance check failed"),
        )

    if decision.verdict != DecisionVerdict.APPROVED:
        logger.warning(
            "execute_flow.council_blocked",
            extra={
                "tenant_id": current_user.tenant_id,
                "user_id": current_user.id,
                "flow_id": flow_id,
                "verdict": decision.verdict.value,
            },
        )

        # ADR-036 OP-167 (sprint dag 2): tot deze fix behandelde deze route HITL_REQUIRED
        # identiek aan BLOCKED -- geen ticket, geen mens werd ooit gevraagd (AI Act art.
        # 14). `hitl_request_id` is None zodra er geen ticket kon worden aangemaakt
        # (geen HITL_REQUIRED-verdict, of een weigering door create_hitl_request zelf) --
        # additieve sleutel, geen wijziging aan het bestaande foutcontract.
        hitl_ticket_ref: str | None = None
        if decision.verdict is DecisionVerdict.HITL_REQUIRED:
            import importlib

            hitl_repository = importlib.import_module("src.core.tool_broker.hitl_repository")
            try:
                hitl_ticket_ref = await hitl_repository.HITLTicketRepository(
                    service.db
                ).create_hitl_request(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    decision_id=str(decision.decision_id),
                    reason=decision.explanation_for_user,
                    action_type=proposal.action_type,
                    action_params=dict(proposal.action_params),
                )
            except (ValueError, PermissionError) as exc:
                logger.warning(
                    "execute_flow.hitl_ticket_refused tenant=%s flow_id=%s: %s: %s",
                    current_user.tenant_id,
                    flow_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                hitl_ticket_ref = None
            else:
                # ADR-036 OP-167-vervolg (dag 4, gevonden door de feature-doc-reviewer):
                # `create_hitl_request()` doet zelf alleen `add()` + `flush()`, nooit
                # `commit()`. Zonder deze commit hier zou de meteen volgende
                # `raise HTTPException` hieronder propageren tot in
                # `database.py::get_db()`'s `except Exception: await session.rollback()`, wat
                # het net geflushte ticket ONGEDAAN maakt voordat het ooit op schijf staat.
                # Alleen op het succespad: bij een geweigerde aanmaak (except hierboven) is
                # er niets te bewaren.
                await service.db.commit()

        raise HTTPException(
            status_code=403,
            detail={
                "code": "FLOW_BLOCKED_BY_COUNCIL",
                "reason": decision.explanation_for_user or "Governance policy violation",
                "decision_id": str(decision.decision_id),
                "hitl_request_id": hitl_ticket_ref,
            },
        )

    try:
        result = await service.execute_flow(flow_id, inputs)
        enrich_span(request, current_user.id, execution_status="triggered")
        logger.info(
            "execute_flow_completed",
            user_id=current_user.id,
            flow_id=flow_id,
            execution_id=result.get("execution_id"),
        )
        await _track_focus_builder_action(
            db=service.db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            session_id=request.headers.get("x-session-id", f"fb_{current_user.id}"),
            behavior_type="focus_builder.flow_executed",
            context={"flow_id": flow_id, "execution_id": result.get("execution_id")},
        )
        return result
    except NietToegestaneStap as e:
        raise HTTPException(
            status_code=422, detail=create_error_response("STEP_NOT_ALLOWED", str(e))
        ) from e
    except ValueError as e:
        logger.warning(
            "execute_flow_value_error",
            user_id=current_user.id,
            flow_id=flow_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=400, detail=create_error_response("EXECUTION_ERROR", "Ongeldig verzoek.")
        )
    except Exception as e:
        logger.error(
            "execute_flow_unexpected_error",
            user_id=current_user.id,
            flow_id=flow_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=create_error_response("EXECUTION_FAILED", "Flow execution failed"),
        )


@execution_router.get("/flows/{flow_id}/runs/latest")
@limiter.limit("30/minute")
async def get_latest_run(
    request: Request,
    response: Response,
    flow_id: int,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get the latest run status for a flow.
    Rate limit: 30 requests per minute.
    """
    enrich_span(request, current_user.id, operation="get_latest_run", flow_id=flow_id)
    logger.debug("get_latest_run_request", user_id=current_user.id, flow_id=flow_id)

    flow = await service.repository.get(flow_id)
    if not flow:
        raise HTTPException(
            status_code=404,
            detail=create_error_response("FLOW_NOT_FOUND", f"Flow {flow_id} not found"),
        )

    if not flow.activepieces_flow_id:
        return {
            "status": "NOT_SYNCED",
            "message": "Flow not synced to automation engine",
        }

    try:
        runs = await (await service.ap_client()).list_runs(flow.activepieces_flow_id, limit=1)
        if runs:
            return runs[0]
        return {"status": "NO_RUNS", "message": "No executions found"}
    except SanskritiError:
        raise
    except Exception as e:
        logger.warning("get_latest_run_error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"status": "UNKNOWN", "error": "Could not fetch run status"}


@execution_router.get("/runs/{run_id}")
@limiter.limit("30/minute")
async def get_run_logs(
    request: Request,
    response: Response,
    run_id: str,
    service: "FocusBuilderService" = Depends(get_focus_builder_service),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get detailed logs for a specific run.
    Rate limit: 30 requests per minute.
    """
    enrich_span(request, current_user.id, operation="get_run_logs", run_id=run_id)
    logger.debug("get_run_logs_request", user_id=current_user.id, run_id=run_id)
    try:
        run_logs = await (await service.ap_client()).get_run_logs(run_id)
        return run_logs
    except SanskritiError:
        raise
    except Exception as e:
        logger.error("get_run_logs_error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"error": "Could not fetch run logs"}
