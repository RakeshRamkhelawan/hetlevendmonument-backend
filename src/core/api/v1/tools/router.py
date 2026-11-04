"""Tools API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.tools.crud_router import crud_router, update_tool  # noqa: F401
from src.core.api.v1.tools.execution_router import clone_tool, execution_router  # noqa: F401
from src.core.api.v1.tools.integrations_router import integrations_router  # noqa: F401
from src.core.api.v1.tools.versions_router import get_tool_versions, versions_router  # noqa: F401

from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

router = APIRouter(prefix="/tools", tags=["Tool Management"])
router.include_router(crud_router)
router.include_router(execution_router)
router.include_router(integrations_router)
router.include_router(versions_router)
