"""
Unit Tests for RLS (Row-Level Security) Validation Module
P5.1.4: A04 Insecure Design - RLS validation, tenant_id checks

Tests verify:
1. Tenant context validation functions
2. Resource tenant ownership validation
3. Security exception handling (returns 404 to avoid info leaks)
4. Decorator behavior for protected endpoints
5. Bulk operation tenant filtering
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.security.rls_validation import (
    RLSViolationError,
    TenantContextMissingError,
    add_tenant_filter,
    audit_tenant_access,
    ensure_tenant_isolation,
    get_required_tenant_id,
    get_safe_tenant_id,
    require_tenant_context,
    validate_bulk_tenant_ids,
    validate_model_has_tenant_id,
    validate_resource_tenant,
    validate_tenant_access,
    validate_tenant_id_param,
)

# ============================================================================
# TEST FIXTURES
# ============================================================================


class MockResource:
    """Mock resource with tenant_id for testing"""

    def __init__(self, id: int, tenant_id: int, name: str = "test"):
        self.id = id
        self.tenant_id = tenant_id
        self.name = name


class MockResourceNoTenant:
    """Mock resource without tenant_id (system-wide resource)"""

    def __init__(self, id: int, name: str = "system"):
        self.id = id
        self.name = name


class MockModel:
    """Mock SQLAlchemy model class"""

    tenant_id = MagicMock()
    __name__ = "MockModel"


class MockModelNoTenant:
    """Mock model without tenant_id"""

    __name__ = "MockModelNoTenant"


# ============================================================================
# TEST: RLSViolationError
# ============================================================================


class TestRLSViolationError:
    """Tests for RLS violation exception"""

    def test_returns_404_status_code(self):
        """Security: RLS violations should return 404 to avoid info leaks"""
        error = RLSViolationError()
        assert error.status_code == 404

    def test_default_detail_message(self):
        """Default message should be generic"""
        error = RLSViolationError()
        assert error.detail == "Resource not found"

    def test_custom_detail_message(self):
        """Can customize detail message"""
        error = RLSViolationError(detail="User not found")
        assert error.detail == "User not found"

    def test_logs_violation_with_tenant_info(self, caplog):
        """Should log violation details for audit"""
        with caplog.at_level("WARNING"):
            RLSViolationError(
                detail="Test",
                resource_type="User",
                resource_id=123,
                attempted_tenant=1,
                actual_tenant=2,
            )

        assert "RLS VIOLATION" in caplog.text
        assert "Tenant 1" in caplog.text
        assert "tenant 2" in caplog.text


class TestTenantContextMissingError:
    """Tests for missing tenant context exception"""

    def test_returns_401_status_code(self):
        """Missing context should be 401 Unauthorized"""
        error = TenantContextMissingError()
        assert error.status_code == 401

    def test_includes_www_authenticate_header(self):
        """Should include WWW-Authenticate for proper 401 response"""
        error = TenantContextMissingError()
        assert error.headers == {"WWW-Authenticate": "Bearer"}

    def test_default_detail_message(self):
        """Default message should indicate auth required"""
        error = TenantContextMissingError()
        assert error.detail == "Authentication required"


# ============================================================================
# TEST: validate_resource_tenant
# ============================================================================


class TestValidateResourceTenant:
    """Tests for resource tenant validation"""

    def test_raises_error_for_none_resource(self):
        """Should raise RLSViolationError for None resource"""
        with pytest.raises(RLSViolationError) as exc_info:
            validate_resource_tenant(None, 1)

        assert exc_info.value.status_code == 404

    def test_passes_for_matching_tenant(self):
        """Should pass when tenant IDs match"""
        resource = MockResource(id=1, tenant_id=123)
        # Should not raise
        validate_resource_tenant(resource, 123)

    def test_raises_for_mismatched_tenant(self):
        """Should raise RLSViolationError for mismatched tenant"""
        resource = MockResource(id=1, tenant_id=123)

        with pytest.raises(RLSViolationError) as exc_info:
            validate_resource_tenant(resource, 456)

        assert exc_info.value.status_code == 404

    def test_passes_for_resource_without_tenant_id(self):
        """Should pass for system-wide resources without tenant_id"""
        resource = MockResourceNoTenant(id=1)
        # Should not raise
        validate_resource_tenant(resource, 123)

    def test_includes_resource_type_in_error(self):
        """Should include resource type in error message"""
        with pytest.raises(RLSViolationError) as exc_info:
            validate_resource_tenant(None, 1, resource_type="User")

        assert "User not found" in exc_info.value.detail


# ============================================================================
# TEST: validate_tenant_id_param
# ============================================================================


class TestValidateTenantIdParam:
    """Tests for tenant ID parameter validation"""

    def test_passes_for_matching_tenant(self):
        """Should pass when tenant IDs match"""
        # Should not raise
        validate_tenant_id_param(123, 123)

    def test_raises_403_for_mismatched_tenant(self):
        """Should raise 403 Forbidden for mismatched tenant"""
        with pytest.raises(HTTPException) as exc_info:
            validate_tenant_id_param(456, 123)

        assert exc_info.value.status_code == 403

    def test_error_message_mentions_access_denied(self):
        """Error message should be clear about access denial"""
        with pytest.raises(HTTPException) as exc_info:
            validate_tenant_id_param(456, 123)

        assert "Access denied" in exc_info.value.detail


# ============================================================================
# TEST: ensure_tenant_isolation
# ============================================================================


class TestEnsureTenantIsolation:
    """Tests for tenant isolation enforcement"""

    def test_returns_true_for_model_with_tenant_id(self):
        """Should return True for models with tenant_id"""
        result = ensure_tenant_isolation(MockModel, 123)
        assert result is True

    def test_returns_false_for_model_without_tenant_id(self):
        """Should return False for models without tenant_id"""
        result = ensure_tenant_isolation(MockModelNoTenant, 123)
        assert result is False

    def test_raises_for_none_tenant_id(self):
        """Should raise TenantContextMissingError if tenant_id is None"""
        with pytest.raises(TenantContextMissingError):
            ensure_tenant_isolation(MockModel, None)


# ============================================================================
# TEST: require_tenant_context Decorator
# ============================================================================


class TestRequireTenantContextDecorator:
    """Tests for require_tenant_context decorator"""

    @pytest.mark.asyncio
    async def test_raises_when_no_context(self):
        """Should raise TenantContextMissingError when no tenant context"""

        @require_tenant_context
        async def protected_endpoint():
            return "success"

        with patch("src.core.security.rls_validation.has_tenant_context", return_value=False):
            with pytest.raises(TenantContextMissingError):
                await protected_endpoint()

    @pytest.mark.asyncio
    async def test_passes_when_context_exists(self):
        """Should execute function when tenant context exists"""

        @require_tenant_context
        async def protected_endpoint():
            return "success"

        with patch("src.core.security.rls_validation.has_tenant_context", return_value=True):
            result = await protected_endpoint()
            assert result == "success"


# ============================================================================
# TEST: add_tenant_filter
# ============================================================================


class TestAddTenantFilter:
    """Tests for query tenant filter helper"""

    def test_adds_filter_for_model_with_tenant_id(self):
        """Should add WHERE clause for models with tenant_id"""
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query

        result = add_tenant_filter(mock_query, MockModel, 123)

        mock_query.where.assert_called_once()

    def test_returns_unchanged_query_for_model_without_tenant_id(self):
        """Should return unchanged query for models without tenant_id"""
        mock_query = MagicMock()

        result = add_tenant_filter(mock_query, MockModelNoTenant, 123)

        mock_query.where.assert_not_called()
        assert result == mock_query


# ============================================================================
# TEST: validate_bulk_tenant_ids
# ============================================================================


class TestValidateBulkTenantIds:
    """Tests for bulk tenant validation"""

    def test_filters_out_wrong_tenant_resources(self):
        """Should filter out resources from wrong tenants"""
        resources = [
            MockResource(id=1, tenant_id=123),
            MockResource(id=2, tenant_id=456),  # Wrong tenant
            MockResource(id=3, tenant_id=123),
        ]

        result = validate_bulk_tenant_ids(resources, 123)

        assert len(result) == 2
        assert all(r.tenant_id == 123 for r in result)

    def test_includes_resources_without_tenant_id(self):
        """Should include system resources without tenant_id"""
        resources = [
            MockResource(id=1, tenant_id=123),
            MockResourceNoTenant(id=2),  # System resource
        ]

        result = validate_bulk_tenant_ids(resources, 123)

        assert len(result) == 2

    def test_logs_violations_count(self, caplog):
        """Should log number of filtered resources"""
        resources = [
            MockResource(id=1, tenant_id=456),  # Wrong tenant
            MockResource(id=2, tenant_id=456),  # Wrong tenant
        ]

        with caplog.at_level("WARNING"):
            validate_bulk_tenant_ids(resources, 123, "User")

        assert "2 User records filtered" in caplog.text


# ============================================================================
# TEST: get_safe_tenant_id / get_required_tenant_id
# ============================================================================


class TestTenantIdHelpers:
    """Tests for tenant ID helper functions"""

    def test_get_safe_tenant_id_returns_none_when_not_set(self):
        """Should return None when no tenant context"""
        with patch("src.core.security.rls_validation.get_tenant_id", return_value=None):
            result = get_safe_tenant_id()
            assert result is None

    def test_get_safe_tenant_id_returns_value_when_set(self):
        """Should return tenant ID when context is set"""
        with patch("src.core.security.rls_validation.get_tenant_id", return_value=123):
            result = get_safe_tenant_id()
            assert result == 123

    def test_get_required_tenant_id_raises_when_not_set(self):
        """Should raise TenantContextMissingError when not set"""
        with patch(
            "src.core.security.rls_validation.require_tenant_id",
            side_effect=RuntimeError("Not set"),
        ):
            with pytest.raises(TenantContextMissingError):
                get_required_tenant_id()

    def test_get_required_tenant_id_returns_value_when_set(self):
        """Should return tenant ID when context is set"""
        with patch("src.core.security.rls_validation.require_tenant_id", return_value=123):
            result = get_required_tenant_id()
            assert result == 123


# ============================================================================
# TEST: validate_model_has_tenant_id
# ============================================================================


class TestValidateModelHasTenantId:
    """Tests for model tenant_id validation"""

    def test_returns_true_for_model_with_tenant_id(self):
        """Should return True for models with tenant_id"""
        result = validate_model_has_tenant_id(MockModel)
        assert result is True

    def test_returns_false_for_model_without_tenant_id(self):
        """Should return False for models without tenant_id"""
        result = validate_model_has_tenant_id(MockModelNoTenant)
        assert result is False


# ============================================================================
# TEST: audit_tenant_access
# ============================================================================


class TestAuditTenantAccess:
    """Tests for tenant access auditing"""

    def test_logs_access_event(self, caplog):
        """Should log access event with all details"""
        with caplog.at_level("INFO"):
            audit_tenant_access(
                action="read",
                resource_type="User",
                resource_id=123,
                tenant_id=1,
                user_id=456,
                details={"reason": "admin_view"},
            )

        assert "TENANT_ACCESS" in caplog.text
        assert "read" in caplog.text
        assert "User:123" in caplog.text
        assert "tenant:1" in caplog.text
        assert "user:456" in caplog.text


# ============================================================================
# INTEGRATION TESTS: RLS with actual models
# ============================================================================


class TestRLSWithActualModels:
    """Integration tests verifying RLS with actual database models"""

    def test_workflow_model_has_tenant_id(self):
        """Workflow model should have proper tenant_id column"""
        from src.core.workflow.models import C7Workflow as Workflow

        assert hasattr(Workflow, "tenant_id")
        # Check it's an Integer FK
        col = Workflow.__table__.c.tenant_id
        assert col.nullable is False

    def test_workflow_execution_model_has_tenant_id(self):
        """WorkflowExecution model should have proper tenant_id column"""
        from src.core.workflow.models import C7WorkflowExecution as WorkflowExecution

        assert hasattr(WorkflowExecution, "tenant_id")
        col = WorkflowExecution.__table__.c.tenant_id
        assert col.nullable is False

    def test_learning_experience_model_has_tenant_id(self):
        """LearningExperience model should have proper tenant_id column"""
        from src.core.learning.models import LearningExperience

        assert hasattr(LearningExperience, "tenant_id")
        col = LearningExperience.__table__.c.tenant_id
        assert col.nullable is False

    def test_knowledge_entry_model_has_tenant_id(self):
        """KnowledgeEntry model should have proper tenant_id column"""
        from src.core.knowledge.models import KnowledgeEntry

        assert hasattr(KnowledgeEntry, "tenant_id")
        col = KnowledgeEntry.__table__.c.tenant_id
        assert col.nullable is False

    def test_workflow_experience_model_has_tenant_id(self):
        """WorkflowExperience model should have proper tenant_id column"""
        # Import directly from the .py file to avoid the models/ directory shadowing
        try:
            # Try standard import first
            from src.core.autonomous_workflow.models import WorkflowExperience
        except ImportError:
            # Fall back to direct file import if directory shadows file
            import importlib.util
            import sys
            from pathlib import Path

            models_file = Path("src/core/autonomous_workflow/models.py")
            if not models_file.exists():
                pytest.skip("WorkflowExperience model file not found")

            spec = importlib.util.spec_from_file_location(
                "autonomous_workflow_models_direct", str(models_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            WorkflowExperience = module.WorkflowExperience

        assert hasattr(WorkflowExperience, "tenant_id")
        col = WorkflowExperience.__table__.c.tenant_id
        assert col.nullable is False

    def test_agent_model_has_tenant_id(self):
        """Agent model should have proper tenant_id column"""
        from src.core.agents.models import Agent

        assert hasattr(Agent, "tenant_id")
        col = Agent.__table__.c.tenant_id
        assert col.nullable is False

    def test_conversation_model_has_tenant_id(self):
        """Conversation model should have proper tenant_id column"""
        from src.core.conversations.models import Conversation

        assert hasattr(Conversation, "tenant_id")
        col = Conversation.__table__.c.tenant_id
        assert col.nullable is False

    def test_cva_conversation_model_has_tenant_id(self):
        """CVAConversation model should have proper tenant_id column"""
        from src.core.conversations.models import CVAConversation

        assert hasattr(CVAConversation, "tenant_id")
        col = CVAConversation.__table__.c.tenant_id
        assert col.nullable is False

    def test_user_session_model_has_tenant_id(self):
        """UserSession model should have proper tenant_id column"""
        from src.core.conversations.models import UserSession

        assert hasattr(UserSession, "tenant_id")
        col = UserSession.__table__.c.tenant_id
        assert col.nullable is False
