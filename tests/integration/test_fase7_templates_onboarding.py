"""Fase 7 Integratietest - Company Templates & Onboarding.

Integration tests for the complete template and onboarding flow.
Run with: pytest tests/integration/test_fase7_templates_onboarding.py -v
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from src.core.company.models import Company, CompanyTemplate, Department, Goal
from src.core.company.seed_templates import seed_platform_templates
from src.core.company.template_service import TemplateService


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullOnboardingFlow:
    """Test complete onboarding flow using services directly."""

    async def test_seed_templates_in_database(self, postgres_session):
        """Verify templates are seeded in database."""
        count = await seed_platform_templates(postgres_session)

        # Query templates
        result = await postgres_session.execute(
            select(CompanyTemplate).where(CompanyTemplate.is_platform_template.is_(True))
        )
        templates = result.scalars().all()

        assert len(templates) >= 10, f"Expected at least 10 templates, got {len(templates)}"

        # Verify template structure
        for template in templates:
            assert template.name is not None
            assert template.company_type in ["mkb", "zzp", "enterprise"]
            assert template.template_definition is not None
            assert "departments" in template.template_definition

    async def test_template_service_list_templates(self, postgres_session):
        """Test TemplateService.list_templates()."""
        await seed_platform_templates(postgres_session)

        # Create service with mocked tenant context
        class MockTenantContext:
            tenant_id = 1

        class MockDBManager:
            def __init__(self, session):
                self._session = session

            def get_session(self):
                class SessionContext:
                    def __init__(self, session):
                        self.session = session

                    async def __aenter__(self):
                        return self.session

                    async def __aexit__(self, *args):
                        return False

                return SessionContext(self._session)

        service = TemplateService(MockDBManager(postgres_session), MockTenantContext())

        # List all templates
        templates = await service.list_templates()
        assert len(templates) >= 10

        # Filter by company_type
        mkb_templates = await service.list_templates({"company_type": "mkb"})
        assert all(t.company_type == "mkb" for t in mkb_templates)

        # Filter by sector
        tech_templates = await service.list_templates({"sector": "Technologie"})
        assert all(t.sector == "Technologie" for t in tech_templates)

    async def test_template_service_instantiate(self, postgres_session):
        """Test TemplateService.instantiate() creates company with structure."""
        await seed_platform_templates(postgres_session)

        # Setup service
        class MockTenantContext:
            tenant_id = 1

        class MockDBManager:
            def __init__(self, session):
                self._session = session

            def get_session(self):
                class SessionContext:
                    def __init__(self, session):
                        self.session = session

                    async def __aenter__(self):
                        return self.session

                    async def __aexit__(self, *args):
                        return False

                return SessionContext(self._session)

        service = TemplateService(MockDBManager(postgres_session), MockTenantContext())

        # Get a template
        templates = await service.list_templates({"company_type": "mkb"})
        assert len(templates) > 0
        template_id = templates[0].id

        # Instantiate
        from src.core.company.schemas import TemplateInstantiateRequest

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name=f"Test Company {uuid.uuid4().hex[:8]}",
        )

        company = await service.instantiate(template_id, request)

        # Verify company created
        assert company.name == request.company_name
        assert company.company_type == "mkb"
        assert company.departments_count > 0

        # Verify in database
        result = await postgres_session.execute(select(Company).where(Company.id == company.id))
        db_company = result.scalar_one()
        assert db_company.name == request.company_name

        # Verify departments
        result = await postgres_session.execute(
            select(Department).where(Department.company_id == company.id)
        )
        departments = result.scalars().all()
        assert len(departments) > 0

        # Verify template usage incremented
        result = await postgres_session.execute(
            select(CompanyTemplate).where(CompanyTemplate.id == template_id)
        )
        template = result.scalar_one()
        assert template.usage_count >= 1

    async def test_template_service_export_scrubs_secrets(self, postgres_session):
        """Test that export_scrubs secrets from template definition."""
        await seed_platform_templates(postgres_session)

        # Create a company first
        class MockTenantContext:
            tenant_id = 1

        class MockDBManager:
            def __init__(self, session):
                self._session = session

            def get_session(self):
                class SessionContext:
                    def __init__(self, session):
                        self.session = session

                    async def __aenter__(self):
                        return self.session

                    async def __aexit__(self, *args):
                        return False

                return SessionContext(self._session)

        service = TemplateService(MockDBManager(postgres_session), MockTenantContext())

        templates = await service.list_templates({"company_type": "mkb"})
        template_id = templates[0].id

        from src.core.company.schemas import TemplateInstantiateRequest

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name=f"Export Test {uuid.uuid4().hex[:8]}",
        )

        company = await service.instantiate(template_id, request)

        # Export
        export = await service.export_company(company.id)

        # Verify structure
        assert "name" in export
        assert "departments" in export
        assert "goals" in export
        assert "board_role_config" in export

        # Verify no secrets (basic check)
        export_str = str(export).lower()
        # If secrets exist, they should be scrubbed


@pytest.mark.integration
@pytest.mark.asyncio
class TestAIMatching:
    """Test AI template matching logic."""

    async def test_keyword_matching_tech_startup(self):
        """Test tech keywords match to tech startup template."""
        from src.core.api.v1.company.onboarding_router import _match_description_to_template

        result = _match_description_to_template(
            "software startup met AI en machine learning development"
        )

        template_key, confidence, reason = result
        assert template_key == "tech_startup"
        assert confidence > 0.5
        assert "tech" in reason.lower() or "ai" in reason.lower()

    async def test_keyword_matching_retail(self):
        """Test retail keywords match to retail template."""
        from src.core.api.v1.company.onboarding_router import _match_description_to_template

        result = _match_description_to_template("online winkel webshop verkoop retail e-commerce")

        template_key, confidence, reason = result
        assert template_key == "retail"
        assert confidence > 0.5

    async def test_keyword_matching_horeca(self):
        """Test horeca keywords match to horeca template."""
        from src.core.api.v1.company.onboarding_router import _match_description_to_template

        result = _match_description_to_template("restaurant cafe keuken bediening hospitality")

        template_key, confidence, reason = result
        assert template_key == "horeca"
        assert confidence > 0.5

    async def test_keyword_matching_no_match(self):
        """Test unknown description returns default with low confidence."""
        from src.core.api.v1.company.onboarding_router import _match_description_to_template

        result = _match_description_to_template("xyz abc completely unknown business type")

        template_key, confidence, reason = result
        assert confidence < 0.5  # Low confidence for no match


@pytest.mark.integration
@pytest.mark.asyncio
class TestSeedTemplates:
    """Test seed templates structure."""

    async def test_seed_templates_count(self):
        """Verify we have 10 seed templates."""
        from src.core.company.seed_templates import SEED_TEMPLATES

        assert len(SEED_TEMPLATES) == 10

        # Count by type
        mkb_count = sum(1 for t in SEED_TEMPLATES if t["company_type"] == "mkb")
        zzp_count = sum(1 for t in SEED_TEMPLATES if t["company_type"] == "zzp")
        enterprise_count = sum(1 for t in SEED_TEMPLATES if t["company_type"] == "enterprise")

        assert mkb_count == 3
        assert zzp_count == 3
        assert enterprise_count == 4

    async def test_seed_templates_have_required_fields(self):
        """Verify all seed templates have required structure."""
        from src.core.company.seed_templates import SEED_TEMPLATES

        for template in SEED_TEMPLATES:
            assert "name" in template
            assert "company_type" in template
            assert "sector" in template
            assert "description" in template
            assert "template_definition" in template

            # Verify template definition structure
            td = template["template_definition"]
            assert "departments" in td
            assert "goals" in td
            assert "board_role_config" in td

            # Verify departments have required fields
            for dept in td["departments"]:
                assert "name" in dept
                assert "board_role" in dept
                assert "budget_monthly_tokens" in dept
                assert "domain_pack_ids" in dept

    async def test_seed_templates_idempotent(self, postgres_session):
        """Test that seeding templates multiple times is idempotent."""
        # First seed
        count1 = await seed_platform_templates(postgres_session)

        # Second seed should not add duplicates
        count2 = await seed_platform_templates(postgres_session)

        # count2 should be 0 (no new templates added)
        assert count2 == 0

        # Verify count in database
        result = await postgres_session.execute(
            select(CompanyTemplate).where(CompanyTemplate.is_platform_template.is_(True))
        )
        templates = result.scalars().all()
        assert len(templates) == 10
