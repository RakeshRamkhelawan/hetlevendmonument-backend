"""Een aparte databaserol voor het pre-authenticatiepad (ADR-036 OP-154).

Revision ID: 20260915_bypass_rol
Revises: adr036_op81_requested_by
Create Date: 2026-09-15

De omschakeling naar `sanskritisetu_app` (OP-151) loopt vast op het inlogpad: dat zoekt een
gebruiker op e-mailadres VOORDAT de tenant bekend is, en zonder tenantcontext geeft die
lookup nul rijen. Gemeten 2026-09-15 op PostgreSQL 15.19 met de policy-vorm uit
`20260522_add_rls_core_tables.py:38-43`:

    als eigenaar, geen tenantcontext           1 rij
    als sanskritisetu_app, geen tenantcontext  0 rijen
    als sanskritisetu_app, tenant 1 gezet      1 rij

**Waarom deze rol NIET aan de applicatierol wordt gegrant.** Gemeten vanaf een ECHTE
inlogverbinding als `sanskritisetu_app`:

    rol gegrant, INHERIT    -> `SET ROLE` lukt -> ALLE tenants zichtbaar
    rol gegrant, NOINHERIT  -> `SET ROLE` lukt -> ALLE tenants zichtbaar
    rol NIET gegrant        -> permission denied to set role

`BYPASSRLS` is een rol-attribuut en geen overerfbaar privilege; `NOINHERIT` geldt niet voor
rol-attributen. Een grant zou de applicatieverbinding een permanente uitweg uit alle
policies geven. De rol is daarom alleen bereikbaar via een EIGEN verbinding
(`BYPASS_DATABASE_URL`, zie `src/core/database/bypass_session.py`). Besluit Rakesh,
2026-08-17.

**NOLOGIN en geen wachtwoord**, om dezelfde reden als bij `20260818_applicatie_databaserol`:
een wachtwoord in een migratie is een geheim in de repository, en migraties draaien ook
offline als platte SQL. Zonder LOGIN verandert er niets aan een draaiende omgeving. Het
aanzetten is een bewuste handeling uit `docs/runbooks/applicatie-databaserol.md`.

**De rechtenset is bewust SMAL.** Alleen SELECT, en alleen op de VIER tabellen die het
pre-authenticatiepad aantoonbaar leest. Afgelezen uit `router_login.py:175-190` op commit
19e4fe34: `select(User)` met `selectinload(User.roles)`, wat `users`, `roles` en de
koppeltabel `user_roles` raakt, plus `select(AccountLockout)` op `account_lockouts`.

**`tenants` stond hier eerst bij, met als reden "voor registratie". Die reden was FOUT en
is nagemeten:** `router_registration.py:41-81` doet nergens een `select(Tenant)` -- de
tenant komt uit `require_tenant_id()` (ContextVar). De tabel is daarom verwijderd in plaats
van met een betere reden behouden. Dit is de regel "een onbewezen oorzaak wordt nooit een
WHY-comment" toegepast op mijn eigen tekst.

Deze rol omzeilt per definitie elke policy -- hoe minder hij mag zien, hoe minder een lek op
die verbinding waard is. Het faalgedrag bij een ontbrekend recht is `permission denied`:
luid, en geen lek.

**Stap 2 heeft hier NIETS bij gevraagd, en dat is met opzet (bijgewerkt 2026-09-15).**
Een eerdere versie van deze docstring voorspelde dat stap 2 INSERT-rechten op `users`,
`user_roles` en `account_lockouts` nodig zou hebben. Het gekozen ontwerp doet precies het
omgekeerde: het pre-authenticatiepad leest alleen `id` en `tenant_id` via deze verbinding,
NEEMT DAARNA DE TENANT AAN (`adopt_tenant`), en schrijft op de GEWONE applicatieverbinding,
afgeschermd tot die ene tenant.

**Deze rol blijft dus SELECT-only.** Wie hier ooit een `GRANT INSERT`/`UPDATE` overweegt:
dat is het signaal dat een aanroepplek het patroon niet volgt, niet dat de rechtenset te
smal is. Twee Gate 2-reviewers noemden onafhankelijk het risico dat deze set stap voor stap
zou uitdijen tot hij niets meer voorstelt; het ontwerp neemt die weg dringt in plaats van
hem te beloven.

**Geen CREATE, geen DDL.** De eigenaar van een tabel omzeilt RLS; een rol die tabellen kan
aanmaken kan zichzelf buiten de policies plaatsen.

De downgrade verwijdert de rol alleen als deze migratie hem IN DEZE DATABASE heeft
aangemaakt -- zelfde boekhoudpatroon en zelfde reden als `20260818_applicatie_databaserol`,
waar drie downgrades zijn betrapt die meer opruimden dan hun upgrade opbouwde.

**De reikwijdte van die boekhouding is beperkt, en dat is geen detail.** Een rol is
CLUSTER-breed, de boekhoudtabel staat PER DATABASE. Draaien twee databases op hetzelfde
cluster deze migratie, dan boekt alleen de eerste `rol_aangemaakt`. Twee gevolgen, allebei
echt: de tweede database ruimt bij downgrade niets op (ongevaarlijk), en de eerste zou een
cluster-brede rol wegtrekken die de tweede nog gebruikt. Dat tweede is hieronder afgedekt
met een `pg_shdepend`-controle: bestaan er elders nog afhankelijkheden, dan blijft de rol
staan en zegt de migratie dat met een `NOTICE`. Dit is dus GEEN "verwijdert alleen wat hij
aanmaakte" in cluster-brede zin -- die belofte kan een per-database tabel niet waarmaken,
en `20260818` claimt hem ten onrechte wel.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260915_bypass_rol"
down_revision = "adr036_op81_requested_by"
branch_labels = None
depends_on = None

_ROL = "sanskritisetu_bypass"
_BOEKHOUDING = "_bypass_rol_20260915"

# Afgelezen uit de modellen op commit 19e4fe34:
#   src/core/models/rbac_models.py:282 (users), :194 (roles), :37 (user_roles)
#   src/core/auth/models/account_lockout.py:31 (account_lockouts)
_TABELLEN = ("users", "roles", "user_roles", "account_lockouts")


def _is_postgresql() -> bool:
    """Rollen en RLS bestaan niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {_BOEKHOUDING} (wat TEXT PRIMARY KEY)"))

    # BYPASSRLS vereist superuser. Lukt dit niet, dan hoort de migratie te FALEN en niet
    # stilzwijgend een rol zonder bypass achter te laten: die zou op het inlogpad nul rijen
    # geven -- precies de stille storing die OP-154 beschrijft.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}') THEN
                    CREATE ROLE {_ROL} NOLOGIN BYPASSRLS;
                    INSERT INTO {_BOEKHOUDING} (wat) VALUES ('rol_aangemaakt')
                        ON CONFLICT DO NOTHING;
                END IF;
            END $$;
            """
        )
    )

    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {_ROL}"))
    for tabel in _TABELLEN:
        # `IF EXISTS`-vorm: een offline dry-run heeft de tabellen niet, en een GRANT op een
        # ontbrekende tabel zou de hele keten laten omvallen.
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{tabel}') IS NOT NULL THEN
                        GRANT SELECT ON public.{tabel} TO {_ROL};
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    # Alles hieronder hangt aan het BESTAAN van de rol. Zonder deze wacht faalt
    # `REVOKE ... FROM <rol>` met "role does not exist" zodra iemand de rol met de hand heeft
    # verwijderd, en dan valt de downgrade halverwege om. De tabelcontrole volstond niet:
    # die toetst de TABEL, niet de ROL.
    _intrekkingen = "".join(
        f"IF to_regclass('public.{tabel}') IS NOT NULL THEN "
        f"EXECUTE 'REVOKE SELECT ON public.{tabel} FROM {_ROL}'; END IF; "
        for tabel in _TABELLEN
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}') THEN
                    RETURN;
                END IF;
                {_intrekkingen}
                EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {_ROL}';
            END $$;
            """
        )
    )

    # Alleen opruimen wat deze migratie in DEZE database zelf heeft aangemaakt.
    # `DROP OWNED BY` moet VOOR het verwijderen van de rol, anders blijft er een rij in
    # `pg_default_acl`/`pg_shdepend` staan en faalt het halverwege -- gemeten bij
    # `20260818_applicatie_databaserol`.
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                elders integer;
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROL}') THEN
                    RETURN;
                END IF;
                IF to_regclass('public.{_BOEKHOUDING}') IS NULL THEN
                    RETURN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM {_BOEKHOUDING} WHERE wat = 'rol_aangemaakt') THEN
                    RETURN;
                END IF;

                EXECUTE 'DROP OWNED BY {_ROL}';

                -- `DROP OWNED BY` werkt alleen in de HUIDIGE database. Hangt de rol elders
                -- in het cluster nog ergens aan, dan zou het verwijderen falen en de
                -- downgrade halverwege afbreken. Dan liever de rol laten staan en dat
                -- hardop zeggen: een per-database boekhouding kan een cluster-brede belofte
                -- niet waarmaken.
                SELECT count(*) INTO elders FROM pg_shdepend d
                    JOIN pg_roles r ON r.oid = d.refobjid
                    WHERE r.rolname = '{_ROL}';
                IF elders > 0 THEN
                    RAISE NOTICE 'Rol {_ROL} blijft staan: nog % afhankelijkheid(heden) in '
                        'andere databases van dit cluster (ADR-036 OP-154).', elders;
                ELSE
                    EXECUTE 'DROP ROLE IF EXISTS {_ROL}';
                END IF;
                DELETE FROM {_BOEKHOUDING} WHERE wat = 'rol_aangemaakt';
            END $$;
            """
        )
    )

    # De boekhoudtabel hoort alleen bij DEZE migratie. Laat hij staan, dan is de downgrade
    # geen inverse van de upgrade en blijft er dode DDL achter -- precies wat
    # `test_the_chain_builds_the_whole_schema` bewaakt.
    op.execute(sa.text(f"DROP TABLE IF EXISTS {_BOEKHOUDING}"))
