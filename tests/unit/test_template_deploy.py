"""
Unit tests for One-Click Template Deploy (TASK-003)
Tests the ADR-033 proxy stub behaviour of the deprecated deploy endpoint.
"""

from unittest.mock import MagicMock

import pytest

from src.core.api.template_endpoints import deploy_template


class TestTemplateDeploy:
    """Test Template Deploy endpoint (ADR-033 proxy stub)"""

    @pytest.fixture
    def mock_response(self):
        return MagicMock()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.tenant_id = 1
        user.id = 100
        return user

    @pytest.mark.asyncio
    async def test_deploy_template_returns_deprecated_stub(self, mock_response, mock_db, mock_user):
        """Stub always returns deprecated message with version=None (ADR-033 compliant)."""
        response = await deploy_template("test-tpl", mock_response, mock_db, mock_user)

        assert response["workflow_id"] == "tpl_test-tpl"
        assert response["version"] is None
        assert "deprecated" in response["message"].lower()

    @pytest.mark.asyncio
    async def test_deploy_template_sets_deprecation_header(self, mock_response, mock_db, mock_user):
        """Stub sets Deprecation header on the response."""
        await deploy_template("test-tpl", mock_response, mock_db, mock_user)

        mock_response.headers.__setitem__.assert_any_call("Deprecation", "true")

    @pytest.mark.asyncio
    async def test_deploy_template_any_id_returns_stub(self, mock_response, mock_db, mock_user):
        """Stub returns consistent response for any template_id, including non-existent ones."""
        response = await deploy_template("non-existent", mock_response, mock_db, mock_user)

        assert response["workflow_id"] == "tpl_non-existent"
        assert response["version"] is None
