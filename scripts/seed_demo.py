import asyncio
import os
import sys

# Ensure /app is in path
if "/app" not in sys.path:
    sys.path.append("/app")

from sqlalchemy import delete, select

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import db_manager
from src.core.models.rbac_models import Role, User, user_roles


async def seed():
    print("Initializing database...")
    await db_manager.initialize()

    async with db_manager.get_session() as db:
        print("Seeding demo user...")
        # Check if user exists
        stmt = select(User).where(User.email == "demo@example.com")
        existing_user = (await db.execute(stmt)).scalar_one_or_none()

        hashed = await jwt_handler.hash_password("demo123")

        if existing_user:
            print("User already exists. Updating password.")
            existing_user.hashed_password = hashed
            existing_user.is_active = True
            existing_user.tenant_id = 1
        else:
            print("Creating new user.")
            existing_user = User(
                email="demo@example.com",
                hashed_password=hashed,
                tenant_id=1,
                is_active=True,
            )
            db.add(existing_user)

        await db.commit()
        await db.refresh(existing_user)

        # Ensure role exists
        stmt = select(Role).where(Role.name == "user")
        role = (await db.execute(stmt)).scalar_one_or_none()
        if not role:
            print("Creating user role.")
            role = Role(name="user", tenant_id=1)
            db.add(role)
            await db.commit()
            await db.refresh(role)

        # Assign role
        # Check junction
        stmt = (
            select(user_roles)
            .where(user_roles.c.user_id == existing_user.id)
            .where(user_roles.c.role_id == role.id)
        )
        res = (await db.execute(stmt)).scalar_one_or_none()
        if not res:
            print("Assigning role.")
            await db.execute(user_roles.insert().values(user_id=existing_user.id, role_id=role.id))
            await db.commit()

        print("Seeding complete. User: demo@example.com / demo123")


if __name__ == "__main__":
    asyncio.run(seed())
