"""`user_roles` krijgt een `tenant_id`; de database dwingt een klant per koppeling af (OP-190 deel 2).

Revision ID: 20261009_user_roles_tenant_id
Revises: 20261008_debiteuren_verzenden_en_opvolgen
Create Date: 2026-10-09

Deel 1 (`20261004_user_roles_rls`) zette een policy op de koppeltabel. Een policy beschermt alleen
een verbinding die eronder valt; de eigenaar omzeilt hem (OP-151). Deze migratie legt dezelfde
eis in het SCHEMA vast, zodat ook de eigenaar geen koppeling over de klantgrens kan leggen:

- kolom `user_roles.tenant_id`, gevuld uit `users.tenant_id`, daarna NOT NULL;
- unieke sleutel `uq_roles_id_tenant` op `roles (id, tenant_id)` (`users` heeft die al:
  `uq_users_id_tenant`, migratie `20260529b`);
- twee samengestelde vreemde sleutels: `(user_id, tenant_id) -> users (id, tenant_id)` en
  `(role_id, tenant_id) -> roles (id, tenant_id)`. De bestaande enkelvoudige sleutels op
  `user_id` en `role_id` (met `ON DELETE CASCADE`) blijven staan;
- een vultrigger: een insert zonder `tenant_id` (de rauwe admin-scripts, testopstellingen en een
  ORM-mutatie via `user.roles`) krijgt de klant van de gebruiker. De trigger VULT alleen; de
  gekruiste koppeling weigert de vreemde sleutel naar `roles`, niet de trigger.

**Interlock 1 (onomkeerbaar/data-rakend), woord van Rakesh 2026-10-09 onder voorwaarde:** alleen
als er nul gekruiste rijen zijn. Deze migratie VULT alleen en verwijdert nooit een rij. Vindt hij na
de backfill een rij zonder gebruiker, zonder rol of met een rol van een andere klant dan de
gebruiker, dan FAALT hij met een melding; de hele migratie loopt in een transactie en laat dus
niets achter. Er is geen stille reparatie.

De downgrade verwijdert precies wat deze migratie aanmaakt, in omgekeerde volgorde: trigger en
functie, de twee sleutels, de unieke sleutel op `roles`, de kolom. Koppelingsrijen blijven staan.

Geen `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261009_user_roles_tenant_id"
down_revision = "20261008_debiteuren_verzenden_en_opvolgen"
branch_labels = None
depends_on = None

_FUNCTIE = "user_roles_vul_tenant_id"
_TRIGGER = "trg_user_roles_vul_tenant_id"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column("user_roles", sa.Column("tenant_id", sa.Integer(), nullable=True))

    if _is_postgresql():
        # Alleen vullen. De eigenaar-verbinding van de migratie omzeilt de RLS-policy.
        op.execute(
            sa.text(
                "UPDATE user_roles ur SET tenant_id = u.tenant_id "
                "FROM users u WHERE u.id = ur.user_id AND ur.tenant_id IS NULL"
            )
        )
        # Wees (gebruiker weg), gekruist (rol van een andere klant) of rol weg: stoppen. Als
        # SQL-blok en niet als `get_bind().execute(...)`: de offline dry-run
        # (`alembic upgrade head --sql`) heeft geen verbinding, en een blok loopt in beide standen.
        op.execute(
            sa.text(
                """
                DO $$
                DECLARE onjuist integer;
                BEGIN
                    SELECT count(*) INTO onjuist
                    FROM user_roles ur LEFT JOIN roles r ON r.id = ur.role_id
                    WHERE ur.tenant_id IS NULL OR r.tenant_id IS DISTINCT FROM ur.tenant_id;
                    IF onjuist > 0 THEN
                        RAISE EXCEPTION USING MESSAGE =
                            'OP-190 deel 2 afgebroken - ' || CAST(onjuist AS text)
                            || ' koppeling(en) in user_roles hebben geen gebruiker, geen rol, of een '
                            || 'gebruiker en rol van VERSCHILLENDE klanten (gekruiste of wees-rij). '
                            || 'Er is niets gewijzigd en niets verwijderd. Los de rijen eerst met de '
                            || 'eigenaar van de data op; deze migratie repareert niet stilletjes.';
                    END IF;
                END $$;
                """
            )
        )

    op.alter_column("user_roles", "tenant_id", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint("uq_roles_id_tenant", "roles", ["id", "tenant_id"])
    op.create_foreign_key(
        "fk_user_roles_user_tenant",
        "user_roles",
        "users",
        ["user_id", "tenant_id"],
        ["id", "tenant_id"],
    )
    op.create_foreign_key(
        "fk_user_roles_role_tenant",
        "user_roles",
        "roles",
        ["role_id", "tenant_id"],
        ["id", "tenant_id"],
    )

    if _is_postgresql():
        op.execute(
            sa.text(
                f"""
                CREATE FUNCTION {_FUNCTIE}() RETURNS trigger AS $f$
                BEGIN
                    IF NEW.tenant_id IS NULL THEN
                        SELECT tenant_id INTO NEW.tenant_id FROM users WHERE id = NEW.user_id;
                    END IF;
                    RETURN NEW;
                END
                $f$ LANGUAGE plpgsql
                """
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_TRIGGER} BEFORE INSERT ON user_roles "
                f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTIE}()"
            )
        )


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON user_roles"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTIE}()"))

    op.drop_constraint("fk_user_roles_role_tenant", "user_roles", type_="foreignkey")
    op.drop_constraint("fk_user_roles_user_tenant", "user_roles", type_="foreignkey")
    op.drop_constraint("uq_roles_id_tenant", "roles", type_="unique")
    op.drop_column("user_roles", "tenant_id")
