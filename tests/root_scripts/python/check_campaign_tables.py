"""Quick check if email campaign tables exist in database"""

import asyncio
import sys

from sqlalchemy import inspect, text

from src.core.database.database import engine


async def check_tables():
    """Check if email campaign tables exist"""
    async with engine.begin() as conn:
        # Get all table names
        result = await conn.execute(
            text(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE '%email%' OR table_name LIKE '%campaign%'
            ORDER BY table_name
            """
            )
        )
        tables = [row[0] for row in result]

        print("Email/Campaign tables found:")
        for table in tables:
            print(f"  ✓ {table}")

        expected = [
            "email_campaigns",
            "campaign_segments",
            "campaign_analytics",
            "ab_tests",
            "email_templates",
            "user_email_preferences",
        ]

        missing = [t for t in expected if t not in tables]
        if missing:
            print(f"\n❌ Missing tables: {missing}")
            return False
        else:
            print("\n✅ All 6 tables exist!")
            return True


if __name__ == "__main__":
    result = asyncio.run(check_tables())
    sys.exit(0 if result else 1)
