"""
ActivePieces Webhook Handlers

Handles webhooks from ActivePieces for:
- Flow execution events (started, completed, failed)
- Connection status changes
- Piece updates

Secured by HMAC signature verification.
"""

from datetime import datetime, timezone
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.dependencies import verify_activepieces_signature
from src.core.activepieces.repositories import (
    ActivePiecesConnectionRepository,
    ActivePiecesFlowRepository,
    ActivePiecesFlowRunRepository,
    ActivePiecesSyncLogRepository,
)
from src.core.api.dependencies import require_admin_user
from src.core.auth.api_deps import UserResponse
from src.core.api.webhooks.dependencies import get_db

router = APIRouter(prefix="/webhooks/activepieces", tags=["Webhooks"])


async def _resolve_execution_tenant_id(
    event: "ExecutionEvent",
    db: AsyncSession | None,
) -> int | None:
    """Resolve tenant from the stored flow reference instead of trusting webhook payload."""
    if not db:
        return None

    flow_repo = ActivePiecesFlowRepository(db)
    flow = await flow_repo.get_by_ap_flow_reference(event.flow_id, event.project_id)
    if not flow:
        logger.warning(
            "No tenant-bound flow found for ActivePieces execution webhook: {} / {}",
            event.flow_id,
            event.project_id,
        )
        return None

    return int(flow.tenant_id) if flow.tenant_id is not None else None


async def _resolve_connection_tenant_id(
    event: "ConnectionEvent",
    db: AsyncSession | None,
) -> int | None:
    """Resolve tenant from the stored connection reference instead of trusting webhook payload."""
    if not db:
        return None

    conn_repo = ActivePiecesConnectionRepository(db)
    connection = await conn_repo.get_by_ap_connection_reference(
        event.connection_id,
        event.project_id,
    )
    if not connection:
        logger.warning(
            "No tenant-bound connection found for ActivePieces webhook: {} / {}",
            event.connection_id,
            event.project_id,
        )
        return None

    return int(connection.tenant_id) if connection.tenant_id is not None else None


# =============================================================================
# Event Models
# =============================================================================


class ExecutionEvent(BaseModel):
    """Flow execution event from ActivePieces"""

    event_type: str = Field(..., alias="type")
    flow_id: str = Field(..., alias="flowId")
    run_id: str = Field(..., alias="runId")
    project_id: str = Field(..., alias="projectId")
    status: str
    start_time: datetime | None = Field(None, alias="startTime")
    finish_time: datetime | None = Field(None, alias="finishTime")
    duration: float | None = None
    payload: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = Field(None, alias="errorMessage")
    # GEEN `tenant_id`. Dit is een REQUEST BODY van een externe dienst, en CLAUDE.md is
    # daar absoluut over: de klant komt nooit uit de payload. Hij werd hier al niet
    # vertrouwd -- `_resolve_execution_tenant_id` haalt hem uit de opgeslagen flow -- maar
    # het veld stond er wel, en dook in DRIE logregels op als `tenant_id or
    # event.tenant_id`. Verwijderd 2026-09-18: een waarde die je toch niet mag geloven,
    # hoor je niet aan te nemen.


class ConnectionEvent(BaseModel):
    """Connection status event from ActivePieces"""

    event_type: str = Field(..., alias="type")
    connection_id: str = Field(..., alias="connectionId")
    app_name: str = Field(..., alias="appName")
    project_id: str = Field(..., alias="projectId")
    status: str  # connected, disconnected, error
    error_message: str | None = Field(None, alias="errorMessage")


class PieceEvent(BaseModel):
    """Piece update event from ActivePieces"""

    event_type: str = Field(..., alias="type")
    piece_name: str = Field(..., alias="pieceName")
    version: str
    action: str  # updated, deprecated, removed


# =============================================================================
# Event Handlers
# =============================================================================


async def handle_execution_started(
    event: ExecutionEvent,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> None:
    """Handle flow execution started event"""
    logger.info(
        "Flow execution started",
        flow_id=event.flow_id,
        run_id=event.run_id,
        tenant_id=tenant_id,
    )

    if not db or not tenant_id:
        logger.debug("No database session or tenant_id, skipping DB update")
        return

    try:
        # Find flow by AP flow ID
        flow_repo = ActivePiecesFlowRepository(db)
        flow = await flow_repo.get_by_ap_flow_id(tenant_id, event.flow_id)

        if not flow:
            logger.warning("Flow not found for AP flow ID: {}", event.flow_id)
            return

        # Create flow run record
        run_repo = ActivePiecesFlowRunRepository(db)
        run = await run_repo.create(
            tenant_id=tenant_id,
            flow_id=flow.id,
            ap_run_id=event.run_id,
            project_id=event.project_id,
            status="RUNNING",
            payload={
                "trigger_type": "webhook",
            },
        )

        await db.commit()
        logger.info("Created flow run {} for AP run {}", run.id, event.run_id)

    except Exception as e:
        logger.error("Failed to handle execution started: {}", e)
        raise


async def handle_execution_completed(
    event: ExecutionEvent,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> None:
    """Handle flow execution completed event"""
    logger.info(
        "Flow execution completed",
        flow_id=event.flow_id,
        run_id=event.run_id,
        status=event.status,
        duration=event.duration,
        tenant_id=tenant_id,
    )

    if not db or not tenant_id:
        logger.debug("No database session or tenant_id, skipping DB update")
        return

    try:
        # Find flow run by AP run ID, then update by internal ID
        run_repo = ActivePiecesFlowRunRepository(db)
        existing_run = await run_repo.get_by_ap_run_id(tenant_id, event.run_id)

        if existing_run:
            normalized_status = event.status.upper()
            await run_repo.update_status(
                tenant_id=tenant_id,
                run_id=existing_run.id,
                status=normalized_status,
                output=event.payload if normalized_status in {"SUCCESS", "SUCCEEDED"} else None,
                error_message=(
                    event.error_message if normalized_status in {"FAILED", "FAILURE"} else None
                ),
                duration_ms=int(event.duration * 1000) if event.duration else None,
            )
            await db.commit()
            logger.info("Updated flow run {} with status {}", event.run_id, normalized_status)
        else:
            logger.warning("Flow run not found: {}", event.run_id)

    except Exception as e:
        logger.error("Failed to handle execution completed: {}", e)
        raise


async def handle_execution_failed(
    event: ExecutionEvent,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> None:
    """Handle flow execution failed event"""
    logger.error(
        "Flow execution failed",
        flow_id=event.flow_id,
        run_id=event.run_id,
        error=event.error_message,
        tenant_id=tenant_id,
    )

    if not db or not tenant_id:
        logger.debug("No database session or tenant_id, skipping DB update")
        return

    try:
        # Find flow run by AP run ID, then update by internal ID
        run_repo = ActivePiecesFlowRunRepository(db)
        existing_run = await run_repo.get_by_ap_run_id(tenant_id, event.run_id)

        if existing_run:
            await run_repo.update_status(
                tenant_id=tenant_id,
                run_id=existing_run.id,
                status="FAILED",
                error_message=event.error_message,
                duration_ms=int(event.duration * 1000) if event.duration else None,
            )
            await db.commit()
            logger.info("Updated flow run {} with failed status", event.run_id)
        else:
            logger.warning("Flow run not found: {}", event.run_id)

    except Exception as e:
        logger.error("Failed to handle execution failed: {}", e)
        raise


async def handle_connection_status_changed(
    event: ConnectionEvent,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> None:
    """Handle connection status change"""
    logger.info(
        "Connection status changed",
        connection_id=event.connection_id,
        app_name=event.app_name,
        status=event.status,
    )

    if not db or not tenant_id:
        logger.debug("No database session or tenant_id, skipping DB update")
        return

    try:
        # Update connection status in database
        conn_repo = ActivePiecesConnectionRepository(db)
        connection = await conn_repo.get_by_ap_connection_id(tenant_id, event.connection_id)

        if connection:
            await conn_repo.update(
                tenant_id=tenant_id,
                connection_id=connection.id,
                status=event.status,
            )
            if event.status == "error" and event.error_message:
                connection.last_error_at = datetime.now(timezone.utc)
                connection.last_error_message = event.error_message
            await db.commit()
            logger.info("Updated connection {} status to {}", event.connection_id, event.status)
        else:
            logger.warning("Connection not found: {}", event.connection_id)

        if event.status == "error":
            logger.warning("Connection error for {}: {}", event.app_name, event.error_message)

    except Exception as e:
        logger.error("Failed to handle connection status change: {}", e)
        raise


async def handle_piece_updated(
    event: PieceEvent,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
) -> None:
    """Handle piece update event"""
    logger.info(
        "Piece updated",
        piece_name=event.piece_name,
        version=event.version,
        action=event.action,
    )

    if not db or not tenant_id:
        logger.debug("No database session or tenant_id, skipping DB update")
        return

    try:
        # Log piece update to sync logs
        sync_repo = ActivePiecesSyncLogRepository(db)
        await sync_repo.create(
            tenant_id=tenant_id,
            sync_type=f"piece_update:{event.piece_name}",
            status="success",
            items_synced=1,
        )
        await db.commit()

        if event.action == "deprecated":
            logger.warning("Piece {} deprecated", event.piece_name)

    except Exception as e:
        logger.error("Failed to handle piece update: {}", e)
        raise


# =============================================================================
# Webhook Endpoints
# =============================================================================


@router.post(
    "",
    dependencies=[Depends(verify_activepieces_signature)],
    summary="ActivePieces webhook handler",
    description="Handles all webhook events from ActivePieces.",
)
async def activepieces_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Handle ActivePieces webhooks.
    Secured by HMAC signature verification.
    """
    try:
        payload: dict[str, Any] = cast(  # TODO(TYPE): replace Any with concrete type
            dict[str, Any], await request.json()  # TODO(TYPE): replace Any with concrete type
        )  # TODO(TYPE): replace Any with concrete type
        event_type: str = cast(str, payload.get("type", "unknown"))

        logger.info("Received ActivePieces webhook: {}", event_type)

        # Route to appropriate handler
        if event_type == "execution.started":
            execution_event = ExecutionEvent(**payload)
            tenant_id = await _resolve_execution_tenant_id(execution_event, db)
            await handle_execution_started(execution_event, db, tenant_id)

        elif event_type == "execution.completed":
            execution_event = ExecutionEvent(**payload)
            tenant_id = await _resolve_execution_tenant_id(execution_event, db)
            await handle_execution_completed(execution_event, db, tenant_id)

        elif event_type == "execution.failed":
            execution_event = ExecutionEvent(**payload)
            tenant_id = await _resolve_execution_tenant_id(execution_event, db)
            await handle_execution_failed(execution_event, db, tenant_id)

        elif event_type == "connection.status_changed":
            connection_event = ConnectionEvent(**payload)
            tenant_id = await _resolve_connection_tenant_id(connection_event, db)
            await handle_connection_status_changed(connection_event, db, tenant_id)

        elif event_type == "piece.updated":
            piece_event = PieceEvent(**payload)
            await handle_piece_updated(piece_event, db, None)

        else:
            logger.warning("Unknown webhook event type: {}", event_type)
            # Still return success to acknowledge receipt

        return {"status": "success", "message": "Webhook processed"}

    except Exception as e:
        logger.error("Error processing ActivePieces webhook: {}", e)
        # Return 200 to prevent ActivePieces from retrying indefinitely
        # Log error for internal investigation
        return {"status": "error", "message": "Internal processing error"}


@router.post(
    "/execution-completed",
    dependencies=[Depends(verify_activepieces_signature)],
    summary="Execution completed webhook",
    description="Specific endpoint for execution completed events.",
)
async def execution_completed_webhook(
    event: ExecutionEvent,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Dedicated endpoint for execution completed events."""
    tenant_id = await _resolve_execution_tenant_id(event, db)
    await handle_execution_completed(event, db, tenant_id)
    return {"status": "success"}


@router.post(
    "/execution-failed",
    dependencies=[Depends(verify_activepieces_signature)],
    summary="Execution failed webhook",
    description="Specific endpoint for execution failed events.",
)
async def execution_failed_webhook(
    event: ExecutionEvent,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Dedicated endpoint for execution failed events."""
    tenant_id = await _resolve_execution_tenant_id(event, db)
    await handle_execution_failed(event, db, tenant_id)
    return {"status": "success"}


@router.post(
    "/test",
    summary="Test webhook endpoint",
    description="Test endpoint that logs the payload without processing.",
)
async def test_webhook(
    request: Request,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Test webhook - logs payload without verification."""
    payload: Any = await request.json()  # TODO(TYPE): replace Any with concrete type
    logger.info("Test webhook received: {}", payload)
    return {"status": "success", "received": payload}


# =============================================================================
# Webhook Configuration
# =============================================================================


@router.get(
    "/config",
    summary="Get webhook configuration",
    description="Get the webhook URL to configure in ActivePieces.",
)
async def get_webhook_config(
    _beheerder: UserResponse = Depends(require_admin_user),  # rolcontrole: beheerder (403)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get webhook configuration for ActivePieces setup."""
    from src.core.config.unified_config import config

    # Construct base URL from config
    host = config.api_host if config.api_host != "0.0.0.0" else "localhost"  # nosec B104
    port = config.api_port if config.api_port != 80 else ""
    base_url = f"http://{host}{':' + str(port) if port else ''}"

    return {
        "webhook_url": f"{base_url}/api/v1/webhooks/activepieces",
        "events_supported": [
            "execution.started",
            "execution.completed",
            "execution.failed",
            "connection.status_changed",
            "piece.updated",
        ],
        "signature_header": "X-AP-Signature",
        "signature_method": "HMAC-SHA256",
        "signature_format": "hex",
    }
