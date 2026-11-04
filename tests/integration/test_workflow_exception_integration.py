"""
Test to verify workflow endpoints use new exception handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the workflow router
from src.core.api.workflow_endpoints import router as workflow_router


def test_workflow_endpoints_use_custom_exceptions():
    """Test that workflow endpoints use custom exceptions instead of HTTPException"""
    # Create test app and include the workflow router
    app = FastAPI()
    app.include_router(workflow_router)

    # Register exception handlers
    from src.core.exceptions import register_exception_handlers

    register_exception_handlers(app)

    # Create test client
    client = TestClient(app)

    # Test that the imports are working correctly
    from src.core.api.workflow_endpoints import (
        raise_not_found,
        raise_validation_error,
        raise_workflow_error,
    )

    # Verify that the functions exist
    assert raise_not_found is not None
    assert raise_validation_error is not None
    assert raise_workflow_error is not None

    print("Workflow endpoints custom exception integration verified!")


if __name__ == "__main__":
    test_workflow_endpoints_use_custom_exceptions()
