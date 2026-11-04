"""
Database Seeding Script

Populates the local database with initial data for development/testing.

Part of SD-3.1 implementation.

Usage:
    python scripts/seed_db.py
"""

import asyncio
import secrets
import string
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_database_url
from src.core.auth.jwt_handler import get_password_hash
from src.core.database.database import Base
from src.core.models.rbac_models import Role, Tenant, User
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402


def generate_secure_password(length: int = 20) -> str:
    """Generate a secure random password."""
    alphabet = (
        string.ascii_letters + string.digits + string.punctuation.replace('"', "").replace("'", "")
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def seed_tenants(session: AsyncSession) -> list[int]:
    """Create seed tenants."""
    tenants_data = [
        {"name": "Default Tenant", "slug": "default", "is_active": True},
        {"name": "Demo Tenant", "slug": "demo", "is_active": True},
    ]

    tenant_ids = []
    for data in tenants_data:
        tenant = Tenant(**data)
        session.add(tenant)
        await session.flush()
        tenant_ids.append(tenant.id)
        print(f"Created tenant: {data['name']} (ID: {tenant.id})")

    return tenant_ids


async def seed_roles(session: AsyncSession, tenant_ids: list[int]) -> list[int]:
    """Create seed roles."""
    roles_data = [
        {"name": "admin", "description": "Administrator role"},
        {"name": "user", "description": "Standard user role"},
        {"name": "viewer", "description": "Read-only role"},
    ]

    role_ids = []
    for tenant_id in tenant_ids:
        for data in roles_data:
            role = Role(tenant_id=tenant_id, **data)
            session.add(role)
            await session.flush()
            role_ids.append(role.id)
            print(f"Created role: {data['name']} for tenant {tenant_id}")

    return role_ids


async def seed_users(session: AsyncSession, tenant_ids: list[int], role_ids: list[int]) -> None:
    """Create seed users with randomly generated passwords."""
    users_data = [
        {"email": "admin@sanskritisetu.nl", "is_active": True},
        {"email": "user1@example.com", "is_active": True},
        {"email": "user2@example.com", "is_active": True},
        {"email": "user3@example.com", "is_active": True},
        {"email": "user4@example.com", "is_active": True},
        {"email": "demo@example.com", "is_active": True},
        {"email": "test1@test.com", "is_active": True},
        {"email": "test2@test.com", "is_active": True},
        {"email": "inactive@example.com", "is_active": False},
        {"email": "viewer@example.com", "is_active": True},
    ]

    print("\n[WARN]  WARNING: Generated passwords below - SAVE THESE BEFORE LOSING THIS OUTPUT!")
    print("These passwords will not be shown again.\n")

    for i, data in enumerate(users_data):
        tenant_id = tenant_ids[i % len(tenant_ids)]
        role_id = role_ids[i % len(role_ids)] if role_ids else None

        # Generate secure random password
        generated_password = generate_secure_password()

        user = User(
            email=data["email"],
            hashed_password=get_password_hash(generated_password),
            tenant_id=tenant_id,
            role_id=role_id,
            is_active=data["is_active"],
        )
        session.add(user)
        print(f"Email: {data['email']:<25} | Password: {generated_password} | Tenant: {tenant_id}")

    await session.flush()


async def main():
    """Main seeding function."""
    print("=" * 50)
    print("Database Seeding Script")
    print("=" * 50)

    # Get database URL
    db_url = get_database_url()
    if not db_url:
        print("ERROR: DATABASE_URL not configured!")
        sys.exit(1)

    # Ensure async driver
    if "postgresql://" in db_url and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    print(f"Connecting to: {database_url_zonder_wachtwoord(db_url)}")

    # Create engine and session
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            async with session.begin():
                print("\n--- Seeding Tenants ---")
                tenant_ids = await seed_tenants(session)

                print("\n--- Seeding Roles ---")
                role_ids = await seed_roles(session, tenant_ids)

                print("\n--- Seeding Users ---")
                await seed_users(session, tenant_ids, role_ids)

            print("\n" + "=" * 50)
            print("Seeding completed successfully!")
            print(f"Created: 2 tenants, {len(role_ids)} roles, 10 users")
            print("=" * 50)

    except Exception as e:
        print(f"ERROR: Seeding failed - {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
