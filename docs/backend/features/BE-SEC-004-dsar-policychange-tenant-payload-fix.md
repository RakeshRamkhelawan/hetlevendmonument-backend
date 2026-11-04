# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-004
- Feature naam: DSAR/PolicyChange tenant_id payload security fix (B-005)
- Status: APPROVED
- Auteur: Claude Sonnet 4.6
- Reviewer: code-reviewer + quality-reviewer subagents
- Datum: 2026-05-30
- Gerelateerde user story / ticket: MASTER-AUDIT-COMPLEET.md B-005; CLAUDE.md sec 6.1
- Gerelateerde router / module: `src/core/copilot/proactive/monitors/`
- Gerelateerde frontend endpoints: geen (interne event bus)
- Gerelateerde database tabellen: geen directe writes (via Council)
- Versie: 1.0

---

## Doel en scope

### Doel

Verwijder CLAUDE.md sec 6.1 overtreding in twee event-driven proactive monitors.
`DSARExportMonitor` en `PolicyChangeMonitor` lazen eerder `tenant_id` direct uit de
user-controlled event payload. Een aanvaller die de event bus kon berichten sturen
kon zo een willekeurige `tenant_id` injecteren en de monitor op data van een andere tenant
laten werken.

### In scope

- `DSARExportMonitor._on_export_initiated()`: verwijder `payload.get("tenant_id")`, vervang door `TenantRepo.get_tenant_id_for_user(user_id)`
- `PolicyChangeMonitor._on_config_updated()`: verwijder `payload.get("tenant_id")`, vervang door `TenantRepo.get_tenant_id_for_workflow(workflow_id)`
- `TenantRepo` protocol: uitbreiden met twee nieuwe methoden
- Bestaande `FakeTenantRepo` implementaties in unit tests bijwerken

### Out of scope

- Concrete `TenantRepo` implementatie buiten tests (productie wire-up via DI)
- Andere event-driven monitors (geen B-005 bevinding)

---

## Build summary

- Nieuw gebouwd: `TenantRepo.get_tenant_id_for_user()` en `get_tenant_id_for_workflow()` (protocol-methoden)
- Gewijzigd:
  - `src/core/copilot/proactive/monitors/protocols.py` (TenantRepo protocol uitgebreid)
  - `src/core/copilot/proactive/monitors/dsar_export.py` (payload-read vervangen)
  - `src/core/copilot/proactive/monitors/policy_change.py` (payload-read vervangen)
  - `tests/unit/copilot/proactive/monitors/test_dsar_export.py` (FakeTenantRepo bijgewerkt)
  - `tests/unit/copilot/proactive/monitors/test_policy_change.py` (FakeTenantRepo bijgewerkt)
- Verwijderd: `tenant_id = payload.get("tenant_id")` uit beide monitors
- Beinvloede bestaande flows: DSAR export alerting; workflow policy change alerting

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-004a | TenantRepo.get_tenant_id_for_user | Protocol methode | `src/core/copilot/proactive/monitors/protocols.py` | Nieuw | DSAR export monitor flow |
| BE-SEC-004b | TenantRepo.get_tenant_id_for_workflow | Protocol methode | `src/core/copilot/proactive/monitors/protocols.py` | Nieuw | Policy change monitor flow |
| BE-SEC-004c | DSARExportMonitor._on_export_initiated | Event handler fix | `src/core/copilot/proactive/monitors/dsar_export.py` | Wijziging | DSAR export monitor flow |
| BE-SEC-004d | PolicyChangeMonitor._on_config_updated | Event handler fix | `src/core/copilot/proactive/monitors/policy_change.py` | Wijziging | Policy change monitor flow |

---

## API-flows

### Flow 1: DSAR export monitor (na fix)

- Naam: DSAR export tenant-safe signal generation
- Trigger: event `dsar.export_initiated` op interne event bus
- Voorwaarden: payload bevat `user_id: int`, `export_type: str`, `contains_pii: bool`
- Request-pad: event bus publish -> `DSARExportMonitor._on_export_initiated(payload)`
- Service-stappen:
  1. Lees `user_id` uit payload; valideer `isinstance(user_id, int)`
  2. `tenant_id = await self._tenant_repo.get_tenant_id_for_user(user_id)` — server-side lookup
  3. Als `tenant_id is None`: log warning + return (onbekende user, event geweigerd)
  4. Valideer `export_type` (str, max 64 chars)
  5. Check `contains_pii is True`; anders return
  6. Dedup check via Redis
  7. Haal admin user op via `get_primary_admin_user_id(tenant_id)`
  8. Maak `Signal` aan met server-side `tenant_id`
  9. `propose_to_council(signal)`
- DB-operaties: geen directe DB-toegang (via TenantRepo)
- Successtatus: Signal aangemaakt en voorgelegd aan Council
- Foutpaden:
  - Ongeldige `user_id`: `logger.warning` + return
  - Onbekende `user_id` (tenant niet gevonden): `logger.warning` + return
  - Ongeldige `export_type`: `logger.warning` + return
  - `contains_pii` is False: stille return
  - TenantRepo fout: `logger.error` + return
- Eindtoestand: geen DB-wijziging in de monitor zelf; Council beslist over actie

### Flow 2: Policy change monitor (na fix)

- Naam: Policy change tenant-safe signal generation
- Trigger: event `workflow.config_updated` op interne event bus
- Voorwaarden: payload bevat `workflow_id: str|int`, `workflow_name: str`, `has_pii_fields: bool`
- Request-pad: event bus publish -> `PolicyChangeMonitor._on_config_updated(payload)`
- Service-stappen:
  1. Lees `workflow_id` uit payload; valideer aanwezig + `isinstance(workflow_id, (str, int))`
  2. Valideer `workflow_name` (str, max 128 chars)
  3. `tenant_id = await self._tenant_repo.get_tenant_id_for_workflow(workflow_id)` — server-side lookup
  4. Als `tenant_id is None`: log warning + return
  5. Check `has_pii_fields is True`; anders return
  6. Dedup check via Redis
  7. Haal admin user op via `get_primary_admin_user_id(tenant_id)`
  8. Maak `Signal` aan met server-side `tenant_id`
  9. `propose_to_council(signal)`
- DB-operaties: geen directe DB-toegang
- Successtatus: Signal aangemaakt
- Foutpaden: identiek patroon als Flow 1
- Eindtoestand: geen DB-wijziging in de monitor

---

## Detaildocumentatie per artefact

---

## [BE-SEC-004a] TenantRepo.get_tenant_id_for_user

### 1. Type

- Protocol methode

### 2. Locatie

- Bestandspad: `src/core/copilot/proactive/monitors/protocols.py`
- Klasse / functie: `TenantRepo.get_tenant_id_for_user`

### 3. Gerelateerde flow

- DSAR export monitor flow

### 4. Doel

Server-side opzoeken van `tenant_id` op basis van `user_id`, zodat event-handlers niet hoeven te
vertrouwen op een user-controlled payload waarde.

### 5. Functionele beschrijving

Gegeven een `user_id` retourneert de methode de `tenant_id` van de tenant die eigenaar is van die
gebruiker. Retourneert `None` als de gebruiker niet bestaat (onbekend of verwijderd).

### 6. Technische beschrijving

- Protocol-methode: elke concrete implementatie moet deze methode bieden
- Handtekening: `async def get_tenant_id_for_user(self, user_id: int) -> int | None`
- Typisch: `SELECT tenant_id FROM users WHERE id = :user_id LIMIT 1`

### 7. Zichtbaarheids- en toegangsregels

- Intern gebruik (event handlers)
- Geen directe HTTP exposure

### 8. Request-specificatie

- `user_id: int` — de gebruiker waarvoor de tenant wordt opgezocht

### 9. Response-specificatie

- `int`: tenant_id bij bekende gebruiker
- `None`: gebruiker niet gevonden

### 10. Validaties en constraints

- `user_id` moet een positief integer zijn (caller verantwoordelijk)

### 11. Business rules

- Return `None` bij onbekende user, nooit een fallback-tenant
- Geen cross-tenant lekkage

### 12. Afhankelijkheden

- Concrete implementatie vereist injectie van DB-sessie of user-repository

### 13. Foutafhandeling

- Database fouten propageren naar caller

### 14. Transacties en dataïntegriteit

- Read-only

### 15. Telemetry / logging / tracing

- Caller logt bij `None` return

### 16. Caching

- Eventueel cacheable (short TTL); geen vereiste in protocol

### 17. Acceptatiecriteria

- Bekende `user_id` retourneert de juiste `tenant_id`
- Onbekende `user_id` retourneert `None`
- Geen cross-tenant resultaten

### 18. Integratoruitleg

- Gebruik bij event handlers die `user_id` ontvangen uit een externe bron
- Weigeringslogica: als `None`, log en return

### 19. Trainingssamenvatting

- Actor: event handler
- Voorwaarde: payload met user_id ontvangen
- Actie: `await tenant_repo.get_tenant_id_for_user(user_id)`
- Systeemverwerking: DB lookup op users tabel
- Succesrespons: `int` tenant_id
- Foutrespons: `None` bij onbekende user
- Uitzonderingen: DB fout propagateert

---

## [BE-SEC-004b] TenantRepo.get_tenant_id_for_workflow

### 1. Type

- Protocol methode

### 2. Locatie

- Bestandspad: `src/core/copilot/proactive/monitors/protocols.py`
- Klasse / functie: `TenantRepo.get_tenant_id_for_workflow`

### 3. Gerelateerde flow

- Policy change monitor flow

### 4. Doel

Server-side opzoeken van `tenant_id` op basis van `workflow_id`.

### 5. Functionele beschrijving

Gegeven een `workflow_id` retourneert de methode de `tenant_id` die eigenaar is van die workflow.
Retourneert `None` als de workflow niet bestaat.

### 6. Technische beschrijving

- Handtekening: `async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None`
- Typisch: `SELECT tenant_id FROM workflows WHERE id = :workflow_id LIMIT 1`
- `workflow_id` kan `str` of `int` zijn (beide formaten komen voor in event payloads)

### 7-19. (identiek patroon aan BE-SEC-004a, met workflow_id i.p.v. user_id)

- Acceptatiecriteria: bekende workflow_id retourneert tenant_id; onbekende retourneert None
- Trainingssamenvatting identiek aan BE-SEC-004a maar voor workflow context

---

## [BE-SEC-004c] DSARExportMonitor._on_export_initiated (na fix)

### 1. Type

- Event handler fix

### 2. Locatie

- Bestandspad: `src/core/copilot/proactive/monitors/dsar_export.py`
- Klasse / functie: `DSARExportMonitor._on_export_initiated`

### 17. Acceptatiecriteria

- `payload.get("tenant_id")` komt NIET voor in de source
- `get_tenant_id_for_user` wordt aangeroepen voor tenant resolution
- Event met onbekende `user_id` (tenant None): logger.warning + geen Signal aangemaakt
- Event met bekende `user_id`: Signal aangemaakt met server-side `tenant_id`
- `isinstance(tenant_id, int)` check op payload-waarde is verwijderd

### 19. Trainingssamenvatting

- Actor: interne event bus (publiceert `dsar.export_initiated`)
- Voorwaarde: payload met `user_id: int`, `export_type: str`, `contains_pii: bool`
- Actie: event bus publish
- Systeemverwerking: user_id -> tenant lookup -> Signal aanmaken -> Council
- Succesrespons: Signal aangemaakt en voorgelegd aan Council
- Foutrespons: logger.warning + return bij onbekende user of ongeldige payload
- Uitzonderingen: TenantRepo fout: logger.error + return

---

## [BE-SEC-004d] PolicyChangeMonitor._on_config_updated (na fix)

### 1. Type

- Event handler fix

### 2. Locatie

- Bestandspad: `src/core/copilot/proactive/monitors/policy_change.py`
- Klasse / functie: `PolicyChangeMonitor._on_config_updated`

### 17. Acceptatiecriteria

- `payload.get("tenant_id")` komt NIET voor in de source
- `get_tenant_id_for_workflow` wordt aangeroepen voor tenant resolution
- Event met onbekende `workflow_id` (tenant None): logger.warning + geen Signal aangemaakt
- Event met bekende `workflow_id`: Signal aangemaakt met server-side `tenant_id`

### 19. Trainingssamenvatting

- Actor: interne event bus (publiceert `workflow.config_updated`)
- Voorwaarde: payload met `workflow_id`, `workflow_name`, `has_pii_fields`
- Actie: event bus publish
- Systeemverwerking: workflow_id -> tenant lookup -> Signal aanmaken -> Council
- Succesrespons: Signal aangemaakt
- Foutrespons: logger.warning + return bij onbekende workflow
- Uitzonderingen: TenantRepo fout: logger.error + return

---

## Integratorhandleiding

### Voor event publishers

- Zorg dat events een valide `user_id` (DSAR) of `workflow_id` (PolicyChange) bevatten
- `tenant_id` in de payload wordt genegeerd — verwijder het of laat het weg
- Event wordt geweigerd als de `user_id` / `workflow_id` niet herkend wordt door TenantRepo

### Voor TenantRepo implementators

- Implementeer `get_tenant_id_for_user(user_id: int) -> int | None`
- Implementeer `get_tenant_id_for_workflow(workflow_id: str | int) -> int | None`
- Return `None` (niet een fallback tenant) bij onbekende IDs

---

## Open aannames

- Concrete TenantRepo implementaties worden via DI geleverd; de protocol-definitie is de enige vereiste hier
- Event bus is intern (niet publiek bereikbaar); het security-risico is lager dan bij HTTP webhooks, maar het principe van CLAUDE.md sec 6.1 geldt ook intern

## Open vragen

- Geen

## Risico's

- Productie-implementaties van TenantRepo moeten de twee nieuwe methoden implementeren; dit is een breaking change voor bestaande concrete klassen
- Als een concrete implementatie `None` retourneert voor alle workflows (bijv. mis-configuratie), worden geen policy change signals gegenereerd — monitoring hierop aanbevolen

---

## QA-checks

- [x] Event handlers functioneel getest (happy path: 10 unit tests SP-S01 + 20 monitor tests)
- [x] Fout-case: onbekende user_id -> geen signal
- [x] Fout-case: onbekende workflow_id -> geen signal
- [x] Tenant-isolatie: geen payload.get("tenant_id") in source
- [x] FakeTenantRepo bijgewerkt in beide testbestanden
- [x] Validaties: isinstance-check op user_id/workflow_id blijft aanwezig

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review: zie `docs/backend/review/review-BE-SEC-004.md`
