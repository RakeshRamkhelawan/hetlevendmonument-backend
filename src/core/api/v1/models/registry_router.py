# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Model Registry sub-router (ADR-033 Laag 1).

All 8 model registry routes migrated from models_endpoints.py.
Thin delivery layer: delegates to ModelRegistryManager via get_registry_manager().
"""

# TODO(SP-VOLGENDE): R-002 -- ModelRegistryManager is een module-level singleton zonder tenant-isolatie;
# tenant A kan modellen van tenant B promoten/terugrollen. Vereist multi-tenant ModelRegistryManager.

import logging
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.api.v1.models.schemas import (
    ModelRegistryManager,
    ModelStage,
    PromoteRequest,
    RollbackRequest,
    get_registry_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["Model Registry"])


# R-001: /rules placed BEFORE /{model_name}/versions to prevent future route-shadowing
# when GET /{model_name} is added (FastAPI matches routes in registration order).
@router.get("/rules")
async def get_promotion_rules(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current promotion rules."""
    try:
        logger.info(
            "get_promotion_rules started",
            extra={"user_id": current_user.id},
        )
        registry = await get_registry_manager()

        return {
            "promotion_rules": registry.rules.to_dict(),
            "description": {
                "staging_criteria": "Minimum accuracy and F1 score thresholds",
                "production_criteria": "Higher accuracy, validation period, and minimum runs",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_promotion_rules failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id},
        )
        raise HTTPException(status_code=500, detail="Failed to get promotion rules")


@router.get("/{model_name}/versions")
async def list_versions(
    model_name: str,
    stage: str | None = None,
    limit: int = Query(default=50, le=500, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all versions of a model."""
    try:
        logger.info(
            "list_model_versions started",
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        registry = await get_registry_manager()

        import anyio

        versions_result: Any = await anyio.to_thread.run_sync(  # pyright: ignore[reportAttributeAccessIssue]  # TODO(TYPE): replace Any with concrete type
            registry.client.search_model_versions,  # NOTE: mlflow stubs gap
            f"name='{model_name}'",
        )
        versions: list[Any] = list(versions_result) if versions_result else []  # TODO(TYPE): replace Any with concrete type

        if stage:
            versions = [v for v in versions if v.current_stage == stage]

        version_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for version in versions:
            metrics = registry._extract_metrics_from_tags(version.tags)
            version_list.append(
                {
                    "version": int(version.version),
                    "stage": version.current_stage,
                    "creation_timestamp": version.creation_timestamp,
                    "last_updated_timestamp": version.last_updated_timestamp,
                    "run_id": version.run_id,
                    "metrics": metrics,
                    "tags": dict(version.tags),
                }
            )

        version_list.sort(key=lambda v: v["version"], reverse=True)
        total_versions = len(version_list)
        # R-005: apply pagination slicing after sort
        version_list = version_list[offset : offset + limit]

        return {
            "model_name": model_name,
            "total_versions": total_versions,
            "versions": version_list,
            "stage_filter": stage,
            "limit": limit,
            "offset": offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "list_model_versions failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Failed to list model versions")


@router.post("/promote")
async def promote_model(
    request: PromoteRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Manually promote model to stage."""
    try:
        logger.info(
            "promote_model started",
            extra={
                "user_id": current_user.id,
                "model_name": request.model_name,
                "version": request.version,
                "target_stage": request.target_stage,
            },
        )
        registry = await get_registry_manager()

        if ModelStage is None:
            raise HTTPException(status_code=503, detail="Model registry not available")
        try:
            stage_key = request.target_stage.upper()
            if stage_key not in ModelStage.__members__:
                raise KeyError(f"Invalid stage: {stage_key}")
            target_stage = ModelStage[stage_key]
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail="Invalid stage: {}. Must be one of: {}".format(
                    request.target_stage, ", ".join(s.name for s in ModelStage)
                ),
            )

        if target_stage == ModelStage.STAGING:
            import anyio

            versions_result: Any = await anyio.to_thread.run_sync(  # pyright: ignore[reportAttributeAccessIssue]  # TODO(TYPE): replace Any with concrete type
                registry.client.search_model_versions,  # NOTE: mlflow stubs gap
                f"name='{request.model_name}' and version='{request.version}'",
            )
            versions: list[Any] = list(versions_result) if versions_result else []  # TODO(TYPE): replace Any with concrete type
            if not versions:
                raise HTTPException(status_code=404, detail="Model version not found")

            metrics = registry._extract_metrics_from_tags(versions[0].tags)
            success = await registry.promote_to_staging(
                request.model_name, request.version, metrics
            )

        elif target_stage == ModelStage.PRODUCTION:
            if not request.validation_results:
                raise HTTPException(
                    status_code=400,
                    detail="Validation results required for production promotion",
                )
            success = await registry.promote_to_production(
                request.model_name, request.version, request.validation_results
            )

        elif target_stage == ModelStage.ARCHIVED:
            await registry._transition_version(
                request.model_name,
                request.version,
                ModelStage.ARCHIVED.value,
            )
            success = True

        else:
            raise HTTPException(status_code=400, detail="Cannot promote to 'None' stage")

        if success:
            return {
                "success": True,
                "model_name": request.model_name,
                "version": request.version,
                "new_stage": target_stage.value,
                "message": f"Successfully promoted to {target_stage.value}",
            }
        return {
            "success": False,
            "model_name": request.model_name,
            "version": request.version,
            "message": "Promotion failed - check criteria",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "promote_model failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": request.model_name},
        )
        raise HTTPException(status_code=500, detail="Model promotion failed")


@router.post("/{model_name}/rollback")
async def rollback_model(
    model_name: str,
    request: RollbackRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Rollback to previous version."""
    try:
        logger.info(
            "rollback_model started",
            extra={
                "user_id": current_user.id,
                "model_name": model_name,
                "target_version": request.target_version,
            },
        )
        registry = await get_registry_manager()
        success = await registry.rollback(model_name, request.target_version)

        if success:
            return {
                "success": True,
                "model_name": model_name,
                "rollback_version": request.target_version,
                "message": f"Successfully rolled back to version {request.target_version}",
            }
        return {
            "success": False,
            "model_name": model_name,
            "message": "Rollback failed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "rollback_model failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Model rollback failed")


@router.get("/{model_name}/compare")
async def compare_versions(
    model_name: str,
    v1: int,
    v2: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Compare two model versions."""
    try:
        logger.info(
            "compare_versions started",
            extra={"user_id": current_user.id, "model_name": model_name, "v1": v1, "v2": v2},
        )
        registry = await get_registry_manager()
        comparison = await registry.compare_versions(model_name, v1, v2)

        if "error" in comparison:
            # R-004: do not leak internal error details to client
            logger.error(
                "compare_versions error: %s",
                comparison["error"],
                extra={"user_id": current_user.id, "model_name": model_name},
            )
            raise HTTPException(status_code=500, detail="Version comparison failed")

        return cast(dict[str, Any], comparison)  # TODO(TYPE): replace Any with concrete type

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "compare_versions failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Version comparison failed")


@router.get("/{model_name}/production")
async def get_production_model(
    model_name: str,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current production model."""
    try:
        logger.info(
            "get_production_model started",
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        registry = await get_registry_manager()
        prod_version = await registry.get_production_model(model_name)

        if not prod_version:
            return {
                "model_name": model_name,
                "production_version": None,
                "message": "No production version found",
            }

        metrics = registry._extract_metrics_from_tags(prod_version.tags)
        return {
            "model_name": model_name,
            "production_version": {
                "version": int(prod_version.version),
                "stage": prod_version.current_stage,
                "creation_timestamp": prod_version.creation_timestamp,
                "last_updated_timestamp": prod_version.last_updated_timestamp,
                "run_id": prod_version.run_id,
                "metrics": metrics,
                "tags": dict(prod_version.tags),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_production_model failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Failed to get production model")


@router.get("/{model_name}/history")
async def get_lifecycle_history(
    model_name: str,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get complete model lifecycle history."""
    try:
        logger.info(
            "get_lifecycle_history started",
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        registry = await get_registry_manager()
        history = await registry.get_lifecycle_history(model_name)

        return {
            "model_name": model_name,
            "total_versions": len(history),
            "lifecycle_history": history,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_lifecycle_history failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Failed to get lifecycle history")


@router.post("/{model_name}/archive-old")
async def archive_old_versions(
    model_name: str,
    keep_last_n: int = Query(default=5, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Archive old model versions."""
    try:
        logger.info(
            "archive_old_versions started",
            extra={
                "user_id": current_user.id,
                "model_name": model_name,
                "keep_last_n": keep_last_n,
            },
        )
        registry = await get_registry_manager()
        archived_count = await registry.archive_old_versions(model_name, keep_last_n)

        return {
            "success": True,
            "model_name": model_name,
            "archived_count": archived_count,
            "kept_versions": keep_last_n,
            "message": f"Archived {archived_count} old versions",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "archive_old_versions failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"user_id": current_user.id, "model_name": model_name},
        )
        raise HTTPException(status_code=500, detail="Failed to archive old versions")
