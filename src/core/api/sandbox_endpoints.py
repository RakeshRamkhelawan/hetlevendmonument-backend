# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import get_current_user, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Sandbox"])


@router.post(
    "/api/v1/sandbox/create",
    response_model=dict[str, str],
    dependencies=[Depends(get_current_user)],
)
async def create_sandbox(
    config: dict[str, Any], current_user: UserResponse = Depends(get_current_user)  # TODO(TYPE): replace Any with concrete type
) -> dict[str, str]:
    if not app_state["sandbox_manager"]:
        raise HTTPException(status_code=503, detail="Sandbox manager not initialized")
    try:
        from src.core.shared.interfaces import SandboxEnvironment
        from src.core.types import IsolationLevel

        sandbox_config = SandboxEnvironment(
            isolation_level=IsolationLevel(config.get("isolation_level", "mock")),
            resource_limits=config.get("resource_limits", {}),
            network_access=config.get("network_access", False),
            filesystem_access=config.get("filesystem_access", {}),
        )
        sandbox_id = await app_state["sandbox_manager"].create_sandbox(sandbox_config)
        return {"sandbox_id": sandbox_id, "status": "created"}
    except Exception as e:
        logger.error(f"Sandbox creation error: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/api/v1/sandbox/{sandbox_id}/status", dependencies=[Depends(get_current_user)])
async def get_sandbox_status(
    sandbox_id: str, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state["sandbox_manager"]:
        raise HTTPException(status_code=503, detail="Sandbox manager not initialized")
    try:
        return cast(
            dict[str, Any], await app_state["sandbox_manager"].get_sandbox_status(sandbox_id)  # TODO(TYPE): replace Any with concrete type
        )
    except Exception as e:
        logger.error(f"Sandbox status error: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")
