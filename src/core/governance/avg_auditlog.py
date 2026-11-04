"""Het auditlog van een op te heffen tenant: bewaren, maar zonder persoonsgegevens (AVG C).

Besluit Rakesh 2026-10-12. Stap 0, gemeten in de code:

- WAT IN DE HASH ZIT (`HashChainVerifier._compute_hash`): `tenant_id`, `action`, `resource`,
  `timestamp` en `previous_hash`; bij AI-context ook de AI-velden. Dat blijft ONGEMOEID: een regel
  wordt dus nooit opnieuw gehasht en de keten breekt niet.
- WAT PERSOONSGEGEVENS KAN BEVATTEN en BUITEN de hash staat: `user_id` (wie), `client_ip`,
  `description` (bv. "Triggered by user <e-mail>"), `details` (bv. `{"email": ...}` bij inlogpogingen
  en gebruikersbeheer) en `event_metadata` (bv. de `user_agent`). Die worden hier geanonimiseerd.
- WAT NIET KAN: `resource` zit in de hash en kan dus niet worden gewist. Wat er in staat is volgens
  de schrijvers een objectnaam of een nummer, geen e-mail; dat is niet uitputtend gemeten.
- HITL-regels binden `user_id` via een digest in `resource` (ADR-036 H-2). Na anonimiseren is
  `user_id` leeg; de regel draagt dan `geanonimiseerd: true` en de verificatie meldt de binding als
  "niet meer na te rekenen" in plaats van als manipulatie (zie `HashChainVerifier._verify_bound_evidence`).
  Dat is een bewuste ruil: wie een regel anonimiseert geeft het bewijs WIE goedkeurde op.

`endpoint` blijft staan (een pad, zonder persoon), net als `event_type`, `threat_level` en `action`.
`event_metadata` houdt alleen de sleutels die de bewijsbindingen nodig hebben.

Bewaartermijn: volgens de werkgever. Er is geen wettelijke termijn gemeten; de eerdere "7 jaar" in
een commentaar was niet bewezen.
"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy import column, delete, table, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

MARKERING = "geanonimiseerd"

# De sleutels van `event_metadata` die een bewijsbinding nodig heeft (hitl_evidence en
# retention_evidence); alles anders (user_agent, e-mailadressen, vrije tekst) verdwijnt. Dezelfde
# lijst staat letterlijk in de SQL hieronder; `tests/integration/test_avg_auditlog_zonder_persoonsgegevens.py`
# bewaakt dat ze gelijk blijven.
BEWIJS_SLEUTELS = (
    "tool_name",
    "approval_binding",
    "records_deleted",
    "cutoff_date",
    "regulatory_basis",
)

_ANONIMISEER = text(
    """
    UPDATE audit_logs
    SET user_id = NULL,
        client_ip = 'geanonimiseerd',
        description = COALESCE(action, 'geanonimiseerd'),
        details = json_build_object('geanonimiseerd', true),
        event_metadata = (
            COALESCE(
                (
                    SELECT jsonb_object_agg(k, v)
                    FROM jsonb_each(
                        CASE WHEN json_typeof(event_metadata) = 'object'
                             THEN event_metadata::jsonb ELSE '{}'::jsonb END
                    ) AS e(k, v)
                    WHERE k IN ('tool_name', 'approval_binding', 'records_deleted',
                                'cutoff_date', 'regulatory_basis')
                ),
                '{}'::jsonb
            ) || jsonb_build_object('geanonimiseerd', true)
        )::json
    WHERE tenant_id = :tenant_id
    """
)


# Regels van een ANDERE klant of zonder klant die een persoon van deze klant dragen. Onder de leesregel van
# `20261024_audit_leesregel` ziet de applicatierol die regels niet (de oude UPDATE raakte 0 rijen en
# `DELETE FROM users` faalde op `audit_logs_user_id_fkey`), dus dit loopt via de smalle databasefunctie uit
# `20261025_audit_anonimiseer_functie`: die controleert zelf dat `tenant_id` de klantcontext is en dat elke
# gebruiker bij die klant hoort, en doet alleen deze anonimisering (Gate 2 F2).
_EIGEN_GEBRUIKERS = text("SELECT id FROM users WHERE tenant_id = :tenant_id")
_ANONIMISEER_ELDERS = text(
    "SELECT audit_logs_anonimiseer_gebruikers(:tenant_id, CAST(:gebruikers AS integer[]))"
)

# Een database die uit de modellen is opgebouwd (de integratietests) en niet uit de migraties heeft de functie niet.
# Alleen DAN valt dit terug op de directe UPDATE (die als eigenaar werkt); elke andere fout blijft een fout.
_ANONIMISEER_ELDERS_DIRECT = text(
    """
    UPDATE audit_logs
    SET user_id = NULL,
        client_ip = 'geanonimiseerd',
        description = COALESCE(action, 'geanonimiseerd'),
        details = json_build_object('geanonimiseerd', true),
        event_metadata = json_build_object('geanonimiseerd', true)
    WHERE tenant_id IS DISTINCT FROM :tenant_id
      AND user_id IN (SELECT id FROM users WHERE tenant_id = :tenant_id)
      AND (resource IS NULL OR resource NOT LIKE 'hitl_ticket:%')
    """
)


_ONGEDEFINIEERDE_FUNCTIE = "42883"
_FUNCTIE_ONTBREEKT = (
    "migratie 20261025_audit_anonimiseer_functie ontbreekt: de functie audit_logs_anonimiseer_gebruikers "
    "bestaat niet in deze database, dus het wissen van een klant kan de personen in auditregels van een "
    "andere klant niet anonimiseren"
)
# Dezelfde toelaatlijst als `redaction.EPHEMERAL_KEY_ENVIRONMENTS` (hier herhaald om geen afhankelijkheid op
# tool_broker te krijgen); alles daarbuiten (production, staging, blue, green) krijgt geen terugval.
_TERUGVAL_OMGEVINGEN = frozenset({"development", "test", "local"})


def _terugval_toegestaan() -> bool:
    """Gelezen uit `os.environ` en niet uit settings, net als `audit_chain_key._environment()`; zonder ENVIRONMENT dus GEEN terugval."""
    return os.environ.get("ENVIRONMENT", "").strip().lower() in _TERUGVAL_OMGEVINGEN


_AI_VRIJE_TEKST = text("UPDATE audit_logs SET ai_explanation_summary = NULL WHERE tenant_id = :tenant_id")
_HEEFT_AI_VRIJE_TEKST = text(
    "SELECT 1 FROM information_schema.columns WHERE table_name = 'audit_logs' "
    "AND column_name = 'ai_explanation_summary' AND table_schema = current_schema()"
)


async def anonimiseer_auditlog_van_tenant(db: AsyncSession, tenant_id: int) -> int:
    """Haal de persoonsgegevens uit ALLE auditregels van deze tenant; geeft het aantal regels terug.

    Alleen kolommen buiten de hash; `audit_hash`, `previous_hash`, `tenant_id`, `action`, `resource`
    en `timestamp` blijven zoals ze zijn. Idempotent. `tenant_id` is een gebonden parameter.

    Drie aanvullingen (Gate 2): (1) `ai_explanation_summary` is vrije tekst buiten de hash en staat
    wel in de database maar niet in het model; die wordt gewist waar de kolom bestaat (het model
    leest hem niet, dus de hash-tak verandert er niet door). (2) Regels van een ANDERE tenant of
    zonder tenant die de `user_id` van een persoon uit deze tenant dragen worden ook ontdaan van
    persoonsgegevens, anders blokkeert `audit_logs_user_id_fkey` het verwijderen van die persoon
    (HITL-gebonden regels blijven buiten schot: zonder tenantrij-uitzondering zou hun binding
    breken). (3) `endpoint` blijft staan en is niet uitputtend op persoonsgegevens gemeten.
    """
    resultaat = await db.execute(_ANONIMISEER, {"tenant_id": tenant_id})
    aantal = int(getattr(resultaat, "rowcount", 0) or 0)
    if (await db.execute(_HEEFT_AI_VRIJE_TEKST)).first() is not None:
        await db.execute(_AI_VRIJE_TEKST, {"tenant_id": tenant_id})
    eigen = await db.execute(_EIGEN_GEBRUIKERS, {"tenant_id": tenant_id})
    gebruikers = [int(g) for g in eigen.scalars().all()]
    if gebruikers:
        try:
            async with db.begin_nested():
                await db.execute(
                    _ANONIMISEER_ELDERS, {"tenant_id": tenant_id, "gebruikers": gebruikers}
                )
        except DBAPIError as fout:
            # Alleen "de functie bestaat niet" (SQLSTATE 42883) en alleen in een testomgeving valt terug. Een
            # weigering van de functie zelf (42501, 22023) en elke andere fout gaat omhoog; nooit op de TEKST
            # van de fout beslissen: die bevat de eigen SQL en dus altijd de functienaam (Gate 2 G2F-1).
            if getattr(fout.orig, "sqlstate", None) != _ONGEDEFINIEERDE_FUNCTIE:
                raise
            if not _terugval_toegestaan():
                raise RuntimeError(_FUNCTIE_ONTBREEKT) from fout
            await db.execute(_ANONIMISEER_ELDERS_DIRECT, {"tenant_id": tenant_id})
    await _anonimiseer_verzoeklog(db, tenant_id)
    return aantal


_HEEFT_VERZOEKLOG = text(
    "SELECT 1 FROM information_schema.tables WHERE table_name = 'request_audit_logs' "
    "AND table_schema = current_schema()"
)
_ANONIMISEER_VERZOEKLOG = text(
    "UPDATE request_audit_logs SET user_id = NULL, user_email = NULL, ip_address = NULL, "
    "user_agent = NULL, query_params = NULL, changes = NULL, "
    "path = regexp_replace(path, :email_patroon, :plaatshouder, 'g') "
    "WHERE tenant_id = :tenant_id"
)


async def _anonimiseer_verzoeklog(db: AsyncSession, tenant_id: int) -> None:
    """`request_audit_logs` (de verzoeklog van de middleware) staat los van het hash-auditlog.

    Gemeten 2026-10-12: die tabel draagt `user_email`, `ip_address`, `user_agent`, `query_params`
    en `changes` per tenant (`tenant_id` als TEKST, zonder vreemde sleutel) en werd bij een harde
    wissing niet geraakt. De regels blijven (verkeersgegevens zonder persoon), de persoonsvelden
    verdwijnen en een e-mailadres in het pad wordt vervangen.
    """
    if (await db.execute(_HEEFT_VERZOEKLOG)).first() is None:
        return
    await db.execute(
        _ANONIMISEER_VERZOEKLOG,
        {
            "tenant_id": str(tenant_id),
            "email_patroon": _EMAIL.pattern,
            "plaatshouder": E_MAIL_PLAATSHOUDER,
        },
    )


# De 15 andere tabellen met een vreemde sleutel naar `tenants` zonder ON DELETE (gemeten 2026-10-12
# met pg_constraint; `audit_logs` is de zestiende en wordt bewaard). Kinderen voor ouders. Het zijn
# gegevens van de op te heffen tenant zelf: de harde wissing belooft permanente verwijdering, dus
# verwijderen, niet anonimiseren. Bewaartermijnen per tabel zijn NIET gemeten; wie voor een van deze
# soorten een wettelijke bewaarplicht kent (bv. meldingen van AI-incidenten) moet dat hier aanpassen.
TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN = (
    "officer_verdicts",
    "decision_contests",
    "council_decisions",
    "workflow_change_logs",
    "workflow_versions",
    "governance_accuracy_metrics",
    "governance_alerts",
    "governance_quality_checks",
    "governance_risk_entries",
    "model_provenance_records",
    "personas",
    "registered_agents",
    "flows",
)

# Tabellen met een persoonsverwijzing zonder ON DELETE naar `users` (NOT NULL of persoonlijk), per
# tenant op te ruimen voor de gebruikers weggaan.
TENANT_TABELLEN_MET_PERSOONSVERWIJZING = (
    "email_campaigns",
    "focus_builder_flows",
    "hitl_tickets",
)


async def ruim_tenant_blokkades_op(db: AsyncSession, tenant_id: int) -> None:
    """Verwijder wat de tenantrij of zijn gebruikers vasthoudt, behalve het (geanonimiseerde) auditlog."""
    for naam in TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN:
        tabel = table(naam, column("tenant_id"))
        await db.execute(delete(tabel).where(tabel.c.tenant_id == tenant_id))
    for naam in TENANT_TABELLEN_MET_PERSOONSVERWIJZING:
        tabel = table(naam, column("tenant_id"))
        await db.execute(delete(tabel).where(tabel.c.tenant_id == tenant_id))
    # Zonder tenant_id-kolom: via de gebruikers van deze tenant.
    await db.execute(
        text(
            "DELETE FROM two_factor_auth WHERE user_id IN "
            "(SELECT id FROM users WHERE tenant_id = :tid)"
        ),
        {"tid": tenant_id},
    )
    await db.execute(
        text(
            "UPDATE token_blacklist SET revoked_by = NULL WHERE revoked_by IN "
            "(SELECT id FROM users WHERE tenant_id = :tid)"
        ),
        {"tid": tenant_id},
    )


# Bewaard, niet verwijderd (besluit regie 2026-10-12): meldingen van AI-incidenten en rapporten aan een
# toezichthouder kunnen onder een bewaarplicht vallen die niet is gemeten. Daarom net als het
# auditlog bewaren zonder persoonsgegevens. Beide tabellen hebben (sinds de migratie) geen vreemde
# sleutel naar `tenants` meer.
TENANT_TABELLEN_BEWAARD_EN_GEANONIMISEERD = (
    "ai_act_incident_reports",
    "governance_authority_reports",
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
E_MAIL_PLAATSHOUDER = "[e-mail verwijderd]"
IP_PLAATSHOUDER = "[ip verwijderd]"


def scrub_tekst(waarde: str) -> str:
    """Haal e-mailadressen en IPv4-adressen uit een tekst. Namen zijn NIET te herkennen."""
    return _IPV4.sub(IP_PLAATSHOUDER, _EMAIL.sub(E_MAIL_PLAATSHOUDER, waarde))


def scrub_json(waarde: object) -> object:
    """Dezelfde scrub over alle tekstwaarden en sleutels van een JSON-structuur (recursief)."""
    if isinstance(waarde, str):
        return scrub_tekst(waarde)
    if isinstance(waarde, list):
        return [scrub_json(x) for x in waarde]
    if isinstance(waarde, dict):
        return {scrub_tekst(str(k)): scrub_json(v) for k, v in waarde.items()}
    return waarde


async def anonimiseer_bewaarde_rapporten_van_tenant(db: AsyncSession, tenant_id: int) -> int:
    """Anonimiseer (verwijder NIET) de AI-incidentmeldingen en toezichthouder-rapporten van de tenant.

    Wat verdwijnt: e-mail- en IP-adressen in de vrije tekst (`description`, `incident_data`,
    `content`) en de persoonsverwijzing `created_by_user_id`. Wat blijft: type, ernst, tijden,
    agentgegevens en de rest van de inhoud, want dat is het bewijs. LET OP: namen van personen in
    vrije tekst worden niet herkend; wie die in deze velden verwacht moet een zwaardere scrub kiezen.
    """
    gewijzigd = 0
    meldingen = await db.execute(
        text(
            "SELECT id, description, incident_data FROM ai_act_incident_reports "
            "WHERE tenant_id = :t"
        ),
        {"t": tenant_id},
    )
    for rij_id, omschrijving, data in meldingen.all():
        await db.execute(
            text(
                "UPDATE ai_act_incident_reports SET description = :d, "
                "incident_data = CAST(:j AS jsonb) WHERE id = :i"
            ),
            {
                "d": scrub_tekst(omschrijving or ""),
                "j": json.dumps(scrub_json(data)) if data is not None else None,
                "i": rij_id,
            },
        )
        gewijzigd += 1
    rapporten = await db.execute(
        text("SELECT id, content FROM governance_authority_reports WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    for rij_id, inhoud in rapporten.all():
        await db.execute(
            text(
                "UPDATE governance_authority_reports SET content = CAST(:j AS jsonb), "
                "created_by_user_id = NULL WHERE id = :i"
            ),
            {"j": json.dumps(scrub_json(inhoud)), "i": rij_id},
        )
        gewijzigd += 1
    # Ook rapporten van een ANDERE tenant die naar een persoon van deze tenant verwijzen.
    await db.execute(
        text(
            "UPDATE governance_authority_reports SET created_by_user_id = NULL "
            "WHERE created_by_user_id IN (SELECT id FROM users WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    return gewijzigd
