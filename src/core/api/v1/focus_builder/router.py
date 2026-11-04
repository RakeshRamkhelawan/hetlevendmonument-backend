"""
# orphan:exempt reason: registered via proxy.get_focus_builder_router() in registries/workflows.py (ADR-033)
FocusBuilder V1 Router composite (ADR-033 Laag 2).

Provides all FocusBuilder API operations via sub-routers.
Replaces: src/core/api/focus_builder_endpoints.py (legacy)

Rate Limits (see sub-routers for details):
- Create/Update: 10/minute (write operations)
- Delete/Execute: 5/minute (destructive/heavy operations)
- List/Get/Runs: 30/minute (read operations)
- Pieces: 20/minute (catalog read)
- Sync: 2/minute (admin-only, heavy)
- AI: 3/minute (LLM-backed, expensive)
"""

from fastapi import APIRouter

from src.core.api.v1.focus_builder.agents import agents_router
from src.core.api.v1.focus_builder.ai_router import ai_router, generate_flow_ai
from src.core.api.v1.focus_builder.execution_router import (
    execution_router,
    execute_flow,
    get_latest_run,
    get_run_logs,
)
from src.core.api.v1.focus_builder.flows_router import (
    flows_router,
    create_flow,
    delete_flow,
    get_flow,
    list_flows,
    update_flow,
)
from src.core.api.v1.focus_builder.pieces_router import (
    pieces_router,
    list_pieces,
    sync_pieces,
)
from src.core.api.v1.focus_builder.shared import get_focus_builder_service
from src.core.api.v1.focus_builder.ws_chat_router import ws_chat_router
from src.core.api.v1.focus_builder.ws_status_router import ws_status_router


from src.core.auth.api_deps import get_current_user  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

router = APIRouter(prefix="/focus-builder", tags=["FocusBuilder V1"])

router.include_router(agents_router, prefix="")
router.include_router(flows_router)
router.include_router(execution_router)
router.include_router(pieces_router)
router.include_router(ai_router)
router.include_router(ws_status_router)
router.include_router(ws_chat_router)

__all__ = [
    "router",
    "create_flow",
    "delete_flow",
    "execute_flow",
    "generate_flow_ai",
    "get_flow",
    "get_focus_builder_service",
    "get_latest_run",
    "get_run_logs",
    "list_flows",
    "list_pieces",
    "sync_pieces",
    "update_flow",
]
