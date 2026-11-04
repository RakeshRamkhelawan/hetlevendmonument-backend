"""Row Level Security op `audit_logs`: lezen per klant, schrijven blijft open (ADR-036 OP-246).

Revision ID: 20261024_audit_leesregel
Revises: 20261020_tenant_noodstop
Create Date: 2026-10-24

`audit_logs` was van de 170 tabellen met een klantnummer de enige zonder afschermingsregel, en
zonder klantcontext waren er alle rijen te lezen (gemeten op staging: 126, tegenover nul in elke
andere tabel). De reden voor de uitzondering -- de ketencontrole moet over klantgrenzen heen
kunnen -- geldt voor SCHRIJVEN, niet voor onbeperkt LEZEN (`20260915_rls_resterende_tabellen.py`).

**Twee policies, en waarom twee.**

- `rls_audit_logs_tenant_isolation` (`FOR ALL`): lezen, bijwerken en verwijderen alleen voor de
  klant uit `app.current_tenant`. Zonder klantcontext is dat NULL en dus geen rij.
- `rls_audit_logs_schrijven` (`FOR INSERT ... WITH CHECK (true)`): een auditregel mag voor elke klant
  worden aangemaakt, ook zonder klantcontext en ook zonder klant (`tenant_id IS NULL`). Dat is wat de
  keten nodig heeft: een mislukte login of een systeemgebeurtenis hoort een regel te krijgen, ook als
  de sessie de klant (nog) niet kent.

Samen geven ze: een klant ziet alleen eigen regels, en een regel gaat niet verloren omdat de
schrijver de verkeerde context had: de INSERT slaagt altijd. `INSERT ... RETURNING` toetst de NIEUWE rij ook tegen de
leesregel; de ORM leest de primaire sleutel daarom niet meer terug via RETURNING maar haalt hem
vooraf op (`AuditLog.__table_args__`, `implicit_returning=False`), anders faalt elke schrijf-
actie voor een andere klant of zonder klant onder de applicatierol met `new row violates
row-level security policy`. Gemeten op PostgreSQL 16 als `sanskritisetu_app`.

**De KETEN is een tweede zaak (Gate 2 F1).** Dat de regel er komt betekent niet dat hij goed gekoppeld
wordt. Alle schrijvers ketenen aan de laatste hash van de klant VOOR WIE ze schrijven en zochten die op
onder de context van de SESSIE. Schreef een sessie van klant A een regel voor klant B (of zonder
context), dan zag de lookup de keten van B niet: elke regel kreeg `previous_hash = NULL`, de keten
splitste stil en `verify_chain` meldde manipulatie, terwijl de schrijver `True` kreeg. Opgelost in de
zes schrijvers met `src/core/governance/ketencontext.py` (de lookup draait onder de context van de klant
van de regel, daarna wordt de oorspronkelijke context teruggezet). Een regel ZONDER klant is bewust
ongeketend: de schrijvers ketenen alleen met een klant (gemeten, `test_een_regel_zonder_klant_hoort_in_geen_keten`).

**Wie schrijft voor een andere klant dan de context (Gate 2 F3).** Statisch geinventariseerd, NIET dynamisch
gemeten: 143 aanroepen van `log_event`, `log_security_event`, `log_action` en `log_request_audit` in `src/`.
Bekende legitieme schrijvers zonder of met een andere context: inlog en tokens (voor authenticatie is er
nog geen context; de klant komt uit de gebruiker), tenantbeheer (een beheerder schrijft voor de doelklant),
de harde wissing van een klant (`erasure_router.py`) en achtergrondtaken. Daarom is de schrijfregel NIET
aangescherpt (`WITH CHECK (true)`); dat is een aparte beslissing die een dynamische meting vraagt.

**Afwijking van het voorstel in OP-246.** De twee reviewers stelden `USING (tenant_id IS NULL OR
tenant_id = <klant>)` voor. Dat laat zonder klantcontext de regels zonder klant zien (die kunnen
persoonsgegevens van gebruikers van andere klanten bevatten, zoals een mislukte inlog) en haalt
de eis uit de brief onderuit: zonder klantcontext nul rijen. Omdat het schrijven nu open blijft
zonder RETURNING, is die uitzondering voor het lezen niet nodig.

**OP-248: de begintoestand wordt vastgelegd en exact teruggezet.** De downgrade van
`20260915_rls_resterende_tabellen.py` zet RLS uit op elke tabel, ook een die RLS al aan had.
Deze migratie doet dat niet: de upgrade legt de begintoestand van `audit_logs` (RLS aan of uit,
FORCE aan of uit) vast in een commentaar op de policy die hij zelf aanmaakt, en de downgrade
zet precies die toestand terug. Geen extra tabel, dus geen afwijking tussen model en database,
en het commentaar verdwijnt vanzelf met de policy. Is het commentaar er niet (de policy is
met de hand aangemaakt of weggehaald), dan haalt de downgrade beide policies weg en laat hij de RLS-stand
ongewijzigd: een tabel die mogelijk RLS nodig heeft blijft afgeschermd (zonder policy is dat
`alles weigeren` voor niet-eigenaren, geen verlies). De oudere migratie is niet herschreven.

**Wat dit NIET doet.** `FORCE ROW LEVEL SECURITY` is niet aangezet: de eigenaar (de applicatie
vandaag) wordt niet beperkt tot de applicatierol is omgeschakeld (OP-151, apart uitrollen).
Tot dan verandert deze migratie niets aan wat de applicatie ziet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261024_audit_leesregel"
down_revision = "20261020_tenant_noodstop"
branch_labels = None
depends_on = None

_LEZEN = "rls_audit_logs_tenant_isolation"
_SCHRIJVEN = "rls_audit_logs_schrijven"

#: Het commentaar op de policy dat laat zien dat DEZE migratie hem maakte, en de begintoestand.
_MARKERING = "20261024_audit_leesregel"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    # `to_regclass`: een offline dry-run (`upgrade head --sql`) heeft de tabel niet, en
    # `ALTER TABLE` op een ontbrekende tabel laat de keten omvallen (backend-patterns regel 9).
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                v_rls boolean;
                v_force boolean;
            BEGIN
                IF to_regclass('public.audit_logs') IS NULL THEN
                    RETURN;
                END IF;

                -- De begintoestand VOOR de wijziging (OP-248).
                SELECT relrowsecurity, relforcerowsecurity INTO v_rls, v_force
                FROM pg_class WHERE oid = to_regclass('public.audit_logs');

                EXECUTE 'ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY';

                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'audit_logs'
                      AND policyname = '{_LEZEN}'
                ) THEN
                    EXECUTE $q$CREATE POLICY {_LEZEN} ON audit_logs FOR ALL
                        USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)$q$;
                    EXECUTE 'COMMENT ON POLICY {_LEZEN} ON audit_logs IS '
                        || quote_literal('{_MARKERING}; rls=' || v_rls::text || '; force=' || v_force::text);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'audit_logs'
                      AND policyname = '{_SCHRIJVEN}'
                ) THEN
                    EXECUTE $q$CREATE POLICY {_SCHRIJVEN} ON audit_logs FOR INSERT WITH CHECK (true)$q$;
                    EXECUTE 'COMMENT ON POLICY {_SCHRIJVEN} ON audit_logs IS '
                        || quote_literal('{_MARKERING}');
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    # Alleen wat DEZE migratie maakte (aan het commentaar te herkennen) wordt weggehaald, en RLS
    # gaat alleen uit als de begintoestand `rls=false` was. Zie OP-248 in de docstring.
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                v_tekst text;
                v_was_aan boolean;
            BEGIN
                IF to_regclass('public.audit_logs') IS NULL THEN
                    RETURN;
                END IF;

                SELECT d.description INTO v_tekst
                FROM pg_policy p
                JOIN pg_description d
                  ON d.objoid = p.oid AND d.classoid = 'pg_policy'::regclass
                WHERE p.polrelid = to_regclass('public.audit_logs') AND p.polname = '{_LEZEN}';

                IF v_tekst IS NULL OR v_tekst NOT LIKE '{_MARKERING}; rls=%' THEN
                    -- Niet van ons, of de begintoestand is onbekend: niets terugdraaien dat we
                    -- niet zeker weten. RLS blijft aan, want uit zetten is de gevaarlijke kant.
                    RAISE NOTICE 'audit_logs: begintoestand onbekend, RLS-stand ongewijzigd';
                    EXECUTE 'DROP POLICY IF EXISTS {_SCHRIJVEN} ON audit_logs';
                    EXECUTE 'DROP POLICY IF EXISTS {_LEZEN} ON audit_logs';
                    RETURN;
                END IF;

                v_was_aan := (v_tekst LIKE '%rls=true%');

                EXECUTE 'DROP POLICY IF EXISTS {_SCHRIJVEN} ON audit_logs';
                EXECUTE 'DROP POLICY IF EXISTS {_LEZEN} ON audit_logs';

                IF NOT v_was_aan THEN
                    EXECUTE 'ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY';
                END IF;
            END $$;
            """
        )
    )
