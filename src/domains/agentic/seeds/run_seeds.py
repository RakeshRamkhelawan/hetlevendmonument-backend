"""
Database Seeder for Agentic System

Populates the database with platform features, prompt templates, and tool definitions.
This script is idempotent - it can be run multiple times safely.

Usage:
    docker exec sanskritisetu_backend python -m src.domains.agentic.seeds.run_seeds
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.database.database import db_manager

# Import RBAC models first to ensure Tenant/User are in the mapper registry
# before agentic models (which have relationships to them) are used
from src.core.models.rbac_models import Tenant, User  # noqa: F401
from src.domains.agentic.models import Feature, PromptTemplate, ToolDefinition
from src.domains.agentic.seeds import INITIAL_PROMPT_TEMPLATES, PLATFORM_FEATURES, TOOL_DEFINITIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_features(db: AsyncSession, tenant_id: int) -> int:
    """Seed platform features. Returns count of inserted records.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): Feature.tenant_id is
    NOT NULL (ADR-005) -- tenant_id is now a required parameter instead of being
    silently omitted (which raised IntegrityError under the NOT NULL constraint).
    """
    inserted: int = 0
    for feature_data in PLATFORM_FEATURES:
        # Check if feature already exists for this tenant
        result = await db.execute(
            select(Feature).where(Feature.id == feature_data["id"], Feature.tenant_id == tenant_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Feature '{feature_data['id']}' already exists, skipping.")
            continue

        # Create Feature with exact model fields
        feature = Feature(
            id=feature_data["id"],
            tenant_id=tenant_id,
            name=feature_data["name"],
            description=feature_data["description"],
            category=feature_data["category"],
            icon=feature_data.get("icon"),
            color=feature_data.get("color"),
            keywords=feature_data.get("keywords"),
            example_queries=feature_data.get("example_queries"),
            capabilities=feature_data.get("capabilities"),
            intent_keywords=feature_data.get("intent_keywords"),
            route_patterns=feature_data.get("route_patterns"),
            domain_context=feature_data.get("domain_context"),
            is_active=feature_data.get("is_active", True),
        )
        db.add(feature)
        inserted += 1
        logger.info(f"Inserted feature: {feature_data['id']}")

    return inserted


async def seed_tools(db: AsyncSession, tenant_id: int) -> int:
    """Seed tool definitions. Returns count of inserted records.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): ToolDefinition.tenant_id
    is NOT NULL (ADR-005) -- tenant_id is now a required parameter.
    """
    inserted: int = 0
    for tool_data in TOOL_DEFINITIONS:
        # Check if tool already exists for this tenant
        result = await db.execute(
            select(ToolDefinition).where(
                ToolDefinition.name == tool_data["name"], ToolDefinition.tenant_id == tenant_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Tool '{tool_data['name']}' already exists, skipping.")
            continue

        # Create ToolDefinition with exact model fields
        tool = ToolDefinition(
            tenant_id=tenant_id,
            name=tool_data["name"],
            display_name=tool_data["display_name"],
            description=tool_data["description"],
            category=tool_data["category"],
            function_schema=tool_data["function_schema"],
            implementation_type=tool_data.get("implementation_type", "internal"),
            implementation_config=tool_data.get("implementation_config"),
            required_permissions=tool_data.get("required_permissions"),
            is_active=tool_data.get("is_active", True),
        )
        db.add(tool)
        inserted += 1
        logger.info(f"Inserted tool: {tool_data['name']}")

    return inserted


async def seed_prompt_templates(db: AsyncSession, tenant_id: int) -> int:
    """Seed prompt templates. Returns count of inserted records.

    SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): PromptTemplate.tenant_id
    is NOT NULL (ADR-005) -- tenant_id is now a required parameter.
    """
    inserted: int = 0
    for template_data in INITIAL_PROMPT_TEMPLATES:
        # Check if template already exists for this tenant
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.name == template_data["name"],
                PromptTemplate.tenant_id == tenant_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Template '{template_data['name']}' already exists, skipping.")
            continue

        # Create PromptTemplate with exact model fields
        template = PromptTemplate(
            tenant_id=tenant_id,
            name=template_data["name"],
            version=template_data["version"],
            system_prompt=template_data["system_prompt"],
            context_template=template_data.get("context_template"),
            output_format=template_data.get("output_format"),
            supported_locales=template_data.get("supported_locales"),
            localized_variants=template_data.get("localized_variants"),
            status=template_data.get("status", "draft"),
        )
        db.add(template)
        inserted += 1
        logger.info(f"Inserted template: {template_data['name']}")

    return inserted


async def run_all_seeds(tenant_id: int = 1) -> dict[str, int]:
    """Run all seeders and return counts.

    Args:
        tenant_id: Tenant to seed platform data for. Defaults to 1 (the system/
            platform tenant) for backward-compatible standalone script usage --
            see SP-DATA-ARCH-1 for context (was previously omitted entirely).
    """
    results: dict[str, int] = {}

    # Initialize database manager if not already initialized
    if not db_manager.is_initialized():
        await db_manager.initialize()

    async with db_manager.get_session() as db:
        try:
            # De klant wordt AANGENOMEN en niet alleen doorgegeven (ADR-036 OP-153).
            #
            # Dit script draait met de hand, buiten elk verzoek, dus de ContextVar is
            # leeg. De drie zaaifuncties filteren keurig op `tenant_id` in Python, maar
            # `features`, `tools` en `prompt_templates` hebben ook een afschermingsregel
            # in de database, en die leest de klant uit `app.current_tenant`. Zonder deze
            # regel faalt elke INSERT hieronder zodra `DATABASE_URL` naar
            # `sanskritisetu_app` wijst.
            async with adopt_tenant(db, tenant_id):
                results["features"] = await seed_features(db, tenant_id)
                results["tools"] = await seed_tools(db, tenant_id)
                results["templates"] = await seed_prompt_templates(db, tenant_id)

                # De commit staat BINNEN het blok, en dat is geen detail.
                #
                # `db.add(...)` in de zaaifuncties stuurt nog geen SQL; SQLAlchemy voert
                # de INSERTs pas uit bij de flush die `commit()` veroorzaakt. Staat die
                # commit buiten het blok, dan draaien juist die INSERTs weer zonder
                # klantcontext -- `adopt_tenant` zet de instelling bij het verlaten terug.
                # Het zaaien zou dan alsnog falen, terwijl de code er correct uitziet.
                await db.commit()
            logger.info(f"Seeding complete: {results}")

        except Exception as e:
            await db.rollback()
            logger.error(f"Seeding failed: {e}")
            raise

    return results


def main() -> None:
    """Entry point."""
    logger.info("Starting agentic system database seeding...")
    results = asyncio.run(run_all_seeds())
    print("\n=== Seeding Complete ===")
    print(f"Features inserted: {results.get('features', 0)}")
    print(f"Tools inserted: {results.get('tools', 0)}")
    print(f"Templates inserted: {results.get('templates', 0)}")


if __name__ == "__main__":
    main()
