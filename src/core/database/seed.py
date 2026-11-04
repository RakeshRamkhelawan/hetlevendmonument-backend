"""
Database Seeding Module - Ensures essential data exists on startup

This module runs during application startup to ensure:
1. Default tenant exists
2. Admin user exists with known credentials

This prevents the "no admin user after rebuild" problem.
"""

import json
import os
from typing import Any, cast

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from passlib.context import CryptContext as _CryptContext

from src.core.database.bypass_session import adopt_tenant
from src.core.models.rbac_models import with_four_eyes_defaults

_seed_pwd_context: _CryptContext = _CryptContext(schemes=["bcrypt"], deprecated="auto")

# Default credentials -- must be set via environment variables, no fallback allowed.
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@sanskritisetu.org")
DEFAULT_ADMIN_PASSWORD: str | None = os.getenv("DEFAULT_ADMIN_PASSWORD")
DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "Default Tenant")
DEFAULT_TENANT_SLUG = os.getenv("DEFAULT_TENANT_SLUG", "default")

# Allowed column names for tenant seed INSERT
_ALLOWED_TENANT_COLS: frozenset[str] = frozenset(
    {
        "name",
        "slug",
        "is_active",
        "subscription_tier",
        "subscription_status",
        "settings",
        "config",
        "max_users",
        "max_agents",
        "max_storage_gb",
    }
)

# Allowed column names for admin user seed INSERT
_ALLOWED_USER_COLS: frozenset[str] = frozenset(
    {
        "tenant_id",
        "email",
        "hashed_password",
        "full_name",
        "is_active",
        "is_superuser",
        "role_id",
    }
)


def _validate_seed_columns(cols: list[str], allowed: frozenset[str], label: str) -> list[str]:
    """Validate that all column names are in the allowed set.

    Raises ValueError if any column name is not in the allowlist.
    Column names cannot be parameterized in SQL -- this allowlist
    prevents injection if insert_cols ever includes external input.
    """
    invalid = [c for c in cols if c not in allowed]
    if invalid:
        raise ValueError(f"Invalid {label} column(s): {invalid}. Allowed: {sorted(allowed)}")
    return cols


async def seed_database(session: AsyncSession) -> bool:
    """
    Seed the database with essential data.

    This function is idempotent - safe to run multiple times.
    It only creates data if it doesn't already exist.

    Returns:
        bool: True if seeding was successful, False otherwise
    """
    if not DEFAULT_ADMIN_PASSWORD:
        raise RuntimeError(
            "DEFAULT_ADMIN_PASSWORD env var is required before seeding. "
            "Set it in .env or docker-compose."
        )

    try:
        # Step 1: Ensure default tenant exists
        tenant_id = await _ensure_default_tenant(session)
        if not tenant_id:
            logger.error("Failed to create/find default tenant")
            return False

        # Step 2: Ensure admin user exists -- BINNEN de aangenomen klant (ADR-036 OP-153).
        #
        # Deze functie draait bij het OPSTARTEN, buiten elk verzoek, dus de ContextVar is
        # leeg. `users`, `roles` en `user_roles` hebben een afschermingsregel, en die leest
        # de klant uit `app.current_tenant` -- gevuld vanuit diezelfde ContextVar. Zonder
        # deze regel faalt het zaaien zodra `DATABASE_URL` naar `sanskritisetu_app` wijst,
        # en dan start de applicatie NIET op: `_seed_initial_data_with_retry` maakt er na
        # drie pogingen een harde fout van.
        #
        # Gemeten 2026-09-17 op staging, en precies zo gebeurd:
        #     RuntimeError: Database seeding failed after 3 attempts.
        #     Cannot start application without admin user.
        #
        # Stap 1 hierboven blijft er bewust BUITEN: `tenants` heeft geen afschermingsregel
        # (gemeten: relrowsecurity = f, nul policies) en de klant bestaat op dat moment nog
        # niet, dus daar valt niets aan te nemen.
        #
        # Waarom dit gat niet door de triage is gevonden: `scripts/triage_tenantcontext_
        # schrijfpaden.py` herkent schrijfacties aan ORM-aanroepen (`add`, `merge`,
        # `insert(...)`). Dit bestand schrijft met RAUWE SQL via `session.execute(text(...))`
        # en was daardoor onzichtbaar. Dat is dezelfde faalvorm als elders in dit project:
        # een vocabulaire doorzoeken en een tweede vocabulaire missen.
        #
        # `tenant_id` komt uit de database, nooit uit invoer.
        async with adopt_tenant(session, tenant_id):
            admin_created = await _ensure_admin_user(session, tenant_id)
            if not admin_created:
                logger.error("Failed to create/find admin user")
                return False

            await session.commit()
        logger.info("[SEED] Database seeding completed successfully")
        return True

    except Exception as e:
        logger.error(f"[SEED] Database seeding failed: {e}")
        await session.rollback()
        return False


async def _get_table_columns(session: AsyncSession, table_name: str) -> set[str]:
    """Introspect actual table columns from the database schema."""
    result = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table_name AND table_schema = 'public'"
        ),
        {"table_name": table_name},
    )
    return {row[0] for row in result.fetchall()}


async def _ensure_default_tenant(session: AsyncSession) -> int | None:
    """Ensure the default tenant exists, return its ID.

    Schema-aware: introspects actual tenants table columns to build
    the INSERT statement dynamically. This prevents crashes when the
    schema evolves (e.g., subscription_tier column added/removed).
    """
    try:
        # Check if default tenant exists
        logger.info(f"[SEED] Checking for default tenant (slug={DEFAULT_TENANT_SLUG})")
        result = await session.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": DEFAULT_TENANT_SLUG},
        )
        row = result.fetchone()

        if row:
            tenant_id = cast(int, row[0])
            logger.info(f"[SEED] [OK] Default tenant already exists (id={tenant_id})")
            return tenant_id

        # Introspect schema to build INSERT dynamically
        columns = await _get_table_columns(session, "tenants")
        logger.info(f"[SEED] Tenants table columns: {sorted(columns)}")

        # Base fields (always present)
        insert_cols = ["name", "slug", "is_active"]
        insert_vals = {
            "name": DEFAULT_TENANT_NAME,
            "slug": DEFAULT_TENANT_SLUG,
            "is_active": True,
        }

        # Optional fields -- only include if column exists in schema
        optional_fields = {
            "subscription_tier": "enterprise",
            "subscription_status": "active",
            "config": "{}",
            # ADR-039: de single-tenant omgeving krijgt bij aanmaken de vier-ogen-standaard
            # (debiteurenagent dag 3). Een bestaande standaardtenant wordt hierboven al
            # teruggegeven en dus niet aangeraakt.
            "settings": json.dumps(with_four_eyes_defaults(None)),
            "max_users": 10,
            "max_agents": 50,
            "max_storage_gb": 5,
        }
        for col, default_val in optional_fields.items():
            if col in columns:
                insert_cols.append(col)
                insert_vals[col] = default_val

        # Validate column names before building SQL
        insert_cols = _validate_seed_columns(insert_cols, _ALLOWED_TENANT_COLS, "tenant")

        col_list = ", ".join(insert_cols)
        param_list = ", ".join(f":{col}" for col in insert_cols)

        logger.info(f"[SEED] Creating default tenant: {DEFAULT_TENANT_NAME}")
        await session.execute(
            text(  # nosec B608: column names validated against allowlist above
                f"INSERT INTO tenants ({col_list}) VALUES ({param_list})"
            ),
            insert_vals,
        )

        # Verify creation
        result = await session.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"),
            {"slug": DEFAULT_TENANT_SLUG},
        )
        row = result.fetchone()

        if row:
            tenant_id = cast(int, row[0])
            logger.info(f"[SEED] [OK] Created default tenant: {DEFAULT_TENANT_NAME} (id={tenant_id})")
            return tenant_id
        else:
            logger.error(
                "[SEED] [FAIL] Failed to verify tenant creation - INSERT succeeded but SELECT returned nothing"
            )
            return None

    except Exception as e:
        logger.error(f"[SEED] [FAIL] Error ensuring default tenant: {type(e).__name__}: {e}")
        return None


async def _ensure_admin_user(session: AsyncSession, tenant_id: int) -> bool:
    """Ensure the admin user exists with correct credentials.

    Schema-aware: introspects actual users table columns to build
    the INSERT statement dynamically.
    """
    try:
        # Check if admin user exists
        logger.info(f"[SEED] Checking for admin user ({DEFAULT_ADMIN_EMAIL}) in tenant {tenant_id}")
        result = await session.execute(
            text("SELECT id, email FROM users WHERE email = :email AND tenant_id = :tenant_id"),
            {"email": DEFAULT_ADMIN_EMAIL, "tenant_id": tenant_id},
        )
        row = result.fetchone()

        # Guard already checked in seed_database(); assert narrows type for the checker.
        assert DEFAULT_ADMIN_PASSWORD is not None
        hashed_password = _seed_pwd_context.hash(DEFAULT_ADMIN_PASSWORD[:72])

        if row:
            user_id = row[0]
            # Update password to ensure it's correct
            logger.info(
                f"[SEED] Admin user exists (id={user_id}), updating password to ensure correctness"
            )
            await session.execute(
                text("UPDATE users SET hashed_password = :hash WHERE id = :id"),
                {"hash": hashed_password, "id": user_id},
            )
            logger.info(f"[SEED] [OK] Admin user password reset: {DEFAULT_ADMIN_EMAIL}")
            return True

        # Introspect schema to build INSERT dynamically
        columns = await _get_table_columns(session, "users")

        insert_cols = ["email", "hashed_password", "is_active", "tenant_id"]
        insert_vals: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "email": DEFAULT_ADMIN_EMAIL,
            "hashed_password": hashed_password,
            "is_active": True,
            "tenant_id": tenant_id,
        }

        # Optional fields -- only include if column exists
        optional_fields: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "role": "admin",
            "is_superuser": True,
            "full_name": "System Administrator",
        }
        for col, default_val in optional_fields.items():
            if col in columns:
                insert_cols.append(col)
                insert_vals[col] = default_val

        # Validate column names before building SQL
        insert_cols = _validate_seed_columns(insert_cols, _ALLOWED_USER_COLS, "user")

        col_list = ", ".join(insert_cols)
        param_list = ", ".join(f":{col}" for col in insert_cols)

        logger.info(f"[SEED] Creating admin user: {DEFAULT_ADMIN_EMAIL}")
        await session.execute(
            text(  # nosec B608: column names validated against allowlist above
                f"INSERT INTO users ({col_list}) VALUES ({param_list})"
            ),
            insert_vals,
        )

        # Verify creation
        result = await session.execute(
            text("SELECT id FROM users WHERE email = :email AND tenant_id = :tenant_id"),
            {"email": DEFAULT_ADMIN_EMAIL, "tenant_id": tenant_id},
        )
        row = result.fetchone()

        if row:
            user_id = row[0]
            logger.info(f"[SEED] [OK] Created admin user: {DEFAULT_ADMIN_EMAIL} (id={user_id})")
            return True
        else:
            logger.error(
                "[SEED] [FAIL] Failed to verify admin user creation - INSERT succeeded but SELECT returned nothing"
            )
            return False

    except Exception as e:
        logger.error(f"[SEED] [FAIL] Error ensuring admin user: {type(e).__name__}: {e}")
        logger.exception(e)  # Full traceback
        return False
