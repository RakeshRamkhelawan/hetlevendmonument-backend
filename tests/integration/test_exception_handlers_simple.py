"""
Simple test to verify exception handlers are working
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.core.exceptions.exceptions import NotFoundError, SanskritiError, ValidationError


def test_exception_handlers():
    """Test that exception handlers are properly registered and working"""
    # Create test app
    app = FastAPI()

    # Register exception handlers
    from src.core.exceptions.handlers import register_exception_handlers

    register_exception_handlers(app)

    # Add test endpoints
    @app.get("/sanskriti-error")
    async def raise_sanskriti_error():
        raise SanskritiError(
            message="Test error",
            error_code="TEST_ERROR",
            status_code=418,
            details={"test": "value"},
        )

    @app.get("/validation-error")
    async def raise_validation_error():
        raise ValidationError("Invalid input")

    @app.get("/not-found")
    async def raise_not_found():
        raise NotFoundError("Resource", "123")

    @app.get("/http-error")
    async def raise_http_error():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    # Test client
    client = TestClient(app)

    # Test SanskritiError
    response = client.get("/sanskriti-error")
    assert response.status_code == 418
    data = response.json()
    assert data["error"]["error_code"] == "TEST_ERROR"
    assert data["error"]["message"] == "Test error"

    # Test ValidationError
    response = client.get("/validation-error")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["error_code"] == "VALIDATION_ERROR"

    # Test NotFoundError
    response = client.get("/not-found")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["error_code"] == "NOT_FOUND"

    # Test HTTPException
    response = client.get("/http-error")
    assert response.status_code == 418
    data = response.json()
    assert data["error"]["error_code"] == "HTTP_ERROR"
    assert "teapot" in data["error"]["message"].lower()

    print("All exception handler tests passed!")


if __name__ == "__main__":
    test_exception_handlers()
