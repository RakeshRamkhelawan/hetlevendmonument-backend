"""Reset admin password script"""

import asyncio
import os
import secrets

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/sanskritisetu",
)


async def reset_admin():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, email FROM users WHERE email = 'admin@sanskritisetu.org'")
        )
        user = result.fetchone()

        # Generate secure random password
        password_from_env = os.getenv("ADMIN_RESET_PASSWORD")
        new_password = password_from_env or secrets.token_urlsafe(16)
        new_hash = pwd_context.hash(new_password)

        if user:
            await session.execute(
                text(
                    "UPDATE users SET password_hash = :hash WHERE email = 'admin@sanskritisetu.org'"
                ),
                {"hash": new_hash},
            )
            await session.commit()
            print("Password reset for: admin@sanskritisetu.org")
            if password_from_env:
                print("New password: the value of ADMIN_RESET_PASSWORD (not shown)")
            else:
                # Nieuw gegenereerd: een mens moet het hier overnemen (uitzonderingslijst van
                # tests/architecture/test_geen_geheim_in_de_uitvoer.py).
                print(f"New password: {new_password}")
                print("\n[WARN]  IMPORTANT: Save this password securely! It will not be shown again.")
        else:
            print("Admin user not found, creating...")
            await session.execute(
                text(
                    """INSERT INTO users (email, password_hash, full_name, is_active, is_superuser, tenant_id)
                        VALUES (:email, :hash, :name, true, true, 'default')"""
                ),
                {
                    "email": "admin@sanskritisetu.org",
                    "hash": new_hash,
                    "name": "System Admin",
                },
            )
            await session.commit()
            print("Admin user created!")
            print("Email: admin@sanskritisetu.org")
            if password_from_env:
                print("Password: the value of ADMIN_RESET_PASSWORD (not shown)")
            else:
                print(f"Password: {new_password}")
                print("\n[WARN]  IMPORTANT: Save this password securely! It will not be shown again.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_admin())
