"""
Persona API endpoints for managing AI personas.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import User
from .dependencies import (
    PersonaCreate,
    PersonaUpdate,
    PersonaDetailResponse,
    PersonaResponse,
    SetPersonaRequest,
    ActivePersonaResponse,
    PersonaService,
    get_persona_service,
)

router = APIRouter(prefix="/api/v1/personas", tags=["personas"])


@router.get("/", summary="List Personas")
async def list_personas(
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get all available personas for the current tenant."""
    personas = await service.get_all_personas(current_user.tenant_id, limit=limit, offset=offset)
    return {
        "data": [PersonaResponse.model_validate(p) for p in personas],
        "limit": limit,
        "offset": offset,
    }


@router.get("/active", response_model=ActivePersonaResponse)
async def get_active_persona(
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> ActivePersonaResponse:
    """Get the current user's active persona."""
    persona = await service.get_user_active_persona(current_user.id, current_user.tenant_id)
    system_prompt = await service.get_system_prompt_for_user(
        current_user.id, current_user.tenant_id
    )

    return ActivePersonaResponse(
        persona=PersonaResponse.model_validate(persona) if persona else None,
        system_prompt=system_prompt,
    )


@router.post("/active", response_model=dict)
async def set_active_persona(
    request: SetPersonaRequest,
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Set the current user's active persona."""
    success = await service.set_user_persona(
        current_user.id, request.persona_id, current_user.tenant_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found or not accessible",
        )

    return {"status": "success", "message": "Active persona updated"}


@router.get("/{persona_id}", response_model=PersonaDetailResponse)
async def get_persona(
    persona_id: int,
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> PersonaDetailResponse:
    """Get details of a specific persona."""
    persona = await service.get_persona_by_id(persona_id, current_user.tenant_id)

    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")

    return persona


@router.post("/", response_model=PersonaDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_persona(
    request: PersonaCreate,
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> PersonaDetailResponse:
    """Create a new custom persona."""
    persona = await service.create_persona(
        tenant_id=current_user.tenant_id,
        name=request.name,
        description=request.description,
        system_prompt=request.system_prompt,
        category=request.category,
        avatar_url=request.avatar_url,
        temperature=request.temperature,
        verbosity=request.verbosity,
        tone=request.tone,
    )
    return persona


@router.patch("/{persona_id}", response_model=PersonaDetailResponse)
async def update_persona(
    persona_id: int,
    request: PersonaUpdate,
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> PersonaDetailResponse:
    """Update an existing persona."""
    updates = request.model_dump(exclude_unset=True)

    persona = await service.update_persona(
        persona_id=persona_id, tenant_id=current_user.tenant_id, **updates
    )

    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")

    return persona


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: int,
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Delete a custom persona (system personas cannot be deleted)."""
    success = await service.delete_persona(persona_id, current_user.tenant_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete persona. It may not exist or is a system persona.",
        )

    return {"status": "success", "message": "Persona deleted"}


@router.post("/seed-defaults", response_model=dict)
async def seed_default_personas(
    service: PersonaService = Depends(get_persona_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Seed default system personas for the tenant (admin only)."""
    created = await service.seed_default_personas(current_user.tenant_id)

    return {
        "status": "success",
        "message": f"Seeded {len(created)} default personas",
        "created_count": len(created),
    }
