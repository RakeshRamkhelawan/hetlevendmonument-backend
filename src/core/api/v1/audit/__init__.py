"""
Audit domain -- mission audit trails and GDPR-compliant exports.

Migrated from src/core/api/audit_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter

from src.core.api.v1.audit.router import router as audit_composite_router

domain_router = APIRouter(prefix="/api/v1", tags=["Audit"])
domain_router.include_router(audit_composite_router)

__all__ = ["domain_router"]
