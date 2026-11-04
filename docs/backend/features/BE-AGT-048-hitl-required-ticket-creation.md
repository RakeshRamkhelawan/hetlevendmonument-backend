# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-048 (primair), BE-SEC-046 (secundair, zie artefact 2)
- Feature naam: HITL_REQUIRED maakt een echt goedkeuringsticket aan (ADR-036 OP-163)
- Status: GEBOUWD, wacht op review
- Auteur: Claude (sprint-uitvoering, ADR-036 fix-sprint Dag 2)
- Reviewer: onafhankelijke doc-reviewer-agent
- Datum: 2026-08-18
- Gerelateerde user story / ticket: ADR-036 fix-sprint, Dag 2 (`docs/agent-briefs/generated/2026-08-18-sprint-dag-2.md`)
- Gerelateerde router / module: `src.core.als.agents.specialist_base`, `src.core.tool_broker.hitl_repository`, `src.core.api.v1.tool_broker.hitl_router`, `src.core.copilot.protocols`
- Gerelateerde frontend endpoints: geen (dit is een intern OODA-uitvoeringspad, geen nieuwe HTTP-route)
- Gerelateerde database tabellen: `hitl_tickets` (bestaande tabel, geen schema-wijziging -- de nieuwe sleutel `_executing_identity` leeft in de bestaande JSONB-kolom `payload`)
- Versie: v1

---

## Doel en scope

### Doel

Tot deze fix behandelde `_council_rejection()` (het Council-poort-mechanisme dat elke tool-actie
van een ALS-skill toetst) het verdict `HITL_REQUIRED` IDENTIEK aan `BLOCKED`: de actie werd
afgewezen en er kwam nooit een echt goedkeuringsticket. Dat is het omgekeerde van "menselijk
toezicht" zoals EU AI Act art. 14 dat eist (de toezichthouder moet de output daadwerkelijk kunnen
goedkeuren of tegenhouden, niet dat de actie stil verdwijnt zonder dat een mens er ooit over kan
beslissen). Deze fix voegt een echte, DB-backed ticket-aanmaak toe op dit pad, door het reeds
bestaande, geteste mechanisme (`HITLTicketRepository.create_hitl_request()`, al gebruikt door
`copilot/service.py` op het HTTP Co-Pilot-pad) ook op dit ALS-skillpad aan te roepen.

Tijdens het bouwen bleek een TWEEDE, gerelateerd gebrek: `create_hitl_request()` toetste de
permissiecheck bij ticket-aanmaak altijd tegen de hardcoded identiteit `"copilot"`
(`_UITVOERENDE_IDENTITEIT`). De piloot-skill (`skillsgaptraining`) heeft in
`config/tool_permissions.yml` een grotendeels afwijkende toolset ten opzichte van `copilot` --
beide profielen delen alleen `send_notification`; `query_hr_database`, de tool die deze fix
concreet raakt, staat UITSLUITEND in het profiel van `skillsgaptraining`. Zonder fix zou ELK
ticket vanuit het ALS-pad voor een piloot-specifieke tool onvoorwaardelijk op deze permissiecheck
stuklopen, ongeacht of de piloot de tool wel degelijk mag uitvoeren -- dit had de Dag 2-fix zelf
voor haar enige praktische toepassing (de piloot) laten mislukken. Dit is artefact 2 (BE-SEC-046)
in deze spec.

### In scope

- `_council_rejection()` in `specialist_base.py`: nieuwe branch voor `DecisionVerdict.HITL_REQUIRED`
  die een echt ticket aanmaakt en de ticketref teruggeeft in de foutmelding.
- `create_hitl_request()` in `hitl_repository.py`: nieuw keyword-argument `executing_identity`
  (default `"copilot"`, backwards compatible), gebruikt voor de permissiecheck EN opgeslagen in de
  payload (`_executing_identity`).
- `_voer_goedgekeurde_actie_uit()` / `approve_hitl_request()` in `hitl_router.py`: leest
  `_executing_identity` terug uit het ticket en gebruikt DEZELFDE identiteit bij het VERZILVEREN
  (uitvoeren) van de goedgekeurde actie, zodat de permissiecheck bij aanmaken en de uitvoering bij
  goedkeuren nooit uit elkaar kunnen lopen.
- `IHITLRepository`-protocol in `copilot/protocols.py`: signatuur bijgewerkt met dezelfde parameter
  (literale default, geen import van de private constante -- ADR-033/034-laagscheiding).
- Testfixture `hitl_ticket_repository` in `tests/fixtures/agent_governance.py` (niet-autouse, zie
  sectie Risico's) plus de drie conftest-bestanden die hem re-exporteren
  (`tests/unit/agents/conftest.py`, `tests/unit/als/conftest.py`,
  `tests/unit/tool_broker/conftest.py`), plus mutatiebewijs in beide richtingen.
- Een architectuur-neutrale implementatiekeuze (`importlib.import_module` in plaats van een
  statische top-level import) om de bestaande Ce-ceiling van `agent_runtime`
  (`tests/architecture/test_dsm_008_reclassification.py`, ceiling 225) niet te overschrijden.

### Out of scope

- D4-001/D4-002 (Annex III-classificatie van de piloot-skill, die een APPROVED-verdict alsnog naar
  HITL_REQUIRED moet dwingen) -- dat is Dag 3 van dezelfde sprint en bouwt op DEZE fix.
- Het generieke `always_hitl_actions`-mechanisme (D4-003) -- Dag 5.
- `_executing_identity` permanent bewaren na resolutie (`_BLIJFT`-tuple in `hitl_repository.py`) --
  bewust uitgesteld, zie de code-comment boven `_BLIJFT` en de "Open aannames"-sectie hieronder.
- De HTTP-route `POST /hitl/request` -- niet gemount, blijft buiten scope (ongewijzigd).

---

## Build summary

- Nieuw gebouwd: geen nieuwe endpoints, modellen of migraties.
- Gewijzigd:
  - `src/core/als/agents/specialist_base.py` (`_council_rejection()`)
  - `src/core/tool_broker/hitl_repository.py` (`create_hitl_request()`, `_BLIJFT`-commentaar)
  - `src/core/api/v1/tool_broker/hitl_router.py` (`_voer_goedgekeurde_actie_uit()`,
    `approve_hitl_request()`)
  - `src/core/copilot/protocols.py` (`IHITLRepository`)
  - `tests/fixtures/agent_governance.py` (nieuwe, niet-autouse `hitl_ticket_repository`-fixture)
  - `tests/unit/agents/conftest.py`, `tests/unit/als/conftest.py`,
    `tests/unit/tool_broker/conftest.py` (importeren de nieuwe fixture, geen ander gedrag)
  - `tests/unit/api/test_approve_executes_with_the_creating_identity.py` (nieuw, toegevoegd na de
    verplichte blinde eindreview -- zie Ronde 3 in `review-BE-AGT-048.md`): bewijst dat
    `approve_hitl_request()` daadwerkelijk met de bij aanmaken bewaarde identiteit verzilvert,
    niet alleen dat `create_hitl_request()` die identiteit correct opslaat.
- Verwijderd: niets.
- Beinvloede bestaande flows: elke ALS-skill-tool-actie die door de Council naar `HITL_REQUIRED`
  wordt gestuurd (vandaag concreet alleen bereikbaar via de piloot-skill `skillsgaptraining`, zie
  Business rules); het bestaande HTTP Co-Pilot HITL-pad (`copilot/service.py`) blijft ongewijzigd
  qua gedrag (default-parameter behoudt de oude aanroep).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-048 | `_council_rejection()` HITL_REQUIRED-branch | BE-AGT (agent-gedrag) | `src/core/als/agents/specialist_base.py` | Wijziging | BE-FLW-058 |
| BE-SEC-046 | `executing_identity`-parameter op `create_hitl_request` + verzilverpad | BE-SEC (permissiecheck) | `src/core/tool_broker/hitl_repository.py`, `src/core/api/v1/tool_broker/hitl_router.py`, `src/core/copilot/protocols.py` | Wijziging | BE-FLW-058 |

---

## API-flows

### Flow ID: BE-FLW-058

- Naam: ALS-skill tool-actie krijgt HITL_REQUIRED -> echt goedkeuringsticket -> latere goedkeuring
  voert de actie uit met de juiste identiteit.
- Trigger: geen HTTP-request -- interne aanroep binnen de OODA-loop
  (`BaseSpecialistAgent.act() -> _council_rejection()`), gestart doordat een skill
  (`execute_with_manifest_prompt()`) een `TOOL_CALL` produceert en de Council een `HITL_REQUIRED`-
  verdict teruggeeft.
- Voorwaarden: een bekende initiator (`self._initiated_by_user_id is not None`, afgedwongen door
  `_reject_before_council()` die hiervoor al loopt); de tool moet een bekende tool zijn
  (`is_known_tool`); de aanvragende agent-identiteit (`self.agent_id`) moet de tool mogen volgens
  `config/tool_permissions.yml`.
- Request-pad: `act()` -> `_council_rejection(tool_name, params)` -> (verdict HITL_REQUIRED) ->
  `HITLTicketRepository(db).create_hitl_request(..., executing_identity=self.agent_id)`.
- Service-stappen:
  1. `is_known_tool(tool)` -- weigert een onbekende tool vroeg en luid (`ValueError`).
  2. `ToolPermissionManager().is_tool_allowed(executing_identity, tool)` -- weigert als de
     aanvragende identiteit de tool niet mag (`PermissionError`).
  3. `HITLTicketRepository.create(...)` -- schrijft de rij, `flush()` binnen de sessie die
     `get_db_session()` beheert.
  4. `get_db_session()`'s eigen `commit()` bij succesvol verlaten van het `async with`-blok.
- DB-operaties: `INSERT INTO hitl_tickets (..., payload)`, waarbij `payload` de originele
  `action_params` bevat plus `_decision_id`, `_reason`, `_requested_by`, `_requested_at`,
  `_executing_identity`.
- Successtatus + response: geen HTTP-response (intern pad). `_council_rejection()` geeft een
  string terug met de ticketref; `act()` neemt die op in `result_data["errors"]`, zodat de
  aanroeper weet dat er een ticket klaarstaat in plaats van dat de actie zonder spoor verdween.
- Foutpaden: `ValueError` (onbekende tool) of `PermissionError` (identiteit mag de tool niet)
  propageren uit `_council_rejection()` naar `act()`'s bestaande brede `except Exception`
  (regel ~692-705 in `specialist_base.py`), die logt met `exc_info=True` en de tool-actie als
  mislukt registreert -- geen enkele van deze fouten laat de tool alsnog uitvoeren.
- Eindtoestand: een `hitl_tickets`-rij met `status="pending"`; GEEN wijziging aan de tool zelf (die
  is niet uitgevoerd). Bij een latere `POST /api/v1/tools/hitl/approve` (bestaand, ongewijzigd
  endpoint) leest `approve_hitl_request()` `_executing_identity` terug uit `ticket.payload` (VOOR
  `repo.approve()` de payload overschrijft) en voert de actie uit met DEZELFDE identiteit die bij
  aanmaken is getoetst.

---

## Detaildocumentatie per artefact

---

## [BE-AGT-048] `_council_rejection()` HITL_REQUIRED-branch

### 1. Type

- Agent-gedrag (interne methode van `BaseSpecialistAgent`, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/als/agents/specialist_base.py`
- Klasse / functie: `BaseSpecialistAgent._council_rejection()`

### 3. Gerelateerde flow

- BE-FLW-058

### 4. Doel

- Zorgen dat een `HITL_REQUIRED`-verdict van de Council daadwerkelijk leidt tot een menselijk
  goedkeuringsmoment (AI Act art. 14), in plaats van dat de actie stil wordt afgewezen zoals bij
  `BLOCKED`/`DEFERRED`/`MODIFIED`.

### 5. Functionele beschrijving

- Wanneer een ALS-skill een tool wil uitvoeren en de Council daarover `HITL_REQUIRED` beslist,
  ontstaat er een concreet, voor een mens zichtbaar goedkeuringsticket (zichtbaar via de bestaande
  `/hitl/pending`-lijst; GEEN live pushmelding -- zie sectie 6 voor waarom). De
  actie wordt niet uitgevoerd totdat een tenant-admin het ticket goedkeurt. Bij goedkeuring voert
  het systeem de actie automatisch uit (bestaand gedrag van `approve_hitl_request()`, ongewijzigd
  behalve de identiteit waarmee wordt uitgevoerd).
- Effect op systeemtoestand: een nieuwe rij in `hitl_tickets` (`status="pending"`); geen effect op
  de tool zelf.

### 6. Technische beschrijving

- Bestandspad: `src/core/als/agents/specialist_base.py:369-411` (na de bestaande
  `DecisionVerdict.APPROVED`-check op regel 366-367, voor de generieke rejection-string op regel
  418 die voor `BLOCKED`/`DEFERRED`/`MODIFIED` blijft gelden).
- Dataflow: `act()` -> `_council_rejection(tool_name, params)` -> `request_council_decision_for_agent()`
  (ongewijzigd) -> bij `HITL_REQUIRED`: `importlib.import_module("src.core.database.session").get_db_session()`
  (async context manager, commit-on-success) -> `importlib.import_module("src.core.tool_broker.hitl_repository").HITLTicketRepository(db).create_hitl_request(...)`.
- `importlib.import_module` in plaats van een statische top-level `from ... import ...`: zelfde
  techniek als al aanwezig in deze klasse's `__init__` (regel ~109, voor `database.database`).
  Reden: `tests/architecture/test_dsm_008_reclassification.py::test_agent_runtime_ce_dag2_final_target`
  telt elke `ast.ImportFrom`-STATEMENT in `agent_runtime`'s bronbestanden tegen een vaste ceiling
  van 225 (`scan_module(..., unique_pairs=False)` in `scripts/dsm_full_analysis.py` telt per
  statement, niet per uniek doel-bucket). Twee statische imports duwden Ce naar 227; `importlib`
  voor beide bracht het terug naar 225 (gemeten, zie Acceptatiecriteria).
- Geen externe calls buiten de database; geen nieuwe caching; geen nieuwe events (de bestaande
  websocket-notificatie bij ticketaanmaak zit al in `HITLStore`/`hitl_notifier`, niet in dit pad --
  `create_hitl_request()` roept die vandaag niet aan, ongewijzigd door deze fix).
- `user_id=cast(int, self._initiated_by_user_id)`: veilig, want `_reject_before_council()` (regel
  ~227-267, aangeroepen door `act()` VOOR `_council_rejection()`) geeft al een afwijzing terug als
  `self._initiated_by_user_id is None`, dus dit pad wordt nooit bereikt zonder bekende initiator.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne methode-aanroep, geen HTTP-laag).
- Vereiste rol / scope: n.v.t. op dit pad; het LATERE goedkeuren van het ticket vereist
  `is_tenant_admin` (bestaand, ongewijzigd, in `hitl_router.py::_require_approver`).
- Tenant-isolatie: `tenant_id=self.tenant_id` (agent-niveau, nooit uit `params`/modeloutput);
  `HITLTicketRepository.create()` schrijft de rij met die `tenant_id`, en `get()`/`approve()`
  filteren er altijd op (bestaand gedrag, ongewijzigd).
- Feature flag: geen.

### 8. Request-specificatie

- n.v.t. (geen HTTP-endpoint). Functie-signatuur: `async def _council_rejection(self, tool_name: str, params: dict[str, Any]) -> str | None`.

### 9. Response-specificatie

- Succes (verdict APPROVED): retourneert `None` (ongewijzigd).
- Verdict HITL_REQUIRED: retourneert een string
  `"Council-verdict hitl_required: <reden> (goedkeuringsticket aangemaakt: <ticket_ref>)"`.
- Verdict BLOCKED/DEFERRED/MODIFIED: ongewijzigd, `"Council-verdict <verdict>: <reden>"`.
- Fout: `ValueError` (onbekende tool) of `PermissionError` (identiteit mag tool niet) propageren
  naar de aanroeper (`act()`'s bestaande `except Exception`, zie Foutafhandeling).

### 10. Validaties en constraints

- `tool_name` moet een bekende tool zijn (`is_known_tool`, gedeeld met het uitvoerpad -- geen
  tweede lijst, ADR-036 OP-78).
- `self.agent_id` (de `executing_identity`) moet de tool mogen volgens
  `config/tool_permissions.yml` (ADR-015 default-deny: onbekende identiteit -> altijd geweigerd).

### 11. Business rules

- Alleen `HITL_REQUIRED` verandert van gedrag; `BLOCKED`/`DEFERRED`/`MODIFIED` blijven een kale
  afwijzing (bewust -- zie de docstring van `_council_rejection()` voor waarom `MODIFIED` niet kan
  worden doorgelaten).
- Het mechanisme is generiek voor alle 135 ALS-skills, maar de ACTUELE blootstelling is vandaag
  beperkt tot de piloot (`skillsgaptraining`): de overige 134 skills bereiken de Council via dit
  pad nooit, omdat `_reject_before_council()` ze eerder weigert op "geen initiator bekend"
  (bewaakt door `tests/unit/als/test_agent_governance_hardening.py::TestOodaPathHasNoInitiator`).
  Toekomstige skills met een initiator raken hetzelfde pad zodra ze die krijgen.
- Per actie, niet per invocatie: als een enkel antwoord van de skill meerdere `TOOL_CALL`s bevat
  die elk `HITL_REQUIRED` opleveren (begrensd door `budget.max_steps`), ontstaat er per tool-call
  een EIGEN, onafhankelijk ticket -- niet een verzameld ticket voor het hele antwoord. Dit volgt
  uit de bestaande "Council per actie"-regel (zie de docstring van `_council_rejection()`), niet
  uit nieuwe logica in deze fix.

### 12. Afhankelijkheden

- `request_council_decision_for_agent()` (ongewijzigd) voor het verdict zelf.
- `HITLTicketRepository.create_hitl_request()` (BE-SEC-046, zie hieronder) voor de ticket-aanmaak.
- `get_db_session()` (`src/core/database/session.py`, ongewijzigd) voor de databasesessie.

### 13. Foutafhandeling

- 400/401/403/404/409/422/429/503: n.v.t., geen HTTP-laag op dit pad.
- 500-equivalent: elke exceptie uit de nieuwe branch (DB-fout, `ValueError`, `PermissionError`)
  wordt door `act()`'s bestaande brede `except Exception` (regel ~692-705) afgevangen, gelogd met
  `exc_info=True`, en omgezet in een mislukte tool-actie (`result.success = False`,
  `errors`-lijst). Geen enkele fout laat de tool alsnog uitvoeren (fail-closed). Een DB-fout
  tijdens de INSERT zelf (bv. een verbindingsstoring NA een geslaagde permissiecheck) valt onder
  dezelfde vangst: `get_db_session()` rollt de sessie terug (zie Transacties en dataintegriteit),
  er blijft geen half aangemaakt ticket staan, en de tool wordt niet uitgevoerd.

### 14. Transacties en dataïntegriteit

- `get_db_session()` commit't automatisch bij succesvol verlaten van het `async with`-blok,
  rollt terug bij een exceptie (bestaand gedrag van die context manager, ongewijzigd).
- Geen open transactie tijdens externe I/O: de enige operatie binnen het blok is de ticket-insert
  zelf (`db.add()` + `db.flush()` binnen `create()`).

### 15. Telemetry / logging / tracing

- `hitl_repository.created`-logregel (bestaand, in `HITLTicketRepository.create()`) met
  `ticket_ref`, `tenant_id`, `tool_name` -- geen wijziging nodig, deze fix roept een bestaand pad
  aan.
- Bij een fout: `act()`'s bestaande logregel (`Agent {id}: tool {naam} geweigerd door de
  governance-poort...`) met `exc_info=True`.

### 16. Caching

- Geen caching op dit pad.

### 17. Acceptatiecriteria

- Een skill-actie die `HITL_REQUIRED` krijgt, resulteert in een `hitl_tickets`-rij met
  `status="pending"` en `tool_name` gelijk aan de gevraagde tool (bewezen:
  `tests/unit/als/test_council_gate_per_action.py::TestHitlRequiredCreatesATicket`).
- De tool wordt NIET uitgevoerd op dit pad (`broker.execute_tool.await_count == 0`, bewezen in
  dezelfde test en in de bestaande parametrized `test_non_approving_verdict_prevents_execution`).
- De teruggegeven foutmelding bevat de ticketref, zodat de aanroeper weet dat er een ticket
  klaarstaat.
- `agent_runtime`'s Ce blijft `<= 225`
  (`tests/architecture/test_dsm_008_reclassification.py::test_agent_runtime_ce_dag2_final_target`,
  gemeten 225 na de `importlib`-aanpassing).

**Verificatiebewijs (eenmalig, tijdens de bouw uitgevoerd -- geen doorlopend CI-criterium):**
met de productiecode teruggezet naar de vorige commit (git stash), faalden
`TestHitlRequiredCreatesATicket` (0 aanroepen naar `create_hitl_request`) en de nieuwe
identiteitstests in `test_hitl_repository.py` (`TypeError`/`KeyError`); met de fix teruggezet
slaagden ze weer.

### 18. Integratoruitleg

- Dit is geen publieke API -- er is geen nieuw endpoint voor externe consumenten.
- Voor teams die de piloot-skill (skills-gap-analyse) integreren: een `HITL_REQUIRED`-uitkomst
  betekent vanaf nu dat er een echt goedkeuringsticket klaarstaat (zichtbaar via de bestaande
  `GET /api/v1/tools/hitl/pending`-route), niet dat het verzoek genegeerd is.
- Bestaande integraties met het HTTP Co-Pilot-pad (`copilot/service.py`) merken niets van deze
  wijziging: die blijft de default-identiteit (`copilot`) gebruiken.

### 19. Trainingssamenvatting

- Actor: een ALS-skill (vandaag concreet: de piloot `skillsgaptraining`), namens een menselijke
  initiator.
- Voorwaarde: de Council heeft de voorgestelde tool-actie beoordeeld met verdict `HITL_REQUIRED`;
  er is een bekende initiator; de tool is bekend en de skill mag de tool volgens haar profiel.
- Actie (request): de skill probeert een tool uit te voeren via `TOOL_CALL` in haar antwoord.
- Systeemverwerking: `_council_rejection()` maakt een `hitl_tickets`-rij aan
  (`status="pending"`) met de originele parameters, de reden van de Council, en de aanvragende
  identiteit; de tool wordt niet uitgevoerd.
- Succesrespons: een stringresultaat met de ticketref, opgenomen in `result_data["errors"]`.
- Foutrespons: `ValueError` (onbekende tool) of `PermissionError` (identiteit mag tool niet),
  afgevangen door `act()` en omgezet in een mislukte actie.
- Uitzonderingen: `BLOCKED`/`DEFERRED`/`MODIFIED`-verdicten blijven een kale afwijzing zonder
  ticket (bewust, geen omissie).

---

## [BE-SEC-046] `executing_identity`-parameter op `create_hitl_request` + verzilverpad

### 1. Type

- Permissiecheck / security-wrapper (BE-SEC).

### 2. Locatie

- Bestandspad: `src/core/tool_broker/hitl_repository.py` (`create_hitl_request()`),
  `src/core/api/v1/tool_broker/hitl_router.py` (`_voer_goedgekeurde_actie_uit()`,
  `approve_hitl_request()`), `src/core/copilot/protocols.py` (`IHITLRepository`).

### 3. Gerelateerde flow

- BE-FLW-058

### 4. Doel

- De permissiecheck bij het AANMAKEN van een HITL-ticket moet de identiteit van de AANVRAGENDE
  agent toetsen, niet altijd de hardcoded `"copilot"` -- anders zou elk ticket vanuit een andere
  agent-identiteit (met een ander toolprofiel) onterecht op de permissiecheck stuklopen, of erger:
  een verkeerde identiteit zou bij VERZILVEREN de actie uitvoeren met andere rechten dan waarmee
  hij is goedgekeurd.

### 5. Functionele beschrijving

- Wanneer een niet-copilot-identiteit (vandaag: de piloot-skill) om goedkeuring vraagt voor een
  tool die zij wel mag uitvoeren, slaagt de aanvraag nu waar hij voorheen altijd faalde.
- Wanneer een identiteit een tool aanvraagt die zij NIET mag uitvoeren, faalt de aanvraag luid
  (`PermissionError`) in plaats van een doodlopend goedkeuringsticket aan te maken.
- Bij goedkeuring voert het systeem de actie uit met DEZELFDE identiteit die bij aanmaken is
  getoetst -- nooit een andere.

### 6. Technische beschrijving

- `create_hitl_request(..., executing_identity: str = _UITVOERENDE_IDENTITEIT)`: de default
  behoudt het bestaande gedrag voor de enige bestaande aanroeper (`copilot/service.py`, die dit
  argument weglaat). De permissiecheck (`ToolPermissionManager().is_tool_allowed(...)`) gebruikt
  nu deze parameter. De waarde wordt opgeslagen in `payload["_executing_identity"]` (NA de
  spreiding van `action_params`, net als `_decision_id`/`_requested_by`/`_requested_at`).
- `hitl_router.py::approve_hitl_request()`: leest `ticket.payload.get("_executing_identity",
  _UITVOERENDE_IDENTITEIT)` VOOR `repo.approve()` wordt aangeroepen (die de payload overschrijft
  naar een kale besluitprojectie) en geeft die identiteit door aan `_voer_goedgekeurde_actie_uit(
  ..., uitvoerende_identiteit=...)`, die het als `agent_id` doorgeeft aan `broker.execute_tool()`.
- `_executing_identity` staat NIET in `_BLIJFT` (overleeft de resolutie-wipe niet) -- bewuste,
  gedocumenteerde keuze, zie Open aannames.
- `IHITLRepository`-protocol: dezelfde parameter met een LETTERLIJKE default `"copilot"` (geen
  import van de private `_UITVOERENDE_IDENTITEIT`-constante, om geen `copilot -> tool_broker`
  laagoverschrijding te introduceren die ADR-033/034 niet toestaat voor dit protocolbestand).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. op `create_hitl_request` zelf (interne repository-methode); het
  bestaande `approve`/`reject`-endpoint blijft `is_tenant_admin`-only (ongewijzigd).
- Tenant-isolatie: ongewijzigd -- alle bestaande tenant-filters blijven intact.
- `executing_identity` komt ALTIJD van de aanroepende code (`self.agent_id` in
  `specialist_base.py`, een code-bundled manifest-waarde) of van de default -- nooit uit
  request-body, modeloutput of een ander niet-vertrouwd kanaal (bevestigd door de
  Gate 2-security-review, zie Risico's).

### 8. Request-specificatie

- n.v.t. (interne Python-functie, geen HTTP-endpoint). Signatuur:
  `async def create_hitl_request(self, *, tenant_id: int, user_id: int, decision_id: str, reason: str, action_type: str, action_params: dict[str, object], executing_identity: str = "copilot") -> str`.

### 9. Response-specificatie

- Succes: `str` (ticket_ref).
- Fout: `ValueError` (onbekende tool) of `PermissionError` (identiteit mag tool niet).

### 10. Validaties en constraints

- `is_known_tool(action_type)` moet `True` zijn.
- `ToolPermissionManager().is_tool_allowed(executing_identity, action_type)` moet `True` zijn.

### 11. Business rules

- De identiteit die bij AANMAKEN wordt getoetst is ALTIJD dezelfde die bij VERZILVEREN uitvoert --
  dit was ook al de eis vóór deze fix (ADR-036 OP-90), nu generiek gemaakt in plaats van hardcoded
  op `"copilot"`.

### 12. Afhankelijkheden

- `ToolPermissionManager.is_tool_allowed()` (ongewijzigd).
- `config/tool_permissions.yml` (ongewijzigd -- geen nieuwe profielen nodig voor deze fix).

### 13. Foutafhandeling

- `ValueError`/`PermissionError` propageren naar de aanroeper (in `specialist_base.py`: naar
  `act()`'s bestaande exception-handling; in `copilot/service.py`: ongewijzigd, bestaand gedrag).
- Geen stack-trace of foutTEKST wordt ooit teruggegeven aan de eindgebruiker (bestaand contract
  van `_voer_goedgekeurde_actie_uit()`, ongewijzigd: alleen het TYPE van de fout gaat naar buiten).

### 14. Transacties en dataïntegriteit

- Geen wijziging aan het bestaande transactiegedrag van `create()`/`approve()`.

### 15. Telemetry / logging / tracing

- Geen nieuwe logregels; bestaande `hitl_repository.created`-logregel blijft ongewijzigd.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- `create_hitl_request(..., executing_identity="skillsgaptraining", action_type="query_hr_database")`
  slaagt; met de (default) identiteit `"copilot"` faalt dezelfde aanroep met `PermissionError`
  (bewezen: `tests/unit/test_hitl_repository.py::TestCreateHitlRequestExecutingIdentity`).
- Het aangemaakte ticket bewaart de gebruikte identiteit in `payload["_executing_identity"]`.
- Het bestaande, parameterloze aanroeppatroon (`copilot/service.py`) blijft werken en zet
  `_executing_identity` op `"copilot"` (bewezen:
  `test_omitting_the_parameter_keeps_the_existing_copilot_caller_working`).
- Een staleness-anker (`test_the_blijft_deferral_decision_is_still_current`) bewaakt dat de
  bewuste "niet in `_BLIJFT`"-beslissing niet stilzwijgend uit sync raakt met `_AUDIT_FIELDS` in
  `hitl_router.py`; mutatie-getest in beide richtingen.

### 18. Integratoruitleg

- Geen publieke API-wijziging. Voor toekomstige interne aanroepers: geef `executing_identity` mee
  als de aanvragende identiteit niet `copilot` is, anders faalt de permissiecheck onterecht.

### 19. Trainingssamenvatting

- Actor: elke interne aanroeper van `create_hitl_request` (vandaag: `copilot/service.py` en
  `specialist_base.py`).
- Voorwaarde: de aanroeper kent de identiteit die de actie straks moet uitvoeren.
- Actie (request): aanroep van `create_hitl_request(..., executing_identity=...)`.
- Systeemverwerking: permissiecheck tegen het profiel van die identiteit; bij succes een
  ticket-rij met de identiteit bewaard in de payload.
- Succesrespons: ticket_ref (str).
- Foutrespons: `ValueError` / `PermissionError`.
- Uitzonderingen: default-identiteit `"copilot"` als het argument wordt weggelaten (backwards
  compatible).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen nieuwe of gewijzigde publieke HTTP-endpoints in deze fix.
- Interne teams die een NIEUWE agent-identiteit toevoegen die via `_council_rejection()` (of een
  vergelijkbaar pad) een HITL-ticket kan aanvragen: geef altijd `executing_identity` mee gelijk
  aan die identiteit's `agent_id`, en zorg dat er een profiel voor bestaat in
  `config/tool_permissions.yml` voor de tools die de identiteit mag aanvragen.
- Het bestaande `POST /api/v1/tools/hitl/approve`-endpoint en zijn response zijn ONGEWIJZIGD.

---

## Open aannames

- `_executing_identity` overleeft de resolutie-wipe NIET (staat niet in `_BLIJFT`). De functionele
  behoefte van deze fix (identiteit bij aanmaken == identiteit bij uitvoeren) is hiermee al
  voldaan, omdat de waarde wordt gelezen VOOR de wipe. Een post-hoc audit-trail ("welke identiteit
  heeft deze allang afgehandelde actie uiteindelijk uitgevoerd") is met deze fix niet mogelijk --
  dat zou ook `hitl_store._ticket_to_dict()` en `_AUDIT_FIELDS` in `hitl_router.py` moeten
  aanpassen, wat het `/hitl/audit`-API-contract raakt. Bewust uitgesteld; bewaakt door een
  staleness-anchor-test (zie BE-SEC-046 §17) zodat deze aanname niet stilzwijgend verandert.

## Open vragen

- Geen.

## Risico's

- Geen resterende. De Gate 2-code- en security-review (2026-08-18, beide GO) hebben o.a.
  getoetst: geen escalatiepad waarbij `executing_identity` door een aanroeper buiten het systeem
  om beinvloed kan worden; `_executing_identity` lekt niet in de daadwerkelijk uitgevoerde
  tool-parameters (underscore-prefix-filter in `approve_hitl_request()`); geen regressie op de
  bestaande `copilot/service.py`-aanroeper.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- n.v.t. HTTP-endpoint, wel: unit- en
      architecture-tests groen (zie Acceptatiecriteria per artefact).
- [x] Alle foutstatus-codes getest -- `ValueError`/`PermissionError`-paden getest.
- [x] Auth en permissies getest -- `ToolPermissionManager`-permissiecheck getest voor beide
      identiteiten (toegelaten en geweigerd).
- [x] Tenant-isolatie getest -- ongewijzigd, bestaande tenant-filtertests blijven groen.
- [x] Validaties getest (ongeldige invoer) -- onbekende tool, verkeerde identiteit.
- [x] Edge cases getest -- ontbrekende `_executing_identity` op oudere tickets (default-fallback
      in `hitl_router.py`).
- [x] Dataintegriteit en transacties getest -- bestaande transactietests ongewijzigd groen.
- [ ] Performance / load getest -- n.v.t., geen nieuwe query-patronen.
- [ ] Caching getest -- n.v.t.
- [x] Logging en tracing gecontroleerd -- geen nieuwe logregels, bestaande ongewijzigd.

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
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
