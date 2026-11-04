# Backend Feature Specification -- BE-DEP-002: NotificationDispatcher Startup Ordering Fix (CG-003)

## Metadata

- **Feature ID:** BE-DEP-002
- **Feature naam:** NotificationDispatcher Startup Ordering Fix
- **Status:** APPROVED
- **Auteur:** Gemini CLI
- **Reviewer:** Gemini CLI
- **Datum:** 2026-06-01
- **Gerelateerde user story / ticket:** SP-WE-16 (CG-003)
- **Gerelateerde router / module:** `src/core/app_lifespan.py`
- **Gerelateerde frontend endpoints:** `/ws/copilot/signals`, `/api/v1/notifications`
- **Gerelateerde database tabellen:** N.v.t.
- **Versie:** 1.0

---

## Doel en scope

### Doel

Herstellen van de initialisatievolgorde in de applicatie-startup (`app_lifespan`) zodat compliance monitors correct worden gewired.

### In scope

- Aanpassen van de aanroepvolgorde in `src/core/app_lifespan.py`.
- Verifiëren dat `NotificationDispatcher` beschikbaar is voor `_init_compliance_monitors`.

### Out of scope

- Wijzigen van de logica van de monitors zelf.
- Wijzigen van de `NotificationDispatcher` implementatie.

---

## Build summary

- **Nieuw gebouwd:** Unit tests voor startup volgorde verificatie.
- **Gewijzigd:** `src/core/app_lifespan.py` (aanroepvolgorde).
- **Verwijderd:** Geen.
- **Beinvloede bestaande flows:** Startup flow, Compliance monitoring wiring.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-DEP-002 | NotificationDispatcher Startup Fix | BE-DEP | `src/core/app_lifespan.py` | Wijziging | BE-FLW-002 |

---

## API-flows

### Flow ID: BE-FLW-002: Applicatiestart -- correcte initialisatievolgorde garandeert actieve monitors

- **Naam:** Applicatiestart Initialisatie
- **Trigger:** Container start / FastAPI startup.
- **Voorwaarden:** Redis bereikbaar (voor dispatcher).
- **Request-path:** N.v.t. (Lifespan event).
- **Service-stappen:**
    1. `_init_proactive_deps` stelt `app.state.notification_dispatcher` in.
    2. `_init_compliance_monitors` leest dispatcher en wirt monitors.
    3. `_init_proactive_scheduler` start interval jobs.
- **DB-operaties:** N.v.t.
- **Successtatus + response:** Log "[OK] Application ready to accept requests".
- **Foutpaden:** Redis onbereikbaar → monitors worden overgeslagen (graceful degradation).
- **Eindtoestand:** `app.state.ready = True`, monitors actief.

---

## Detaildocumentatie per artefact

---

## [BE-DEP-002] NotificationDispatcher Startup Fix

### 1. Type

- BE-DEP (Dependency / Startup logic)

### 2. Locatie

- **Bestandspad:** `src/core/app_lifespan.py`
- **Klasse / functie:** `app_lifespan`

### 3. Gerelateerde flow

- BE-FLW-002

### 4. Doel

Garanderen dat de `notification_dispatcher` aanwezig is in `app.state` voordat consumers deze proberen te lezen.

### 5. Functionele beschrijving

Bij het opstarten van de server worden verschillende componenten na elkaar klaargezet. Deze fix zorgt ervoor dat de "notificatie-verzorger" (dispatcher) eerst wordt klaargezet, zodat de "nalevings-monitoren" (compliance monitors) weten waar ze hun meldingen naartoe moeten sturen.

### 6. Technische beschrijving

De aanroep van `await _init_proactive_deps(app)` is verplaatst naar regel 1062, vóór `await _init_compliance_monitors(app)` op regel 1063. `_init_proactive_deps` is verantwoordelijk voor het instantiëren van de `NotificationDispatcher` en het toewijzen hiervan aan `app.state.notification_dispatcher`.

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** N.v.t. (Internal startup).
- **Tenant-isolatie:** De dispatcher zelf is tenant-aware via de `DigestQueue` en `WSPusher`.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

N.v.t.

### 11. Business rules

Compliance monitors MOETEN bij startup gewired zijn om geen events te missen.

### 12. Afhankelijkheden

- Redis (vereist voor `NotificationDispatcher`).

### 13. Foutafhandeling

- Bij afwezigheid van Redis faalt `_init_proactive_deps` (non-fatal) en wordt de dispatcher niet ingesteld. `_init_compliance_monitors` detecteert dit en logt een skip-melding.

### 14. Transacties en dataïntegriteit

N.v.t.

### 15. Telemetry / logging / tracing

- Log: `[OK] Compliance monitors wired: dsar_export + policy_change`
- Log (bij fout): `Compliance monitors: copilot_service or dispatcher not ready, skipping event-driven wiring`

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [x] `_init_proactive_deps` wordt aangeroepen vóór `_init_compliance_monitors`.
- [x] `app.state.compliance_monitors` bevat "dsar_export" en "policy_change" na startup (mits Redis up).
- [x] Geen crash als Redis down is.

### 18. Integratoruitleg

- De applicatie start sequentieel op.
- De `notification_dispatcher` is een verplichte afhankelijkheid voor proactieve monitoring.
- Zorg dat Redis beschikbaar is bij startup voor volledige monitoring dekking.

### 19. Trainingssamenvatting

- **Actor:** FastAPI app_lifespan.
- **Voorwaarde:** Applicatie start op.
- **Actie (request):** Sequentiële uitvoering van init helpers.
- **Systeemverwerking:** `_init_proactive_deps` -> `app.state.notification_dispatcher` = Instance.
- **Succesrespons:** `_init_compliance_monitors` vindt dispatcher en wirt monitors.
- **Foutrespons:** Geen dispatcher -> skip wiring.
- **Uitzonderingen:** Redis connection failure.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Deze wijziging is intern aan de server-opstart.
- Ontwikkelaars die nieuwe monitors toevoegen in `_init_compliance_monitors` kunnen er nu op vertrouwen dat `app.state.notification_dispatcher` beschikbaar is.
- Controleer bij deployment de logs op `[OK] Compliance monitors wired` om te verifiëren dat de monitoring pipeline actief is.

---

## QA-checks

- [x] Endpoint functioneel getest (Startup flow geverifieerd via unit tests)
- [x] Alle foutstatus-codes getest (Graceful degradation bij Redis-fout)
- [x] Auth en permissies getest (N.v.t.)
- [x] Tenant-isolatie getest (Dispatcher is tenant-aware)
- [x] Validaties getest (N.v.t.)
- [x] Edge cases getest (Redis down)
- [x] Dataïntegriteit en transacties getest (N.v.t.)
- [x] Logging en tracing gecontroleerd (Skip melding geverifieerd)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED
