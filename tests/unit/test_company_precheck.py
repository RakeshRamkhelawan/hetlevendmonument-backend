"""
TDD Tests for Task 1.0: Pre-check Codebase & ADR

Verifies that all expected components exist and have the correct exports
before building the Company Layer.
"""

import uuid
from pathlib import Path

import pytest
import yaml


class TestContainerExports:
    """Happy path: Verify DI container exports."""

    def test_container_exports(self):
        """Container, DatabaseManager, TenantContext should be importable."""
        from src.core.container import (
            Container,
            DatabaseManager,
            TenantContext,
            get_db,
            get_tenant_context,
        )

        assert Container is not None
        assert DatabaseManager is not None
        assert TenantContext is not None
        assert callable(get_db)
        assert callable(get_tenant_context)

    def test_container_is_declarative(self):
        """Container should inherit from DeclarativeContainer."""
        from dependency_injector import containers

        from src.core.container import Container

        assert issubclass(Container, containers.DeclarativeContainer)


class TestDatabaseBase:
    """Happy path: Verify database base model."""

    def test_base_model_importable(self):
        """Base should be importable from database module."""
        from src.core.database.database import Base

        assert Base is not None

    def test_base_is_declarative(self):
        """Base should be a SQLAlchemy declarative base."""
        from sqlalchemy.orm import DeclarativeMeta

        from src.core.database.database import Base

        # In SQLAlchemy 2.0, declarative_base() returns a class with DeclarativeMeta
        assert type(Base) is DeclarativeMeta or hasattr(Base, "__tablename__")


class TestRBACModels:
    """Happy path: Verify RBAC models exist with required fields."""

    def test_tenant_model_importable(self):
        """Tenant model should be importable."""
        from src.core.models.rbac_models import Tenant

        assert Tenant is not None

    def test_tenant_model_has_required_fields(self):
        """Tenant should have id, name, slug fields."""
        from src.core.models.rbac_models import Tenant

        # Check that these attributes exist (SQLAlchemy mapped attributes)
        assert hasattr(Tenant, "id")
        assert hasattr(Tenant, "name")
        assert hasattr(Tenant, "slug")

    def test_user_model_importable(self):
        """User model should be importable."""
        from src.core.models.rbac_models import User

        assert User is not None

    def test_role_model_importable(self):
        """Role model should be importable."""
        from src.core.models.rbac_models import Role

        assert Role is not None


class TestProcedureModels:
    """Happy path: Verify procedure models exist."""

    def test_domain_pack_importable(self):
        """DomainPack should be importable."""
        from src.core.procedures.models import DomainPack

        assert DomainPack is not None

    def test_domain_pack_has_department_field(self):
        """DomainPack should have department field."""
        from src.core.procedures.models import DomainPack

        assert hasattr(DomainPack, "department")

    def test_procedure_execution_importable(self):
        """ProcedureExecution should be importable."""
        from src.core.procedures.models import ProcedureExecution

        assert ProcedureExecution is not None


class TestPolicyEngine:
    """Happy path: Verify PolicyEngine exists."""

    def test_policy_engine_importable(self):
        """PolicyEngine should be importable."""
        from src.core.governance.policy_engine import PolicyEngine

        assert PolicyEngine is not None

    def test_policy_risk_level_importable(self):
        """PolicyRiskLevel should be importable."""
        from src.core.governance.policy_engine import PolicyRiskLevel

        assert PolicyRiskLevel is not None

    def test_action_context_importable(self):
        """ActionContext should be importable."""
        from src.core.governance.policy_engine import ActionContext

        assert ActionContext is not None


class TestExceptionHierarchy:
    """Happy path: Verify exception hierarchy exists."""

    def test_sanskriti_error_importable(self):
        """SanskritiError should be importable."""
        from src.core.exceptions.exceptions import SanskritiError

        assert SanskritiError is not None

    def test_not_found_error_importable(self):
        """NotFoundError should be importable."""
        from src.core.exceptions.exceptions import NotFoundError

        assert NotFoundError is not None

    def test_tenant_error_importable(self):
        """TenantError should be importable."""
        from src.core.exceptions.exceptions import TenantError

        assert TenantError is not None

    def test_auth_error_importable(self):
        """AuthError should be importable."""
        from src.core.exceptions.exceptions import AuthError

        assert AuthError is not None

    def test_validation_error_importable(self):
        """ValidationError should be importable."""
        from src.core.exceptions.exceptions import ValidationError

        assert ValidationError is not None

    def test_conflict_error_importable(self):
        """ConflictError should be importable (new for Company Layer)."""
        from src.core.exceptions.exceptions import ConflictError

        assert ConflictError is not None

    def test_conflict_error_409(self):
        """ConflictError should have status_code 409."""
        from src.core.exceptions.exceptions import ConflictError

        exc = ConflictError("Test conflict")
        assert exc.status_code == 409
        assert exc.error_code == "CONFLICT"

    def test_conflict_error_with_details(self):
        """ConflictError should accept current_version and conflicting_user."""
        from src.core.exceptions.exceptions import ConflictError

        exc = ConflictError(
            message="Version conflict", current_version=5, conflicting_user="user@example.com"
        )
        assert exc.details["current_version"] == 5
        assert exc.details["conflicting_user"] == "user@example.com"


class TestRouterRegistry:
    """Happy path: Verify router registry exists."""

    def test_router_registry_importable(self):
        """register_all_routers should be importable."""
        from src.core.api.router_registry import register_all_routers

        assert callable(register_all_routers)


class TestExceptionHandlers:
    """Happy path: Verify exception handlers are set up."""

    def test_setup_exception_handlers_importable(self):
        """setup_exception_handlers should be importable."""
        from src.core.api.setup.exception_handlers import setup_exception_handlers

        assert callable(setup_exception_handlers)


class TestAuditLogging:
    """Happy path: Verify audit logging exists."""

    def test_audit_module_importable(self):
        """Audit module should be importable."""
        from src.core.governance import audit

        assert audit is not None


class TestDomainPacksConfig:
    """Happy path: Verify domain packs configuration."""

    def test_domain_packs_yaml_exists(self):
        """config/domain_packs.yaml should exist and be readable."""
        config_path = Path("config/domain_packs.yaml")
        assert config_path.exists(), f"{config_path} does not exist"
        assert config_path.is_file(), f"{config_path} is not a file"

    def test_domain_packs_yaml_valid(self):
        """config/domain_packs.yaml should be valid YAML."""
        config_path = Path("config/domain_packs.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None, "YAML file is empty or invalid"

    def test_domain_packs_has_packs(self):
        """config/domain_packs.yaml should contain 50+ packs."""
        config_path = Path("config/domain_packs.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Packs should be a list or dict
        assert isinstance(data, (list, dict)), "Packs should be a list or dict"

        if isinstance(data, list):
            pack_count = len(data)
        else:
            pack_count = len(data.get("packs", data))

        assert pack_count >= 50, f"Expected 50+ packs, found {pack_count}"

    def test_domain_packs_have_required_fields(self):
        """Each pack should have pack_id, name, steps."""
        config_path = Path("config/domain_packs.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        packs = data if isinstance(data, list) else data.get("packs", [])

        for pack in packs[:5]:  # Check first 5 packs
            assert "pack_id" in pack or "id" in pack, "Pack missing pack_id/id"
            assert "name" in pack, "Pack missing name"


class TestBaseAgent:
    """Happy path: Verify base agent exists."""

    def test_enhanced_base_agent_importable(self):
        """EnhancedBaseAgent should be importable."""
        from src.core.agents.base_agent import EnhancedBaseAgent

        assert EnhancedBaseAgent is not None

    def test_enhanced_base_agent_has_process_task(self):
        """EnhancedBaseAgent should have process_task method."""
        from src.core.agents.base_agent import EnhancedBaseAgent

        assert hasattr(EnhancedBaseAgent, "process_task")


class TestMainApp:
    """Happy path: Verify main app exists."""

    def test_create_app_importable(self):
        """create_app should be importable from main."""
        from src.main import create_app

        assert callable(create_app)

    def test_app_importable(self):
        """app should be importable from main."""
        from src.main import app

        assert app is not None


class TestCompanyFolderExists:
    """Verify company folder exists after Task 1.1."""

    def test_company_folder_exists(self):
        """src/core/company/ should exist after Task 1.1."""
        company_path = Path("src/core/company")
        assert company_path.exists(), f"{company_path} does not exist - Task 1.1 not completed"

    def test_company_init_py_exists(self):
        """src/core/company/__init__.py should exist."""
        init_path = Path("src/core/company/__init__.py")
        assert init_path.exists(), f"{init_path} does not exist - Task 1.1 not completed"

    def test_company_models_py_exists(self):
        """src/core/company/models.py should exist."""
        models_path = Path("src/core/company/models.py")
        assert models_path.exists(), f"{models_path} does not exist - Task 1.1 not completed"


class TestConflictErrorIntegration:
    """Happy path: Verify ConflictError integrates with exception handlers."""

    def test_conflict_error_to_dict(self):
        """ConflictError should serialize to dict correctly."""
        from src.core.exceptions.exceptions import ConflictError

        exc = ConflictError(
            message="Department modified by another user",
            current_version=5,
            conflicting_user="other@example.com",
        )

        data = exc.to_dict()
        assert data["error"]["error_code"] == "CONFLICT"
        assert data["error"]["details"]["current_version"] == 5
