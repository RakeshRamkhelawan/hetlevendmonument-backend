"""Een eigen databaserol voor de applicatie, zodat Row Level Security gaat werken.

Revision ID: 20260818_app_rol
Revises: 20260817_sched_uniek
Create Date: 2026-08-16

ADR-036 OP-151. PostgreSQL past Row Level Security NIET toe op de eigenaar van een tabel
en niet op een superuser; `FORCE ROW LEVEL SECURITY` helpt evenmin tegen een superuser. De
applicatie verbindt vandaag als `postgres` -- de eigenaar -- dus de 137 policies in deze
keten zijn inert. Gemeten 2026-08-16 op een verse database, tabel `agents` met een rij per
tenant:

    als eigenaar postgres                  2 van 2 rijen
    als niet-eigenaar, tenant gezet        1 van 2
    als niet-eigenaar, lege tenantcontext  0 van 2

Deze migratie maakt de rol en deelt de rechten uit. Zij zet BEWUST geen wachtwoord en geen
inlogrecht:

- een wachtwoord in een migratie is een geheim in de repository, en migratiebestanden
  worden ook offline als platte SQL uitgedraaid (`upgrade head --sql`, gebruikt door
  `scripts/pre-deploy-check.sh` en de CD-preflight);
- zonder LOGIN verandert er niets aan een draaiende omgeving. Het omzetten van een
  omgeving is een bewuste handeling met een eigen moment, beschreven in
  `docs/runbooks/applicatie-databaserol.md`.

`SET ROLE` werkt wel op een NOLOGIN-rol, dus CI en de integratietests kunnen de rol en de
rechten volledig uitoefenen zonder dat er ergens een wachtwoord bestaat.

De rol krijgt GEEN CREATE op het schema. Dat is geen detail: de eigenaar van een tabel
omzeilt RLS, dus een applicatie die zelf tabellen kan aanmaken kan zichzelf ook buiten de
policies plaatsen. Migraties draaien daarom bewust met een andere, hoger geprivilegieerde
verbinding.

De downgrade verwijdert de rol ALLEEN als deze migratie hem heeft aangemaakt. In de week
voor deze migratie zijn drie downgrades betrapt die meer opruimden dan hun upgrade
opbouwde; de boekhoudtabel hieronder is het antwoord daarop.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_app_rol"
down_revision = "20260817_sched_uniek"
branch_labels = None
depends_on = None

_ROL = "sanskritisetu_app"
_BOEKHOUDING = "_app_rol_20260818"


def _is_postgresql() -> bool:
    """Rollen en RLS bestaan niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    # Boekhouding: wat heeft DEZE migratie zelf gedaan? Zonder dit weet de downgrade niet
    # of de rol al bestond -- en dan zou hij een rol weggooien die een beheerder eerder
    # met de hand heeft aangemaakt en waar een draaiende omgeving op verbindt.
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_BOEKHOUDING} (
                wat TEXT PRIMARY KEY
            )
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}') THEN
                    CREATE ROLE {_ROL} NOLOGIN;
                    INSERT INTO {_BOEKHOUDING} (wat) VALUES ('rol_aangemaakt')
                        ON CONFLICT DO NOTHING;
                END IF;
            END $$;
            """
        )
    )

    # De rechten worden ALTIJD (opnieuw) uitgedeeld, ook als de rol al bestond: een
    # bestaande rol met te weinig rechten is even stuk als een ontbrekende rol, en GRANT
    # is idempotent.
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {_ROL}"))
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_ROL}")
    )
    op.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_ROL}"))

    # Tabellen die NA deze migratie worden aangemaakt krijgen de rechten automatisch --
    # maar alleen als ze door dezelfde rol worden aangemaakt als die deze regel uitvoert.
    # Draait een omgeving haar migraties met een andere rol, dan mist een nieuwe tabel de
    # GRANT. Dat is geen lek maar een storing (`permission denied`), en
    # `test_the_application_role_can_read_every_table` betrapt het op een verse database.
    op.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_ROL}"
        )
    )
    op.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {_ROL}"
        )
    )

    # De migratieboekhouding is geen applicatiegegeven. De applicatie leest hem (een
    # health-endpoint toont de schemaversie) maar mag hem niet bijwerken: een rol die
    # `alembic_version` kan herschrijven kan liegen over de schematoestand, waarna een
    # volgende deploy migraties overslaat of opnieuw draait. `IF EXISTS` omdat een verse
    # database deze migratie draait nadat Alembic de tabel heeft aangemaakt, maar een
    # offline dry-run geen tabel heeft.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.alembic_version') IS NOT NULL THEN
                    REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {_ROL};
                END IF;
            END $$;
            """
        )
    )

    # PostgreSQL 15 heeft CREATE op `public` al van PUBLIC afgenomen; 13 en 14 niet. Zonder
    # deze regel zou de applicatierol op een oudere server alsnog tabellen kunnen aanmaken
    # -- en de eigenaar van een tabel omzeilt RLS. Alleen intrekken als PUBLIC het nu heeft,
    # zodat de downgrade weet of hij iets terug moet geven.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF has_schema_privilege('public', 'public', 'CREATE') THEN
                    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
                    INSERT INTO {_BOEKHOUDING} (wat) VALUES ('public_create_ingetrokken')
                        ON CONFLICT DO NOTHING;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    """Exacte inverse: alleen terugdraaien wat de upgrade zelf heeft gedaan."""
    if not _is_postgresql():
        return

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{_BOEKHOUDING}') IS NOT NULL
                   AND EXISTS (SELECT 1 FROM {_BOEKHOUDING} WHERE wat = 'public_create_ingetrokken')
                THEN
                    GRANT CREATE ON SCHEMA public TO PUBLIC;
                END IF;
            END $$;
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}') THEN
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public
                        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {_ROL};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public
                        REVOKE USAGE, SELECT ON SEQUENCES FROM {_ROL};
                    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_ROL};
                    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {_ROL};
                    REVOKE ALL ON SCHEMA public FROM {_ROL};
                END IF;
            END $$;
            """
        )
    )

    # De rol zelf alleen weghalen als DEZE migratie hem heeft aangemaakt. Bestond hij al,
    # dan verbindt er mogelijk een draaiende omgeving mee en is weggooien geen inverse maar
    # een storing.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{_BOEKHOUDING}') IS NOT NULL
                   AND EXISTS (SELECT 1 FROM {_BOEKHOUDING} WHERE wat = 'rol_aangemaakt')
                   AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}')
                THEN
                    EXECUTE 'DROP OWNED BY {_ROL}';
                    EXECUTE 'DROP ROLE {_ROL}';
                END IF;
            END $$;
            """
        )
    )

    op.execute(sa.text(f"DROP TABLE IF EXISTS {_BOEKHOUDING}"))
