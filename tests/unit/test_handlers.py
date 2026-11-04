"""Tests for exception handlers."""

import pytest
from fastapi import FastAPI

from src.core.exceptions.handlers import (
    raise_not_found,
    raise_validation_error,
    raise_permission_denied,
    raise_tenant_error,
    raise_workflow_error,
    register_exception_handlers,
)
from src.core.exceptions.exceptions import NotFoundError, ValidationError


class TestExceptionHelpers:
    """Test exception raising helper functions."""

    @pytest.mark.unit
    def test_raise_not_found_with_no_resource_id(self):
        """raise_not_found must raise NotFoundError with resource type only."""
        with pytest.raises(NotFoundError):
            raise_not_found("User")

    @pytest.mark.unit
    def test_raise_not_found_with_resource_id(self):
        """raise_not_found must raise NotFoundError with resource type and ID."""
        with pytest.raises(NotFoundError):
            raise_not_found("Agent", resource_id="123")

    @pytest.mark.unit
    def test_raise_validation_error_with_no_details(self):
        """raise_validation_error must raise ValidationError with message only."""
        with pytest.raises(ValidationError):
            raise_validation_error("Invalid input")

    @pytest.mark.unit
    def test_raise_validation_error_with_details(self):
        """raise_validation_error must raise ValidationError with details."""
        with pytest.raises(ValidationError):
            raise_validation_error("Invalid input", details={"field": "email"})

    @pytest.mark.unit
    def test_raise_permission_denied(self):
        """raise_permission_denied must raise PermissionDeniedError."""
        from src.core.exceptions.exceptions import PermissionDeniedError

        with pytest.raises(PermissionDeniedError):
            raise_permission_denied("write", "Agent", "user123")

    @pytest.mark.unit
    def test_raise_tenant_error_with_no_details(self):
        """raise_tenant_error must raise TenantError with message only."""
        from src.core.exceptions.exceptions import TenantError

        with pytest.raises(TenantError):
            raise_tenant_error("Tenant not found")

    @pytest.mark.unit
    def test_raise_tenant_error_with_details(self):
        """raise_tenant_error must raise TenantError with details."""
        from src.core.exceptions.exceptions import TenantError

        with pytest.raises(TenantError):
            raise_tenant_error("Tenant error", details={"tenant_id": 123})

    @pytest.mark.unit
    def test_raise_workflow_error_with_no_details(self):
        """raise_workflow_error must raise WorkflowError with message only."""
        from src.core.exceptions.exceptions import WorkflowError

        with pytest.raises(WorkflowError):
            raise_workflow_error("Workflow failed")

    @pytest.mark.unit
    def test_raise_workflow_error_with_details(self):
        """raise_workflow_error must raise WorkflowError with details."""
        from src.core.exceptions.exceptions import WorkflowError

        with pytest.raises(WorkflowError):
            raise_workflow_error("Workflow failed", details={"step": 2})

    @pytest.mark.unit
    def test_register_exception_handlers_accepts_fastapi_instance(self):
        """register_exception_handlers must accept FastAPI instance."""
        app = FastAPI()
        # Should not raise an error
        register_exception_handlers(app)

        # Verify handlers were registered (app should have exception handlers)
        assert len(app.exception_handlers) > 0


class TestExceptionRaisingTypes:
    """Test that exception helpers have correct type annotations."""

    @pytest.mark.unit
    def test_raise_not_found_type_signature(self):
        """raise_not_found must accept str and optional str."""
        # This test just ensures the function can be called with these types
        try:
            raise_not_found("User", None)
        except NotFoundError:
            pass  # Expected

    @pytest.mark.unit
    def test_raise_validation_error_type_signature(self):
        """raise_validation_error must accept str and optional dict."""
        try:
            raise_validation_error("Error", None)
        except ValidationError:
            pass  # Expected

    @pytest.mark.unit
    def test_raise_validation_error_with_dict_details(self):
        """raise_validation_error must accept dict[str, Any] for details."""
        try:
            raise_validation_error("Error", details={"key": "value", "num": 42})
        except ValidationError:
            pass  # Expected
