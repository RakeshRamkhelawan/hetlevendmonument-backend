"""
Complete Database Rebuild Script voor SanskritiSetu.org Local-Prod
==================================================================

Maakt schone database met:
- Tenant 1: "SanskritiSetu Admin" + admin@sanskritisetu.org (Admin123!)
- Tenant 2: "Demo Organization" + Demo@sanskritisetu.org (Demo123!)
- Proper bcrypt password hashing (12 rounds)
- Volledig schema volgens rbac_models.py
"""

import asyncio
import sys
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402

# Database URL voor local-prod (host machine connectie)
DATABASE_URL = "postgresql+asyncpg://postgres:LocalProdPassword123!@localhost:5434/sanskritisetu"

# Tenant en user configuratie
TENANTS = [
    {
        "name": "SanskritiSetu Admin",
        "slug": "admin-org",
        "subdomain": "admin",
        "subscription_tier": "enterprise",
        "max_users": 100,
        "max_agents": 200,
        "user_email": "admin@sanskritisetu.org",
        "user_password": "Admin123!",
    },
    {
        "name": "Demo Organization",
        "slug": "demo-org",
        "subdomain": "demo",
        "subscription_tier": "free",
        "max_users": 10,
        "max_agents": 50,
        "user_email": "Demo@sanskritisetu.org",
        "user_password": "Demo123!",
    },
]


def hash_password(password: str) -> str:
    """Hash password met bcrypt (12 rounds - production grade)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


async def drop_all_tables(session: AsyncSession):
    """Drop alle tabellen in de juiste volgorde (foreign keys eerst)."""
    print("\n[TRASH]  Dropping alle bestaande tabellen...")

    drop_statements = [
        "DROP TABLE IF EXISTS user_roles CASCADE",
        "DROP TABLE IF EXISTS role_permissions CASCADE",
        "DROP TABLE IF EXISTS refresh_tokens CASCADE",
        "DROP TABLE IF EXISTS account_lockouts CASCADE",
        "DROP TABLE IF EXISTS audit_logs CASCADE",
        "DROP TABLE IF EXISTS permissions CASCADE",
        "DROP TABLE IF EXISTS users CASCADE",
        "DROP TABLE IF EXISTS roles CASCADE",
        "DROP TABLE IF EXISTS tenants CASCADE",
        "DROP TABLE IF EXISTS alembic_version CASCADE",
    ]

    for stmt in drop_statements:
        await session.execute(text(stmt))
        table_name = stmt.split("IF EXISTS ")[1].split(" CASCADE")[0]
        print(f"   [OK] Dropped {table_name}")

    await session.commit()
    print("[OK] Alle tabellen verwijderd")


async def create_schema(session: AsyncSession):
    """Creeer volledige database schema."""
    print("\n[U+0001F3D7]  Creeren database schema...")

    # Tenants table - MET slug kolom (conform model)
    await session.execute(
        text(
            """
        CREATE TABLE tenants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            slug VARCHAR(100) NOT NULL UNIQUE,
            subdomain VARCHAR(63) UNIQUE,
            domain VARCHAR(255) UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            max_users INTEGER NOT NULL DEFAULT 10,
            max_agents INTEGER NOT NULL DEFAULT 50,
            max_storage_gb INTEGER DEFAULT 5,
            subscription_tier VARCHAR(50) DEFAULT 'free',
            subscription_status VARCHAR(50) DEFAULT 'active',
            stripe_customer_id VARCHAR(100) UNIQUE,
            settings JSONB DEFAULT '{}',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
        )
    )
    print("   [OK] Created tenants")

    # Roles table
    await session.execute(
        text(
            """
        CREATE TABLE roles (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            description VARCHAR(200),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
        )
    )
    await session.execute(
        text("CREATE UNIQUE INDEX idx_role_tenant_name ON roles(tenant_id, name)")
    )
    await session.execute(
        text("CREATE INDEX idx_role_tenant_active ON roles(tenant_id, is_active)")
    )
    print("   [OK] Created roles")

    # Users table - MET stripe_customer_id en last_login
    await session.execute(
        text(
            """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_login TIMESTAMP WITH TIME ZONE,
            stripe_customer_id VARCHAR(100) UNIQUE
        )
    """
        )
    )
    await session.execute(
        text("CREATE UNIQUE INDEX idx_user_tenant_email ON users(tenant_id, email)")
    )
    await session.execute(
        text("CREATE INDEX idx_user_tenant_active ON users(tenant_id, is_active)")
    )
    print("   [OK] Created users")

    # User-Role junction table
    await session.execute(
        text(
            """
        CREATE TABLE user_roles (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (user_id, role_id)
        )
    """
        )
    )
    print("   [OK] Created user_roles")

    # Permissions table
    await session.execute(
        text(
            """
        CREATE TABLE permissions (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description VARCHAR(255),
            resource_type VARCHAR(50),
            action VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
        )
    )
    print("   [OK] Created permissions")

    # Role-Permission junction table
    await session.execute(
        text(
            """
        CREATE TABLE role_permissions (
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
    """
        )
    )
    print("   [OK] Created role_permissions")

    # Audit logs - MET action kolom (conform governance model)
    await session.execute(
        text(
            """
        CREATE TABLE audit_logs (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100),
            resource VARCHAR(100),
            resource_id VARCHAR(100),
            details JSONB DEFAULT '{}',
            event_type VARCHAR(100) NOT NULL,
            threat_level VARCHAR(20) NOT NULL,
            client_ip VARCHAR(45) NOT NULL,
            endpoint TEXT NOT NULL,
            description TEXT NOT NULL,
            event_metadata JSONB DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
        )
    )
    await session.execute(text("CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id)"))
    await session.execute(text("CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id)"))
    await session.execute(text("CREATE INDEX idx_audit_logs_action ON audit_logs(action)"))
    await session.execute(text("CREATE INDEX idx_audit_logs_resource ON audit_logs(resource)"))
    await session.execute(text("CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type)"))
    await session.execute(text("CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp)"))
    print("   [OK] Created audit_logs (hybrid schema met action + event_type)")

    # Account lockouts table
    await session.execute(
        text(
            """
        CREATE TABLE account_lockouts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            locked_until TIMESTAMP WITH TIME ZONE,
            reason VARCHAR(255),
            failed_attempts INTEGER DEFAULT 0 NOT NULL,
            last_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
            ip_address VARCHAR(45),
            user_agent VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
        )
    )
    await session.execute(
        text("CREATE INDEX idx_account_lockouts_user_id ON account_lockouts(user_id)")
    )
    await session.execute(
        text("CREATE INDEX idx_lockout_user_ip ON account_lockouts(user_id, ip_address)")
    )
    print("   [OK] Created account_lockouts")

    # Refresh tokens table
    await session.execute(
        text(
            """
        CREATE TABLE refresh_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(500) NOT NULL UNIQUE,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            revoked BOOLEAN DEFAULT false
        )
    """
        )
    )
    await session.execute(
        text("CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id)")
    )
    await session.execute(text("CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token)"))
    print("   [OK] Created refresh_tokens")

    # Alembic version table
    await session.execute(
        text(
            """
        CREATE TABLE alembic_version (
            version_num VARCHAR(32) PRIMARY KEY
        )
    """
        )
    )
    print("   [OK] Created alembic_version")

    await session.commit()
    print("[OK] Schema volledig aangemaakt")


async def seed_permissions(session: AsyncSession) -> dict[str, int]:
    """Creeer standaard permissions en return mapping."""
    print("\n[LOCKED] Creeren permissions...")

    permissions = [
        ("users.create", "Create new users", "users", "create"),
        ("users.read", "View users", "users", "read"),
        ("users.update", "Update users", "users", "update"),
        ("users.delete", "Delete users", "users", "delete"),
        ("roles.create", "Create roles", "roles", "create"),
        ("roles.read", "View roles", "roles", "read"),
        ("roles.update", "Update roles", "roles", "update"),
        ("roles.delete", "Delete roles", "roles", "delete"),
        ("agents.create", "Create agents", "agents", "create"),
        ("agents.read", "View agents", "agents", "read"),
        ("agents.update", "Update agents", "agents", "update"),
        ("agents.delete", "Delete agents", "agents", "delete"),
        ("workflows.create", "Create workflows", "workflows", "create"),
        ("workflows.read", "View workflows", "workflows", "read"),
        ("workflows.update", "Update workflows", "workflows", "update"),
        ("workflows.execute", "Execute workflows", "workflows", "execute"),
        ("admin.access", "Access admin panel", "admin", "access"),
        ("audit.read", "View audit logs", "audit", "read"),
        ("tenants.manage", "Manage tenant settings", "tenants", "manage"),
    ]

    perm_map = {}
    for name, desc, resource, action in permissions:
        result = await session.execute(
            text(
                """
                INSERT INTO permissions (name, description, resource_type, action)
                VALUES (:name, :desc, :resource, :action)
                RETURNING id
            """
            ),
            {"name": name, "desc": desc, "resource": resource, "action": action},
        )
        perm_id = result.scalar_one()
        perm_map[name] = perm_id
        print(f"   [OK] {name}")

    await session.commit()
    print(f"[OK] {len(permissions)} permissions aangemaakt")
    return perm_map


async def create_tenants_and_users(session: AsyncSession, perm_map: dict[str, int]):
    """Creeer tenants, users, roles en assignments."""
    print("\n[U+0001F465] Creeren tenants en users...")

    for idx, tenant_config in enumerate(TENANTS, 1):
        # Create tenant
        result = await session.execute(
            text(
                """
                INSERT INTO tenants (name, slug, subdomain, subscription_tier, max_users, max_agents, is_active)
                VALUES (:name, :slug, :subdomain, :tier, :max_users, :max_agents, true)
                RETURNING id
            """
            ),
            {
                "name": tenant_config["name"],
                "slug": tenant_config["slug"],
                "subdomain": tenant_config["subdomain"],
                "tier": tenant_config["subscription_tier"],
                "max_users": tenant_config["max_users"],
                "max_agents": tenant_config["max_agents"],
            },
        )
        tenant_id = result.scalar_one()
        print(f"\n   [U+0001F3E2] Tenant {idx}: {tenant_config['name']} (id={tenant_id})")

        # Create admin role for this tenant
        result = await session.execute(
            text(
                """
                INSERT INTO roles (tenant_id, name, description, is_active)
                VALUES (:tenant_id, 'admin', 'Administrator with full permissions', true)
                RETURNING id
            """
            ),
            {"tenant_id": tenant_id},
        )
        role_id = result.scalar_one()
        print(f"      [OK] Admin role created (id={role_id})")

        # Assign ALL permissions to admin role
        for perm_id in perm_map.values():
            await session.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id)"
                ),
                {"role_id": role_id, "perm_id": perm_id},
            )
        print(f"      [OK] Assigned {len(perm_map)} permissions to admin role")

        # Hash password
        hashed_pw = hash_password(tenant_config["user_password"])
        print("      [OK] Password hashed (bcrypt $2b$12)")

        # Create user
        result = await session.execute(
            text(
                """
                INSERT INTO users (tenant_id, email, hashed_password, is_active)
                VALUES (:tenant_id, :email, :password, true)
                RETURNING id
            """
            ),
            {
                "tenant_id": tenant_id,
                "email": tenant_config["user_email"],
                "password": hashed_pw,
            },
        )
        user_id = result.scalar_one()
        print(f"      [OK] User created: {tenant_config['user_email']} (id={user_id})")

        # Assign admin role to user
        await session.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
            {"user_id": user_id, "role_id": role_id},
        )
        print("      [OK] Admin role assigned to user")

    await session.commit()
    print(f"\n[OK] {len(TENANTS)} tenants en users volledig geconfigureerd")


async def mark_alembic_current(session: AsyncSession):
    """Mark database als up-to-date met laatste migratie."""
    print("\n[NOTE] Markeren Alembic versie...")

    # Latest migration van onderzoek: db594ab6cd8e (add_account_lockouts)
    await session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('db594ab6cd8e')"))
    await session.commit()
    print("   [OK] Alembic version: db594ab6cd8e (account_lockouts)")
    print("[OK] Database gemarkeerd als up-to-date")


async def verify_setup(session: AsyncSession):
    """Verificatie van de setup."""
    print("\n[SEARCH] Verificatie van database setup...")

    # Check tenants
    result = await session.execute(text("SELECT COUNT(*) FROM tenants"))
    tenant_count = result.scalar_one()
    print(f"   [OK] Tenants: {tenant_count}")

    # Check users
    result = await session.execute(text("SELECT COUNT(*) FROM users"))
    user_count = result.scalar_one()
    print(f"   [OK] Users: {user_count}")

    # Check roles
    result = await session.execute(text("SELECT COUNT(*) FROM roles"))
    role_count = result.scalar_one()
    print(f"   [OK] Roles: {role_count}")

    # Check permissions
    result = await session.execute(text("SELECT COUNT(*) FROM permissions"))
    perm_count = result.scalar_one()
    print(f"   [OK] Permissions: {perm_count}")

    # Check user-role assignments
    result = await session.execute(text("SELECT COUNT(*) FROM user_roles"))
    assignment_count = result.scalar_one()
    print(f"   [OK] User-Role assignments: {assignment_count}")

    # Check audit_logs schema
    result = await session.execute(
        text(
            """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'audit_logs' AND column_name IN ('action', 'event_type')
        ORDER BY column_name
    """
        )
    )
    audit_cols = [row[0] for row in result.fetchall()]
    print(f"   [OK] Audit_logs heeft kolommen: {', '.join(audit_cols)}")

    # List users met credentials
    print("\n[LIST] User Accounts:")
    result = await session.execute(
        text(
            """
        SELECT u.email, t.name as tenant_name, r.name as role
        FROM users u
        JOIN tenants t ON u.tenant_id = t.id
        JOIN user_roles ur ON u.id = ur.user_id
        JOIN roles r ON ur.role_id = r.id
        ORDER BY t.id
    """
        )
    )
    for row in result.fetchall():
        email, tenant, role = row
        print(f"   - {email} ({tenant}) - Role: {role}")

    print("\n[OK] Verificatie compleet!")


async def main():
    """Hoofdfunctie voor database rebuild."""
    print("=" * 80)
    print("[U+0001F504] SANSKRITISETU.ORG - COMPLETE DATABASE REBUILD")
    print("=" * 80)
    print(f"\nDatabase: {database_url_zonder_wachtwoord(DATABASE_URL)}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Stap 1: Drop alles
            await drop_all_tables(session)

            # Stap 2: Creeer schema
            await create_schema(session)

            # Stap 3: Seed permissions
            perm_map = await seed_permissions(session)

            # Stap 4: Creeer tenants en users
            await create_tenants_and_users(session, perm_map)

            # Stap 5: Mark Alembic
            await mark_alembic_current(session)

            # Stap 6: Verificatie
            await verify_setup(session)

        print("\n" + "=" * 80)
        print("[OK] DATABASE REBUILD SUCCESVOL VOLTOOID!")
        print("=" * 80)
        print("\n[NOTE] Volgende stappen:")
        print(
            "   1. Herstart backend: docker-compose -f docker-compose.local-prod.yml restart backend"
        )
        print("   2. Test login admin: python test_me_endpoint.py")
        print("   3. Test frontend: http://localhost:3005")
        print()

        return 0

    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
