"""
Unit tests for Model Registry Management API Endpoints

Tests cover MLflow Model Registry operations including:
- Model version listing and filtering
- Manual promotion control (Staging/Production/Archived)
- Version comparison and rollback
- Production model queries
- Lifecycle history tracking
- Old version archival (ADMIN)
- Promotion rules retrieval

Author: Test Engineer
Date: 2025-11-11
"""

import sys
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import BaseModel


# Create MockUserResponse FIRST
class MockUserResponse(BaseModel):
    id: int = 1
    username: str = "test_user"
    email: str = "test@example.com"


# Create MockModelStage enum to match real ModelStage
class MockModelStage(str, Enum):
    """Mock ModelStage enum matching core.learning.model_registry.ModelStage"""

    NONE = "None"
    STAGING = "Staging"
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


# Mock ALL dependencies BEFORE importing
# sys.modules['src.core.auth.rbac'] = MagicMock()
# sys.modules['src.core.auth.dependencies'] = MagicMock()
# sys.modules['src.core.auth'] = MagicMock()

# Mock auth_endpoints to avoid FastAPI router initialization
# CRITICAL: Mock BOTH import paths (relative .auth_endpoints resolves to core.api.auth_endpoints)
mock_auth_endpoints = MagicMock()
mock_auth_endpoints.get_current_user = MagicMock()
sys.modules["src.core.api.auth_endpoints"] = mock_auth_endpoints
sys.modules["src.core.api.auth_endpoints"] = mock_auth_endpoints

# Mock learning modules WITH ModelStage enum
mock_model_registry = MagicMock()
mock_model_registry.ModelStage = MockModelStage
mock_model_registry.ModelRegistryManager = MagicMock
sys.modules["src.core.learning.mlflow_integration"] = MagicMock()
sys.modules["src.core.learning.model_registry"] = mock_model_registry

from src.core.api.models_endpoints import (
    PromoteRequest,
    RollbackRequest,
    VersionInfo,
    get_registry_manager,
    router,
)


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.username = "test_user"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_registry():
    """Mock ModelRegistryManager."""
    import asyncio
    from concurrent.futures import Future

    registry = MagicMock()

    # Create proper executor that returns Future objects
    def create_future_result(result):
        """Helper to create a completed Future."""
        future = Future()
        future.set_result(result)
        return future

    # Mock executor with proper submit that returns Future
    mock_executor = MagicMock()
    mock_executor.submit = MagicMock(
        side_effect=lambda func, *args: create_future_result(func(*args))
    )
    registry._executor = mock_executor

    # Mock client with search_model_versions
    mock_client = MagicMock()
    registry.client = mock_client

    # Mock async methods
    registry.promote_to_staging = AsyncMock(return_value=True)
    registry.promote_to_production = AsyncMock(return_value=True)
    registry._transition_version = AsyncMock()
    registry.rollback = AsyncMock(return_value=True)
    registry.compare_versions = AsyncMock(
        return_value={
            "model_name": "test_model",
            "v1": {"version": 1, "metrics": {"accuracy": 0.85}},
            "v2": {"version": 2, "metrics": {"accuracy": 0.90}},
            "differences": {"accuracy": 0.05},
        }
    )
    registry.get_production_model = AsyncMock(return_value=None)
    registry.get_lifecycle_history = AsyncMock(return_value=[])
    registry.archive_old_versions = AsyncMock(return_value=3)

    # Mock rules
    mock_rules = MagicMock()
    mock_rules.to_dict = MagicMock(
        return_value={
            "staging": {"min_accuracy": 0.80, "min_f1": 0.75},
            "production": {"min_accuracy": 0.85, "validation_days": 7},
        }
    )
    registry.rules = mock_rules

    # Mock _extract_metrics_from_tags
    registry._extract_metrics_from_tags = MagicMock(
        return_value={"accuracy": 0.90, "f1_score": 0.88}
    )

    return registry


class TestListVersions:
    """Test suite for list_versions endpoint."""

    @pytest.mark.asyncio
    async def test_list_versions_success(self, mock_user, mock_registry):
        """Test successful version listing."""
        # Mock model versions
        mock_version = MagicMock()
        mock_version.version = "2"
        mock_version.current_stage = "Staging"
        mock_version.creation_timestamp = 1699999999000
        mock_version.last_updated_timestamp = 1700000000000
        mock_version.run_id = "run_123"
        mock_version.tags = {"accuracy": "0.90", "f1_score": "0.88"}

        mock_registry.client.search_model_versions = MagicMock(return_value=[mock_version])

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import list_versions

                result = await list_versions(
                    model_name="test_model", stage=None, limit=50, offset=0, current_user=mock_user, _=1
                )

                assert result["model_name"] == "test_model"
                assert result["total_versions"] == 1
                assert len(result["versions"]) == 1
                assert result["versions"][0]["version"] == 2
                assert result["versions"][0]["stage"] == "Staging"

    @pytest.mark.asyncio
    async def test_list_versions_with_stage_filter(self, mock_user, mock_registry):
        """Test version listing with stage filter."""
        # Mock versions with different stages
        mock_v1 = MagicMock()
        mock_v1.version = "1"
        mock_v1.current_stage = "Staging"
        mock_v1.creation_timestamp = 1699999999000
        mock_v1.last_updated_timestamp = 1700000000000
        mock_v1.run_id = "run_1"
        mock_v1.tags = {}

        mock_v2 = MagicMock()
        mock_v2.version = "2"
        mock_v2.current_stage = "Production"
        mock_v2.creation_timestamp = 1700000000000
        mock_v2.last_updated_timestamp = 1700000001000
        mock_v2.run_id = "run_2"
        mock_v2.tags = {}

        mock_registry.client.search_model_versions = MagicMock(return_value=[mock_v1, mock_v2])

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import list_versions

                result = await list_versions(
                    model_name="test_model",
                    stage="Production",
                    limit=50,
                    offset=0,
                    current_user=mock_user,
                    _=1,
                )

                # Should only return Production version
                assert result["total_versions"] == 1
                assert result["versions"][0]["stage"] == "Production"
                assert result["stage_filter"] == "Production"


class TestPromoteModel:
    """Test suite for promote_model endpoint."""

    @pytest.mark.asyncio
    async def test_promote_to_staging_success(self, mock_user, mock_registry):
        """Test successful promotion to Staging."""
        # Mock version lookup
        mock_version = MagicMock()
        mock_version.tags = {"accuracy": "0.85"}
        mock_registry.client.search_model_versions = MagicMock(return_value=[mock_version])

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(model_name="test_model", version=2, target_stage="Staging")

                result = await promote_model(request=request, current_user=mock_user, _=1)

                assert result["success"] is True
                assert result["model_name"] == "test_model"
                assert result["version"] == 2
                assert result["new_stage"] == "Staging"

    @pytest.mark.asyncio
    async def test_promote_to_production_success(self, mock_user, mock_registry):
        """Test successful promotion to Production with validation."""
        validation_results = {
            "accuracy": 0.92,
            "f1_score": 0.90,
            "validation_passed": True,
        }

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="test_model",
                    version=3,
                    target_stage="Production",
                    validation_results=validation_results,
                )

                result = await promote_model(request=request, current_user=mock_user, _=1)

                assert result["success"] is True
                assert result["new_stage"] == "Production"
                mock_registry.promote_to_production.assert_called_once()

    @pytest.mark.asyncio
    async def test_promote_invalid_stage(self, mock_user, mock_registry):
        """Test promotion with invalid stage name."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="test_model", version=2, target_stage="InvalidStage"
                )

                with pytest.raises(HTTPException) as exc_info:
                    await promote_model(request=request, current_user=mock_user, _=1)

                assert exc_info.value.status_code == 400
                assert "Invalid stage" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_promote_production_without_validation(self, mock_user, mock_registry):
        """Test production promotion without validation results."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="test_model",
                    version=2,
                    target_stage="Production",
                    validation_results=None,  # Missing validation
                )

                with pytest.raises(HTTPException) as exc_info:
                    await promote_model(request=request, current_user=mock_user, _=1)

                assert exc_info.value.status_code == 400
                assert "Validation results required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_promote_version_not_found(self, mock_user, mock_registry):
        """Test promoting non-existent model version (covers line 188)."""
        # Mock registry.client.search_model_versions to return empty list
        mock_registry.client = MagicMock()
        mock_registry.client.search_model_versions = MagicMock(return_value=[])
        mock_registry._executor = None  # Used by run_in_executor

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="nonexistent_model", version=999, target_stage="Staging"
                )

                with pytest.raises(HTTPException) as exc_info:
                    await promote_model(request=request, current_user=mock_user, _=1)

                assert exc_info.value.status_code == 404
                assert "Model version not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_promote_to_archived_success(self, mock_user, mock_registry):
        """Test archiving a model version (covers lines 210-219 - 10 lines!)."""
        # Mock version exists
        mock_version = MagicMock()
        mock_version.tags = {"accuracy": "0.95", "f1_score": "0.93"}
        mock_registry.search_model_versions = MagicMock(return_value=[mock_version])
        mock_registry._transition_version = AsyncMock()

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="old_model",
                    version=5,
                    target_stage="Archived",  # Triggers ARCHIVED branch
                )

                result = await promote_model(request=request, current_user=mock_user, _=1)

                # Verify success response
                assert result["success"] is True
                assert result["model_name"] == "old_model"
                assert result["version"] == 5
                assert "archived" in result["message"].lower()

                # Verify _transition_version was called with ARCHIVED stage
                mock_registry._transition_version.assert_called_once_with(
                    "old_model", 5, "Archived"
                )

    @pytest.mark.asyncio
    async def test_promote_criteria_not_met(self, mock_user, mock_registry):
        """Test promotion when criteria are not met (covers line 233)."""
        # Mock promote_to_staging to return False (criteria not met)
        mock_version = MagicMock()
        mock_version.tags = {"accuracy": "0.50"}  # Too low quality!
        mock_registry.client.search_model_versions = MagicMock(return_value=[mock_version])
        mock_registry._extract_metrics_from_tags = MagicMock(return_value={"accuracy": 0.50})
        mock_registry.promote_to_staging = AsyncMock(return_value=False)  # Criteria failed

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import promote_model

                request = PromoteRequest(
                    model_name="low_quality_model", version=3, target_stage="Staging"
                )

                result = await promote_model(request=request, current_user=mock_user, _=1)

                # Verify failure response (success == False branch)
                assert result["success"] is False
                assert result["model_name"] == "low_quality_model"
                assert result["version"] == 3
                assert "failed" in result["message"].lower()
                assert "check criteria" in result["message"].lower()


class TestRollbackModel:
    """Test suite for rollback_model endpoint."""

    @pytest.mark.asyncio
    async def test_rollback_success(self, mock_user, mock_registry):
        """Test successful model rollback."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import rollback_model

                request = RollbackRequest(target_version=1)

                result = await rollback_model(
                    model_name="test_model",
                    request=request,
                    current_user=mock_user,
                    _=1,
                )

                assert result["success"] is True
                assert result["model_name"] == "test_model"
                assert result["rollback_version"] == 1
                mock_registry.rollback.assert_called_once_with("test_model", 1)

    @pytest.mark.asyncio
    async def test_rollback_failure(self, mock_user, mock_registry):
        """Test rollback failure scenario."""
        mock_registry.rollback = AsyncMock(return_value=False)

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import rollback_model

                request = RollbackRequest(target_version=1)

                result = await rollback_model(
                    model_name="test_model",
                    request=request,
                    current_user=mock_user,
                    _=1,
                )

                assert result["success"] is False
                assert "failed" in result["message"].lower()


class TestCompareVersions:
    """Test suite for compare_versions endpoint."""

    @pytest.mark.asyncio
    async def test_compare_versions_success(self, mock_user, mock_registry):
        """Test successful version comparison."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import compare_versions

                result = await compare_versions(
                    model_name="test_model", v1=1, v2=2, current_user=mock_user, _=1
                )

                assert result["model_name"] == "test_model"
                assert "v1" in result
                assert "v2" in result
                assert "differences" in result

    @pytest.mark.asyncio
    async def test_compare_versions_error(self, mock_user, mock_registry):
        """Test version comparison with error."""
        mock_registry.compare_versions = AsyncMock(return_value={"error": "Version not found"})

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import compare_versions

                with pytest.raises(HTTPException) as exc_info:
                    await compare_versions(
                        model_name="test_model",
                        v1=1,
                        v2=999,
                        current_user=mock_user,
                        _=1,
                    )

                assert exc_info.value.status_code == 500


class TestProductionModel:
    """Test suite for get_production_model endpoint."""

    @pytest.mark.asyncio
    async def test_get_production_model_found(self, mock_user, mock_registry):
        """Test getting existing production model."""
        mock_version = MagicMock()
        mock_version.version = "3"
        mock_version.current_stage = "Production"
        mock_version.creation_timestamp = 1700000000000
        mock_version.last_updated_timestamp = 1700000001000
        mock_version.run_id = "run_prod"
        mock_version.tags = {"accuracy": "0.95"}

        mock_registry.get_production_model = AsyncMock(return_value=mock_version)

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import get_production_model

                result = await get_production_model(
                    model_name="test_model", current_user=mock_user, _=1
                )

                assert result["model_name"] == "test_model"
                assert result["production_version"] is not None
                assert result["production_version"]["version"] == 3
                assert result["production_version"]["stage"] == "Production"

    @pytest.mark.asyncio
    async def test_get_production_model_not_found(self, mock_user, mock_registry):
        """Test getting production model when none exists."""
        mock_registry.get_production_model = AsyncMock(return_value=None)

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import get_production_model

                result = await get_production_model(
                    model_name="test_model", current_user=mock_user, _=1
                )

                assert result["model_name"] == "test_model"
                assert result["production_version"] is None
                assert "No production version" in result["message"]


class TestLifecycleHistory:
    """Test suite for get_lifecycle_history endpoint."""

    @pytest.mark.asyncio
    async def test_get_lifecycle_history_success(self, mock_user, mock_registry):
        """Test successful lifecycle history retrieval."""
        mock_history = [
            {"version": 1, "stage": "Staging", "timestamp": 1699999999000},
            {"version": 2, "stage": "Production", "timestamp": 1700000000000},
        ]
        mock_registry.get_lifecycle_history = AsyncMock(return_value=mock_history)

        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import get_lifecycle_history

                result = await get_lifecycle_history(
                    model_name="test_model", current_user=mock_user, _=1
                )

                assert result["model_name"] == "test_model"
                assert result["total_versions"] == 2
                assert result["lifecycle_history"] == mock_history


class TestArchiveOldVersions:
    """Test suite for archive_old_versions endpoint."""

    @pytest.mark.asyncio
    async def test_archive_old_versions_success(self, mock_user, mock_registry):
        """Test successful archival of old versions."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import archive_old_versions

                result = await archive_old_versions(
                    model_name="test_model", keep_last_n=5, current_user=mock_user, _=1
                )

                assert result["success"] is True
                assert result["model_name"] == "test_model"
                assert result["archived_count"] == 3
                assert result["kept_versions"] == 5
                mock_registry.archive_old_versions.assert_called_once_with("test_model", 5)


class TestPromotionRules:
    """Test suite for get_promotion_rules endpoint."""

    @pytest.mark.asyncio
    async def test_get_promotion_rules_success(self, mock_user, mock_registry):
        """Test successful promotion rules retrieval."""
        with patch(
            "src.core.api.v1.models.registry_router.get_registry_manager",
            return_value=mock_registry,
        ):
            with patch(
                "src.core.api.v1.models.registry_router.get_current_user_dependency",
                return_value=mock_user,
            ):
                from src.core.api.v1.models.registry_router import get_promotion_rules

                result = await get_promotion_rules(current_user=mock_user, _=1)

                assert "promotion_rules" in result
                assert "description" in result
                assert "staging_criteria" in result["description"]
                assert "production_criteria" in result["description"]


# Test error handling for registry initialization
class TestRegistryInitialization:
    """Test suite for get_registry_manager function."""

    @pytest.mark.asyncio
    async def test_registry_manager_initialization_failure(self):
        """Test registry manager initialization failure."""
        with patch(
            "src.core.api.v1.models.schemas.MLflowTracker",
            side_effect=Exception("MLflow unavailable"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                # Reset global state before awaiting async initializer
                import src.core.api.models_endpoints as models_endpoints_module
                from src.core.api.v1.models.registry_router import get_registry_manager

                models_endpoints_module._registry_manager = None

                await get_registry_manager()

            assert exc_info.value.status_code == 503
            assert "not available" in exc_info.value.detail.lower()
