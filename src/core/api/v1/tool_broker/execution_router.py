# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tool Broker execution endpoints: execute + history."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.shared.production_logging import SafeLogger
from src.core.tool_broker.dependencies import get_tool_broker_service
from src.core.tool_broker.redaction import (
    redact_for_publication,
    safe_digest_result,
    safe_value_digest,
)
from src.core.tool_broker.service import ToolBrokerService

from src.core.api.v1.tool_broker_shared import (
    ToolExecutionHistoryItem,
    ToolExecutionRequest,
    ToolExecutionResponse,
    gebruik_van,
    tool_execution_history,
    zoek_tool,
)

logger = SafeLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["Tool Broker"])


@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(
    request: ToolExecutionRequest,
    service: ToolBrokerService = Depends(get_tool_broker_service),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> ToolExecutionResponse:
    """
    Execute a tool with provided payload.

    Requires: OAuth2Scope.AGENTS_WRITE
    """
    try:
        tool_name_lower = request.tool_name.lower()
        # Alleen een tool van DEZE klant of een meegeleverde (brief 2026-10-24): de tool van een andere klant bestaat
        # hier niet.
        tool_info = zoek_tool(current_user.tenant_id, request.tool_name)
        if not request.tool_name or tool_info is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tool '{}' not found or not available".format(request.tool_name),
            )

        logger.info("User %s executing tool: %s", current_user.id, request.tool_name)

        execution_start = datetime.now(timezone.utc)
        execution_id = "{}_{}".format(tool_name_lower, execution_start.timestamp())
        status_result = "success"
        error_msg = None
        result = None
        execution_time_ms = 0.0

        # `tool_execution_history` hieronder is de VIJFDE bewarende sink (ADR-036 OP-27): een
        # proces-globale, ongelimiteerde dict die tot de worker-recycle blijft leven (ADR-011)
        # en via GET /api/v1/tools/history/recent uitleesbaar is voor elke gebruiker van
        # dezelfde tenant met AGENTS_READ. Hij stond in de eerste telling niet, omdat de
        # architectuur-guard AANROEPEN van sinks bewaakte en dit een dict-assignment is.
        #
        # Binnen de `try`: zonder pseudonimiseringssleutel gooit dit, en dan hoort de uitvoering
        # niet te beginnen. De `finally` legt dan een lege payload vast in plaats van een rauwe.
        publish_payload: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        try:
            publish_payload = redact_for_publication(
                tool_name_lower, request.payload, tenant_id=current_user.tenant_id
            )

            result = await service.execute_tool(
                tool_name_lower,
                request.payload,
                agent_id=str(current_user.id),
                context={"tenant_id": current_user.tenant_id, "user_id": current_user.id},
            )

            execution_end = datetime.now(timezone.utc)
            execution_time_ms = (execution_end - execution_start).total_seconds() * 1000

            # Tellers per klant: op het gedeelde meegeleverde object zou klant A het gebruik van klant B zien.
            gebruik = gebruik_van(current_user.tenant_id, request.tool_name, tool_info, aanmaken=True)
            gebruik["execution_count"] += 1
            gebruik["last_used"] = execution_end.isoformat()

            return ToolExecutionResponse(
                tool_name=request.tool_name,
                status="success",
                result=result,
                timestamp=execution_end.isoformat(),
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            status_result = "failed"
            # ALLEEN het exceptietype, niet `str(e)` (ADR-036 OP-27/OP-29).
            # `ToolBrokerException` zet zijn `context` in `detail`, en Starlette rendert
            # `HTTPException.__str__` als "500: {detail}". Met `str(e)` belandde die context --
            # inclusief, tot deze commit, de rauwe payload -- in DEZELFDE regel waarvan het
            # `payload`-veld hieronder net geredigeerd is, en die regel is via
            # GET /api/v1/tools/history/recent uitleesbaar voor elke gebruiker van dezelfde
            # tenant met AGENTS_READ. Het redigeren van dat ene veld was daarmee omzeilbaar
            # door de tool te laten falen.
            error_msg = type(e).__name__
            execution_end = datetime.now(timezone.utc)
            execution_time_ms = (execution_end - execution_start).total_seconds() * 1000

            # Het volledige verhaal gaat naar het log, dat een operator-oppervlak is en geen
            # API-oppervlak.
            logger.error("Tool execution failed: %s: %s", type(e).__name__, e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Tool execution failed",
            )
        finally:
            execution_end = datetime.now(timezone.utc)
            execution_time_ms = (execution_end - execution_start).total_seconds() * 1000

            # OP-29: result/error are unfiltered tool output (file contents, model text) in a
            # process-global store readable via GET /api/v1/tools/history/recent by every user
            # of the same tenant with AGENTS_READ -- same class of risk `payload` already got
            # redacted for above. error_msg is only the exception TYPE name (never str(e), see
            # the comment above), but digested anyway to match the publish_result/publish_error
            # naming contract this history's own architecture guard expects.
            #
            # safe_digest_result (not digest_result) because this runs in a `finally`: a missing
            # pseudonymisation key already raised once inside `try` (redact_for_publication), and
            # an exception raised again HERE would replace the HTTPException(500) that's supposed
            # to propagate to the client -- Python's finally-block-exception-shadowing semantics.
            # Same failure mode as redaction.py::safe_digest_result's own docstring.
            publish_result = safe_digest_result(
                result if status_result == "success" else None,
                tenant_id=current_user.tenant_id,
            )
            publish_error = safe_value_digest(error_msg, tenant_id=current_user.tenant_id)

            tool_execution_history[execution_id] = {
                "id": execution_id,
                "tenant_id": current_user.tenant_id,
                "user_id": current_user.id,
                "tool_name": request.tool_name,
                "payload": publish_payload,
                "result": publish_result,
                "status": status_result,
                "timestamp": execution_start.isoformat(),
                "execution_time_ms": execution_time_ms,
                "error": publish_error,
                "retry_count": 0,
            }

            logger.info("Tool execution recorded: %s (%s)", execution_id, status_result)

    except HTTPException:
        raise


@router.get("/history", response_model=list[ToolExecutionHistoryItem])
async def get_execution_history_list(
    limit: int = 50,
    offset: int = 0,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> list[ToolExecutionHistoryItem]:
    """
    Get execution history for the authenticated tenant (paginated).

    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        # C-1 fix: filter by tenant
        tenant_id = current_user.tenant_id
        tenant_items = [
            item for item in tool_execution_history.values() if item.get("tenant_id") == tenant_id
        ]
        history_items = sorted(tenant_items, key=lambda x: x["timestamp"], reverse=True)

        return [
            ToolExecutionHistoryItem(
                id=item["id"],
                tool_name=item["tool_name"],
                status=item.get("status", "success"),
                execution_time_ms=item["execution_time_ms"],
                timestamp=item["timestamp"],
                retry_count=item.get("retry_count", 0),
                error=item.get("error"),
                user_id=item.get("user_id"),
            )
            for item in history_items[offset : offset + limit]
        ]

    except Exception as e:
        logger.error("Failed to get history: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get history",
        )


@router.get("/history/recent", response_model=list[dict[str, Any]])
async def get_execution_history_recent(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Get recent tool execution history for the authenticated tenant (paginated).

    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 1000",
            )

        logger.info("User %s retrieving execution history (limit=%s)", current_user.id, limit)

        # C-1 fix: filter by tenant
        tenant_id = current_user.tenant_id
        tenant_items = [
            (k, v) for k, v in tool_execution_history.items() if v.get("tenant_id") == tenant_id
        ]
        recent = sorted(tenant_items, key=lambda x: x[1]["timestamp"], reverse=True)

        # Dezelfde projectie als GET /history, en met opzet NIET de hele regel (ADR-036 OP-27).
        # De regel bevat `payload` en `result`, beide sinds OP-29 gepseudonimiseerd. Het
        # teruggeven van de payload maakte er bovendien een bevestigingsorakel van: een
        # gebruiker kon zelf een waarde insturen via POST /tools/execute en de digest daarvan
        # vergelijken met de digest in de regel van iemand anders. Dat omzeilt de
        # pseudonimisering zonder de sleutel te kennen. De vorm van de aanroep blijft
        # traceerbaar in de auditketen, die daar het aangewezen oppervlak voor is.
        return [
            {
                "id": entry["id"],
                "tool_name": entry["tool_name"],
                "status": entry.get("status", "success"),
                "execution_time_ms": entry["execution_time_ms"],
                "timestamp": entry["timestamp"],
                "retry_count": entry.get("retry_count", 0),
                "error": entry.get("error"),
                "user_id": entry.get("user_id"),
            }
            for _, entry in recent[offset : offset + limit]
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get execution history: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve execution history",
        )
