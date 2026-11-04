# Direct test of the login flow - DOES NOT require running server
# Simulates exactly what the unified auth router does

import asyncio
import os
import sys

# Set environment FIRST - before any imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///sanskriti_setu.db"
# Redis port updated from 6379 to 6380 (commentaar stond eerder in de string)
os.environ["REDIS_URL"] = "redis://localhost:6380/0"
os.environ["JWT_SECRET"] = "dev-secret-for-testing"
os.environ["ENVIRONMENT"] = "development"
os.environ["TESTING"] = "1"  # This may help bypass some checks

# Now add src to path
sys.path.insert(0, "src")


async def test_login_flow():
    from sqlalchemy import select

    from src.core.auth.jwt_handler import jwt_handler
    from src.core.database.database import db_manager, get_async_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import User

    # Initialize database
    await db_manager.initialize()

    async for db in get_async_session():
        email = "admin@sanskritisetu.org"
        password = "AdminPass123!"

        # Step 1: Find user
        print(f"\n[STEP 1] Finding user by email: {email}")
        with TenantFilterBypass():
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

        if not user:
            print("  [FAIL] User not found!")
            return

        print(f"  [OK] Found user: id={user.id}, email={user.email}")
        print(f"  [INFO] Stored hash: {user.hashed_password[:60]}...")

        # Step 2: Verify password using jwt_handler (what oauth2_endpoints does)
        print("\n[STEP 2] Verifying password with jwt_handler.verify_password()")
        print(f"  Input password: '{password}'")

        is_valid = await jwt_handler.verify_password(password, user.hashed_password)

        if is_valid:
            print("  [OK] Password VALID!")
        else:
            print("  [FAIL] Password INVALID!")

            # Debug: Let's check the password hash format
            print("\n[DEBUG] Checking password hash format:")
            print(f"  Hash starts with: {user.hashed_password[:20]}")
            print(f"  Hash length: {len(user.hashed_password)}")

            # Try direct bcrypt verification
            print("\n[DEBUG] Trying direct bcrypt verification:")
            import bcrypt

            try:
                bcrypt_result = bcrypt.checkpw(password.encode(), user.hashed_password.encode())
                print(f"  bcrypt.checkpw result: {bcrypt_result}")
            except Exception as e:
                print(f"  bcrypt error: {e}")

        # Step 3: Check user is active
        print("\n[STEP 3] Checking if user is active:")
        print(f"  is_active: {user.is_active}")

        # Step 4: Test token generation
        if is_valid and user.is_active:
            print(f"\n[STEP 4] Would generate tokens for user {user.id}")
            print(f"  tenant_id: {user.tenant_id}")

        print("\n" + "=" * 60)
        if is_valid and user.is_active:
            print("[RESULT] Login should SUCCEED!")
        else:
            print("[RESULT] Login should FAIL!")
        break  # Only need one iteration


if __name__ == "__main__":
    asyncio.run(test_login_flow())
