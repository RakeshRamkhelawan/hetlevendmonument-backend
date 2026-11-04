"""Direct database authentication test"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.auth.auth_service import auth_service


async def test_direct_auth():
    """Test authentication directly against database"""
    print("=" * 60)
    print("DIRECT AUTHENTICATION TEST")
    print("=" * 60)

    # Create database connection
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/sanskritisetu"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as db:
        print("\n[1] Testing get_user_by_email...")
        user = await auth_service.get_user_by_email(db, "admin@sanskritisetu.org")

        if not user:
            print("[FAIL] User not found in database!")
            return

        print(f"[OK] User found: {user.email}")
        print(f"    - ID: {user.id}")
        print(f"    - Active: {user.is_active}")
        print(f"    - Tenant ID: {user.tenant_id}")
        print(f"    - Role ID: {user.role_id}")
        print(f"    - Hash (first 30 chars): {user.hashed_password[:30]}...")

        print("\n[2] Testing authenticate_user...")
        authenticated_user = await auth_service.authenticate_user(
            db,
            email="admin@sanskritisetu.org",
            password="Admin123!",
            client_ip="127.0.0.1",
        )

        if authenticated_user:
            print("[SUCCESS] ✓ Authentication PASSED!")
            print(f"    - User: {authenticated_user.email}")
            print(f"    - ID: {authenticated_user.id}")
        else:
            print("[FAIL] ✗ Authentication FAILED!")
            print("    Password verification returned False")

            # Test password directly
            print("\n[3] Testing password hash directly...")
            from src.core.auth.jwt_handler import jwt_handler

            is_valid = await jwt_handler.verify_password("Admin123!", user.hashed_password)
            print(f"    Direct verification result: {is_valid}")


if __name__ == "__main__":
    asyncio.run(test_direct_auth())
