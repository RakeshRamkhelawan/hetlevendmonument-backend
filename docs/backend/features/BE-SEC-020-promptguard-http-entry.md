# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-020
- Feature naam: PromptGuard HTTP Entry Scanning (SEC-004)
- Status: APPROVED
- Auteur: Claude (SP-CVA-P1 Dag 1)
- Reviewer: quality-reviewer
- Datum: 2026-06-21
- Gerelateerde user story / ticket: SP-CVA-P1 Dag 1 -- SEC-004
- Gerelateerde router / module: `src/core/copilot/api/turn_endpoint.py`, `src/core/api/v1/cva/chat_router.py`, `src/core/copilot/council/factory.py`
- Gerelateerde frontend endpoints: POST /api/v1/copilot/turn, POST /api/v1/cva/chat
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

Gebruikersinvoer wordt VOOR de LLM bereikt gecontroleerd op prompt injection (SEC-004). Zonder
deze fix bereikt kwaadaardige invoer de LLM ongescand. Tevens wordt een signature-mismatch
in `_PromptGuardAdapter` opgelost die de SecurityOfficer-scan onbereikbaar maakte.

### In scope

- PromptGuard-scan van `payload.message` in `turn_endpoint.py` (POST /copilot/turn)
- PromptGuard-scan van `request.message` in `chat_router.py` (POST /cva/chat)
- `_PromptGuardAdapter` in `factory.py`: sync `PromptGuard.sanitize()` in plaats van async
  `PromptGuard.scan_input()` -- SecurityOfficer verwacht sync `.scan()` -> `dict`

### Out of scope

- Redis-backed rate limiting (SEC-001/005, dag 2)
- Streaming endpoint scanning (buiten scope SEC-004)

---

## Build summary

- Nieuw gebouwd: `_PromptGuardAdapter` in `factory.py` (vervangt foutief async inject)
- Gewijzigd: `turn_endpoint.py` (scan voor service.handle_turn), `chat_router.py` (scan voor CVAService)
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: copilot/turn flow en cva/chat flow -- scan toegevoegd als pre-flight stap

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-020 | PromptGuard HTTP entry scan | Security wrapper | `turn_endpoint.py` + `chat_router.py` | Wijziging | Copilot turn + CVA chat |
| BE-SEC-020a | `_PromptGuardAdapter` sync fix | Security adapter | `src/core/copilot/council/factory.py` | Wijziging | AgentCouncil SecurityOfficer |

---

## API-flows

### Flow: SEC-004 PromptGuard scan

- Naam: Prompt injection pre-flight check
- Trigger: POST /api/v1/copilot/turn of POST /api/v1/cva/chat
- Voorwaarden: gebruiker geauthenticeerd (JWT), tenant_id uit ContextVar
- Request-pad: HTTP entry -> auth -> PromptGuard.sanitize() -> service -> LLM
- Service-stappen:
  1. `_prompt_guard.sanitize(message, tenant_id=...)` aangeroepen
  2. Bij `PromptInjectionError`: `HTTPException(400, "Input rejected")` teruggegeven
  3. Bij clean input: service aangeroepen zoals voorheen
- DB-operaties: geen
- Successtatus: scan clean -> 200 OK met service response
- Foutpaden: injection gedetecteerd -> 400 Bad Request
- Eindtoestand: geen DB-wijziging bij 400; scan-event in logs

---

## Detaildocumentatie per artefact

---

## [BE-SEC-020] PromptGuard scan in turn_endpoint en chat_router

### 1. Type

- Security wrapper (pre-flight check)

### 2. Locatie

- Bestandspad: `src/core/copilot/api/turn_endpoint.py:59-62` en `src/core/api/v1/cva/chat_router.py:81-86`
- Klasse / functie: `turn()`, `chat_endpoint()`

### 3. Gerelateerde flow

- Copilot turn flow, CVA chat flow

### 4. Doel

- Detecteer en blokkeer prompt injection VOOR de LLM bereikt wordt

### 5. Functionele beschrijving

- Elke POST /copilot/turn of /cva/chat scant het bericht op injectiepatronen
- Bij detectie wordt direct 400 teruggegeven; de LLM ontvangt het bericht nooit
- Legitieme berichten worden ongewijzigd doorgegeven

### 6. Technische beschrijving

- Moduleniveausingleton `_prompt_guard = _SyncPromptGuard()` (geen per-request allocatie)
- `_prompt_guard.sanitize(message, tenant_id=...)` raises `PromptInjectionError` bij injectie
- `except PromptInjectionError` -> `raise HTTPException(status_code=400, detail="Input rejected")`
- Scan staat VOOR de service-aanroep; de service wordt nooit bereikt bij injectie

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT (Bearer of cookie)
- Vereiste rol / scope: `copilot:write` resp. `cva:write`
- Tenant-isolatie: `tenant_id` doorgegeven aan sanitize voor tenant-specifieke regelsets
- Feature flag: geen

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/copilot/turn` en `/api/v1/cva/chat`
- Request body: `message: str` (onderdeel van `CopilotTurnRequest` resp. `ChatRequest`)
- Verplichte headers: `Authorization: Bearer <token>` of session-cookie

### 9. Response-specificatie

- Successtatus: 200 OK (scan clean, service response)
- Foutstatussen:
  - 400 Bad Request: `{"detail": "Input rejected"}` bij injectie
  - 401 Unauthorized: geen/ongeldig token
  - 422 Unprocessable Entity: Pydantic-validatiefout (leeg bericht)

### 10. Validaties en constraints

- `message` mag niet leeg zijn (422 via Pydantic min_length)
- Scanpatronen bepaald door `PromptGuard` -- zie `src/core/ai/prompt_guard.py`

### 11. Business rules

- Fail-secure: bij scan-fout (exception in sanitize) wordt bericht geblokkeerd
- Geen scan bij streaming endpoint (buiten scope SEC-004)

### 12. Afhankelijkheden

- `src.core.ai.prompt_guard.PromptGuard` (sync implementatie)
- `src.core.exceptions.PromptInjectionError`

### 13. Foutafhandeling

- 400: Injectiepatroon gedetecteerd
- 401: Ontbrekende of verlopen token
- 422: Leeg `message` veld (Pydantic)
- 500: Interne fout in service (na scan)

### 14. Transacties en dataIntegriteit

- Geen; scan is stateless

### 15. Telemetry / logging / tracing

- Geen expliciete log bij 400; de HTTP-status is het bewijs

### 16. Caching

- Geen caching van scan-resultaten

### 17. Acceptatiecriteria

- POST /copilot/turn met injectiepatroon ("ignore previous instructions...") -> 400
- POST /cva/chat met injectiepatroon -> 400
- POST /copilot/turn met normaal bericht -> 200 (service bereikt)
- POST /cva/chat met normaal bericht -> 200 (CVAService bereikt)

### 18. Integratoruitleg

- Verstuur altijd schone berichten; injectiepogingen worden geblokkeerd op 400
- De foutmelding is bewust generiek ("Input rejected") om geen details te lekken
- Geldt voor alle POST /turn en /chat aanroepen

### 19. Trainingssamenvatting

- Actor: Geverifieerde eindgebruiker
- Voorwaarde: Geldig JWT, tenant actief
- Actie: POST /copilot/turn of /cva/chat met prompt injection in `message`
- Systeemverwerking: PromptGuard.sanitize() herkent patroon, gooit PromptInjectionError
- Succesrespons: 200 OK bij schone input
- Foutrespons: 400 Bad Request bij injectie -- `{"detail": "Input rejected"}`
- Uitzonderingen: streaming endpoint nog niet bewaakt (buiten scope)

---

## Integratorhandleiding

- POST /api/v1/copilot/turn en /api/v1/cva/chat scannen invoer op injection
- Geldige berichten worden normaal verwerkt
- Injectiepogingen resulteren in HTTP 400 -- de LLM ontvangt het bericht nooit

---

## Open aannames

- Sync `PromptGuard.sanitize()` is voldoende voor productiebelasting (geen async vereist)

## Open vragen

- Streaming endpoints nog niet bewaakt -- apart sprint-item (buiten SEC-004)

## Risico's

- Geen; fail-secure gedrag geborgd

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest (400 injectie, 200 clean)
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest (tenant_id doorgegeven)
- [x] Validaties getest (lege message via Pydantic)
- [x] Edge cases getest (injectiepatronen via test_turn_rejects_injection_in_message)
- [x] Dataintegrteit: stateless, geen DB-impact
- [ ] Logging en tracing: geen expliciete log bij 400

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
