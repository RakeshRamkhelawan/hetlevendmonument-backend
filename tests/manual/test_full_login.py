# Test the exact login flow from the unified auth router to find the error

import asyncio
import os
import sys
import traceback

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///sanskriti_setu.db"
# Redis port updated from 6379 to 6380 (commentaar stond eerder in de string)
os.environ["REDIS_URL"] = "redis://localhost:6380/0"
os.environ["JWT_SECRET"] = "dev-secret-for-testing"
os.environ["ENVIRONMENT"] = "development"
os.environ["TESTING"] = "1"

sys.path.insert(0, "src")


async def test_full_login_flow():
    from sqlalchemy import select

    from src.core.auth.jwt_handler import jwt_handler
    from src.core.auth.oauth2_service import oauth2_service
    from src.core.database.database import db_manager, get_async_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import User

    await db_manager.initialize()

    async for db in get_async_session():
        try:
            email = "admin@sanskritisetu.org"
            password = "AdminPass123!"

            print(f"\n[STEP 1] Finding user by email: {email}")
            with TenantFilterBypass():
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()

            if not user:
                print("  [FAIL] User not found!")
                return
            print(f"  [OK] Found user: id={user.id}")

            print("\n[STEP 2] Verifying password...")
            is_valid = await jwt_handler.verify_password(password, user.hashed_password)
            print(f"  Password valid: {is_valid}")

            print(f"\n[STEP 3] Checking is_active: {user.is_active}")

            print("\n[STEP 4] Loading user roles...")
            try:
                with TenantFilterBypass():
                    await db.refresh(user, ["roles"])
                print(f"  [OK] Loaded roles: {user.roles}")
                role_ids = [role.id for role in user.roles] if user.roles else []
                print(f"  Role IDs: {role_ids}")
            except Exception as e:
                print(f"  [FAIL] Error loading roles: {e}")
                traceback.print_exc()
                # Try without roles
                role_ids = []

            print("\n[STEP 5] Getting user scopes...")
            try:
                # Simplified scope mapping
                scopes = ["users.read", "workflows.read", "workflows.write"]
                print(f"  [OK] Scopes: {scopes}")
            except Exception as e:
                print(f"  [FAIL] Error getting scopes: {e}")
                traceback.print_exc()

            print("\n[STEP 6] Creating tokens...")
            try:
                tokens = await oauth2_service.create_tokens(
                    user_id=user.id,
                    email=user.email,
                    role_ids=role_ids,
                    scopes=scopes,
                    tenant_id=user.tenant_id,
                )
                print("  [OK] Tokens created!")
                print(f"  Access token: {tokens['access_token'][:50]}...")
                print(f"  Refresh token: {tokens['refresh_token'][:50]}...")
            except Exception as e:
                print(f"  [FAIL] Error creating tokens: {e}")
                traceback.print_exc()

            print("\n" + "=" * 60)
            print("[SUCCESS] Full login flow completed!")

        except Exception as e:
            print(f"\n[FATAL ERROR] {e}")
            traceback.print_exc()
        finally:
            break


if __name__ == "__main__":
    asyncio.run(test_full_login_flow())
