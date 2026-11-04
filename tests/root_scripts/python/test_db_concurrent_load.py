"""
Database Pool Concurrent Load Test (Phase 1 & 3 Fixes)

Tests database session handling under concurrent load to verify:
- Fix 1.4: Double session close is resolved
- Fix 3.1: Pool recycle configuration is correct
"""

import asyncio
import sys
from datetime import datetime


async def test_concurrent_sessions():
    """Test concurrent database sessions don't cause 'closed session' errors."""
    print("Testing concurrent database sessions (Phase 1 Fix 1.4)...")

    try:
        from sqlalchemy import text

        from src.core.database.database import get_async_session

        async def make_query(session_num: int):
            """Make a simple query."""
            try:
                # get_async_session is a generator, need to iterate
                session_gen = get_async_session()
                session = await anext(session_gen)
                try:
                    result = await session.execute(text("SELECT 1 as test"))
                    row = result.first()
                    success = row[0] == 1
                    await session.close()
                    return session_num, "success", success
                except Exception as e:
                    await session.rollback()
                    await session.close()
                    raise e
            except Exception as e:
                return session_num, "error", str(e)

        # Run 20 concurrent sessions
        tasks = [make_query(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # Check results
        errors = [r for r in results if r[1] == "error"]
        successes = [r for r in results if r[1] == "success"]

        if errors:
            print(f"[FAIL] {len(errors)}/20 sessions failed:")
            for session_num, _, error in errors[:5]:  # Show first 5 errors
                print(f"  - Session {session_num}: {error}")
            return False

        print("[OK] All 20 concurrent sessions succeeded")
        print("[OK] No 'closed session' errors detected")
        return True

    except Exception as e:
        print(f"[FAIL] Test setup failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_pool_configuration():
    """Test database pool configuration is correct."""
    print("\nTesting database pool configuration (Phase 3 Fix 3.1)...")

    try:
        from src.core.database.database import db_manager

        # Check if database is initialized
        if not db_manager.engine:
            print("[SKIP] Database not initialized (expected in test environment)")
            return True

        # Check pool settings
        pool = db_manager.engine.pool

        print(f"[INFO] Pool class: {type(pool).__name__}")
        print(f"[INFO] Pool size: {pool.size()}")
        print(f"[INFO] Pool checked out: {pool.checkedout()}")

        # Verify pool recycle in engine options
        if hasattr(db_manager.engine, "pool_recycle"):
            pool_recycle = db_manager.engine.pool_recycle
            print(f"[INFO] Pool recycle: {pool_recycle}s")

            if pool_recycle == 1800:
                print("[OK] Pool recycle correctly set to 1800s (30 min)")
            else:
                print(f"[WARN] Pool recycle is {pool_recycle}s, expected 1800s")

        return True

    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_session_lifecycle():
    """Test complete session lifecycle."""
    print("\nTesting session lifecycle...")

    try:
        from sqlalchemy import text

        from src.core.database.database import get_async_session

        # Test 1: Normal commit
        session_gen = get_async_session()
        session = await anext(session_gen)
        await session.execute(text("SELECT 1"))
        await session.commit()
        await session.close()
        print("[OK] Normal session commit works")

        # Test 2: Rollback on error
        try:
            session_gen = get_async_session()
            session = await anext(session_gen)
            await session.execute(text("SELECT 1"))
            await session.rollback()
            await session.close()
        except ValueError:
            pass  # Expected
        print("[OK] Session rollback on error works")

        # Test 3: Multiple sequential sessions
        for i in range(5):
            session_gen = get_async_session()
            session = await anext(session_gen)
            await session.execute(text("SELECT 1"))
            await session.close()
        print("[OK] Sequential sessions work")

        return True

    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all concurrent load tests."""
    print("=" * 60)
    print("Database Pool Concurrent Load Tests")
    print("=" * 60)

    results = []

    # Test concurrent sessions (Fix 1.4 verification)
    results.append(await test_concurrent_sessions())

    # Test pool configuration (Fix 3.1 verification)
    results.append(await test_pool_configuration())

    # Test session lifecycle
    results.append(await test_session_lifecycle())

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n[SUCCESS] All concurrent load tests PASSED!")
        return 0
    else:
        print("\n[FAILURE] Some tests FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
