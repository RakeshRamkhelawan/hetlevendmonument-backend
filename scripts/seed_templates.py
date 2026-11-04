#!/usr/bin/env python3
"""
Seed workflow templates into the database.
Idempotent script that can be run multiple times safely.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config.unified_config import config
from src.core.database.database import Base
from src.core.workflow.models import WorkflowTemplate
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402

# Template files to seed
TEMPLATE_FILES = [
    "templates/customer_ticket_triage.json",
    "templates/customer_feedback_analysis.json",
    "templates/spreadsheet_data_sync.json",
    "templates/webhook_data_capture.json",
    "templates/document_classification.json",
    "templates/email_campaign_sender.json",
    "templates/daily_report_generator.json",
    "templates/real_time_monitoring.json",
    "templates/community_member_onboarding.json",
    "templates/heritage_artifact_curation.json",
]


async def load_templates_from_files() -> List[Dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Load template data from JSON files."""
    templates = []
    project_root = Path(__file__).parent.parent

    for template_file in TEMPLATE_FILES:
        file_path = project_root / template_file
        if not file_path.exists():
            print(f"[FAIL] Template file not found: {template_file}")
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                template_data = json.load(f)
                templates.append(template_data)
                print(f"[OK] Loaded template: {template_data['template_id']}")
        except Exception as e:
            print(f"[FAIL] Failed to load template {template_file}: {e}")

    return templates


async def seed_templates():
    """Seed workflow templates into database."""
    # Get database configuration
    db_config = config.get_database_config()
    database_url = db_config["url"]

    print(f"[LINK] Connecting to database: {database_url_zonder_wachtwoord(database_url)}")

    # Create engine and session
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Load templates from files
    templates = await load_templates_from_files()
    print(f"\n[CHART] Loaded {len(templates)} templates from files")

    async with async_session() as session:
        try:
            # Process each template
            for template_data in templates:
                template_id = template_data["template_id"]

                # Check if template already exists
                stmt = select(WorkflowTemplate).where(WorkflowTemplate.template_id == template_id)
                result = await session.execute(stmt)
                existing_template = result.scalar_one_or_none()

                if existing_template:
                    print(f"[U+0001F504] Updating existing template: {template_id}")
                    # Update existing template
                    existing_template.name = template_data["name"]
                    existing_template.category = template_data["category"]
                    existing_template.description = template_data["description"]
                    existing_template.spec_json = template_data["spec"]
                    existing_template.author = template_data.get("author", "system")
                    existing_template.is_public = template_data.get("is_public", True)
                else:
                    print(f"[U+2795] Creating new template: {template_id}")
                    # Create new template
                    new_template = WorkflowTemplate(
                        template_id=template_id,
                        name=template_data["name"],
                        category=template_data["category"],
                        description=template_data["description"],
                        spec_json=template_data["spec"],
                        author=template_data.get("author", "system"),
                        is_public=template_data.get("is_public", True),
                        usage_count=0,
                    )
                    session.add(new_template)

            # Commit changes
            await session.commit()
            print(f"\n[OK] Successfully seeded {len(templates)} templates")

        except Exception as e:
            await session.rollback()
            print(f"[FAIL] Failed to seed templates: {e}")
            raise
        finally:
            await engine.dispose()


async def verify_templates():
    """Verify that templates were seeded correctly."""
    # Get database configuration
    db_config = config.get_database_config()
    database_url = db_config["url"]

    print(f"\n[SEARCH] Verifying templates in database: {database_url_zonder_wachtwoord(database_url)}")

    # Create engine and session
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # Count templates
            stmt = select(WorkflowTemplate)
            result = await session.execute(stmt)
            templates = result.scalars().all()

            print(f"[CHART] Found {len(templates)} templates in database:")
            for template in templates:
                print(f"  - {template.template_id}: {template.name} ({template.category})")

            # Verify all expected templates are present
            template_ids = {t.template_id for t in templates}
            expected_ids = {Path(f).stem for f in TEMPLATE_FILES}

            missing_templates = expected_ids - template_ids
            if missing_templates:
                print(f"[FAIL] Missing templates: {missing_templates}")
                return False
            else:
                print("[OK] All templates successfully seeded!")
                return True

        except Exception as e:
            print(f"[FAIL] Failed to verify templates: {e}")
            raise
        finally:
            await engine.dispose()


async def main():
    """Main entry point."""
    print("[U+0001F331] Seeding workflow templates...")

    try:
        # Seed templates
        await seed_templates()

        # Verify templates
        success = await verify_templates()

        if success:
            print("\n[DONE] Template seeding completed successfully!")
            return 0
        else:
            print("\n[FAIL] Template seeding completed with issues!")
            return 1

    except Exception as e:
        print(f"\n[BOOM] Template seeding failed: {e}")
        return 1


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
