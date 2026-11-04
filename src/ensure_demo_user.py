import asyncio
import os
import sys
from typing import Optional, cast

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.core.database.bypass_session import adopt_tenant
from src.core.models.rbac_models import Role, RolePermission, Tenant, User
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord


# Local constant instead of missing Enum
class UserRole:
    ADMIN = "admin"
    EDITOR = "editor"
    USER = "user"


async def ensure_demo_user() -> None:
    # Attempt to get from env (container), fallback to localhost for external run
    db_url: str | None = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in env, using default localhost...")
        # Local connection to docker port
        db_url = "postgresql+asyncpg://postgres:postgres@localhost:5433/sanskriti_setu"

    print(f"Connecting to {database_url_zonder_wachtwoord(db_url)}...")

    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # 1. Ensure Tenant
        result = await session.execute(select(Tenant).where(Tenant.name == "Demo Tenant"))
        tenant: Tenant | None = result.scalar_one_or_none()

        if not tenant:
            print("Creating Demo Tenant...")
            tenant = Tenant(name="Demo Tenant", slug="demo-tenant", is_active=True)
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
        else:
            print(f"Found Tenant: {tenant.name} ({tenant.id})")

        # Vanaf hier draait alles BINNEN de klant (ADR-036 OP-153).
        #
        # Dit script draait met de hand, buiten elk verzoek, dus er is geen klantcontext.
        # `tenants` heeft geen afschermingsregel en kon daarom hierboven gewoon gelezen
        # en geschreven worden; `roles`, `role_permissions`, `users` en `user_roles`
        # hebben er wel een. Zonder deze aanname faalt elke INSERT hieronder zodra
        # `DATABASE_URL` naar `sanskritisetu_app` wijst -- en dat is precies de omgeving
        # waarin je dit script nodig hebt om de omschakeling te kunnen uitproberen.
        #
        # LET OP: de INSERTs falen LUID, maar de wijziging in de `else`-tak verderop
        # (bestaande gebruiker, wachtwoord bijwerken) is een UPDATE en die raakt zonder
        # klantcontext nul rijen ZONDER foutmelding. Het script zou dan "User updated."
        # melden terwijl er niets is gebeurd.
        async with adopt_tenant(session, tenant.id):
            await _zorg_voor_rol_en_gebruiker(session, tenant)

    await engine.dispose()


async def _zorg_voor_rol_en_gebruiker(session: "AsyncSession", tenant: Tenant) -> None:
    """De rol, de rechten en de demogebruiker -- alles binnen een aangenomen klant."""
    # 2. Ensure Role (Admin)
    result = await session.execute(
        select(Role).where(Role.name == UserRole.ADMIN, Role.tenant_id == tenant.id)
    )
    role: Role | None = result.scalar_one_or_none()

    if not role:
        print("Creating Admin Role...")
        role = Role(
            name=UserRole.ADMIN,
            description="Administrator",
            # permissions will be added separately
            tenant_id=tenant.id,
            # is_system=True # Removed invalid field
        )
        session.add(role)
        await session.commit()
        await session.refresh(role)

        # Add ALL permissions
        print("Adding permissions...")
        perm = RolePermission(
            role_id=role.id, resource="*", action="*", conditions={"all": True}
        )
        session.add(perm)
        await session.commit()
    else:
        print(f"Found Role: {role.name}")

    # 3. Ensure User
    email = "demo@example.com"
    result = await session.execute(select(User).where(User.email == email))
    user: User | None = result.scalar_one_or_none()

    password_plain = "demo123"
    hashed = bcrypt.hashpw(password_plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    if not user:
        print(f"Creating User {email}...")
        user = User(
            email=email,
            hashed_password=hashed,
            is_active=True,
            is_superuser=True,
            tenant_id=tenant.id,
        )
        # Add role via user_roles or old way?
        # Model has roles = relationship('Role', secondary=user_roles, backref='users')
        # So user.roles.append(role)
        user.roles.append(role)

        session.add(user)
        await session.commit()
        print("User created successfully.")
    else:
        print(f"User {email} already exists. Updating password...")
        user.hashed_password = hashed
        user.is_active = True
        user.tenant_id = tenant.id
        # optimize: typically we don't clear roles but merely ensure logic
        # Cast roles to List[Role] for type checking
        user_roles: list[Role] = cast(list[Role], user.roles)
        if role not in user_roles:
            user.roles.append(role)

        session.add(user)
        await session.commit()
        print("User updated.")


if __name__ == "__main__":
    asyncio.run(ensure_demo_user())
