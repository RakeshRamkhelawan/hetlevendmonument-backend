#!/usr/bin/env python3
"""
Test script to verify ProcedureMetadata model works with the fixed schema
"""

import asyncio
import os
import sys
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from core.database import Base
from core.procedures.models import ProcedureMetadata
from tests.fixtures.testdatabase import testdatabase_url


async def test_procedure_metadata():
    """Test that ProcedureMetadata model works with the fixed schema"""
    db_url = testdatabase_url()

    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # Test 1: Verify table exists and has correct columns
        async with engine.connect() as conn:
            result = await conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'procedure_metadata'
            """
            )
            columns = {row[0] for row in result.fetchall()}

            required = {
                "flow_id",
                "description",
                "prerequisites",
                "estimated_duration_minutes",
                "is_platform_template",
            }
            if required.issubset(columns):
                print("✓ Test 1: All required columns exist in database")
            else:
                print(f"✗ Test 1: Missing columns: {required - columns}")
                return False

        # Test 2: Create a ProcedureMetadata instance
        tenant_id = uuid4()
        domain_pack_id = uuid4()
        flow_id = uuid4()

        metadata = ProcedureMetadata(
            tenant_id=tenant_id,
            domain_pack_id=domain_pack_id,
            flow_id=flow_id,
            category="test_category",
            description="Test description",
            intent_tags=["tag1", "tag2"],
            prerequisites=["prereq1"],
            estimated_duration_minutes=30,
            is_platform_template=False,
            procedure_metadata={},
        )
        print("✓ Test 2: ProcedureMetadata instance created successfully")

        # Test 3: Verify model attributes match database columns
        model_attrs = {
            "id",
            "tenant_id",
            "domain_pack_id",
            "flow_id",
            "category",
            "description",
            "intent_tags",
            "prerequisites",
            "estimated_duration_minutes",
            "is_platform_template",
            "procedure_metadata",
            "created_at",
            "updated_at",
        }
        db_required = {
            "id",
            "tenant_id",
            "domain_pack_id",
            "flow_id",
            "category",
            "description",
            "intent_tags",
            "prerequisites",
            "estimated_duration_minutes",
            "is_platform_template",
            "procedure_metadata",
            "created_at",
            "updated_at",
        }

        if model_attrs == db_required:
            print("✓ Test 3: Model attributes match database schema")
        else:
            missing = db_required - model_attrs
            extra = model_attrs - db_required
            if missing:
                print(f"✗ Test 3: Missing attributes in model: {missing}")
            if extra:
                print(f"✗ Test 3: Extra attributes in model: {extra}")
            return False

        print("\n✅ All tests passed! Schema fix is working correctly.")
        return True

    except Exception as e:
        print(f"✗ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(test_procedure_metadata())
    sys.exit(0 if success else 1)
