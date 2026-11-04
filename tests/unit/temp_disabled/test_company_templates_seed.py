"""
Test Company Template Seeding

CRITICAL TEST: Verifies that company templates are seeded in the database.
Without this, users cannot create companies.
"""

import pytest
from sqlalchemy import delete, select

from src.core.company.models import CompanyTemplate
from src.core.company.seed_templates import SEED_TEMPLATES, seed_platform_templates
from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_company_templates_seeded(monkeypatch: pytest.MonkeyPatch):
    """
    CRITICAL: Company templates must exist in database.

    This test verifies that seed_platform_templates() creates
    templates that can be used for company creation.
    """
    # Initialize database
    initialized = await db_manager.initialize()
    assert initialized, "Database must be initialized"

    try:
        async with db_manager.get_session() as session:
            expected_count = len(SEED_TEMPLATES)
            expected_names = {template["name"] for template in SEED_TEMPLATES}

            # Seeder must not execute runtime DDL; schema belongs to migrations.
            def _forbid_runtime_create(*args, **kwargs):
                raise AssertionError("seed_platform_templates must not call Table.create at runtime")

            monkeypatch.setattr(CompanyTemplate.__table__, "create", _forbid_runtime_create)

            # Start from a deterministic baseline for exact count assertions.
            with TenantFilterBypass():
                await session.execute(
                    delete(CompanyTemplate).where(CompanyTemplate.is_platform_template.is_(True))
                )
            await session.commit()

            # Seed templates
            first_count = await seed_platform_templates(session)

            # Verify templates were created (platform templates are cross-tenant/global)
            with TenantFilterBypass():
                result = await session.execute(
                    select(CompanyTemplate).where(CompanyTemplate.is_platform_template.is_(True))
                )
                seeded_templates = result.scalars().all()

            # Run seeding a second time to prove idempotency.
            second_count = await seed_platform_templates(session)
            with TenantFilterBypass():
                second_result = await session.execute(
                    select(CompanyTemplate).where(CompanyTemplate.is_platform_template.is_(True))
                )
                templates_after_second_run = second_result.scalars().all()

            # Assertions
            assert first_count == expected_count, (
                f"Expected exactly {expected_count} inserted templates on first seed, got {first_count}"
            )
            assert len(seeded_templates) == expected_count, (
                f"Expected exactly {expected_count} platform templates, got {len(seeded_templates)}"
            )
            assert second_count == 0, (
                f"Expected idempotent second seed to insert 0 templates, got {second_count}"
            )
            assert len(templates_after_second_run) == expected_count, (
                "Expected total platform template count to stay unchanged on second seed"
            )

            seeded_names = {template.name for template in seeded_templates}
            assert seeded_names == expected_names, "Seeded template names must exactly match seed source"

            # Verify template structure
            for template in seeded_templates:
                assert template.name is not None, "Template must have name"
                assert template.company_type in [
                    "mkb",
                    "zzp",
                    "enterprise",
                ], f"Invalid company_type: {template.company_type}"
                assert template.sector is not None, "Template must have sector"
                assert template.is_platform_template is True, "Template must be platform template"
                assert isinstance(template.template_definition, dict), (
                    "Template definition must be a dict"
                )
                assert template.template_definition.get("departments"), (
                    "Template must contain at least one department"
                )
                assert template.template_definition.get("goals"), (
                    "Template must contain at least one goal"
                )

            print(f"✅ Successfully verified {len(seeded_templates)} company templates")

    finally:
        await db_manager.close()


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_api_returns_templates():
    """
    Test that the API endpoint returns templates.

    This simulates what the frontend calls when browsing templates.
    """
    from fastapi.testclient import TestClient

    from src.main import app

    client = TestClient(app)

    # Note: This requires authentication, so it will likely return 401
    # But it verifies the endpoint exists and is registered
    response = client.get("/api/v1/templates")

    # Should not be 404 (endpoint doesn't exist)
    assert response.status_code != 404, "Template API endpoint must exist"

    # Without auth, expect 401 or 403
    assert response.status_code in [200, 401, 403], f"Unexpected status: {response.status_code}"

    print(f"✅ Template API endpoint exists (status: {response.status_code})")
