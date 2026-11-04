"""Official HR Acceptance Data Seeding Script.

Seeds minimal test and benchmark data for HR skill gap analysis and training scheduling.
Ensures that scripts/acceptance_thread.py passes stages 5 and 6 when executed.

Idempotent: safe to run repeatedly against development or test environments.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
from src.core.models.hr_training_models import Training
from src.core.models.rbac_models import Role, Tenant, User, user_roles
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402


async def seed_hr_acceptance_data(session: AsyncSession, tenant_id: int = 1) -> dict[str, int]:
    """Seed test data required for HR gap analysis and training tools.

    Creates (if not already existing):
    1. Tenant (id=tenant_id)
    2. Role ('Developer')
    3. User ('developer<tenant_id>@sanskritisetu.org')
    4. user_roles link
    5. Skill ('Python Programming')
    6. RoleRequiredSkill (required_level=4)
    7. EmployeeSkill (level=2, creating a genuine gap: below_requirement=1)
    8. Training ('Advanced Python & Security Architecture')

    Returns dict with identifiers of seeded entities.
    """
    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    previous_tenant = get_tenant_id()
    set_tenant_id(tenant_id)
    try:
        # 1. Tenant
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                id=tenant_id,
                name=f"Acceptance Tenant {tenant_id}",
                slug=f"acceptance-tenant-{tenant_id}",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()

        # 2. Role
        role_name = "Developer"
        result = await session.execute(
            select(Role).where(and_(Role.tenant_id == tenant_id, Role.name == role_name))
        )
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                name=role_name,
                description="Software Developer Role",
                is_active=True,
            )
            session.add(role)
            await session.flush()

        # 3. User
        user_email = f"developer{tenant_id}@sanskritisetu.org"
        result = await session.execute(
            select(User).where(and_(User.tenant_id == tenant_id, User.email == user_email))
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant_id,
                email=user_email,
                hashed_password="$2b$12$WqJTQqMXvDHMYndXLTpn6u66lPZfLuWW17se2s2vsD/zpBl7a/0dO",
                is_active=True,
            )
            session.add(user)
            await session.flush()

        # 4. User Role Association
        ur_check = await session.execute(
            select(user_roles).where(
                and_(user_roles.c.user_id == user.id, user_roles.c.role_id == role.id)
            )
        )
        if ur_check.first() is None:
            await session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
            await session.flush()

        # 5. Skill
        skill_name = "Python Programming"
        result = await session.execute(
            select(Skill).where(and_(Skill.tenant_id == tenant_id, Skill.name == skill_name))
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            skill = Skill(
                tenant_id=tenant_id,
                name=skill_name,
                category="Engineering",
            )
            session.add(skill)
            await session.flush()

        # 6. Role Required Skill (level 4)
        result = await session.execute(
            select(RoleRequiredSkill).where(
                and_(
                    RoleRequiredSkill.tenant_id == tenant_id,
                    RoleRequiredSkill.role_id == role.id,
                    RoleRequiredSkill.skill_id == skill.id,
                )
            )
        )
        req_skill = result.scalar_one_or_none()
        if req_skill is None:
            req_skill = RoleRequiredSkill(
                tenant_id=tenant_id,
                role_id=role.id,
                skill_id=skill.id,
                required_level=4,
            )
            session.add(req_skill)
            await session.flush()

        # 7. Employee Skill (level 2 -> genuine gap)
        result = await session.execute(
            select(EmployeeSkill).where(
                and_(
                    EmployeeSkill.tenant_id == tenant_id,
                    EmployeeSkill.user_id == user.id,
                    EmployeeSkill.skill_id == skill.id,
                )
            )
        )
        emp_skill = result.scalar_one_or_none()
        if emp_skill is None:
            emp_skill = EmployeeSkill(
                tenant_id=tenant_id,
                user_id=user.id,
                skill_id=skill.id,
                level=2,
            )
            session.add(emp_skill)
            await session.flush()

        # 8. Training Catalog Entry
        training_name = "Advanced Python & Security Architecture"
        result = await session.execute(
            select(Training).where(
                and_(Training.tenant_id == tenant_id, Training.name == training_name)
            )
        )
        training = result.scalar_one_or_none()
        if training is None:
            training = Training(
                tenant_id=tenant_id,
                name=training_name,
                description="Advanced Python programming and secure architectural patterns",
                skill_id=skill.id,
            )
            session.add(training)
            await session.flush()

        await session.commit()

        return {
            "tenant_id": tenant_id,
            "role_id": role.id,
            "user_id": user.id,
            "skill_id": skill.id,
            "required_level": req_skill.required_level,
            "employee_level": emp_skill.level,
            "training_id": training.id,
        }
    finally:
        set_tenant_id(previous_tenant)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed HR acceptance thread data")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID to seed (default: 1)")
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database URL (default: from env SANSKRITISETU_TEST_DATABASE_URL or DATABASE_URL)",
    )
    args = parser.parse_args()

    db_url = (
        args.db_url
        or os.environ.get("SANSKRITISETU_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not db_url:
        db_url = "postgresql+asyncpg://postgres:postgres@localhost:5455/sanskritisetu"

    print(f"[SEED] Seeding HR acceptance data for tenant {args.tenant_id} into {database_url_zonder_wachtwoord(db_url)}...")
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_factory() as session:
            summary = await seed_hr_acceptance_data(session, tenant_id=args.tenant_id)
            print("[SEED] Successfully seeded HR acceptance data:")
            for key, val in summary.items():
                print(f"       - {key}: {val}")
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
