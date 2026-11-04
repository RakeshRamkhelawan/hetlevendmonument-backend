# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-035 (endpoints), BE-UTL-049 (gedeelde weigeringshelper)
- Feature naam: Agent-besturingsknoppen weigeren luid in plaats van ongedekt succes te melden
- Status: Gebouwd, Gate 2 doorlopen, wacht op merge-GO
- Auteur: Rakesh Ramkhelawan (via AI-assistent)
- Reviewer: onafhankelijke code-reviewer zonder context (Gate 2, 2026-08-31), twee rondes
- Datum: 2026-08-31
- Gerelateerde user story / ticket: ADR-036 registerrij OP-178 (bijvangst van de OP-03-nameting)
- Gerelateerde router / module: `src/core/api/v1/management/agents_router.py`,
  `src/core/api/management_endpoints.py`, `src/core/api/agent_control_unavailable.py`
- Gerelateerde frontend endpoints: de pauzeknoppen in de agent-beheerschermen
- Gerelateerde database tabellen: geen
- Versie: 2 (versie 1 was de eerste fix, versie 2 verwerkt de Gate 2-bevindingen)

---

## Doel en scope

### Doel

`POST /api/v1/agents/{agent_id}/pause`, `.../resume` en `.../restart` antwoordden met
`{"status": "success", "message": "Agent X paused"}` terwijl hun hele body bestond uit een
logregel en twee appends aan een lijst in het geheugen. Er werd geen agent, geen wachtrij en
geen circuit breaker aangeraakt. Een toezichtsknop die altijd slaagt en nooit werkt is
misleidender dan geen knop: een beheerder die tijdens een incident een ontsporende agent
stilzet, krijgt een groene bevestiging terwijl de agent doorloopt.

### In scope

- De drie knoppen in beide mount-paden luid laten weigeren met HTTP 501.
- Een gedeelde weigeringshelper zodat de tekst en de foutcode op een plek staan.
- Een eerlijke OpenAPI: de routes declareerden `200` en `422`, met een onbereikbare 200.
- Een guard die de INVARIANT bewaakt ("meld geen succes zonder effect"), niet de statuscode.

### Out of scope

- Een echt pauzeermechanisme. Dat vraagt een nieuw, duurzaam per-(tenant, agent) hold plus een
  proces dat het raadpleegt, en is een ontwerpbeslissing met een eigen ADR-traject.
- Het opruimen van het duplicaat tussen de twee mount-paden. Zolang `api/main.py` een tweede
  app-object opbouwt, is de legacy module niet dood te bewijzen en moet de fix op beide plekken
  staan.

---

## Build summary

- Nieuw gebouwd: `src/core/api/agent_control_unavailable.py` (BE-UTL-049), met
  `refuse_agent_control()` en de gedeelde OpenAPI-constante `UNAVAILABLE_RESPONSES`.
- Gewijzigd: de zes handlers in `agents_router.py` en `management_endpoints.py` -- body vervangen
  door de weigering, `status_code` naar 501, `response_model=None`, returntype naar `NoReturn`.
- Verwijderd: de appends aan `log_entries` en de succesresponsen.
- Beinvloede bestaande flows: elke client die vandaag een 200 op deze drie routes verwacht,
  krijgt een 501. Dat is het doel: de 200 was niet gedekt.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-049 | refuse_agent_control | Utility | `src/core/api/agent_control_unavailable.py` | Nieuw | BE-FLW-035 |
| BE-EP-035 | Agent control (pause/resume/restart), beide mount-paden | Endpoint | `src/core/api/v1/management/agents_router.py`, `src/core/api/management_endpoints.py` | Wijziging | BE-FLW-035 |

---

## API-flows

### Flow ID: BE-FLW-035

- Naam: Beheerder vraagt een agent te pauzeren, hervatten of herstarten
- Trigger: `POST /api/v1/agents/{agent_id}/{pause|resume|restart}`
- Voorwaarden: geldig JWT; scope `OAuth2Scope.ADMIN_ALL`
- Request-pad: router -> `get_current_user` -> `require_scopes(ADMIN_ALL)` -> handler
- Service-stappen: handler logt de poging en roept `refuse_agent_control()` aan
- DB-operaties: geen
- Successtatus + response: geen. Deze flow heeft geen succespad zolang er geen hold bestaat.
- Foutpaden: 401 (geen/ongeldig token), 403 (scope ontbreekt), 422 (padparameter ongeldig),
  501 (altijd, zodra de aanroeper langs auth is)
- Eindtoestand: ongewijzigd. Dat is de kern van de fix -- de vorige versie meldde een
  toestandsverandering die er niet was.

---

## Detaildocumentatie per artefact

---

## [BE-UTL-049] refuse_agent_control

### 1. Type

Utility / gedeelde weigeringshelper.

### 2. Locatie

- Bestandspad: `src/core/api/agent_control_unavailable.py`
- Klasse / functie: `refuse_agent_control(action, agent_id, requested_by) -> NoReturn`, plus de
  constanten `ERROR_CODE` en `UNAVAILABLE_RESPONSES`

### 3. Gerelateerde flow

BE-FLW-035.

### 4. Doel

Een besturingsactie weigeren met een expliciete 501 in plaats van een ongedekt succes te melden,
op een plek zodat beide mount-paden dezelfde tekst, foutcode en OpenAPI-beschrijving gebruiken.

### 5. Functionele beschrijving

De aanroeper krijgt een ondubbelzinnig antwoord: deze functie bestaat nog niet, er is niets
gebeurd. De melding noemt de gevraagde actie en de agent, zodat een beheerder weet welke knop
niets deed.

### 6. Technische beschrijving

De module importeert bewust alleen `fastapi` en `logging`, zodat zowel de geserveerde router als
de legacy flat module hem kan gebruiken zonder importcyclus. `refuse_agent_control` schrijft een
`logger.warning` met actie, agent en het gebruikersNUMMER van de aanvrager, en gooit daarna
altijd een `HTTPException` met status 501 en een dict-detail in de projectvorm
`{"success": False, "error": {...}}`.

Gemeten platformgedrag dat hierbij hoort: op een app met `register_exception_handlers` stopt
`src/core/exceptions/handlers.py:72-82` het hele dict-detail in `error.message`. Een client leest
de foutcode dus op `body.detail.error.code`, niet op `body.error.code`. Dat is bestaand gedrag
voor elke `HTTPException` met een dict-detail en staat in de moduledocstring opgeschreven omdat
het afwijkt van wat de gedocumenteerde projectvorm doet vermoeden.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (de helper draait pas na de auth-dependencies van de handler)
- Vereiste rol / scope: n.v.t. op helperniveau
- Tenant-isolatie: n.v.t. -- er wordt niets gelezen of geschreven
- Feature flag: geen

### 8. Request-specificatie

Geen HTTP-oppervlak. Functie-signatuur: `action: str`, `agent_id: str`, `requested_by: str`.
`requested_by` is het gebruikersNUMMER en bewust niet het e-mailadres: `.claude/rules/security.md`
verbiedt persoonsgegevens in logs.

### 9. Response-specificatie

Geen returnwaarde. Het returntype is `NoReturn` -- de functie eindigt altijd in een `raise`.

### 10. Validaties en constraints

Geen. `agent_id` wordt niet geresolved; hij wordt alleen gelogd en teruggegeven.

### 11. Business rules

Meld nooit succes voor een actie die je niet uitvoert. Dit is dezelfde afweging als OP-74:
liever expliciet weigeren dan stil doen alsof.

### 12. Afhankelijkheden

`fastapi` (HTTPException, status) en `logging`. Bewust niets anders.

### 13. Foutafhandeling

- 501: altijd, met `ERROR_CODE = "AGENT_CONTROL_NOT_IMPLEMENTED"`.
- Alle overige statussen worden door de aanroepende handler en zijn dependencies bepaald.

### 14. Transacties en dataintegriteit

Geen. De functie raakt geen database, cache of wachtrij.

### 15. Telemetry / logging / tracing

Een `logger.warning` per weigering, met actie, agent en gebruikersnummer. Bewust GEEN
audit-entry: een 501 is geen autorisatiebesluit -- de aanroeper is al door
`require_scopes(ADMIN_ALL)` gekomen, dus er is geen rechtenweigering om vast te leggen, en een
onveranderde toestand is geen gegevensmutatie. De audit-keten van ADR-019 legt besluiten en
mutaties vast; dit is geen van beide. Zodra er wel een hold-mechanisme is, verandert dat: een
geslaagde pauze is wel een besluit met effect en hoort dan wel in de keten.

### 16. Caching

Niet van toepassing.

### 17. Acceptatiecriteria

- Elke aanroep eindigt in een `HTTPException` met status 501; de functie kan niet normaal
  terugkeren (afgedwongen door het returntype `NoReturn`).
- De foutcode in het detail is `AGENT_CONTROL_NOT_IMPLEMENTED`.
- De logregel bevat geen e-mailadres of andere persoonsgegevens.
- `UNAVAILABLE_RESPONSES` wordt door alle zes routes gebruikt; de tekst staat nergens anders.

### 18. Integratoruitleg

- Deze helper is intern; je roept hem niet zelf aan.
- Zie de endpoint-uitleg hieronder voor wat een client merkt.

### 19. Trainingssamenvatting

- Actor: de FastAPI-handler van een agent-besturingsknop
- Voorwaarde: de aanroeper is geauthenticeerd en heeft de ADMIN_ALL-scope
- Actie (request): de handler roept `refuse_agent_control(actie, agent_id, gebruikersnummer)` aan
- Systeemverwerking: een waarschuwing wordt gelogd; er wordt niets gelezen of geschreven
- Succesrespons: geen -- deze functie keert nooit normaal terug
- Foutrespons: HTTP 501 met foutcode `AGENT_CONTROL_NOT_IMPLEMENTED`
- Uitzonderingen: geen; er is geen invoer die tot een ander pad leidt

---

## [BE-EP-035] Agent control endpoints (pause, resume, restart)

### 1. Type

Endpoint-groep, zes routes over twee mount-paden.

### 2. Locatie

- Bestandspad: `src/core/api/v1/management/agents_router.py` (geserveerd),
  `src/core/api/management_endpoints.py` (legacy flat module)
- Klasse / functie: `pause_agent`, `resume_agent`, `restart_agent` in beide modules

### 3. Gerelateerde flow

BE-FLW-035.

### 4. Doel

De knoppen laten zeggen wat waar is.

### 5. Functionele beschrijving

Een beheerder die op pauze, hervatten of herstarten drukt, krijgt een expliciete weigering met
uitleg dat de functie niet bestaat, in plaats van een groene bevestiging zonder effect.

### 6. Technische beschrijving

Elke handler logt de poging en roept `refuse_agent_control()` aan. De decorator zet
`status_code=501`, `response_model=None` (nodig omdat `NoReturn` geen geldig Pydantic-veldtype
is; gemeten op FastAPI 0.121.1: zonder deze vlag weigert de route te laden met een
`FastAPIError`) en `responses=UNAVAILABLE_RESPONSES`.

Waarom beide modules geraakt zijn: `management_endpoints.py` wordt gemount door
`api/setup/router_registry.py:374` via `api/main.py:160` -- een tweede app-object dat onder
TESTING tot een no-op is gestubd, maar in een `uvicorn src.core.api.main:app`-start wel de oude
handlers serveert. Zolang die mount bestaat, mag de leugen daar net zo min staan.

Waarom een 501 en geen echte pauze, gemeten en niet aangenomen. Er zijn twee kandidaten en geen
van beide is een operator-hold:

1. `AgentCircuitBreaker`. Openen kan alleen via de private `_open_circuit()`, en `allow()` draait
   een OPEN circuit zelf terug naar HALF_OPEN zodra `reset_timeout_seconds` verstreken is --
   default 30 seconden. Een pauze via die weg vervalt dus stil na een halve minuut.
2. `AgentConfig.is_active`. `AgentRunner.start()` laadt de actieve configs EENMALIG en de lus
   herleest ze nooit, dus een agent die al draait stopt niet door de vlag om te zetten.

En het argument dat boven beide uit gaat: de pacemaker draait niet. `AgentRunner(` komt nul keer
voor in `src/` en `scripts/`, en `agent_runner` staat in geen enkel compose-bestand en in geen
workflow. Ook een correct geopend circuit zou dus door niemand gelezen worden.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT via `get_current_user_dependency`
- Vereiste rol / scope: `OAuth2Scope.ADMIN_ALL`
- Tenant-isolatie: niet van toepassing -- er wordt geen tenant-data gelezen of geschreven. De
  endpoints hebben geen `tenant_id` en geen agent-registry om `agent_id` tegen te resolven; dat
  is een van de redenen dat een echte pauze hier vandaag niet te bouwen is.
- Feature flag: geen

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/agents/{agent_id}/pause`, `/resume`, `/restart`
- Path parameters: `agent_id: str`
- Query parameters: geen
- Request body: geen
- Verplichte headers: `Authorization: Bearer <token>`

### 9. Response-specificatie

- Successtatus: geen. Er is geen succespad.
- Response schema: geen (`response_model=None`)
- Foutstatussen: 401, 403, 422, 501

### 10. Validaties en constraints

`agent_id` moet een string zijn; FastAPI geeft 422 bij een ontbrekende padparameter. Er is geen
validatie op bestaan van de agent, want er is niets om tegen te resolven.

### 11. Business rules

Geen bevestiging zonder effect.

### 12. Afhankelijkheden

`get_current_user_dependency`, `require_scopes(OAuth2Scope.ADMIN_ALL)`, BE-UTL-049.

### 13. Foutafhandeling

- 400: niet van toepassing
- 401: ontbrekend of ongeldig token (auth-dependency)
- 403: token zonder de ADMIN_ALL-scope (scope-dependency)
- 404: niet van toepassing -- er wordt geen resource opgezocht
- 409: niet van toepassing
- 422: ongeldige padparameter (FastAPI-validatie)
- 429: via de generieke rate limiting van het platform, niet per endpoint
- 500: niet verwacht; de handler heeft geen pad dat kan falen behalve de bedoelde 501
- 503: niet van toepassing -- er is geen downstream afhankelijkheid

### 14. Transacties en dataintegriteit

Geen. De eindtoestand is per definitie gelijk aan de begintoestand.

### 15. Telemetry / logging / tracing

Twee regels per aanroep: de `logger.info` in de handler en de `logger.warning` uit BE-UTL-049.
Geen audit-entry, om de reden die bij BE-UTL-049 staat.

### 16. Caching

- Gecached: nee
- Cache-sleutel: n.v.t.
- TTL: n.v.t.
- Invalidatie: n.v.t.

### 17. Acceptatiecriteria

- Alle zes handlers gooien een `HTTPException` met status 501 (unittest, geparametriseerd over
  de zes; niet drie -- beide modules bevatten alle drie).
- Via een echte `TestClient` komt de 501 ook daadwerkelijk bij de client aan.
- De guard wordt ROOD bij elk van deze mutaties op echte code: een validatie-`raise` naast een
  succes-return; een weigering in EEN tak met succes in de andere; de oude body terug.
- De guard blijft GROEN bij een legitieme implementatie (echt werk plus een succesantwoord).
- De OpenAPI declareert 501 en niet 200.

### 18. Integratoruitleg

- Deze drie routes geven altijd 501. Bouw geen client-logica op een 200.
- De foutcode staat op `body.detail.error.code` en is `AGENT_CONTROL_NOT_IMPLEMENTED`.
- Krijg je 401 of 403, dan is dat je token of je scope -- niet deze functie.
- Zodra er een echt pauzeermechanisme is, verandert het antwoord. Behandel 501 dus als
  "voorlopig niet beschikbaar", niet als "bestaat nooit".

### 19. Trainingssamenvatting

- Actor: beheerder met de ADMIN_ALL-scope
- Voorwaarde: geldig JWT en de juiste scope
- Actie (request): `POST /api/v1/agents/{agent_id}/pause` (of `/resume`, `/restart`)
- Systeemverwerking: de poging wordt gelogd; er wordt geen agent, wachtrij of circuit breaker
  aangeraakt
- Succesrespons: geen -- deze endpoints hebben geen succespad
- Foutrespons: HTTP 501 met foutcode `AGENT_CONTROL_NOT_IMPLEMENTED`
- Uitzonderingen: 401 zonder geldig token, 403 zonder de ADMIN_ALL-scope, 422 bij een ongeldige
  padparameter

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De drie besturingsknoppen voor agents zijn nog niet gebouwd. Ze antwoorden daarom met HTTP 501
en een foutcode `AGENT_CONTROL_NOT_IMPLEMENTED`. Tot voor kort gaven ze een 200 met
`{"status": "success"}` terwijl er niets gebeurde; als je client daarop leunt, moet die
aangepast worden. Toon de gebruiker geen bevestiging op deze routes.

De foutcode vind je op `body.detail.error.code`. Dat wijkt af van wat je zou verwachten: de
platform-foutafhandelaar verpakt het hele detail nog een keer, dus `body.error.code` bestaat
niet.

---

## Open aannames

- Het duplicaat in `management_endpoints.py` blijft bereikbaar zolang `api/main.py` een tweede
  app-object opbouwt. Dat is niet dood te bewijzen, dus beide paden zijn gefixt. Als iemand later
  aantoont dat die mount weg kan, mag de legacy module in zijn geheel weg.

## Open vragen

- Wanneer wordt een echt hold-mechanisme ontworpen? Dat bepaalt wanneer deze 501 verdwijnt.

## Risico's

- Een client die vandaag op de 200 leunt, breekt. Dat is bedoeld en is de reden dat dit als een
  registerrij (OP-178) is vastgelegd in plaats van als een stille wijziging.
- Bekend restgat in de guard, opgeschreven en niet weggemoffeld: een handler met een eigen
  responsmodel telt als "effect" en blijft groen. Dat gat wordt gedekt door de unittest die voor
  alle zes handlers hard op 501 asserteert.

---

## QA-checks

- [x] Endpoint functioneel getest (er is geen happy path; de weigering is getest)
- [x] Alle foutstatus-codes getest die deze endpoints zelf produceren (501 via handler en via
      TestClient)
- [x] Auth en permissies getest (de scope-dependency blijft ongewijzigd en actief)
- [ ] Tenant-isolatie getest -- niet van toepassing, er is geen tenant-data
- [x] Validaties getest (ongeldige padparameter geeft 422 via FastAPI)
- [x] Edge cases getest (alle zes handlers, beide modules)
- [ ] Dataintegriteit en transacties getest -- niet van toepassing
- [ ] Performance / load getest -- niet relevant voor een constante weigering
- [ ] Caching getest -- niet van toepassing
- [x] Logging en tracing gecontroleerd (geen PII in de logregel)

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
- [x] Review door reviewer-prompt: zie `docs/backend/review/review-BE-EP-035.md` en
      `docs/backend/review/review-BE-UTL-049.md`
