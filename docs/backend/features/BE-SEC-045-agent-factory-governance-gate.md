# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-045
- Feature naam: Vijf "Phase 4 Autonomous Systems"-endpoints uitgeschakeld wegens ontbrekende
  governance (ADR-036 D12.5)
- Status: APPROVED (zie `docs/backend/review/review-BE-SEC-045.md`, eindoordeel na 3 doc-rondes
  + een verplichte blinde eindreview)
- Auteur: Claude Sonnet 5
- Reviewer: onafhankelijke doc-reviewer-agent (twee rondes NEEDS REVISION, alle bevindingen
  verwerkt in deze versie), een onafhankelijke code-reviewer en security-reviewer op de code
  zelf (beiden GO), en een verplichte, volledig blinde eindreview (GO, met 1 MINOR die in v4
  is gefixt) -- zie `docs/backend/review/review-BE-SEC-045.md` voor het eindoordeel op DEZE
  versie
- Datum: 2026-08-18
- Gerelateerde user story / ticket: ADR036-D12-5-001 (CRITICAL/P0), audit-to-fix-brief
  2026-08-18
- Gerelateerde router / module: `src/core/api/v1/autonomous/agents_router.py`,
  `src/core/api/v1/autonomous/healing_router.py`,
  `src/core/api/v1/autonomous/code_router.py`,
  `src/core/api/v1/autonomous/emergence_router.py`,
  `src/core/api/autonomous_endpoints.py`
- Gerelateerde frontend endpoints: geen (geen frontend-consument gevonden voor een van de vijf)
- Gerelateerde database tabellen: geen
- Versie: 4 (herzien na twee rondes NEEDS REVISION + 1 MINOR uit de verplichte blinde
  eindreview -- zie "Revisiehistorie" onderaan)

---

## Doel en scope

### Doel

`POST /api/v1/autonomous/agents/create` kon een nieuwe autonome agent aanmaken zonder ooit
`GovernanceContract.is_action_permitted()` aan te roepen -- ADR-036 D12.5, CRITICAL/P0. Tijdens
de Gate 2-documentatiereview van de eerste fix bleek dezelfde governance-leemte te bestaan op
**vier andere muterende endpoints** binnen hetzelfde "Phase 4 Autonomous Systems"-domein, elk
in twee implementaties (het actieve pad onder `src/core/api/v1/autonomous/`, en een legacy
duplicaat in `src/core/api/autonomous_endpoints.py` dat zichzelf al "vervangen" noemt maar nooit
is opgeruimd). Deze feature schakelt alle vijf muterende endpoints uit (HTTP 503) totdat een
governance-laag gebouwd is, in plaats van onder tijdsdruk een governance-check toe te voegen aan
een fundament (`AgentFactory`/`BaseAgent`, `SelfHealingSystem`, `DynamicCodeGenerator`,
`EmergentIntelligence`) dat `tenant_id` structureel niet kent.

### In scope

**Vijf muterende endpoints, elk in twee implementaties (10 functies totaal):**

| Endpoint | Scope | Wat het deed | Actief bestand | Legacy duplicaat |
|---|---|---|---|---|
| `POST /agents/create` | AGENTS_WRITE | Agent aanmaken | `agents_router.py::create_autonomous_agent` | `autonomous_endpoints.py::create_autonomous_agent` |
| `POST /healing/report-failure` | AGENTS_WRITE | Kan met `auto_repair=true` een reparatie DIRECT UITVOEREN | `healing_router.py::report_system_failure` | `autonomous_endpoints.py::report_system_failure` |
| `POST /healing/execute-repair/{id}` | ADMIN_ALL | Voert een reparatieplan uit | `healing_router.py::execute_repair` | `autonomous_endpoints.py::execute_repair` |
| `POST /code/generate` | AGENTS_WRITE | Genereert code | `code_router.py::generate_code` | `autonomous_endpoints.py::generate_code` |
| `POST /emergence/facilitate` | AGENTS_WRITE | Faciliteert emergent gedrag tussen agents | `emergence_router.py::facilitate_emergence` | `autonomous_endpoints.py::facilitate_emergence` |

Alle tien roepen vandaag NERGENS `GovernanceContract.is_action_permitted()` aan (geverifieerd:
0 treffers op `is_action_permitted`/`GovernanceContract` in
`src/core/autonomy/self_healing_system.py`, `src/core/generation/dynamic_code_generator.py`,
`src/core/emergence/emergent_intelligence.py` en `src/core/subagents/agent_factory.py`).

De legacy duplicaten zijn gewired via `src/core/api/setup/router_registry.py` ->
`src/core/app_factory.py` **en** `src/core/api/main.py` (dat een eigen uitvoerbare FastAPI-app
+ `if __name__ == "__main__": uvicorn.run(...)`-blok heeft). Dit is niet het productiepad
(`gunicorn src.main:app`, dat via `src/core/api/router_registry.py` ->
`src/core/api/registries/*` loopt en alleen de actieve routers registreert), maar wel
zelfstandig uitvoerbaar en wordt geimporteerd door 4 testbestanden (2 integratie:
`test_copilot_websocket.py`, `test_refactor_integrity.py`; 2 unit:
`test_main_api_critical_coverage.py`, `test_sp_type01_main_py_types.py`) -- geen van deze
roept een van de vijf create/execute/generate/facilitate-routes zelf aan.

### Out of scope

- **De 10 read-only endpoints in dezelfde bestanden** (`agents/templates` GET, `factory/metrics`,
  `healing/status`, `code/templates`, `code/metrics`, `emergence/behaviors`,
  `emergence/intelligence-levels`, `status`, `health` -- elk in 2 implementaties waar van
  toepassing -- plus `agents/templates` POST dat een template registreert maar geen
  agent/reparatie/code/gedrag produceert) -- deze scheppen of wijzigen geen state. Conform de
  scoping-logica van de oorspronkelijke ADR-036-audit zelf (die ook alleen de CREATE-actie
  vlagde, niet de READ-endpoints in hetzelfde bestand). GEEN governance-gat aangetroffen dat
  voor deze endpoints relevant is, want ze voeren geen onomkeerbare actie uit.
- Het daadwerkelijk bouwen van de governance-check (vereist eerst `tenant_id` als concept in
  `AgentFactory`/`BaseAgent`/`SelfHealingSystem`/`DynamicCodeGenerator`/`EmergentIntelligence`,
  D1/Fase 4-werk).
- Het opruimen van de legacy `router_registry.py`(setup)/`app_factory.py`/`main.py`-registratie
  zelf (D12.3/D12.4-achtig opruimwerk, apart traject).
- **Bekende, niet-actieve testcaller**: `tests/unit/temp_disabled/test_autonomous.py` bevat
  HTTP-client-niveau tests voor alle vijf endpoints (`test_create_autonomous_agent_success`,
  `test_report_failure_with_auto_repair`, `test_execute_repair_success`,
  `test_generate_code_success`, `test_facilitate_emergence_success`). Dit bestand is
  gequarantained (`pyproject.toml`: `norecursedirs` + expliciete `--ignore`) en draait dus
  niet mee in de suite -- geen CI/runtime-caller, maar wel een grep-vindbare, wat de claim
  "geen vindbare caller" preciseert tot "geen vindbare ACTIEVE caller".

---

## Build summary

- Nieuw gebouwd: `tests/architecture/test_agent_factory_governance_gate.py` -- 15 tests:
  1 parametrized test over de 10 bewaakte functies (een eigen testcase per functie, zichtbaar
  in de test-ID) + 5 mutatiebewijs-tests.
- Gewijzigd:
  - Alle 5 actieve routerbestanden (`agents_router.py`, `healing_router.py`, `code_router.py`,
    `emergence_router.py`) en `autonomous_endpoints.py` -- elke van de 10 functies raiset nu
    onvoorwaardelijk 503 als eerste statement; oude bedrijfslogica verwijderd (niet als dode
    code laten staan, git-historie bewaart de oude versie). Nu-ongebruikte imports per bestand
    verwijderd (`uuid`, `GenerationRequest`, `FailureType`, `SystemFailure`, `CodeRequirement`,
    `CodeType`, `GenerationStrategy`, `EmergenceType`, `IntelligenceLevel`).
  - `tests/unit/api/v1/test_no_dict_str_e_leak.py` -- de bestaande OWASP A5-test voor
    `create_autonomous_agent` (agents_router.py) is aangepast om het nieuwe 503-gedrag te
    toetsen (inclusief `mock_factory.assert_not_called()`), met behoud van de sentinel-leak-
    check als vangnet. **Deze test WAS al een vindbare caller** (zie Technische kanttekening
    onder BE-EP-201) -- de andere 9 functies hadden geen vergelijkbare test.
  - `docs/user-guide/backend/autonomous-domain-migration.md` -- endpoint-tabel bijgewerkt voor
    het eerste endpoint; de overige vier staan niet in die tabel (die beschrijft alleen de
    Agent-Factory-sectie) en zijn dus niet aangepast.
- Verwijderd: de oorspronkelijke bedrijfslogica in alle 10 functies (archetype-/type-validatie,
  service-aanroepen, response-constructie) -- terugvindbaar in git-historie.
- Beinvloede bestaande flows: geen vindbare externe consument voor een van de vijf endpoints
  (frontend, actieve tests, CI/CD, gegenereerde OpenAPI-specs bevestigen alleen het BESTAAN van
  de routes, geen consumptie) -- zie Risico's voor de precieze grens van dit bewijs.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-201 | POST /agents/create (actief) | Endpoint | `agents_router.py` | Wijziging | BE-FLW-057 |
| BE-EP-202 | POST /agents/create (legacy) | Endpoint | `autonomous_endpoints.py` | Wijziging | BE-FLW-057 |
| BE-EP-203 | POST /healing/report-failure (actief) | Endpoint | `healing_router.py` | Wijziging | BE-FLW-057 |
| BE-EP-204 | POST /healing/report-failure (legacy) | Endpoint | `autonomous_endpoints.py` | Wijziging | BE-FLW-057 |
| BE-EP-205 | POST /healing/execute-repair/{id} (actief) | Endpoint | `healing_router.py` | Wijziging | BE-FLW-057 |
| BE-EP-206 | POST /healing/execute-repair/{id} (legacy) | Endpoint | `autonomous_endpoints.py` | Wijziging | BE-FLW-057 |
| BE-EP-207 | POST /code/generate (actief) | Endpoint | `code_router.py` | Wijziging | BE-FLW-057 |
| BE-EP-208 | POST /code/generate (legacy) | Endpoint | `autonomous_endpoints.py` | Wijziging | BE-FLW-057 |
| BE-EP-209 | POST /emergence/facilitate (actief) | Endpoint | `emergence_router.py` | Wijziging | BE-FLW-057 |
| BE-EP-210 | POST /emergence/facilitate (legacy) | Endpoint | `autonomous_endpoints.py` | Wijziging | BE-FLW-057 |
| BE-SEC-045-A | Governance-gate architecture-guard (10 functies) | Architecture test | `tests/architecture/test_agent_factory_governance_gate.py` | Nieuw | BE-FLW-057 |

---

## API-flows

### Flow ID: BE-FLW-057

- Naam: Aanroep op een van de vijf uitgeschakelde "Phase 4"-endpoints
- Trigger (HTTP-methode + route of event): een van de vijf POST-routes in de tabel hierboven
- Voorwaarden (auth, tenant, feature flag): geldige JWT + de vereiste scope (AGENTS_WRITE voor
  vier van de vijf, ADMIN_ALL voor `execute-repair`) -- ongewijzigd, wordt nog steeds vóór de
  handler-body geevalueerd door FastAPI's dependency-resolutie
- Request-pad: `Depends(get_current_user)` -> `Depends(require_scopes(...))` -> handler body
- Service-stappen: geen -- elke handler raiset onmiddellijk, geen enkele service wordt
  aangeroepen
- DB-operaties: geen
- Successtatus + response: N.v.t. -- geen van de vijf kan vandaag nog een succesrespons geven
- Foutpaden:
  - 401: ontbrekende/ongeldige token
  - 403: ontbrekende scope, OF de globaal gewired `SecurityMiddleware` blokkeert het IP, OF een
    kritieke-dreiging-detectie (ongewijzigd door deze fix, zie Foutafhandeling onder BE-EP-201)
  - 422: Pydantic-validatiefout op de request body (ongewijzigd, FastAPI-laag, vóór de handler)
  - 429: mogelijk, ongewijzigd -- de globaal gewired `SecurityMiddleware`
    (`src/core/security/security_middleware.py:130-158`) doet IP-block- en rate-limit-checks
    vóór ELKE route zonder pad-uitzondering, dus ook vóór deze vijf
  - 503: altijd, voor elke verder geldige aanroep
- Eindtoestand (DB, cache, events): geen wijziging aan enige staat

---

## Detaildocumentatie per artefact

Alle vijf endpoints delen exact dezelfde vorm; onderstaande sectie beschrijft het patroon
generiek met BE-EP-201 als representatief voorbeeld, en benoemt per sectie expliciet waar een
van de andere vier afwijkt.

---

## [BE-EP-201 t/m BE-EP-210] De vijf uitgeschakelde endpoints (representatieve detaillering)

### 1. Type

- Endpoint (5x, elk in 2 implementaties)

### 2. Locatie

- Zie de tabel in "In scope" hierboven voor de exacte bestandspaden en functienamen.

### 3. Gerelateerde flow

- BE-FLW-057 (gedeeld door alle tien)

### 4. Doel

- Voorheen: elk endpoint voerde zijn eigen bedrijfsactie uit (agent aanmaken, reparatie
  uitvoeren, code genereren, emergent gedrag faciliteren). Nu: het governance-gat dichten
  totdat een echte check bestaat.

### 5. Functionele beschrijving

- Elke aanroep, ongeacht payload, retourneert een 503 met een vaste, veilige foutmelding
  specifiek per endpoint (bijv. "Self-healing repair execution is temporarily disabled..." voor
  `execute-repair`). Geen actie wordt uitgevoerd, geen state gewijzigd.

### 6. Technische beschrijving

- Elke functie raiset `HTTPException(503, detail=<statische, per-endpoint specifieke string>)`
  als eerste statement in de functie-body (na de docstring). Geen `try`/`except` meer nodig --
  er is geen bedrijfslogica die kan falen. Nu-ongebruikte imports per bestand zijn verwijderd
  (zie Build summary).
- **Technische kanttekening (gecorrigeerd na review)**: de docstrings in de code zelf verwijzen
  naar "geen vindbare caller" voor deze endpoints. Voor BE-EP-201 specifiek is dat gedeeltelijk
  onjuist: `tests/unit/api/v1/test_no_dict_str_e_leak.py` riep `create_autonomous_agent`
  wel rechtstreeks aan (als OWASP A5-regressietest, niet als frontend/CI/productiegebruik) en is
  daarom aangepast. Voor de overige 9 functies is geen vergelijkbare test gevonden.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT via `get_current_user` (alle 10)
- Vereiste rol / scope: `AGENTS_WRITE` (8 van de 10) of `ADMIN_ALL` (`execute_repair`, 2 van de
  10)
- Tenant-isolatie: N.v.t. -- geen data wordt gelezen of geschreven
- Feature flag: geen (onvoorwaardelijke disable, geen vlag om aan/uit te zetten)

### 8. Request-specificatie

- Methode: POST (alle vijf)
- Routes: zie tabel "In scope"
- Path parameters: `failure_id` (alleen `execute-repair/{failure_id}`)
- Query parameters: geen
- Request body (schema): ongewijzigd per endpoint (`AgentCreationRequest`,
  `FailureReportModel`, `CodeGenerationRequest`, `EmergenceFacilitationRequest`) -- wordt nog
  steeds door FastAPI/Pydantic gevalideerd voordat de handler-body draait
- Verplichte headers: `Authorization: Bearer <jwt>`

### 9. Response-specificatie

- Successtatus: geen (deze endpoints geven nooit meer 2xx)
- Response schema: N.v.t.
- Foutstatussen: 401, 403 (scope OF security-middleware), 422, 429, 503 (altijd daarna) -- zie
  Flow BE-FLW-057 voor de volledige toelichting
- **Bekende discrepantie (OpenAPI/Swagger)**: geen van de tien functies heeft een
  `responses=`-override gekregen en de returntype-annotatie blijft `-> dict[str, Any]`. FastAPI
  genereert het successchema op basis van de annotatie, ongeacht of de functie ooit normaal
  terugkeert -- de gegenereerde OpenAPI-spec (`/docs`, `/openapi.json`) toont dus nog een
  200-successchema voor deze routes. Een integrator die de Swagger-UI raadpleegt in plaats van
  deze spec of de routes daadwerkelijk aanroept, krijgt een misleidend beeld.

### 10. Validaties en constraints

- Pydantic-validatie van de requestbody blijft actief (FastAPI-laag, vóór de handler) -- een
  structureel ongeldige body geeft dus nog steeds 422, niet 503.

### 11. Business rules

- Onvoorwaardelijk uitgeschakeld tot een governance-check bestaat. Geen uitzonderingen, geen
  whitelist, geen bypass-parameter.

### 12. Afhankelijkheden

- Geen -- geen van de tien handlers roept na de fix nog een andere service aan.

### 13. Foutafhandeling

- 400: N.v.t.
- 401: ontbrekende/ongeldige JWT (FastAPI-dependency, ongewijzigd)
- 403: ontbrekende scope (ongewijzigd); OF de globaal gewired `SecurityMiddleware` blokkeert
  het IP (`security_middleware.py:116-128`) of detecteert een kritieke dreiging (regel
  166-176) -- beide ongewijzigd door deze fix en niet beperkt tot de scope-403
- 404: N.v.t.
- 409: N.v.t.
- 422: Pydantic-validatiefout op de body (ongewijzigd, FastAPI-laag)
- 429: mogelijk, ongewijzigd door deze fix -- afgedwongen door de globaal gewired
  `SecurityMiddleware` (`security_middleware.py:130-158`, IP-block-check + per-IP/tenant
  rate limiting), die vóór de handler-body draait voor elk endpoint zonder padexceptie
- 500: N.v.t. -- er is geen bedrijfslogica meer die kan falen
- 503: altijd, voor elke verder geldige aanroep -- statische, veilige detail-string per endpoint

### 14. Transacties en dataintegriteit

- N.v.t. -- geen databasetoegang meer in dit pad.

### 15. Telemetry / logging / tracing

- Geen aparte logregel toegevoegd voor de 503 zelf. Geen wijziging aan bestaande tracing.

### 16. Caching

- Gecached: nee (alle vijf)

### 17. Acceptatiecriteria

- Elke aanroep op een van de vijf endpoints, met geldige JWT + vereiste scope + geldige body,
  geeft **altijd** HTTP 503 met een detail-string die geen interne informatie bevat.
- De onderliggende service (`AgentFactory`, `SelfHealingSystem`, `DynamicCodeGenerator`,
  `EmergentIntelligence`) wordt **nooit** aangeroepen -- bewezen voor BE-EP-201 via
  `mock_factory.assert_not_called()`; voor de overige 9 functies bewezen door AST-inspectie
  (de architecture-guard), niet door een aparte mock-test per functie.
- `tests/architecture/test_agent_factory_governance_gate.py::test_bewaakte_functie_kan_geen_2xx_geven_zonder_governance_of_disable`
  slaagt voor alle 10 parameters.
- Een toekomstige her-activering die `is_action_permitted()` aanroept maar het resultaat
  negeert, wordt door dezelfde guard afgekeurd (bewezen in
  `test_a_governance_call_whose_result_is_discarded_is_rejected`).

### 18. Integratorhandleiding

- Alle vijf endpoints geven vanaf nu altijd `503 Service Unavailable` terug.
- Er is geen alternatieve manier om via de API een agent aan te maken, een reparatie uit te
  voeren, code te genereren, of emergent gedrag te faciliteren -- die paden bestaan momenteel
  niet.
- De gegenereerde OpenAPI-spec/Swagger-UI kan nog een 200-successschema tonen voor deze routes;
  dit is een FastAPI-annotatie-artefact en weerspiegelt niet het werkelijke gedrag (zie sectie 9).
- Dit is een bewuste, tijdelijke maatregel (geen bug); elke detail-tekst verwijst naar ADR-036
  D12.5 voor context.

### 19. Trainingssamenvatting

- Actor: geauthenticeerde gebruiker/service met de vereiste scope (AGENTS_WRITE of ADMIN_ALL)
- Voorwaarde: geldige JWT, geldige scope, geldige requestbody (Pydantic-schema)
- Actie (request): POST op een van de vijf routes met de bijbehorende body
- Systeemverwerking: geen -- de handler raiset onmiddellijk 503, geen enkele service wordt
  aangeroepen
- Succesrespons: N.v.t. (bestaat niet meer)
- Foutrespons: 503 met statische, veilige, per-endpoint specifieke detail-string
- Uitzonderingen: 401/403/422/429 blijven mogelijk als de aanroep zelf al ongeldig is of door de
  globale security-middleware wordt geblokkeerd (vóór de handler-body)

---

## [BE-SEC-045-A] Governance-gate architecture-guard

### 1. Type

- Auth guard / architecture test

### 2. Locatie

- Bestandspad: `tests/architecture/test_agent_factory_governance_gate.py`

### 3. Gerelateerde flow

- BE-FLW-057

### 4. Doel

- Voorkomen dat een van de 10 bewaakte functies ooit weer een 2xx kan geven zonder afgedwongen
  governance, ongemerkt (bijv. bij een toekomstige refactor die de 503 per ongeluk verwijdert).

### 5. Functionele beschrijving

- Een expliciet benoemde verzameling (`BEWAAKTE_FUNCTIES`, 10 elementen) wordt elk apart
  getoetst via `pytest.mark.parametrize` (eigen testcase-ID per functie). Per functie: (a)
  bevat de functie een aanroep van `is_action_permitted()` die daadwerkelijk de controleflow
  stuurt (in een `if`-test, met een `raise`/`return` in minstens een van de takken), of (b) is
  het eerste statement van de functie een onvoorwaardelijke `raise HTTPException(status_code=503, ...)`.
  Minstens een van de twee moet waar zijn.

### 6. Technische beschrijving

- `ast.parse` + `ast.walk` op de broncode van elke functie (via `inspect.getsource`). Geen
  string-matching op de broncode zelf. Vijf aparte mutatiebewijs-tests op synthetische
  AST-snippets tonen dat de guard in beide richtingen werkt, inclusief de "aanroep aanwezig maar
  resultaat genegeerd"-bypass die tijdens Gate 2-review is gevonden en gereproduceerd.

### 7-16

- N.v.t. (test, geen runtime-component)

### 17. Acceptatiecriteria

- Alle 15 tests in het bestand slagen (10 parametrized + 5 mutatiebewijs).
- Het verwijderen van de 503-guard in een van de tien bewaakte functies maakt de bijbehorende
  parametrized testcase rood (handmatig bevestigd tijdens implementatie voor BE-EP-201, niet
  als permanente testcode voor alle 10 herhaald).

### 18-19

- N.v.t.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- De vijf endpoints in de tabel onder "In scope" retourneren vanaf nu altijd `503`.
- Gebruik deze endpoints niet in nieuwe integraties; er is geen vervangend pad.
- De 10 read-only endpoints onder `/api/v1/autonomous/` (templates, metrics, healing/status,
  code/templates, code/metrics, behaviors, intelligence-levels, en de systeembrede `status`/
  `health`) zijn ongewijzigd.
- Raadpleeg bij twijfel deze spec, niet alleen de gegenereerde Swagger-UI (zie sectie 9 voor de
  bekende discrepantie).

---

## Open aannames

- Aangenomen dat er geen externe, buiten deze repo geconfigureerde consument bestaat (API-key,
  partnerintegratie) voor een van de vijf endpoints -- een repo-grep kan dit niet bewijzen,
  alleen "geen vindbare caller" aantonen.

## Open vragen

- Wanneer wordt D1 (Manager/Hoofdagent-laag, Fase 4) opgepakt, wat de natuurlijke plek is om
  `tenant_id` alsnog aan deze vier services toe te voegen en de endpoints met een echte
  governance-check te herstellen?

## Risico's

- Een onbekende externe consument die een van deze vijf endpoints gebruikte, krijgt vanaf nu
  een 503 in plaats van een 2xx. Mitigatie: de 503-body is informatief (geen stille breuk). Er
  is GEEN nieuwe monitoring/dashboard gebouwd voor deze fix; de bestaande request-access-logging
  legt path + statuscode al vast voor elk verzoek, dus een toename van 503's op deze vijf paden
  is zichtbaar in de bestaande logs zonder extra instrumentatie -- dit is bewust geen nieuwe
  belofte, alleen een constatering van wat er al bestaat.
- De legacy duplicaten leefden in een bestand dat zichzelf al "vervangen" noemt maar nooit is
  opgeruimd -- dat opruimwerk zelf blijft open (zie Out of scope).
- `GenerationRequest` (gedefinieerd in `autonomous_endpoints.py`) is na deze fix niet meer
  gebruikt door productiecode (alleen nog geimporteerd door `tests/unit/test_api_endpoints_batch.py`
  voor een modelvalidatietest) -- opruimen valt onder het D12.3/D12.4-achtige opruimtraject, niet
  onder deze fix.
- **Bijvangst, buiten de oorspronkelijke D12.5-scope maar in dezelfde bestanden gefixt**: alle
  10 overige (niet-uitgeschakelde) endpoints in `autonomous_endpoints.py` gaven `str(e)`
  verbatim terug in de HTTP-response (OWASP A5) -- dezelfde bugklasse als het "ERGERE lek" dat
  bij de vijf nu-uitgeschakelde endpoints is genoemd. Omdat het bestand al open lag voor exact
  deze bugklasse, zijn alle 10 in dezelfde commit meegefixt (`detail="Internal error"` /
  `"error": "Internal error"`, met `exc_info=True` in de logging) -- inclusief
  `get_agent_templates`, die de gedeelde utility `handle_endpoint_error`/
  `ErrorDiagnostics.create_http_exception` gebruikte: de blinde eindreview wees er terecht op dat
  het vervangen van DIE ENE aanroep door het al-toegepaste directe patroon geen wijziging aan de
  gedeelde utility zelf vergt (die door andere, ongerelateerde endpoints elders in de repo wordt
  gebruikt en dus wel een eigen impact-analyse zou vergen -- dat blijft terecht buiten deze fix).

---

## QA-checks

- [x] Endpoint functioneel getest (happy path is N.v.t. voor alle vijf -- er is geen happy path
  meer, dat is het punt)
- [x] Alle foutstatus-codes beschreven (503 direct getest voor BE-EP-201 en via AST voor de
  overige 9; 401/403/422/429 ongewijzigd, niet opnieuw getest omdat de dependency-/middleware-
  laag niet is aangeraakt)
- [x] Auth en permissies getest (bevestigd: dependencies draaien nog steeds vóór de body)
- [x] Tenant-isolatie getest (N.v.t. -- geen data-toegang meer)
- [ ] Validaties getest (ongeldige invoer) -- niet apart hertoetst, geen wijziging aan een
  Pydantic-schema of de validatielaag
- [x] Edge cases getest (N.v.t. want de body wordt nooit gelezen na Pydantic-validatie)
- [x] Dataintegriteit en transacties getest (N.v.t., geen DB-toegang meer)
- [ ] Performance / load getest -- niet van toepassing op een statische 503
- [ ] Caching getest -- N.v.t.
- [x] Logging en tracing gecontroleerd (geen wijziging, bevestigd via code-review)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd (10 functies, 1 architecture-guard)
- [x] Alle relevante foutstatussen zijn beschreven (inclusief 429/403 via security-middleware,
  na correctie)
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd (met 3 N.v.t.-items expliciet toegelicht)
- [x] Review door reviewer-prompt: `docs/backend/review/review-BE-SEC-045.md` -- APPROVED

---

## Revisiehistorie

- **v1 (2026-08-18)**: eerste versie, alleen BE-EP-201/202 (het door de audit gevonden
  endpoint). Onafhankelijke doc-review: **NEEDS REVISION**. Bevindingen: (1) CRITICAL --
  metadata claimde een afgeronde tweede reviewronde met verwijzing naar een niet-bestaand
  reviewbestand, terwijl de eigen DoD-checkbox aangaf dat de review nog niet had plaatsgevonden;
  (2) HIGH -- 429 ten onrechte als "N.v.t." gemarkeerd terwijl de globale SecurityMiddleware dat
  endpoint ongewijzigd aan rate limiting onderwerpt; (3) HIGH -- "Out of scope" dekte slechts 4
  van de 12+ overige endpoints in het aangeraakte legacy-bestand, terwijl de overige acht
  dezelfde governance-leemte bleken te hebben; (4) MEDIUM -- padverwijzing
  `src/core/api/app_factory.py` bestond niet (moest `src/core/app_factory.py` zijn); (5) MEDIUM
  -- interne tegenspraak tussen de code-docstring ("geen vindbare caller... tests") en de eigen
  Build Summary (die een gevonden test-caller beschreef); (6) MEDIUM -- geen vermelding van de
  OpenAPI/Swagger-200-schema-discrepantie; (7) LOW -- diverse kleinere inconsistenties.
- **v2 (2026-08-18)**: bevinding (3) leidde tot een feitelijke uitbreiding van de
  IMPLEMENTATIE, niet alleen de documentatie -- de vier extra muterende endpoints
  (`healing/report-failure`, `healing/execute-repair`, `code/generate`, `emergence/facilitate`,
  elk in 2 implementaties) zijn na een eigen exhaustieve caller-check (0 vindbare actieve
  callers, net als bij BE-EP-201/202) ook uitgeschakeld en toegevoegd aan de architecture-guard.
  Bevindingen (1), (2), (4), (5), (6) en (7) zijn verwerkt. Onafhankelijke herbeoordeling:
  **NEEDS REVISION** (3 nieuwe ronde). Bevindingen: (8) HIGH -- `docs/backend/features/ID-REGISTRY.md`
  en ADR-036 OP-162 beschreven nog de v1-scope (1 endpoint/2 functies/7 tests) i.p.v. de
  daadwerkelijke v2-scope (5 endpoints/10 functies/15 tests); (9) HIGH -- de Build-Summary-claim
  dat de user-guide voor de overige vier endpoints niet was aangepast, was zelf onjuist (het
  bestand heeft wel degelijk aparte tabellen per endpoint-familie, die de 503-disable misten);
  (10) MEDIUM -- "8 read-only endpoints" in Out-of-scope miste `status`/`health` (moest 10 zijn);
  (11) MEDIUM -- de docstring in `agents_router.py` zelf claimde nog "geen vindbare caller...
  tests", niet alleen de spec-tekst; (12) MEDIUM -- `tests/unit/temp_disabled/test_autonomous.py`
  (gequarantained, draait niet mee) bevat HTTP-niveau tests voor alle vijf endpoints en was niet
  vermeld; (13) LOW -- regelverwijzing `166-172` moest `166-176` zijn. Parallel aan deze
  documentatieronde bevestigden een code-reviewer en een security-reviewer de CODE zelf als
  **GO** (de security-reviewer voerde een eigen mutatietest uit op `execute_repair` en bevond de
  guard betrouwbaar), met drie kleine non-blocking bevindingen: een non-ASCII-teken
  (`kopieën` -> `duplicaten`), en 9 resterende OWASP-A5-lekken (`detail=str(e)`) in de
  NIET-uitgeschakelde endpoints van hetzelfde legacy-bestand.
- **v3 (2026-08-18)**: alle bevindingen (8) t/m (13) verwerkt (ID-REGISTRY, ADR-036
  OP-162, user-guide, Out-of-scope-telling, docstring, temp_disabled-vermelding, regelverwijzing).
  De 3 code-/security-bevindingen zijn ook verwerkt: ASCII-fix, en de 9 resterende OWASP-A5-lekken
  in `autonomous_endpoints.py` zijn gedicht (zie Risico's, "Bijvangst"). Derde, gerichte
  doc-verificatieronde: **APPROVED**. Vervolgens liep de volledige regressiesuite (buiten deze
  documentatie-review om) tegen een ANDERE, pre-existing architecture-guard aan
  (`test_adr036_register_is_parseable.py`), die eiste dat een GESLOTEN OP-registerrij haar eigen
  OP-nummer terugvindt in het aangehaalde testbestand -- de OP-162-rij voldeed daar niet aan;
  gefixt door "OP-162" toe te voegen aan de docstring van
  `test_agent_factory_governance_gate.py`, bevestigd met een tweede volledige suite-run
  (15695 passed, 0 failed).
- **v4 (2026-08-18, deze versie)**: de verplichte, volledig blinde eindreview (final-approver-
  pijplijn, `docs/agent-briefs/final-approver.md`) gaf **GO**, met een eigen mutatietest op
  `healing_router.py::execute_repair` als bewijs dat de guard niet hol is (de mutatie maakte
  precies en alleen die ene parametrized testcase rood). Eén MINOR: `get_agent_templates` in
  `autonomous_endpoints.py` gebruikte nog de gedeelde utility `handle_endpoint_error()`, die
  hetzelfde `str(error)[:200]`-lekpatroon heeft als de 9 al gefixte endpoints -- de reviewer
  wees er terecht op dat het vervangen van DIE ENE aanroep door het al-toegepaste directe
  patroon geen wijziging aan de gedeelde utility zelf (en dus geen repo-brede impact-analyse)
  vergt. Gefixt: alle 10 (niet 9) overige endpoints in dat bestand zijn nu vrij van dit
  OWASP-A5-patroon.
