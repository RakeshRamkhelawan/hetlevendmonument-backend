"""Smalle databasefunctie voor het anonimiseren van personen in auditregels van een ANDERE klant (Gate 2 F2, OP-246).

Revision ID: 20261025_audit_anonimiseer_functie
Revises: 20261024_audit_leesregel
Create Date: 2026-10-25

**Het probleem.** De harde wissing van een klant (`erasure_router.py`) anonimiseert via
`avg_auditlog._ANONIMISEER_ELDERS` ook de auditregels van een ANDERE klant of zonder klant waarin een persoon van de
klant staat, omdat `audit_logs_user_id_fkey` het verwijderen van die persoon anders blokkeert. Onder de leesregel
van `20261024_audit_leesregel` ziet de applicatierol met de context van de wissende klant die regels niet: de UPDATE raakt
0 rijen, daarna faalt `DELETE FROM users` op de vreemde sleutel en draait de hele wissing terug (500).

**De oplossing (besluit Rakesh).** Geen bredere rechten voor de bypass-rol, maar een smalle functie:
`audit_logs_anonimiseer_gebruikers(p_tenant integer, p_gebruikers integer[]) RETURNS integer`.

- `SECURITY DEFINER`, eigenaar is wie de migratie draait (de tabeleigenaar), `search_path` vast op
  `pg_catalog, public, pg_temp`. Alle objecten zijn bovendien met schema genoemd.
- `EXECUTE` alleen voor `sanskritisetu_app`; `PUBLIC` heeft het niet, dus ook de bypass-rol niet.
- De functie doet ALLEEN de anonimisering van dezelfde persoonsvelden als de oude UPDATE (`user_id`, `client_ip`,
  `description`, `details`, `event_metadata`), alleen op regels van een andere klant of zonder klant, alleen voor de
  opgegeven gebruikers, en laat HITL-gebonden regels (`resource LIKE 'hitl_ticket:%'`) ongemoeid.
- Invoer wordt gecontroleerd: `p_tenant` moet gelijk zijn aan de klantcontext van de sessie (`app.current_tenant`), en
  ELKE opgegeven gebruiker moet bij die klant horen. Een klant kan dus geen gebruikers van een andere klant
  anonimiseren, en zonder klantcontext doet de functie niets (fout `42501`).
- Gemeten: de hashvelden zijn `tenant_id`, `action`, `resource`, `timestamp` en `previous_hash` (plus AI-velden); geen van
  de aangeraakte kolommen zit erin, dus de keten breekt niet (zie `avg_auditlog.py`, getoetst in de integratietest).

**Wat dit NIET doet.** Heeft de eigenaar later FORCE ROW LEVEL SECURITY op `users` of `audit_logs` (OP-151), dan valt de
functie zelf onder de leesregel en moet er een bypass-eigenaar voor komen.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261025_audit_anonimiseer_functie"
down_revision = "20261024_audit_leesregel"
branch_labels = None
depends_on = None

_FUNCTIE = "audit_logs_anonimiseer_gebruikers"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.audit_logs') IS NULL OR to_regclass('public.users') IS NULL THEN
                    RETURN;
                END IF;

                EXECUTE $f$
                CREATE OR REPLACE FUNCTION public.{_FUNCTIE}(p_tenant integer, p_gebruikers integer[])
                RETURNS integer
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path = pg_catalog, public, pg_temp
                AS $body$
                DECLARE
                    v_context text;
                    v_vreemd integer;
                    v_aantal integer;
                BEGIN
                    IF p_tenant IS NULL OR p_gebruikers IS NULL THEN
                        RAISE EXCEPTION 'tenant en gebruikers zijn verplicht' USING ERRCODE = '22023';
                    END IF;

                    v_context := NULLIF(pg_catalog.current_setting('app.current_tenant', true), '');
                    IF v_context IS NULL OR v_context::integer <> p_tenant THEN
                        RAISE EXCEPTION 'alleen de klant zelf mag zijn eigen gebruikers anonimiseren'
                            USING ERRCODE = '42501';
                    END IF;

                    IF pg_catalog.cardinality(p_gebruikers) = 0 THEN
                        RETURN 0;
                    END IF;

                    SELECT pg_catalog.count(*) INTO v_vreemd
                    FROM pg_catalog.unnest(p_gebruikers) AS g(id)
                    WHERE NOT EXISTS (
                        SELECT 1 FROM public.users u WHERE u.id = g.id AND u.tenant_id = p_tenant
                    );
                    IF v_vreemd > 0 THEN
                        RAISE EXCEPTION 'de gebruikers horen niet allemaal bij deze klant'
                            USING ERRCODE = '42501';
                    END IF;

                    UPDATE public.audit_logs
                    SET user_id = NULL,
                        client_ip = 'geanonimiseerd',
                        description = COALESCE(action, 'geanonimiseerd'),
                        details = pg_catalog.json_build_object('geanonimiseerd', true),
                        event_metadata = pg_catalog.json_build_object('geanonimiseerd', true)
                    WHERE tenant_id IS DISTINCT FROM p_tenant
                      AND user_id = ANY (p_gebruikers)
                      AND (resource IS NULL OR resource NOT LIKE 'hitl_ticket:%');
                    GET DIAGNOSTICS v_aantal = ROW_COUNT;
                    RETURN v_aantal;
                END
                $body$
                $f$;

                EXECUTE 'REVOKE ALL ON FUNCTION public.{_FUNCTIE}(integer, integer[]) FROM PUBLIC';
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanskritisetu_app') THEN
                    EXECUTE 'GRANT EXECUTE ON FUNCTION public.{_FUNCTIE}(integer, integer[]) TO sanskritisetu_app';
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{_FUNCTIE}(integer, integer[])"))
