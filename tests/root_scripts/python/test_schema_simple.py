#!/usr/bin/env python3
"""
Simple SQL-based test for ProcedureMetadata schema fix
"""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.fixtures.testdatabase import testdatabase_url


async def test_schema():
    """Verify procedure_metadata table schema"""
    db_url = testdatabase_url()

    engine = create_async_engine(db_url, echo=False)

    try:
        async with engine.connect() as conn:
            # Get all columns in procedure_metadata
            result = await conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'procedure_metadata'
                ORDER BY ordinal_position
            """
                )
            )

            columns = result.fetchall()

            if not columns:
                print("✗ procedure_metadata table not found")
                return False

            # Expected columns from the model
            expected = {
                "id": "uuid",
                "tenant_id": "uuid",
                "domain_pack_id": "uuid",
                "flow_id": "uuid",
                "category": "character varying",
                "description": "character varying",
                "intent_tags": "ARRAY",
                "prerequisites": "ARRAY",
                "estimated_duration_minutes": "integer",
                "is_platform_template": "boolean",
                "procedure_metadata": "jsonb",
                "created_at": "timestamp with time zone",
                "updated_at": "timestamp with time zone",
            }

            actual = {row[0]: row[1] for row in columns}

            print("procedure_metadata schema verification:")
            print("=" * 60)

            all_good = True
            for col_name, expected_type in expected.items():
                if col_name in actual:
                    if actual[col_name] == expected_type or expected_type in actual[col_name]:
                        print(f"✓ {col_name:40} {actual[col_name]}")
                    else:
                        print(f"✗ {col_name:40} Expected: {expected_type}, Got: {actual[col_name]}")
                        all_good = False
                else:
                    print(f"✗ {col_name:40} MISSING")
                    all_good = False

            # Check for unexpected columns
            print("\nAdditional columns in database:")
            for col_name, col_type in actual.items():
                if col_name not in expected:
                    print(f"  • {col_name}: {col_type}")

            if all_good:
                print("\n✅ Schema verification PASSED!")
                print("\nThe procedure_metadata table has all required columns.")
                print("The ProcedureMetadata SQLAlchemy model should work correctly.")
            else:
                print("\n✗ Schema verification FAILED!")

            return all_good

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import sys

    success = asyncio.run(test_schema())
    sys.exit(0 if success else 1)
