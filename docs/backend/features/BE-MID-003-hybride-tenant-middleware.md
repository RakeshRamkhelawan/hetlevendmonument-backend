# Backend Feature Specification

## Metadata

- Feature ID: BE-MID-003
- Feature naam: Hybride Tenant Middleware Fallback
- Status: IMPLEMENTED
- Auteur: AI Copilot
- Reviewer: AI Reviewer
- Datum: 2026-06-27
- Gerelateerde user story / ticket: AUDIT-TENANT-01
- Gerelateerde router / module: `src/core/middleware/tenant_middleware.py`
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

Ondersteuning bieden voor een hybride deployment model (SaaS of Single-Tenant) door middel van een fallback-mechanisme in de `TenantMiddleware`. Wanneer de applicatie in `single_tenant` modus draait, wordt bij ontbrekende of ongeldige tokens (waarbij geen `tenant_id` kan worden afgeleid) automatisch een fallback gedaan naar een default `tenant_id=1`. Hierdoor blijven RLS en bestaande tenant-gebaseerde logica werken zonder dat de codebase opgesplitst hoeft te worden voor on-premise/single-tenant klanten.

### In scope

- Uitlezen van `DEPLOYMENT_MODE` configuratievariabele
- Fallback naar `tenant_id=1` indien `DEPLOYMENT_MODE == "single_tenant"` en er geen token of geldige tenant claim is
- Voorzien van default mock properties (`user_id="system"`, `roles=["admin"]`) in het request state voor fallback-verzoeken in single_tenant mode
- In stand houden van strikte SaaS security (401 Unauthorized) indien `DEPLOYMENT_MODE != "single_tenant"`

### Out of scope

- Volledige ombouw van multi-tenant datastructuren
- Verwijderen van RLS op de database tabellen (behoud is essentieel)

---

## Build summary

- Nieuw gebouwd: `DEPLOYMENT_MODE` configuratie in `src/config.py`
- Gewijzigd: `TenantMiddleware.__call__` in `src/core/middleware/tenant_middleware.py` om fallback toe te passen.
- Verwijderd: N/A
- Beinvloede bestaande flows: Alle binnenkomende HTTP verzoeken die authenticatie/tenant context vereisen.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MID-003 | Hybride Tenant Middleware | Middleware | `src/core/middleware/tenant_middleware.py` | Wijziging | BE-FLW-002 (Algemene request flow) |
| BE-CFG-006 | DEPLOYMENT_MODE | Config | `src/config.py` | Nieuw | BE-FLW-002 |

---

## API-flows

### Flow ID: BE-FLW-002

- Naam: Algemene Tenant Context Extractie
- Trigger (HTTP-methode + route of event): Elke HTTP request via de ASGI stack.
- Voorwaarden (auth, tenant, feature flag): `DEPLOYMENT_MODE` bepaalt SaaS of single_tenant fallback.
- Request-pad: Middleware laagt in ASGI -> `TenantMiddleware.__call__`
- Service-stappen: 
  1. Extraheer JWT (header of cookie)
  2. Als JWT ontbreekt en `DEPLOYMENT_MODE == "single_tenant"`, fallback naar `tenant_id=1`
  3. Als JWT aanwezig is, verifieer en extraheer `tenant_id`
  4. Als JWT aanwezig is maar `tenant_id` ontbreekt en `DEPLOYMENT_MODE == "single_tenant"`, fallback naar `tenant_id=1`
  5. Sla `tenant_id` op in ContextVar via `set_tenant_id`
- DB-operaties: Geen direct. Wel invloed op alle latere queries via RLS.
- Successtatus + response: Verzoek gaat door naar next app (HTTP 200/201/etc)
- Foutpaden: HTTP 401 Unauthorized als `DEPLOYMENT_MODE == "saas"` en geldige tenant-context ontbreekt.
- Eindtoestand (DB, cache, events): ContextVar ingevuld, later opgeruimd via `clear_tenant_context()`.

---

## Detaildocumentatie per artefact

---

## [BE-MID-003] Hybride Tenant Middleware Fallback

### 1. Type

- ASGI Middleware

### 2. Locatie

- Bestandspad: `src/core/middleware/tenant_middleware.py`
- Klasse / functie: `TenantMiddleware.__call__`

### 3. Gerelateerde flow

- BE-FLW-002

### 4. Doel

- Automatisch en veilig afvangen van tenant-identiteit over verschillende deploy-strategieën.

### 5. Functionele beschrijving

- De middleware valideert en extraheert de tenant-context voor ieder inkomend verzoek. In de SaaS configuratie (default) worden requests zonder geldige tenant onherroepelijk geweigerd met een 401. In een Enterprise single-tenant omgeving (`DEPLOYMENT_MODE="single_tenant"`) is deze afdwinging onnodig streng voor interne API-calls of single-user setups, vandaar dat er wordt teruggevallen op de root-tenant (`tenant_id=1`).

### 6. Technische beschrijving

- Pure ASGI middleware. Bij ontbreken van auth-token (`not token`), wordt gecontroleerd of de module global `DEPLOYMENT_MODE` gelijk is aan `"single_tenant"`. Zo ja, dan roept het `set_tenant_id(1)` aan en vult het `scope["state"]` met default admin waarden (user `system`, rol `admin`). Vervolgens stuurt het het verzoek door in de ASGI chain. Dezelfde logica geldt wanneer er wél een token is, maar zonder `tenant_id` claim. Bij de teardown wordt de context netjes opgeruimd.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Afhankelijk van mode (SaaS = Verplicht, Single-Tenant = Fallback).
- Vereiste rol / scope: N/A
- Tenant-isolatie: Forceert tenant `1` in single_tenant mode.
- Feature flag: `DEPLOYMENT_MODE`

### 8. Request-specificatie

- Methode: ALL
- Route: ALL (behalve EXCLUDED_PREFIXES)
- Path parameters: N/A
- Query parameters: N/A
- Request body (schema): N/A
- Verplichte headers: Authorization / Cookie (Alleen in SaaS mode)

### 9. Response-specificatie

- Successtatus: Doorgegeven van endpoint
- Response schema: Doorgegeven van endpoint
- Foutstatussen: 401 Unauthorized

### 10. Validaties en constraints

- JWT validatie via `jwt_handler`
- Formaat validatie: `tenant_id` moet resolveable zijn tot `int`

### 11. Business rules

- Een SaaS installatie deelt nooit data tussen tenants en tolereert geen request zonder expliciete eigenaar.

### 12. Afhankelijkheden

- `src.config.DEPLOYMENT_MODE`
- `src.core.middleware.tenant_context`
- `src.core.auth.jwt_handler`

### 13. Foutafhandeling

- 400: N/A
- 401: Bij afwezige of ongeldige token (in SaaS mode)
- 403: N/A
- 404: N/A
- 409: N/A
- 422: N/A
- 429: N/A
- 500: N/A
- 503: N/A

### 14. Transacties en dataïntegriteit

- Voorkomt tenant cross-talk door na afronding van ASGI send `clear_tenant_context()` aan te roepen in de `finally` block.

### 15. Telemetry / logging / tracing

- Security Event log `TENANT_CONTEXT_FAILED` indien fallback faalt of SaaS mode een 401 triggert.

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N/A
- TTL: N/A
- Invalidatie: N/A

### 17. Acceptatiecriteria

- Bij `DEPLOYMENT_MODE="saas"` zonder token retourneert de server 401.
- Bij `DEPLOYMENT_MODE="single_tenant"` zonder token wijst de request state `tenant_id=1` toe en roept succesvol de downstream endpoint aan (status 200).
- Bij `DEPLOYMENT_MODE="single_tenant"` mét token die geldig is voor tenant 99, krijgt de request state `tenant_id=99`.

### 18. Integratoruitleg

- In de standaard (SaaS) modus vereist de API een expliciete Authentication Bearer met een specifieke tenant claim.
- Voor On-Premise/Single-Tenant (Enterprise) hoeft u dit niet aan te leveren; het systeem neemt default tenant-1 aan voor uw gehele bedrijfsomgeving.

### 19. Trainingssamenvatting

- Actor: Middleware
- Voorwaarde: Iedere inkomende ASGI HTTP call
- Actie (request): Evalueer Token en `DEPLOYMENT_MODE`
- Systeemverwerking: Initialiseert `ContextVar` voor RLS scheiding
- Succesrespons: ASGI call chain gaat door
- Foutrespons: HTTP 401
- Uitzonderingen: Geen exceptions; fouten worden afgevangen in 401 ASGI responses.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Als ontwikkelaar voor een Enterprise instantie (Single Tenant Mode), kan de API benaderd worden zonder ingewikkelde tenant-specifieke authenticatie voor machine-to-machine communicatie die lokaal draait, het systeem zal automatisch de context toewijzen aan tenant `1`.
Draait u in de cloud (SaaS Mode), wees u er dan van bewust dat elk verzoek ten alle tijde voorzien moet zijn van een geldige JWT inclusief `tenant_id` (via Header of Session Cookie).

---

## Open aannames

- `tenant_id=1` is veilig gereserveerd als de standaard master tenant voor single-tenant installaties.

## Open vragen

- Geen.

## Risico's

- Als de env var configuratie per abuis faalt, valt de app fallback naar SaaS wat kan zorgen voor timeouts of onbereikbaarheid in Enterprise (fail secure).

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [x] Dataïntegriteit en transacties getest
- [ ] Performance / load getest (indien relevant)
- [ ] Caching getest (indien van toepassing)
- [x] Logging en tracing gecontroleerd

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
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
