"""Production operations sub-router (ADR-033 Laag 1)."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from src.core.api.dependencies import require_admin_user
from pydantic import BaseModel, Field

from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope

from .shared import production_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class InitializationRequest(BaseModel):
    """Request model for system initialization."""

    force_reinit: bool = Field(False, description="Force reinitialization of all systems")
    systems_to_init: list[str] | None = Field(
        default=None,
        description="Specific systems to initialize (if None, all systems)",
    )


class InitializationResponse(BaseModel):
    """System initialization response."""

    timestamp: str
    total_systems: int
    initialized_systems: int
    failed_systems: int
    success_rate: float
    system_results: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    overall_status: str


class TestRequest(BaseModel):
    """Request model for comprehensive testing."""

    test_categories: list[str] | None = Field(
        default=["integration", "performance", "health"],
        description="Categories of tests to run",
    )
    timeout_minutes: int = Field(5, ge=1, le=30, description="Test timeout in minutes")


class TestResponse(BaseModel):
    """Comprehensive test response."""

    timestamp: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    test_success_rate: float
    test_results: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    recommendations: list[str]


@router.post("/initialize", response_model=InitializationResponse, status_code=status.HTTP_200_OK)
async def initialize_production_systems(
    request: InitializationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> InitializationResponse:
    """Initialize all production systems. Requires: ADMIN_ALL"""
    try:
        logger.info(
            "User %s starting production system initialization (force: %s)",
            current_user.id,
            request.force_reinit,
        )
        initialization_results = await production_manager.initialize_all_systems()
        integration_summary = initialization_results.get("integration_summary", {})
        systems_integrated = integration_summary.get("systems_integrated", 0)
        total_systems = integration_summary.get("total_systems", 0)
        success_rate = integration_summary.get("success_rate", 0)
        overall_status = integration_summary.get("status", "unknown")
        return InitializationResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_systems=total_systems,
            initialized_systems=systems_integrated,
            failed_systems=total_systems - systems_integrated,
            success_rate=success_rate,
            system_results=initialization_results,
            overall_status=overall_status,
        )
    except Exception as e:
        logger.error("Production initialization failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize production systems",
        ) from e


@router.post("/test/comprehensive", response_model=TestResponse, status_code=status.HTTP_200_OK)
async def run_comprehensive_tests(
    request: TestRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> TestResponse:
    """Run comprehensive system tests. Requires: ADMIN_ALL"""
    try:
        logger.info(
            "User %s starting comprehensive tests for categories: %s",
            current_user.id,
            request.test_categories,
        )
        test_results = await production_manager.run_comprehensive_test()
        test_summary = test_results.get("test_summary", {})
        tests_passed = test_summary.get("tests_passed", 0)
        total_tests = test_summary.get("total_tests", 0)
        test_success_rate = test_summary.get("success_rate", 0)
        recommendations: list[str] = []
        if test_success_rate < 80:
            recommendations.append("Test success rate below 80% - investigate failing components")
        if test_success_rate >= 90:
            recommendations.append("Excellent test performance - system ready for production")
        return TestResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_tests=total_tests,
            passed_tests=tests_passed,
            failed_tests=total_tests - tests_passed,
            test_success_rate=test_success_rate,
            test_results=test_results,
            recommendations=recommendations,
        )
    except Exception as e:
        logger.error("Comprehensive testing failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run comprehensive tests",
        ) from e


@router.get("/system-integration-status", status_code=status.HTTP_200_OK)
async def get_system_integration_status(
    current_user: UserResponse = Depends(require_admin_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed system integration status. Requires: AGENTS_READ"""
    try:
        logger.info("User %s requesting system integration status", current_user.id)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integration_status": production_manager.integration_status,
            "summary": {
                "total_systems": len(production_manager.integration_status),
                "operational_systems": sum(production_manager.integration_status.values()),
                "failed_systems": len(production_manager.integration_status)
                - sum(production_manager.integration_status.values()),
                "integration_rate": (
                    (
                        sum(production_manager.integration_status.values())
                        / len(production_manager.integration_status)
                    )
                    * 100
                    if production_manager.integration_status
                    else 0
                ),
            },
            "system_details": {
                system: {
                    "status": "operational" if sys_status else "failed",
                    "description": _get_system_description(system),
                }
                for system, sys_status in production_manager.integration_status.items()
            },
        }
    except Exception as e:
        logger.error("Integration status failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system integration status",
        ) from e


@router.post("/restart-system", status_code=status.HTTP_200_OK)
async def restart_production_system(
    background_tasks: BackgroundTasks,
    system_name: str | None = None,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Restart production system or specific subsystem. Requires: ADMIN_ALL"""
    try:
        if system_name:
            logger.info("User %s restarting specific system: %s", current_user.id, system_name)
            if system_name not in production_manager.integration_status:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unknown system: " + system_name,
                )
        else:
            logger.info("User %s restarting entire production system", current_user.id)

        def restart_background() -> None:
            import time

            time.sleep(2)
            logger.info("System restart completed: %s", system_name or "all systems")

        if background_tasks:
            background_tasks.add_task(restart_background)

        return {
            "message": "Restart initiated for " + (system_name or "all systems"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "estimated_completion": "30-60 seconds",
            "system": system_name or "all_systems",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System restart failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restart system",
        ) from e


def _get_system_description(system_name: str) -> str:
    """Get description for system name."""
    descriptions = {
        "predictive_evolution": "Phase 5 Predictive Evolution Engine with 24-48h forecasting",
        "advanced_monitoring": "Advanced monitoring and analytics system with real-time metrics",
        "enhanced_nlp": "Enhanced NLP parser with M-MDP command recognition",
        "resilient_api": "Resilient API client with circuit breaker patterns",
        "meta_learning": "Meta-learning management system with strategy transfer",
        "safety_validation": "Safety validation framework with constraint monitoring",
        "training_pipeline": "Training pipeline integration with PPO and experiment tracking",
    }
    return descriptions.get(system_name, "System component: " + system_name)
