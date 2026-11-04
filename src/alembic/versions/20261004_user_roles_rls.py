"""Row Level Security op `user_roles`: een koppeling alleen zichtbaar als BEIDE kanten het zijn (OP-190).

Revision ID: 20261004_user_roles_rls
Revises: 20260920_tenant_llm
Create Date: 2026-10-04

`user_roles` is een kale koppeltabel (`user_id`, `role_id`, `created_at`) zonder `tenant_id`.
`users` en `roles` hebben wel een policy; de koppeltabel zelf had er geen. Een RECHTSTREEKSE
lees- of schrijfactie op `user_roles` had daardoor geen databasebescherming.

Variant A uit de brief (puur toevoegend): ENABLE ROW LEVEL SECURITY plus een policy FOR ALL
waarvan USING en WITH CHECK allebei eisen dat zowel de gebruiker (via `users`) ALS de rol
(via `roles`) bij de huidige tenant horen. De tenantcontext-uitdrukking is die van
`20260915_rls_resterende_tabellen.py`, de policynaam volgt zijn naamgeving. Geen kolom, geen
backfill, geen UPDATE/DELETE van data, geen FORCE ROW LEVEL SECURITY, geen databaserol.

Let op: een policy beschermt alleen een verbinding die er onder valt. De eigenaar omzeilt hem
zonder FORCE; zie OP-151. De inlogkant leest via `sanskritisetu_bypass` (BYPASSRLS) en blijft
dus ongemoeid.

De downgrade verwijdert precies wat deze migratie aanmaakt: de policy en de RLS-vlag.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261004_user_roles_rls"
down_revision = "20260920_tenant_llm"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    # `to_regclass`: zie 20260915_rls_resterende_tabellen.py (offline dry-run).
    # Dollar-quoting ($q$) voor de policy: de expressie bevat zelf enkele quotes.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regclass('public.user_roles') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY';
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'user_roles'
                      AND policyname = 'rls_user_roles_tenant_isolation'
                ) THEN
                    EXECUTE $q$CREATE POLICY rls_user_roles_tenant_isolation ON user_roles FOR ALL
                        USING (
                            EXISTS (
                                SELECT 1 FROM users u
                                WHERE u.id = user_roles.user_id
                                  AND u.tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
                            )
                            AND EXISTS (
                                SELECT 1 FROM roles r
                                WHERE r.id = user_roles.role_id
                                  AND r.tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
                            )
                        )
                        WITH CHECK (
                            EXISTS (
                                SELECT 1 FROM users u
                                WHERE u.id = user_roles.user_id
                                  AND u.tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
                            )
                            AND EXISTS (
                                SELECT 1 FROM roles r
                                WHERE r.id = user_roles.role_id
                                  AND r.tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
                            )
                        )$q$;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regclass('public.user_roles') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'DROP POLICY IF EXISTS rls_user_roles_tenant_isolation ON user_roles';
                EXECUTE 'ALTER TABLE user_roles DISABLE ROW LEVEL SECURITY';
            END $$;
            """
        )
    )
