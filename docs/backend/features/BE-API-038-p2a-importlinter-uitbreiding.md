# BE-API-038 -- P2a Import-linter Contract 1 Uitbreiding (*_router.py coverage)

Sprint: SP-API-010 Dag 1
Datum: 2026-06-11
Categorie: architecture / quality (DEFERRED -- stop-conditie getriggerd)
Status: BACKLOG

---

## Samenvatting

P2a scan uitgevoerd op alle `*_router.py` bestanden in `src/core/api/v1/` om te bepalen of
import-linter Contract 1 uitgebreid kan worden naar deze bestanden.

---

## Scan-resultaten (2026-06-11)

- Totaal gescande kandidaten: 148 bestanden
- Clean (0 violations): 104 bestanden
- Met violations: 44 bestanden, >50 violations totaal

Stop-conditie getriggerd per dag 1 brief: `> 20 violations totaal = STOP`.

---

## Violations per domein (top-level overzicht)

| Domein | Bestanden met violations | Soort violation |
|--------|--------------------------|-----------------|
| activepieces | 4 | governance.rate_limiter |
| admin | 2 | database.database, governance.models |
| agentic | 2 | agents.*, database.database, learning.* |
| agents | 1 | agents.models |
| ai_act | 1 | governance.incident_service |
| als | 2 | database.database |
| company | 5 | database.database, governance.policy_engine |
| copilot_intent | 1 | database.database |
| cva | 5 | agents.*, database.* |
| documents | 3 | governance.audit |
| experimentation | 1 | database.database |
| feature_flags | 1 | database.tenant_query_filter |
| focus_builder | 1 | agents.focus_builder_* |
| gatekeeper | 1 | governance.models |
| governance | 2 | governance.alert_manager, accuracy_monitor, risk_register, quality, authority |
| health | 1 | database.database |
| knowledge | 1 | agents.agent_registry |
| models | 1 | learning.model_registry |
| privacy | 4 | governance.models, ai_transparency_service, cookie_consent, database.models |
| tenant_management | 1 | database.database, tenant_query_filter, governance.audit |
| tenants | 1 | agents.models, governance.models |
| user_management | 2 | database.database, tenant_query_filter, governance.audit |

---

## Backlog

Architecture test aangemaakt: `tests/architecture/test_sp_api_010_backlog.py::test_star_router_files_have_no_forbidden_imports`

Fix-strategie per violation: verboden imports verplaatsen naar `<domein>/dependencies.py` (ADR-033 §2).
Daarna: alle 148 `*_router.py` bestanden + `agency_capabilities.py` + `learning.py` toevoegen
aan Contract 1 `source_modules`.

Verwachte effort: meerdere sprint-dagen (sprint SP-API-011 of later).

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
