"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Canvas Export & Import API

Endpoints for exporting canvases to various formats and importing them back.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.canvas.schemas import StandardResponse
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.middleware.tenant_context import get_tenant_id
from src.domains.canvas.export_import import (
    ExportFormat,
    ImportFormat,
    canvas_exporter,
    canvas_importer,
)
from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.schemas import BlockCreate, Position, Size
from src.domains.canvas.service import CanvasService

# NOTE: router is not registered; all canvas_service.* calls below are unreachable dead code
canvas_service: Any = None

router = APIRouter(prefix="/canvas", tags=["canvas-export-import"])


# ============================================================================
# Export Endpoints
# ============================================================================


@router.get("/{canvas_id}/export", response_model=None)
async def export_canvas(
    canvas_id: UUID,
    format: ExportFormat = Query(..., description="Export format"),
    pretty: bool = Query(True, description="Pretty print JSON output"),
    include_history: bool = Query(False, description="Include revision history"),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> Response | StreamingResponse:
    """
    Export a canvas to various formats.

    Formats:
    - **json**: Native format with full data
    - **markdown**: Documentation format
    - **html**: Interactive web page
    - **svg**: Vector graphics
    - **png**: Image (placeholder)
    - **pdf**: Document (placeholder)
    """
    # CanvasService enforces tenant isolation and access control via _check_canvas_access()
    svc = CanvasService(db=db, tenant_id=tenant_id, user_id=cast(UUID, current_user.id))
    try:
        canvas = await svc.get_canvas(canvas_id)
    except PermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not found",
        )

    # Prepare canvas data for export
    canvas_data = {
        "id": str(canvas.id),
        "name": canvas.name,
        "description": canvas.description,
        "template": canvas.template,
        "version": canvas.version,
        "is_public": canvas.is_public,
        "created_at": canvas.created_at.isoformat() if canvas.created_at else None,
        "updated_at": canvas.updated_at.isoformat() if canvas.updated_at else None,
        "blocks": [],
        "connections": [],
    }

    # Get blocks
    blocks = await canvas_service.get_canvas_blocks(db, canvas_id)
    for block in blocks:
        canvas_data["blocks"].append(
            {
                "id": str(block.id),
                "type": block.type,
                "x": block.x,
                "y": block.y,
                "width": block.width,
                "height": block.height,
                "content": block.content,
                "z_index": block.z_index,
            }
        )

    # Get connections
    connections = await canvas_service.get_canvas_connections(db, canvas_id)
    for conn in connections:
        canvas_data["connections"].append(
            {
                "id": str(conn.id),
                "source_block_id": str(conn.source_block_id),
                "target_block_id": str(conn.target_block_id),
                "connection_type": conn.connection_type,
                "label": conn.label,
            }
        )

    # Export
    options = {
        "pretty": pretty,
        "include_history": include_history,
    }

    result = await canvas_exporter.export_canvas(canvas_data, format, options)

    logger.info(
        f"Exported canvas {canvas_id} to {format.value} "
        f"by user {current_user.id} ({result.size_bytes} bytes)"
    )

    # Return appropriate response based on format
    if isinstance(result.content, str):
        return Response(
            content=result.content,
            media_type=result.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
            },
        )
    else:
        return StreamingResponse(
            iter([result.content]),
            media_type=result.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
            },
        )


@router.get("/{canvas_id}/export/json", response_model=StandardResponse)
async def export_canvas_json(
    canvas_id: UUID,
    pretty: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> StandardResponse:
    """Export canvas as JSON (API response format)."""
    svc = CanvasService(db=db, tenant_id=tenant_id, user_id=cast(UUID, current_user.id))
    try:
        canvas = await svc.get_canvas(canvas_id)
    except (PermissionDeniedError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not found",
        )

    # Get full canvas data
    canvas_data = await canvas_service.get_canvas_with_blocks(db, canvas_id, tenant_id)

    return StandardResponse(
        success=True,
        data={
            "canvas": canvas_data,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
    )


# ============================================================================
# Import Endpoints
# ============================================================================


@router.post("/import", response_model=StandardResponse)
async def import_canvas(
    format: ImportFormat,
    content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> StandardResponse:
    """
    Import a canvas from various formats.

    Formats:
    - **json**: Native JSON format
    - **markdown**: Markdown with structure hints
    """
    try:
        # Import
        imported_data = await canvas_importer.import_canvas(
            content=content.get("content", ""),
            format=format,
        )

        # Override name if provided
        if name:
            imported_data["name"] = name
        elif not imported_data.get("name"):
            imported_data["name"] = (
                f"Imported Canvas {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )

        # Create canvas from imported data
        from src.domains.canvas.schemas import CanvasCreate

        canvas_create = CanvasCreate(
            name=imported_data["name"],
            template=imported_data.get("template", "blank"),
            is_public=False,
        )

        canvas = await canvas_service.create_canvas(
            db=db,
            canvas_data=canvas_create,
            owner_id=current_user.id,
            tenant_id=tenant_id,
        )

        # Add blocks
        for block_data in imported_data.get("blocks", []):
            block_create = BlockCreate(
                type=block_data.get("type", "text"),
                position=Position(
                    x=Decimal(str(block_data.get("x", 0))),
                    y=Decimal(str(block_data.get("y", 0))),
                ),
                size=Size(
                    width=Decimal(str(block_data.get("width", 200))),
                    height=Decimal(str(block_data.get("height", 100))),
                ),
                content=block_data.get("content", {}),
            )

            await canvas_service.create_block(
                db=db,
                canvas_id=canvas.id,
                block_data=block_create,
                tenant_id=tenant_id,
            )

        logger.info(f"Imported canvas {canvas.id} from {format.value} by user {current_user.id}")

        return StandardResponse(
            success=True,
            data={
                "canvas_id": str(canvas.id),
                "name": canvas.name,
                "blocks_imported": len(imported_data.get("blocks", [])),
            },
        )

    except ValueError as e:
        logger.opt(exception=True).error("import_canvas mislukt: {}", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )
    except Exception as e:
        logger.exception(f"Import error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Import failed",
        )


@router.post("/import/validate", response_model=StandardResponse)
async def validate_import(
    format: ImportFormat,
    content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """
    Validate import content without actually importing.

    Returns validation errors and preview of what would be imported.
    """
    try:
        imported_data = await canvas_importer.import_canvas(
            content=content.get("content", ""),
            format=format,
        )

        # Validate structure
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        warnings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if not imported_data.get("name"):
            warnings.append("No canvas name found, will use default")

        blocks = imported_data.get("blocks", [])
        if not blocks:
            warnings.append("No blocks found in import")

        for i, block in enumerate(blocks):
            if not block.get("type"):
                errors.append(f"Block {i}: Missing type")

        return StandardResponse(
            success=len(errors) == 0,
            error="; ".join(errors) if errors else None,
            data={
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "preview": {
                    "name": imported_data.get("name", "Untitled"),
                    "block_count": len(blocks),
                    "connection_count": len(imported_data.get("connections", [])),
                },
            },
        )

    except Exception as e:
        logger.opt(exception=True).error("validate_import mislukt: {}", type(e).__name__)
        return StandardResponse(
            success=False,
            error="Er is een fout opgetreden.",
            data={"valid": False},
        )


# ============================================================================
# Clone/Duplicate
# ============================================================================


@router.post("/{canvas_id}/clone", response_model=StandardResponse)
async def clone_canvas(
    canvas_id: UUID,
    new_name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> StandardResponse:
    """
    Create a copy of an existing canvas.

    This is a convenience endpoint that exports and re-imports
    the canvas with a new name.
    """
    # Get source canvas
    source_canvas = await canvas_service.get_canvas_with_blocks(db, canvas_id, tenant_id)

    if not source_canvas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source canvas not found",
        )

    # Prepare name
    if not new_name:
        new_name = f"{source_canvas['name']} (Copy)"

    # Create new canvas
    from src.domains.canvas.schemas import CanvasCreate

    canvas_create = CanvasCreate(
        name=new_name,
        template=source_canvas.get("template", "blank"),
        is_public=False,
    )

    new_canvas = await canvas_service.create_canvas(
        db=db,
        canvas_data=canvas_create,
        owner_id=current_user.id,
        tenant_id=tenant_id,
    )

    # Copy blocks
    for block in source_canvas.get("blocks", []):
        block_create = BlockCreate(
            type=block["type"],
            position=Position(
                x=Decimal(str(block.get("x", 0))),
                y=Decimal(str(block.get("y", 0))),
            ),
            size=Size(
                width=Decimal(str(block.get("width", 200))),
                height=Decimal(str(block.get("height", 100))),
            ),
            content=block.get("content", {}),
            z_index=block.get("z_index", 0),
        )

        await canvas_service.create_block(
            db=db,
            canvas_id=new_canvas.id,
            block_data=block_create,
            tenant_id=tenant_id,
        )

    logger.info(f"Cloned canvas {canvas_id} to {new_canvas.id} by user {current_user.id}")

    return StandardResponse(
        success=True,
        data={
            "canvas_id": str(new_canvas.id),
            "name": new_canvas.name,
            "source_canvas_id": str(canvas_id),
        },
    )


# ============================================================================
# Batch Operations
# ============================================================================


@router.post("/export/batch", response_model=None)
async def batch_export(
    canvas_ids: list[UUID],
    format: ExportFormat = ExportFormat.JSON,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> StreamingResponse:
    """
    Export multiple canvases as a zip file.

    Returns a zip archive containing all exported canvases.
    """
    import zipfile
    from io import BytesIO

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for canvas_id in canvas_ids:
            svc = CanvasService(db=db, tenant_id=tenant_id, user_id=cast(UUID, current_user.id))
            try:
                canvas = await svc.get_canvas(canvas_id)
            except Exception:
                continue

            # Export individual canvas
            canvas_data = {
                "id": str(canvas.id),
                "name": canvas.name,
                "blocks": [],
                "connections": [],
            }

            result = await canvas_exporter.export_canvas(
                canvas_data,
                format,
                {"pretty": True},
            )

            # Add to zip
            content = result.content
            if isinstance(content, str):
                content = content.encode("utf-8")

            zip_file.writestr(result.filename, content)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="canvas_export_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.zip"',
        },
    )
