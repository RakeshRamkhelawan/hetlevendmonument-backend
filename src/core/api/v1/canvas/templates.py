"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Canvas Templates API

Endpoints for managing canvas templates and applying them to canvases.
"""

from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from src.core.api.v1.canvas.schemas import StandardResponse
from src.core.auth.api_deps import UserResponse, get_current_user
from src.domains.canvas.templates import (
    TemplateCategory,
    TemplateCreateRequest,
    TemplateDifficulty,
    TemplateRegistry,
    template_registry,
)

router = APIRouter(prefix="/canvas/templates", tags=["canvas-templates"])


# ============================================================================
# Template Listing & Search
# ============================================================================


@router.get("", response_model=StandardResponse)
async def list_templates(
    category: TemplateCategory | None = None,
    difficulty: TemplateDifficulty | None = None,
    tags: list[str] | None = Query(None),
    search: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """
    List available canvas templates with optional filtering.

    Query Parameters:
    - **category**: Filter by category (blank, business, data_analysis, etc.)
    - **difficulty**: Filter by difficulty (beginner, intermediate, advanced)
    - **tags**: Filter by tags (comma-separated)
    - **search**: Search in template name and description
    """
    templates = template_registry.list_templates(
        category=category,
        difficulty=difficulty,
        tags=tags,
        search=search,
    )

    return StandardResponse(
        success=True,
        data={
            "templates": [t.to_dict() for t in templates],
            "count": len(templates),
            "filters": {
                "category": category.value if category else None,
                "difficulty": difficulty.value if difficulty else None,
                "tags": tags,
                "search": search,
            },
        },
    )


@router.get("/categories", response_model=StandardResponse)
async def get_template_categories(
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get all template categories with counts."""
    categories = template_registry.get_categories()

    return StandardResponse(
        success=True,
        data={"categories": categories},
    )


@router.get("/tags", response_model=StandardResponse)
async def get_template_tags(
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get all template tags with counts."""
    tags = template_registry.get_tags()

    return StandardResponse(
        success=True,
        data={"tags": tags},
    )


# ============================================================================
# Template Details
# ============================================================================


@router.get("/{template_id}", response_model=StandardResponse)
async def get_template(
    template_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get detailed information about a specific template."""
    template = template_registry.get(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return StandardResponse(
        success=True,
        data=template.to_dict(),
    )


@router.get("/by-name/{template_name}", response_model=StandardResponse)
async def get_template_by_name(
    template_name: str,
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get template by its name."""
    template = template_registry.get_by_name(template_name)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return StandardResponse(
        success=True,
        data=template.to_dict(),
    )


# ============================================================================
# Template Application
# ============================================================================


@router.post("/{template_id}/apply", response_model=StandardResponse)
async def apply_template(
    template_id: UUID,
    canvas_id: UUID,
    customizations: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """
    Apply a template to a canvas.

    This generates blocks and connections based on the template
    and returns them ready to be added to the canvas.
    """
    try:
        result = template_registry.apply_template(
            template_id=template_id,
            canvas_id=canvas_id,
            customizations=customizations,
        )

        logger.info(
            f"Applied template {template_id} to canvas {canvas_id} " f"by user {current_user.id}"
        )

        return StandardResponse(
            success=True,
            data=result,
        )

    except ValueError as e:
        logger.opt(exception=True).error("apply_template mislukt: {}", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Niet gevonden.",
        )


# ============================================================================
# Custom Template Management
# ============================================================================


@router.post("", response_model=StandardResponse)
async def create_template(
    request: TemplateCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """
    Create a new custom template.

    Users can create their own templates from existing canvases
    or from scratch.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    from src.domains.canvas.templates import CanvasTemplate, TemplateBlock, TemplateConnection

    # Convert request blocks to TemplateBlocks
    blocks = [
        TemplateBlock(
            id=b.get("id", str(uuid4())),
            type=b.get("type", "text"),
            x=b.get("x", 0),
            y=b.get("y", 0),
            width=b.get("width", 200),
            height=b.get("height", 100),
            content=b.get("content", {}),
            style=b.get("style", {}),
            connections=b.get("connections", []),
        )
        for b in request.blocks
    ]

    # Convert request connections to TemplateConnections
    connections = [
        TemplateConnection(
            source_block_id=c.get("source_block_id") or "",
            target_block_id=c.get("target_block_id") or "",
            connection_type=c.get("type", "default"),
            label=c.get("label"),
            style=c.get("style", {}),
        )
        for c in request.connections
    ]

    # Create template
    template = CanvasTemplate(
        id=uuid4(),
        name=request.name,
        description=request.description,
        category=request.category,
        difficulty=request.difficulty,
        blocks=blocks,
        connections=connections,
        tags=request.tags,
        author=str(current_user.id),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    template_registry.register(template)

    logger.info(f"Created custom template {template.id} by user {current_user.id}")

    return StandardResponse(
        success=True,
        data={
            "template_id": str(template.id),
            "message": "Template created successfully",
        },
    )


@router.delete("/{template_id}", response_model=StandardResponse)
async def delete_template(
    template_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """
    Delete a custom template.

    Built-in templates cannot be deleted.
    """
    template = template_registry.get(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Check if it's a built-in template
    if template.author is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete built-in templates",
        )

    # Check ownership (in production, also check admin role)
    if template.author != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only delete your own templates",
        )

    template_registry.unregister(template_id)

    logger.info(f"Deleted template {template_id} by user {current_user.id}")

    return StandardResponse(success=True)


# ============================================================================
# Featured & Recommended
# ============================================================================


@router.get("/featured/list", response_model=StandardResponse)
async def get_featured_templates(
    limit: int = Query(6, ge=1, le=20),
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get featured/recommended templates."""
    # For now, return popular templates by category
    featured: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    # One from each major category
    for category in [
        TemplateCategory.PROJECT_MANAGEMENT,
        TemplateCategory.DATA_ANALYSIS,
        TemplateCategory.AI_WORKFLOW,
    ]:
        templates = template_registry.list_templates(category=category, limit=1)
        featured.extend(templates)

    # Fill with others if needed
    if len(featured) < limit:
        others = template_registry.list_templates(limit=limit - len(featured))
        featured.extend(others)

    return StandardResponse(
        success=True,
        data={
            "templates": [t.to_dict() for t in featured[:limit]],
        },
    )


@router.get("/starter/pack", response_model=StandardResponse)
async def get_starter_templates(
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get essential starter templates for new users."""
    starters: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    # Always include blank
    blank = template_registry.get_by_name("Blank Canvas")
    if blank:
        starters.append(blank)

    # Add beginner-friendly templates
    beginner = template_registry.list_templates(
        difficulty=TemplateDifficulty.BEGINNER,
        limit=4,
    )
    starters.extend(beginner)

    return StandardResponse(
        success=True,
        data={
            "templates": [t.to_dict() for t in starters],
            "count": len(starters),
        },
    )
