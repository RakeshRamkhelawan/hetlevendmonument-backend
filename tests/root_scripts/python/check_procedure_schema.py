import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def check_schema():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://sanskriti_user:sanskriti_pass@localhost:5432/sanskritisetu",
    )
    engine = create_async_engine(database_url)

    try:
        async with engine.connect() as conn:
            # Query the procedure_metadata table structure
            query = text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'procedure_metadata'
                ORDER BY ordinal_position
            """
            )
            result = await conn.execute(query)
            rows = result.fetchall()
            print("procedure_metadata columns:")
            for row in rows:
                print(f"  {row[0]}: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await engine.dispose()


asyncio.run(check_schema())
