"""Tenants API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.tenants.tenants_detail_router import tenants_detail_router
from src.core.api.v1.tenants.tenants_list_router import tenants_list_router
from src.core.api.v1.tenants.tenants_stats_router import tenants_stats_router

router = APIRouter(prefix="/tenants", tags=["Tenant Management"])
router.include_router(tenants_list_router)
router.include_router(tenants_detail_router)
router.include_router(tenants_stats_router)
