"""
API endpoints for tenant custom data (EAV key-value store).
Allows tenants to persist arbitrary configuration per namespace/key.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from src.core.auth.api_deps import UserResponse, get_current_user
from .dependencies import TenantCustomDataService, get_tenant_custom_data_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tenant-custom-data",
    tags=["tenant-custom-data"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CustomDataValue(BaseModel):
    """Request body for setting a custom data value."""

    value: Any = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="The value to store (any JSON-serialisable type)"
    )


class CustomDataEntry(BaseModel):
    """Response model for a single custom data entry."""

    namespace: str
    key: str
    value: Any  # TODO(TYPE): replace Any with concrete type


class NamespaceList(BaseModel):
    """Response listing available namespaces."""

    namespaces: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{namespace}",
    response_model=list[CustomDataEntry],
    summary="List all keys in a namespace",
)
async def list_namespace(
    namespace: str = Path(..., min_length=1, max_length=100),
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> list[CustomDataEntry]:
    """Return all key-value pairs within *namespace* for the current tenant."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    rows = await service.get_namespace(current_user.tenant_id, namespace)
    return [
        CustomDataEntry(namespace=namespace, key=key, value=value) for key, value in rows.items()
    ]


@router.get(
    "/{namespace}/{key}",
    response_model=CustomDataEntry,
    summary="Get a single value",
)
async def get_value(
    namespace: str = Path(..., min_length=1, max_length=100),
    key: str = Path(..., min_length=1, max_length=255),
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> CustomDataEntry:
    """Retrieve the value for *namespace*/*key*."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    value = await service.get_value(current_user.tenant_id, namespace, key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return CustomDataEntry(namespace=namespace, key=key, value=value)


@router.put(
    "/{namespace}/{key}",
    response_model=CustomDataEntry,
    summary="Set a value (upsert)",
)
async def set_value(
    body: CustomDataValue,
    namespace: str = Path(..., min_length=1, max_length=100),
    key: str = Path(..., min_length=1, max_length=255),
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> CustomDataEntry:
    """Create or update *namespace*/*key* with the given value."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await service.set_value(current_user.tenant_id, namespace, key, body.value)
    return CustomDataEntry(namespace=namespace, key=key, value=body.value)


@router.delete(
    "/{namespace}/{key}",
    status_code=204,
    summary="Delete a single key",
)
async def delete_value(
    namespace: str = Path(..., min_length=1, max_length=100),
    key: str = Path(..., min_length=1, max_length=255),
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> None:
    """Remove *namespace*/*key*."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await service.delete_value(current_user.tenant_id, namespace, key)


@router.delete(
    "/{namespace}",
    status_code=204,
    summary="Delete an entire namespace",
)
async def delete_namespace(
    namespace: str = Path(..., min_length=1, max_length=100),
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> None:
    """Remove all keys in *namespace*."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await service.delete_namespace(current_user.tenant_id, namespace)


@router.get(
    "/",
    response_model=NamespaceList,
    summary="List all namespaces",
)
async def list_namespaces(
    current_user: UserResponse | None = Depends(get_current_user),
    service: TenantCustomDataService = Depends(get_tenant_custom_data_service),
) -> NamespaceList:
    """Return all namespaces that have at least one key for the current tenant."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    ns = await service.list_namespaces(current_user.tenant_id)
    return NamespaceList(namespaces=ns)
