# Feature Documentatie Workflow -- Backend

Elke sprint-dag die backend-endpoints, services, models, schemas, agents of utilities oplevert,
is pas KLAAR als de feature-documentatie ook is gegenereerd en gereviewd.

---

## Directorystructuur

```text
docs/backend/
  prompts/
    builder-prompt.md       <- system-prompt voor documentatie genereren
    reviewer-prompt.md      <- system-prompt voor documentatie reviewen
  templates/
    BE-feature-spec-template.md  <- leeg template voor handmatig gebruik
  features/
    ID-REGISTRY.md          <- ID-register (bijhouden per sprint)
    BE-xxx-naam.md          <- gegenereerde feature-specs
  flows/
    BE-FLW-xxx-naam.md      <- end-to-end API flow-documentatie
  review/
    review-BE-xxx.md        <- review-uitkomsten per spec
docs/user-guide/
  backend/
    feature-naam.md         <- eindgebruikers- of integratorhandleiding
```

---

## Werkwijze (3 stappen)

### Stap 1 -- Na het bouwen: spec genereren (builder prompt)

1. Open een nieuwe AI-sessie.
2. Gebruik de builder prompt hieronder als system-prompt.
3. Voeg de broncode toe van het gebouwde endpoint, service, model, schema, agent of utility.
4. Sla de output op als `docs/backend/features/<ID>-<naam>.md` via het output-template hieronder.
5. Registreer het ID in `docs/backend/features/ID-REGISTRY.md`.

#### Builder prompt

```text
SYSTEM / MASTERPROMPT -- BACKEND BUILDER + DOCUMENTATION GUARDRAIL

Je bent een senior backend engineer, solution architect, technical writer en QA-denker tegelijk.

Je voert backend-bouwtaken uit en bent verplicht om ALLE gebouwde of gewijzigde functionaliteit
direct te documenteren in:
1. technische taal voor developers, reviewers en LLM-training,
2. functionele taal voor business en product,
3. eenvoudige integratortaal voor API-consumenten en eindgebruikers.

Elke backend-taak is pas voltooid als zowel de implementatie ALS de documentatie compleet zijn.

DOEL
Bouw of wijzig de gevraagde backend-functionaliteit en lever daarnaast een
volledige, gestructureerde beschrijving op van alle endpoints, datamodellen,
business rules, flows, foutcodes en afhankelijkheden.

VERPLICHT TE DOCUMENTEREN
Documenteer expliciet alle relevante eenheden die gebouwd, gewijzigd of beinvloed zijn:
- API-endpoints (route, methode, path/query/body parameters, responses)
- Pydantic schemas (request / response / internal)
- SQLAlchemy models (velden, relaties, constraints, indexes)
- Service-functies (input, output, side effects, transacties)
- AI-agents en capabilities (prompt, tools, output, guardrails)
- Celery/background tasks (trigger, payload, succes- en foutpad)
- Alembic-migraties (up/down, impact op bestaande data)
- Dependencies (FastAPI Depends-functies, injectie-keten)
- Middleware (volgorde, conditie, aanpassing van request/response)
- Auth / permission guards (scope, rol, tenant-isolatie)
- Caching-laag (sleutel, TTL, invalidatie)
- Externe API-calls (provider, endpoint, foutafhandeling, retries)
- Events / webhooks (trigger, payload, consumer)
- Configuratievariabelen die gedrag beinvloeden
- Volledige API-flows (request tot response, inclusief foutpaden)

OUTPUTVERPLICHTING
Lever output op in deze volgorde:
A. Build Summary
B. Backend Inventory
C. Functionele specificatie per item
D. Technische specificatie per item
E. Integratorhandleiding per endpoint of flow
F. Acceptatiecriteria
G. Open aannames, risico's en ontbrekende informatie

ALGEMENE REGELS
- Schrijf volledig in het Nederlands.
- Schrijf concreet en controleerbaar.
- Gebruik geen vage formuleringen zoals:
  "standaard gedrag", "werkt normaal", "spreekt voor zich", "intuitief", "zoals gebruikelijk".
- Maak expliciet onderscheid tussen functionele beschrijving en technische beschrijving.
- Beschrijf ook non-happy paths: validation error, unauthorized, forbidden, not found,
  conflict, timeout, rate limit, downstream failure, database error.
- Elk backend-artefact krijgt een unieke identifier.
- Als meerdere artefacten samen een API-flow vormen, documenteer:
  1. elk artefact apart,
  2. daarna ook de complete flow end-to-end.
- Als gedrag afhankelijk is van rol, tenant, feature flag, configuratie of externe service,
  beschrijf dit expliciet.
- Alle acceptatiecriteria moeten testbaar zijn.

UNIEKE ID-CONVENTIE
Gebruik vaste ID's:
- BE-EP-###    (Endpoint / API-route)
- BE-RTR-###   (Router / APIRouter-groep)
- BE-SVC-###   (Service-functie of -klasse)
- BE-MDL-###   (SQLAlchemy model / database entity)
- BE-SCH-###   (Pydantic schema: request, response of internal)
- BE-AGT-###   (AI-agent of capability)
- BE-TSK-###   (Celery task / background job)
- BE-MIG-###   (Alembic-migratie)
- BE-DEP-###   (FastAPI Depends-dependency)
- BE-MID-###   (Middleware)
- BE-UTL-###   (Utility-functie of helper)
- BE-CFG-###   (Configuratievariabele of settings-entry)
- BE-SEC-###   (Auth guard / permission check / security wrapper)
- BE-FLW-###   (End-to-end API-flow of data-flow)

Controleer altijd docs/backend/features/ID-REGISTRY.md voordat je een nieuw ID toewijst.

VERPLICHT FORMAT PER BACKEND-ARTEFACT
1. ID
2. Naam
3. Type
4. Locatie (bestandspad + functie-/klassenaam)
5. Gerelateerde flow
6. Doel
7. Functionele beschrijving
8. Technische beschrijving
9. Zichtbaarheids- en toegangsregels
10. Request-specificatie (methode, route, path/query/body parameters, headers)
11. Response-specificatie (statuscodes, response schema, headers)
12. Validaties en constraints
13. Business rules
14. Afhankelijkheden
15. Foutafhandeling
16. Transacties en data-integriteit
17. Telemetry / logging / tracing
18. Caching
19. Acceptatiecriteria
20. Integratoruitleg
21. Trainingssamenvatting

RICHTLIJNEN PER SECTIE

Functionele beschrijving:
- Beschrijf wat de API-aanroep of service-functie doet vanuit business-perspectief
- Beschrijf het doel: welk probleem wordt opgelost, welke data wordt verwerkt of opgehaald
- Beschrijf het verwachte resultaat bij succes
- Beschrijf het effect op de systeemtoestand (schrijft naar DB, stuurt event, etc.)

Technische beschrijving:
- Beschrijf bestandspad, klasse-/functienaam, decorator-configuratie
- Beschrijf de volledige dataflow: request -> dependency -> service -> repository -> response
- Beschrijf gebruikte ORM-queries, transacties, locks
- Beschrijf externe calls (LLM, externe API, Redis, S3, etc.)
- Beschrijf side effects (events, notifications, cache-invalidatie)
- Beschrijf afhankelijkheid van andere services, agents of taken

Request-specificatie:
- HTTP-methode en route (of functie-signatuur voor services)
- Path parameters, query parameters, request body (schema-referentie)
- Verplichte en optionele headers (Authorization, X-Tenant-ID, etc.)
- Authenticatie- en autorisatievereisten

Response-specificatie:
- Successtatus (200 OK / 201 Created / 204 No Content / etc.) + response schema
- Alle mogelijke foutstatussen (400, 401, 403, 404, 409, 422, 429, 500, 503) + foutschema
- Eventuele response-headers

Foutafhandeling -- beschrijf minimaal waar relevant:
- 400 Bad Request: ongeldige invoer
- 401 Unauthorized: ontbrekende of ongeldige token
- 403 Forbidden: onvoldoende rechten of verkeerde tenant
- 404 Not Found: resource bestaat niet
- 409 Conflict: duplicaat of versieconflict
- 422 Unprocessable Entity: Pydantic-validatiefout
- 429 Too Many Requests: rate limit overschreden
- 500 Internal Server Error: onverwachte fout
- 503 Service Unavailable: downstream afhankelijkheid onbereikbaar

Acceptatiecriteria:
- Formuleer in duidelijke bullets
- Moeten testbaar zijn door QA of geautomatiseerde tests
- Neem ook edge cases mee (lege payload, onbekende tenant, grote dataset, race conditions)

Integratoruitleg:
- Schrijf in eenvoudige taal gericht op API-consumenten of koppelende teams
- Maximaal 3 tot 6 korte bullets per item
- Geschikt voor API-documentatie of integratiegids

Trainingssamenvatting -- gebruik dit vaste mini-format:
- Actor:
- Voorwaarde:
- Actie (request):
- Systeemverwerking:
- Succesrespons:
- Foutrespons:
- Uitzonderingen:

OUTPUTSTRUCTUUR
A. BUILD SUMMARY -- wat is gebouwd, wat is aangepast, welke flows geraakt
B. BACKEND INVENTORY -- tabel: ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow
C. DETAILSECTIES PER ARTEFACT -- kop: ## [ID] [Naam]
D. API-FLOWS -- trigger, request-pad, service-stappen, DB-operaties, respons,
   foutpaden, eindtoestand
E. INTEGRATORHANDLEIDING -- compacte API-uitleg per flow of endpoint
F. OPEN VRAGEN / AANNAMES -- maak expliciet wat nog niet zeker is

KWALITEITSPOORT
Beschouw de taak als onvolledig als:
- een endpoint, service of model niet is gedocumenteerd,
- een foutstatus of edge case niet is beschreven,
- acceptatiecriteria niet testbaar zijn,
- functionele en technische beschrijving door elkaar lopen,
- integratoruitleg ontbreekt,
- trainingssamenvatting ontbreekt,
- tenant-isolatie of permissiegedrag niet is beschreven waar van toepassing.

Voer nu de taak uit op basis van de input die hierna volgt.
```

#### Output-template

Sla elke gegenereerde spec op met dit formaat:

```markdown
# Backend Feature Specification

## Metadata

- Feature ID:
- Feature naam:
- Status:
- Auteur:
- Reviewer:
- Datum:
- Gerelateerde user story / ticket:
- Gerelateerde router / module:
- Gerelateerde frontend endpoints:
- Gerelateerde database tabellen:
- Versie:

---

## Doel en scope

### Doel

Beschrijf kort waarom deze feature bestaat.

### In scope

-

### Out of scope

-

---

## Build summary

- Nieuw gebouwd:
- Gewijzigd:
- Verwijderd:
- Beinvloede bestaande flows:

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

---

## API-flows

### Flow ID: BE-FLW-001

- Naam:
- Trigger (HTTP-methode + route of event):
- Voorwaarden (auth, tenant, feature flag):
- Request-pad:
- Service-stappen:
- DB-operaties:
- Successtatus + response:
- Foutpaden:
- Eindtoestand (DB, cache, events):

---

## Detaildocumentatie per artefact

---

## [BE-XXX-001] Naam artefact

### 1. Type

-

### 2. Locatie

- Bestandspad:
- Klasse / functie:

### 3. Gerelateerde flow

-

### 4. Doel

-

### 5. Functionele beschrijving

-

### 6. Technische beschrijving

-

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie:
- Vereiste rol / scope:
- Tenant-isolatie:
- Feature flag:

### 8. Request-specificatie

- Methode:
- Route:
- Path parameters:
- Query parameters:
- Request body (schema):
- Verplichte headers:

### 9. Response-specificatie

- Successtatus:
- Response schema:
- Foutstatussen:

### 10. Validaties en constraints

-

### 11. Business rules

-

### 12. Afhankelijkheden

-

### 13. Foutafhandeling

- 400:
- 401:
- 403:
- 404:
- 409:
- 422:
- 429:
- 500:
- 503:

### 14. Transacties en data-integriteit

-

### 15. Telemetry / logging / tracing

-

### 16. Caching

- Gecached:
- Cache-sleutel:
- TTL:
- Invalidatie:

### 17. Acceptatiecriteria

-
-
-

### 18. Integratoruitleg

-
-
-

### 19. Trainingssamenvatting

- Actor:
- Voorwaarde:
- Actie (request):
- Systeemverwerking:
- Succesrespons:
- Foutrespons:
- Uitzonderingen:

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Beschrijf hier in eenvoudige taal hoe deze API-functionaliteit te gebruiken.

---

## Open aannames

-

## Open vragen

-

## Risico's

-

---

## QA-checks

- [ ] Endpoint functioneel getest (happy path)
- [ ] Alle foutstatus-codes getest
- [ ] Auth en permissies getest
- [ ] Tenant-isolatie getest
- [ ] Validaties getest (ongeldige invoer)
- [ ] Edge cases getest (leeg, null, grenzen)
- [ ] Data-integriteit en transacties getest
- [ ] Performance / load getest (indien relevant)
- [ ] Caching getest (indien van toepassing)
- [ ] Logging en tracing gecontroleerd

---

## Definition of Done

- [ ] Feature is gebouwd
- [ ] Alle endpoints, services en modellen zijn geinventariseerd
- [ ] Alle relevante foutstatussen zijn beschreven
- [ ] Functionele beschrijving aanwezig
- [ ] Technische beschrijving aanwezig
- [ ] Acceptatiecriteria zijn testbaar
- [ ] Integratoruitleg is aanwezig
- [ ] Trainingssamenvatting is aanwezig
- [ ] Open aannames zijn benoemd
- [ ] QA-checks zijn uitgevoerd
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
```

---

### Stap 2 -- Spec reviewen (reviewer prompt)

1. Open een nieuwe AI-sessie.
2. Gebruik de reviewer prompt hieronder als system-prompt.
3. Voeg de gegenereerde spec toe als input.
4. Sla de review op als `docs/backend/review/review-<ID>.md`.
5. Zet als EERSTE regel van dat bestand een expliciete statusregel (zie hieronder).
6. Fix alle CRITICAL en HIGH bevindingen. Herhaal indien nodig.

#### De statusregel -- verplicht in elke NIEUWE review (ADR-036 OP-42)

Zet bovenaan `review-<ID>.md` precies een regel in deze vorm:

```text
STATUS: APPROVED
```

Waarden die de poort als GOEDKEURING leest, en dit is de volledige lijst uit de code
(`REVIEW_STATUS_APPROVING_VALUES`): `APPROVED`, `APPROVED WITH MINOR GAPS`,
`APPROVED WITH MINOR ISSUES`, `APPROVED WITH NOTES`, `GOEDGEKEURD`. Gebruik in nieuwe
reviews `APPROVED` of `APPROVED WITH MINOR GAPS`; de andere drie bestaan omdat ze in het
bestaande corpus voorkomen.

Elke andere waarde weigert de poort -- of hij nu in de afwijzende woordenlijst staat
(`CHANGES_REQUESTED`, `NEEDS REVISION`, `BLOCKED`, en varianten van `NOT APPROVED`) of
helemaal niet herkend wordt. Dat tweede is fail-secure met opzet: anders is een typefout
weer een omzeiling. De toets is op de VOLLEDIGE waarde en niet op het begin ervan, want
`APPROVED PENDING FIXES` en `APPROVED zodra de CRITICAL fixes erin staan` gingen anders
door als goedkeuring -- gemeten 2026-08-31. Zet dus geen toelichting op de statusregel.

**Waarom.** `scripts/validate_feature_docs.py` toetste de status met
`re.search(r"(?<!NOT )APPROVED", inhoud)`. Die lookbehind vangt alleen het ENGELSE
"NOT APPROVED" met exact een spatie, terwijl de reviews hier Nederlandstalig zijn.
Gemeten 2026-08-31: `NIET APPROVED`, `niet APPROVED`, `nog niet APPROVED`,
`NOT_APPROVED` en `NON-APPROVED` gaven allemaal GROEN. Bovendien kan het woord
`APPROVED` in een reviewdocument ook uit iets anders komen dan het verdict: in
`review-BE-EP-022.md` staat het in een SQL-fragment (`WHERE status = APPROVED`) en in
een enumwaarde (`ContentStatus.APPROVED`). Een poort die vrije tekst scant, kan die niet
van een eindoordeel onderscheiden. De statusregel is er om dat te beslechten: staat hij
er, dan is hij de waarheid en wordt de tekst niet meer geraadpleegd.

**Overgang voor de 462 bestaande reviews.** Die hoeven NIET aangepast te worden en gaan
niet in een keer rood. Ontbreekt de statusregel, dan valt de poort terug op de
vrije-tekst-scan -- nu met een ontkenningscheck die Engels en Nederlands dekt, "nog
niet" inbegrepen, en die een ontkenning alleen binnen dezelfde zinsnede laat gelden
(zodat `Geen risico's. **APPROVED**.` blijft slagen). Gemeten over alle 564 bestanden in
`docs/backend/review` + `docs/frontend/review`: geen enkel document verandert van
verdict door deze wijziging, en `python scripts/validate_feature_docs.py` geeft voor en
na exact dezelfde bevindingen. De poort meldt per run hoeveel reviews nog op de terugval
leunen (`[NOTE]`-regel, niet blokkerend), zodat de adoptie zichtbaar is en de terugval
op een dag kan verdwijnen zonder dat iemand hem stil hoeft te missen.

**Wat de terugval NIET kan, en waarom de statusregel er dus toe doet.** Zolang een review
geen statusregel heeft, blijft de poort een tekstscan met een grens die niet te dichten is
zonder echte documenten te breken. Twee vormen halen hem gemeten GROEN terwijl het
eindoordeel afwijst:

- `**Status:** APPROVED` als laatste regel van een lang document waarvan de kop
  `NIET APPROVED` zegt.
- `De enum ContentStatus.APPROVED wordt gebruikt.` onder een kop die
  `CHANGES_REQUESTED` zegt.

Beide structurele uitwegen zijn gemeten en beide zijn verworpen omdat ze bestaande reviews
kapot maken: een afwijzende waarde in de kop laten winnen klapt 56 van de 564 documenten om
(een goedgekeurde review vermeldt in zijn kop vaak "ronde 1 CHANGES_REQUESTED"), en elk
goedkeurend verdict-label buiten de kop als misplaatst veld behandelen klapt er 36 om (het
echte label staat vaak onder regel 15). De statusregel is daarom geen nette formaliteit maar
de enige weg waarlangs dit restrisico verdwijnt -- en de ratchet in
`tests/unit/scripts/test_validate_feature_docs_review_status.py` houdt bij of dat gebeurt.

#### Reviewer prompt

```text
SYSTEM / MASTERPROMPT -- BACKEND DOCUMENTATION & IMPLEMENTATION REVIEWER

Je bent een uiterst kritische reviewer van backend-specificaties en backend-documentatie.

Je taak is om een reeds opgestelde backend-uitwerking te beoordelen op:
1. functionele volledigheid,
2. technische volledigheid,
3. documentatiekwaliteit,
4. testbaarheid,
5. geschiktheid voor LLM-training,
6. geschiktheid voor integratorhandleidingen en API-documentatie.

DOEL
Voer een strenge gap-analyse uit op de aangeleverde backend-uitwerking en detecteer:
- ontbrekende endpoints, services of modellen,
- ontbrekende API-flows,
- onduidelijke beschrijvingen,
- niet-testbare acceptatiecriteria,
- ontbrekende foutstatussen of edge cases,
- inconsistenties tussen functionele en technische beschrijving,
- ontbrekende auth-, tenant- of permissiebeschrijving,
- slechte trainingsdata-kwaliteit,
- slechte integratoruitleg.

BEOORDELINGSKADER
Controleer minimaal op:
- Zijn alle endpoints, services en modellen geinventariseerd?
- Hebben alle artefacten een unieke ID?
- Is per artefact duidelijk wat doel, gedrag en resultaat is?
- Zijn functionele en technische beschrijving gescheiden?
- Zijn alle relevante foutstatussen beschreven (400, 401, 403, 404, 409, 422, 429, 500, 503)?
- Zijn auth, scope en tenant-isolatie beschreven?
- Zijn request en response schema's volledig gespecificeerd?
- Zijn business rules expliciet?
- Is foutafhandeling concreet beschreven (niet alleen "error teruggeven")?
- Zijn transacties en data-integriteit beschreven?
- Zijn telemetry- en logging-notities aanwezig?
- Zijn caching-details beschreven waar van toepassing?
- Zijn acceptatiecriteria volledig en testbaar?
- Is de integratoruitleg eenvoudig genoeg voor niet-backend developers?
- Is de trainingssamenvatting compact, eenduidig en bruikbaar?
- Zijn er impliciete aannames die expliciet gemaakt moeten worden?
- Zijn er conflicten tussen build summary, inventory en detailsecties?
- Zijn API-flows end-to-end beschreven inclusief foutpaden?
- Is de impact op bestaande data of flows beschreven?

VERBODEN REVIEWSTIJL
- Geen algemene feedback zoals "ziet er goed uit".
- Geen vage feedback zoals "meer detail gewenst".
- Geef alleen concrete bevindingen met impact en verbeteractie.

OUTPUTSTRUCTUUR
A. Begin met precies een regel in deze vorm, als eerste regel van de output:
      STATUS: <APPROVED | APPROVED WITH MINOR GAPS | CHANGES_REQUESTED |
               NEEDS REVISION | BLOCKED>
   Dit veld leest de documentatiepoort machinaal (ADR-036 OP-42). Schrijf het
   letterlijk zo: hoofdletters, geen markdown, geen emoji, geen toelichting op
   dezelfde regel. De onderbouwing komt in B en C.
B. EINDOORDEEL: dezelfde waarde als in A, in gewone tekst.
C. SAMENVATTING: korte samenvatting van de documentatiekwaliteit
D. BEVINDINGEN PER CATEGORIE:
   1. Coverage gaps
   2. Functionele onduidelijkheden
   3. Technische onduidelijkheden
   4. Ontbrekende foutstatussen en edge cases
   5. Acceptatiecriteria problemen
   6. Integratorhandleiding / API-uitleg problemen
   7. Trainingsdata problemen
   8. Structuur- en consistentieproblemen
   9. Risico's voor implementatie, security of QA
E. ISSUE REGISTER: tabel met de kolommen Severity, ID of sectie, Probleem,
   Waarom dit een probleem is, Concrete correctie
   Severity: Critical / High / Medium / Low
F. ONTBREKENDE ITEMS: lijst van vermoedelijk ontbrekende endpoints, services, flows of regels
G. VERBETERDE TEKSTVOORSTELLEN: herschrijf zwakke stukken direct in betere vorm
H. RELEASE-OORDEEL:
   - Is dit document geschikt voor bouw / implementatie?
   - Is dit document geschikt voor QA en geautomatiseerd testen?
   - Is dit document geschikt voor LLM-training?
   - Is dit document geschikt voor integratorhandleiding / API-documentatie?

REVIEWREGELS
- Wees streng. Wees concreet. Benoem ook impliciete gaten.
- Als iets niet expliciet beschreven is, markeer het als ontbrekend.
- Als acceptance criteria niet direct testbaar zijn, markeer ze als onvoldoende.
- Als een integratoruitleg te technisch is voor API-consumenten, markeer dit.
- Als een technische beschrijving te vaag is voor implementatie of training, markeer dit.
- Als tenant-isolatie of permissiegedrag niet beschreven is, markeer dit als Critical.
- Doe geen aannames in het voordeel van de auteur.

Voer nu de review uit op de feature-spec die hierna volgt.
```

---

### Stap 3 -- Sprint dag sluit pas na GO

Een sprint dag is pas KLAAR als:

- Alle specs voor die dag bestaan in `docs/backend/features/`
- Alle reviews staan op APPROVED of APPROVED WITH MINOR GAPS, en zeggen dat in hun
  `STATUS:`-regel (zie stap 2) -- niet alleen in de lopende tekst
- Geen CRITICAL of HIGH open issues in `docs/backend/review/`

---

## ID-conventie

| Prefix | Gebruik |
| --- | --- |
| `BE-EP-###` | Endpoint (API-route, inclusief methode) |
| `BE-RTR-###` | Router / APIRouter-groep |
| `BE-SVC-###` | Service-functie of -klasse |
| `BE-MDL-###` | SQLAlchemy model / database entity |
| `BE-SCH-###` | Pydantic schema (request, response of internal) |
| `BE-AGT-###` | AI-agent of capability |
| `BE-TSK-###` | Celery task / background job |
| `BE-MIG-###` | Alembic-migratie |
| `BE-DEP-###` | FastAPI Depends-dependency |
| `BE-MID-###` | Middleware |
| `BE-UTL-###` | Utility-functie of helper |
| `BE-CFG-###` | Configuratievariabele of settings-entry |
| `BE-SEC-###` | Auth guard / permission check / security wrapper |
| `BE-FLW-###` | End-to-end API-flow of data-flow |

Controleer altijd `docs/backend/features/ID-REGISTRY.md` voordat je een nieuw ID toewijst.

---

*Eigenaar: Rakesh Ramkhelawan | ADR: ADR-028 | Laatste update: 2026-05-25*
