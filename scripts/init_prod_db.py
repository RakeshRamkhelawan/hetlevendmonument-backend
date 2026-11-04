"""
Quick script to create production database schema directly via SQL.
Use this when Alembic migrations can't run (Docker networking issues).
"""

import sys

import psycopg2

# Connection string for local-prod PostgreSQL
DATABASE_URL = "postgresql://postgres:LocalProdPassword123!@localhost:5434/sanskritisetu"

SQL_SCHEMA = """
-- Create tenants table first (referenced by other tables)
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    subdomain VARCHAR(63) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    stripe_customer_id VARCHAR(255) UNIQUE,
    subscription_tier VARCHAR(50) DEFAULT 'free',
    max_users INTEGER DEFAULT 5,
    max_agents INTEGER DEFAULT 10
);

-- Create roles table
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(name, tenant_id)
);

CREATE INDEX IF NOT EXISTS ix_roles_tenant_id ON roles(tenant_id);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    login_count INTEGER DEFAULT 0,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE,
    must_change_password BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users(tenant_id);

-- Create user_roles junction table
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- Create permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description TEXT,
    UNIQUE(resource, action)
);

-- Create role_permissions junction table
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Create account_lockouts table
CREATE TABLE IF NOT EXISTS account_lockouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_account_lockouts_user_id ON account_lockouts(user_id);

-- Create refresh_tokens table
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(500) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token ON refresh_tokens(token);

-- Create audit_logs table (WITH resource column!)
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    description TEXT,
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_resource ON audit_logs(resource);
CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs(timestamp);

-- Create alembic_version table (for migration tracking)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Insert default tenant
INSERT INTO tenants (name, subdomain, subscription_tier, max_users, max_agents)
VALUES ('Default Organization', 'default', 'enterprise', 100, 200)
ON CONFLICT (name) DO NOTHING;

-- Insert admin role
INSERT INTO roles (name, description, tenant_id)
SELECT 'admin', 'Administrator role with full permissions', id
FROM tenants WHERE name = 'Default Organization'
ON CONFLICT (name, tenant_id) DO NOTHING;

-- Insert all permissions
INSERT INTO permissions (resource, action, description) VALUES
    ('users', 'read', 'View user information'),
    ('users', 'write', 'Create and update users'),
    ('users', 'delete', 'Delete users'),
    ('roles', 'read', 'View role information'),
    ('roles', 'write', 'Create and update roles'),
    ('roles', 'delete', 'Delete roles'),
    ('agents', 'read', 'View agent information'),
    ('agents', 'write', 'Create and update agents'),
    ('agents', 'delete', 'Delete agents'),
    ('agents', 'execute', 'Execute agents'),
    ('workflows', 'read', 'View workflow information'),
    ('workflows', 'write', 'Create and update workflows'),
    ('workflows', 'delete', 'Delete workflows'),
    ('workflows', 'execute', 'Execute workflows'),
    ('admin', 'access', 'Access admin panel'),
    ('audit', 'read', 'View audit logs'),
    ('tenants', 'read', 'View tenant information'),
    ('tenants', 'write', 'Manage tenant settings')
ON CONFLICT (resource, action) DO NOTHING;

-- Assign all permissions to admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'admin'
ON CONFLICT DO NOTHING;

COMMIT;
"""


def main():
    """Create database schema."""
    print("[INFO] Connecting to database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cursor = conn.cursor()

        print("[INFO] Executing schema creation...")
        cursor.execute(SQL_SCHEMA)

        print("[INFO] Committing changes...")
        conn.commit()

        # Verify tables
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """
        )
        tables = cursor.fetchall()

        print("\n[OK] Schema created successfully! Tables:")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()
        print("\n[SUCCESS] Database ready for use!")
        return 0

    except Exception as e:
        print(f"[ERROR] Failed to create schema: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
