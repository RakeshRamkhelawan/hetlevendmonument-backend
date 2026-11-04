"""Unit tests for tenant custom data domain dependencies."""

import inspect
from unittest.mock import AsyncMock

from fastapi.params import Depends

from src.core.api.v1.tenant_custom_data.dependencies import (
    TenantCustomDataRepository,
    TenantCustomDataService,
    get_db,
    get_tenant_custom_data_service,
)
from src.core.database.database import get_db as original_get_db
from src.core.services.tenant_custom_data_repository import (
    TenantCustomDataRepository as OriginalRepo,
)
from src.core.services.tenant_custom_data_service import (
    TenantCustomDataService as OriginalService,
)


def test_reexports_match_target_classes() -> None:
    """Verify that re-exports match their original source classes and functions."""
    assert get_db is original_get_db
    assert TenantCustomDataRepository is OriginalRepo
    assert TenantCustomDataService is OriginalService


def test_fastapi_dependency_signature() -> None:
    """Verify that get_tenant_custom_data_service declares db as Depends(get_db)."""
    sig = inspect.signature(get_tenant_custom_data_service)
    assert "db" in sig.parameters
    param = sig.parameters["db"]
    assert isinstance(param.default, Depends)
    assert param.default.dependency is get_db


def test_get_tenant_custom_data_service_factory() -> None:
    """Verify factory returns TenantCustomDataService wired with repository and session."""
    mock_db = AsyncMock()
    service = get_tenant_custom_data_service(db=mock_db)

    assert isinstance(service, TenantCustomDataService)
    assert isinstance(service._repo, TenantCustomDataRepository)
    assert service._repo._session is mock_db

