@echo off
REM Manual verification script for P2-006 migration
REM Run this in a NEW PowerShell window (not VS Code terminal)

echo ======================================
echo P2-006 Migration Verification
echo ======================================
echo.

echo [1/3] Checking current migration revision...
alembic -c src/alembic.ini current
echo.

echo [2/3] Applying email campaign migration...
alembic -c src/alembic.ini upgrade head
echo.

echo [3/3] Verifying campaign tables...
python -c "import asyncio; from src.core.database.database import engine; from sqlalchemy import text; async def check(): async with engine.begin() as c: r = await c.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('email_campaigns', 'campaign_segments', 'campaign_analytics', 'ab_tests', 'email_templates', 'user_email_preferences') ORDER BY table_name\")); tables = [row[0] for row in r]; print(f'Found {len(tables)}/6 tables:'); [print(f'  - {t}') for t in tables]; return len(tables) == 6; result = asyncio.run(check()); print('\n=== SUCCESS ===' if result else '\n=== MISSING TABLES ==='); exit(0 if result else 1)"
echo.

if %ERRORLEVEL% == 0 (
    echo ======================================
    echo ✅ Migration successfully applied!
    echo ======================================
    echo.
    echo Next step: Run email campaign tests
    echo   pytest tests_reboot/api/test_email_campaigns.py -v
    echo.
) else (
    echo ======================================
    echo ❌ Migration failed or tables missing
    echo ======================================
    echo Check error messages above
)

pause
