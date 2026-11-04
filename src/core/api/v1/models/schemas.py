# dsm:exempt reason: non-router schemas/dependency provider for models domain (ADR-033 Laag 1)
"""Models domain schemas and get_registry_manager (ADR-033 Laag 1)."""

import asyncio
import logging
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Optional ML dependencies
MLflowTracker: Any = None
ModelStage: Any = None
ModelRegistryManager: Any = None
MLFLOW_AVAILABLE = False
try:
    from src.core.learning.mlflow_integration import MLFLOW_AVAILABLE, MLflowTracker
    from src.core.learning.model_registry import ModelRegistryManager, ModelStage
except ImportError:
    pass

_registry_manager: Any = None
# R-003: Lock for thread-safe singleton initialization under concurrent requests
_init_lock: asyncio.Lock | None = None


def _get_init_lock() -> asyncio.Lock:
    """Return (or lazily create) the singleton init lock."""
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def get_registry_manager() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Get or create Model Registry Manager."""
    global _registry_manager

    if not MLFLOW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install it with: pip install mlflow",
        )

    # Fast path: already initialized
    if _registry_manager is not None:
        return _registry_manager

    # R-003: serialize concurrent initialization via asyncio.Lock
    async with _get_init_lock():
        if _registry_manager is None:
            try:
                import anyio

                tracker_instance = await asyncio.wait_for(
                    anyio.to_thread.run_sync(MLflowTracker),  # pyright: ignore[reportAttributeAccessIssue]
                    timeout=5.0,
                )
                if tracker_instance is None:
                    raise HTTPException(
                        status_code=503,
                        detail="MLflow tracker initialization returned None",
                    )
                _registry_manager = ModelRegistryManager(tracker_instance)
                logger.info("Model Registry Manager initialized")
            except Exception as e:  # R-007: TimeoutError is already a subclass of Exception
                logger.error(
                    "Failed to initialize Model Registry Manager: %s: %s",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                raise HTTPException(status_code=503, detail="Model Registry Manager not available")

    return _registry_manager


class PromoteRequest(BaseModel):
    """Request body for model promotion."""

    model_name: str = Field(..., description="Name of the registered model")
    version: int = Field(..., description="Version number to promote")
    target_stage: str = Field(..., description="Target stage (Staging/Production)")
    validation_results: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None, description="Validation results for production promotion"
    )


class RollbackRequest(BaseModel):
    """Request body for model rollback."""

    target_version: int = Field(..., description="Version to rollback to")


class VersionInfo(BaseModel):
    """Model version information."""

    version: int
    stage: str
    creation_timestamp: int
    last_updated_timestamp: int
    metrics: dict[str, float]
    tags: dict[str, str]
