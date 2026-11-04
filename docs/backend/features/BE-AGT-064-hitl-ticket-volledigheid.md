# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-064
- Feature naam: HITL-ticket-volledigheid over alle Council-aanroeppunten (ADR-036 OP-167/OP-168,
  fix-sprint "HITL-ticket-volledigheid", dag 1-4)
- Status: GEBOUWD, wacht op review
- Auteur: Claude (sprint-uitvoering)
- Reviewer: onafhankelijke doc-reviewer-agent
- Datum: 2026-08-25
- Gerelateerde user story / ticket:
  `docs/agent-briefs/generated/2026-08-25-sprint-opstarten-hitl-ticket-volledigheid.md` +
  `2026-08-25-final-approver-hitl-ticket-volledigheid-dag-1.md`, `...-dag-2.md`, `...-dag-3.md`
  (dag 4 is dit document plus de ADR-036-registerbijwerking)
- Gerelateerde router / module: `src.core.copilot.council.coordinator`,
  `src.core.copilot.council.background_gate`, `src.core.copilot.council.governance_gate`,
  `src.core.copilot.service`, `src.core.api.v1.focus_builder.execution_router`,
  `src.core.als.agents.specialist_base`
- Gerelateerde frontend endpoints: elke route die via `require_council_approval()` of
  `execute_flow()` een HTTP 403 kan teruggeven (9 aanroepers van de eerste, 1 van de tweede,
  over de domeinen CVA, ALS, Focus Builder, Agentic Flow, Agents). Geen enkel bestaand
  request/response-schema is vervangen -- elke 403-body kreeg uitsluitend een additieve
  sleutel (`hitl_request_id`).
- Gerelateerde database tabellen: geen nieuwe tabel. De bestaande tabel `hitl_tickets` (model
  `HITLTicket`, `src/core/tool_broker/models.py:26-29`, geschreven via
  `HITLTicketRepository.create_hitl_request()`, reeds aanwezig sinds eerder werk, ADR-036
  OP-163/BE-FLW-058) krijgt nu rijen vanuit 4 aanroeppunten die dat voorheen niet deden. LET OP:
  er bestaat OOK een ONGERELATEERD model `hitl_requests` (`src/core/governance/models.py:351`)
  -- niet te verwarren met `hitl_tickets`, dat is niet waar deze sprint naar schrijft.
- Versie: v1

---

## Doel en scope

### Doel

`AgentCouncil.deliberate()` (`src/core/copilot/council/coordinator.py`) is de gedeelde ingang
voor 5 verschillende aanroepers die samen bepalen of een AI-agent-actie mag doorgaan. Een van
de mogelijke verdicten is `HITL_REQUIRED`: een mens moet de actie expliciet goedkeuren voordat
ze uitgevoerd wordt (AI Act art. 14 -- verplicht menselijk toezicht op hoog-risico
AI-toepassingen; GDPR art. 22 -- het recht om niet uitsluitend aan een geautomatiseerde
beslissing onderworpen te worden, met een daadwerkelijk, niet-symbolisch interventiepad voor
een mens).

Een eerdere audit (vastgelegd bij BE-AGT-051, zie
`docs/backend/features/BE-AGT-051-always-hitl-action-override.md`, Doel-sectie) bracht in kaart
dat van de 5 aanroepers van `deliberate()` er destijds maar 2 een HITL_REQUIRED-verdict
daadwerkelijk in een echt goedkeuringsticket omzetten. De andere 3 behandelden HITL_REQUIRED
identiek aan BLOCKED: geen ticket, geen mens werd ooit gevraagd, en de actie verdween in een
onherstelbaar dood spoor. Dat gat is met opzet niet meegenomen in BE-AGT-051 zelf (dat
mechanisme -- `ALWAYS_HITL_ACTIONS` -- kreeg een bewust LEGE lijst juist omdat dit gat nog
openstond) en apart vastgelegd als ADR-036 OP-167. Een tweede, kleiner gat (OP-168) werd bij
diezelfde audit gevonden: de `ALWAYS_HITL_ACTIONS`-upgrade zelf vuurde alleen vanaf een unaniem
APPROVED-verdict, nooit vanaf `APPROVE_WITH_MODIFICATION` -- een routinematig, niet zeldzaam
officiersverdict.

Deze 4-daagse sprint sluit beide gaten. Na dag 3 (commits `c9c44efc`, `1be758bf`, `238a2efa`,
`88acf9f7`, `44790fd1`) maakt elk van de 5 oorspronkelijke aanroeppunten van
`AgentCouncil.deliberate()` een echt `HITLTicketRepository.create_hitl_request()`-record aan
zodra het EFFECTIEVE verdict HITL_REQUIRED is -- ongeacht of dat verdict rechtstreeks van de
Council kwam, van de `ALWAYS_HITL_ACTIONS`-override (coordinator.py), of van
`specialist_base.py`'s eigen Annex III/HITL-"floor"-mechanisme (D4-002, gebruikt door de live
`skillsgaptraining`-piloot-skill).

**Een bekend, gedocumenteerd, NIET gedicht restgat:** `submit_proactive_proposal`'s enige
productie-aanroeper (`proactive/monitor.py::propose_to_council`) gebruikt altijd
`action_type="send_notification"`, een naam die nergens in `BusinessToolRegistry`/
`HRToolRegistry` geregistreerd staat. `HITLTicketRepository.create_hitl_request()` weigert
daardoor zelf met een `ValueError` (onbekende tool, OP-90) voor dat specifieke pad. De fix in
deze sprint vangt die weigering, logt haar duidelijk, en laat de aanroep verder normaal
verlopen -- maar produceert voor DAT ene productiepad vandaag GEEN echt ticket. Het pad is dus
**veilig gemaakt** (geen crash, geen misleidende foutclassificatie), niet **daadwerkelijk
gedicht**. Zie artefact BE-AGT-064-3 hieronder.

**Een tweede restgat, gevonden tijdens de review van dit document (zie
`docs/backend/review/review-BE-AGT-064.md` sectie B/C.9, empirisch bevestigd tegen de echte
testdatabase, poort 5455) en niet door de sprint zelf ontdekt -- en SINDSDIEN GEFIXED, commit
`d54bc5c4` (2026-08-25):** `require_council_approval()` (BE-AGT-064-4, 9 aanroepers) en
`execute_flow()` (BE-AGT-064-5) maken hun ticket aan via `create_hitl_request()`, die intern
alleen `flush()` doet, nooit `commit()`. Beide functies wierpen DIRECT DAARNA een
`HTTPException(403)` op op DEZELFDE databasesessie (`Depends(get_db)`), die bij een exception
rollback't (`src/core/database/database.py::get_db()`: `except Exception: await
session.rollback(); raise`). Tot commit `d54bc5c4` overleefde de aangemaakte ticket-rij de
eigen 403-respons NIET -- de `hitl_request_id` in die respons verwees naar een rij die na de
request niet meer (of nooit) bestond. Dit was **erger dan de oorspronkelijke OP-167-bug**: er
werd een ticketreferentie getoond die suggereerde dat menselijk toezicht was geregeld, terwijl
er geen rij was om op te reageren. Geen bestaande test ving dit (alle tests voor deze twee
artefacten gebruikten `AsyncMock` voor `db` en voor `HITLTicketRepository`, dus de echte
commit/rollback-cyclus werd nooit uitgevoerd). De andere 4 artefacten (BE-AGT-064-1/-2/-3/-6)
hadden dit probleem NIET: `background_gate.py` en `specialist_base.py`'s floor-tak gebruiken
elk hun eigen, toegewijde `async with get_db_session()`-blok en werpen daarna nooit een
exception, dus dat blok sluit altijd via het succespad (commit). Dit defect was een CODE-bug,
geen documentatiefout, en viel buiten de scope van dit documentatie-artefact om te FIXEN --
het is hier vastgelegd omdat het document anders ten onrechte zou suggereren dat
BE-AGT-064-4/-5 altijd hebben gewerkt zoals bedoeld. **Fix (commit `d54bc5c4`):** een
expliciete `await db.commit()` (governance_gate.py) / `await service.db.commit()`
(execution_router.py) op het succespad, in een nieuwe `else:`-clausule op het bestaande
`try/except (ValueError, PermissionError)`-blok, VOOR de `raise HTTPException`. Bewijs: nieuwe
integratietest `tests/integration/test_governance_gate_hitl_ticket_commit.py`, tegen de echte
testdatabase (poort 5455), mutatiegetest in beide richtingen (rood zonder de commit, groen
met).

### In scope

- `coordinator.py`: de `ALWAYS_HITL_ACTIONS`-upgrade vuurt nu vanaf `APPROVED` **of**
  `MODIFIED` in plaats van uitsluitend `APPROVED` (OP-168, artefact BE-AGT-064-1).
- `background_gate.py::request_council_decision_for_agent`: garandeert nu zelf een ticket bij
  een RAUW HITL_REQUIRED-verdict, via een nieuw `AgentCouncilOutcome`-return-type (OP-167,
  artefact BE-AGT-064-2).
- `service.py::submit_proactive_proposal`: maakt nu een ticket aan bij HITL_REQUIRED in plaats
  van het verdict ongebruikt weg te gooien (OP-167, artefact BE-AGT-064-3, met het hierboven
  genoemde restgat).
- `governance_gate.py::require_council_approval`: nieuwe optionele `db`-parameter, maakt een
  ticket aan bij HITL_REQUIRED en zet `hitl_request_id` in de 403-detail-body. Alle 9 bekende
  aanroepers (CVA, ALS, Focus Builder, Agentic Flow, Agents -- 5 domeinen, zie sectie 6 van
  artefact BE-AGT-064-4) bijgewerkt om `db=` mee te geven (OP-167, artefact BE-AGT-064-4). **Zie
  het restgat in de Doel-sectie: deze ticket-aanmaak overleefde de eigen 403-respons niet tot
  commit `d54bc5c4`, dat er een expliciete commit voor de raise aan toevoegde.**
- `execution_router.py::execute_flow`: eigen ticket-aanmaak-implementatie (niet via
  `require_council_approval`, om het bestaande, afwijkende 403-foutcontract van deze route niet
  te breken) (OP-167, artefact BE-AGT-064-5).
- `specialist_base.py`'s D4-002 Annex III/HITL-"floor" (apart mechanisme van
  `ALWAYS_HITL_ACTIONS`, gebruikt door de live `skillsgaptraining`-piloot-skill via
  `human_in_the_loop: hitl` in het skill-manifest): dezelfde APPROVED-only-bug als OP-168,
  gefixt naar `(APPROVED, MODIFIED)` (OP-168-vervolg, artefact BE-AGT-064-6).
- Bijvangst: exception-veiligheid (`ValueError`/`PermissionError` uit
  `create_hitl_request()` zelf) op alle 5 nieuwe/gewijzigde ticket-aanmaak-plekken, plus een
  ADR-033-schending (directe `AsyncSession`-import in `legacy_router.py`) en ontbrekende
  `exc_info=True`-logging, allebei gevonden en gefixt tijdens Gate 2 (zie Build summary).

### Out of scope

- Het vullen van `ALWAYS_HITL_ACTIONS` met een echte actie -- apart beleidsbesluit van Rakesh
  (OP-164), niet iets dat deze sprint zelf beslist. De lijst blijft leeg; alle code in deze
  sprint is dus vandaag functioneel inert voor dat specifieke mechanisme (coordinator.py), maar
  WEL functioneel actief voor de andere 5 artefacten, die niet van een lege lijst afhangen.
- `send_notification` als geregistreerde tool toevoegen -- zou het BE-AGT-064-3-restgat sluiten,
  maar is een eigen, apart besluit over de tool-registry, niet vandaag genomen.
- `execute_flow` ombouwen naar hergebruik van `require_council_approval` -- zou de
  code-duplicatie tussen beide oplossen, maar zou het bestaande, van het generieke contract
  afwijkende 403-foutcontract van `execute_flow` wijzigen (andere sleutelnamen: `reason` i.p.v.
  `message`, `FLOW_BLOCKED_BY_COUNCIL` i.p.v. `GOVERNANCE_BLOCKED`) -- een potentiele breaking
  change voor de Focus Builder-frontend die niets met OP-167 te maken heeft. Bewust
  geaccepteerd als gedocumenteerd drift-risico (Gate 2-bevinding, dag 2).
- Fijnmazige filtering van WELKE `MODIFIED`-gevallen een upgrade verdienen (bijv. alleen
  bepaalde officier-redenen) -- Rakesh's expliciete GO (dag 3): "houd de brede regel... zodra je
  hoog-sensitieve acties toevoegt wil je dat elke AI-wijziging hoe dan ook door een mens wordt
  beoordeeld; fijnmazig filteren zonder reele productievoorbeelden zou nu giswerk zijn."
- Normalisatie van `action_type`-stringvergelijking (case/whitespace) -- ongewijzigd
  overgenomen uit BE-AGT-051, nog steeds niet relevant zolang `ALWAYS_HITL_ACTIONS` leeg is.

---

## Build summary

- Nieuw gebouwd: `AgentCouncilOutcome`-`NamedTuple` (`background_gate.py`),
  `_create_proactive_hitl_ticket()`/`_is_known_tool()` (`service.py`), een eigen
  ticket-aanmaak-blok in `execute_flow()` (`execution_router.py`), 20+ nieuwe/gewijzigde tests
  over 10 testbestanden (zie Acceptatiecriteria per artefact).
- Gewijzigd: `coordinator.py` (upgrade-conditie), `background_gate.py` (return-type +
  ticket-garantie), `service.py` (proactieve ticket-aanmaak), `governance_gate.py` (`db`-param +
  ticket-aanmaak + `hitl_request_id`), `execution_router.py` (ticket-aanmaak + dezelfde sleutel
  op zijn eigen contract), `specialist_base.py` (unpacking van het nieuwe outcome-type,
  onderscheid floor-toegepast vs. raw-HITL_REQUIRED-ticketpad, en de D4-002-floor-conditie
  zelf), 9 aanroepers van `require_council_approval` (db-doorgifte:
  `agentic_flow_endpoints.py`, `als_tasks_router.py`, `agent_management_router.py`,
  `agent_execution_router.py`, `agents/dependencies.py`-facade, `legacy_router.py`,
  `cva/dependencies.py`-facade, `cva_service.py`, `focus_builder/ai_router.py`),
  `cva/dependencies.py.__all__` (AsyncSession toegevoegd, ADR-033-fix).
- Verwijderd: niets.
- Beinvloede bestaande flows: de ticket-aanmaakflow (BE-FLW-058, zie BE-AGT-051-doc) wordt nu
  vanuit 5 plekken aangeroepen in plaats van 2. Het bestaande 403-foutcontract van
  `require_council_approval` en `execute_flow` blijft ONGEWIJZIGD in vorm -- beide kregen alleen
  een additieve `hitl_request_id`-sleutel (`null` wanneer geen ticket kon worden aangemaakt).

**Commits:**

| Commit | Dag | Inhoud |
| --- | --- | --- |
| `c9c44efc` | 1 | `background_gate.py` + `service.py` + `specialist_base.py` (outcome-unpacking) -- OP-167 deel 1/3 |
| `1be758bf` | 2 | `governance_gate.py` (9 aanroepers) + `execution_router.py` -- OP-167 deel 2-3/3 |
| `238a2efa` | 3 | `coordinator.py` MODIFIED-upgrade -- OP-168 |
| `88acf9f7` | 3 | Gate-2-vervolgfix op `238a2efa` (overclaim-comment + ontbrekende mutatietest) |
| `44790fd1` | 3 | `specialist_base.py` D4-002-floor MODIFIED-upgrade -- OP-168-vervolg, Rakesh's GO |

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-064-1 | `ALWAYS_HITL_ACTIONS`-upgrade dekt ook MODIFIED | BE-AGT (agent-gedrag) | `src/core/copilot/council/coordinator.py` | Wijziging | BE-FLW-058 |
| BE-AGT-064-2 | `AgentCouncilOutcome` + zelf-gegarandeerd ticket | BE-AGT (agent-gedrag) | `src/core/copilot/council/background_gate.py` | Wijziging (nieuw return-type) | BE-FLW-058 |
| BE-AGT-064-3 | Ticket-aanmaak bij proactief voorstel | BE-SVC (service-methode) | `src/core/copilot/service.py` | Wijziging | BE-FLW-058 |
| BE-AGT-064-4 | `require_council_approval` maakt ticket + `hitl_request_id` in 403 | BE-SEC (governance-poort) | `src/core/copilot/council/governance_gate.py` | Wijziging | BE-FLW-058 |
| BE-AGT-064-5 | `execute_flow` eigen ticket-aanmaak + `hitl_request_id` in 403 | BE-EP (endpoint) | `src/core/api/v1/focus_builder/execution_router.py` | Wijziging | BE-FLW-058 |
| BE-AGT-064-6 | D4-002-HITL-floor dekt ook MODIFIED (skillsgaptraining-piloot) | BE-AGT (agent-gedrag) | `src/core/als/agents/specialist_base.py` | Wijziging | BE-FLW-058 |

---

## API-flows

### Flow ID: BE-FLW-058 (bestaand, uitgebreid)

- Naam: HITL-ticket-aanmaak bij een HITL_REQUIRED-Councilverdict.
- Trigger: elk van de 5 aanroeppunten van `AgentCouncil.deliberate()` waarvan het EFFECTIEVE
  verdict (na de `ALWAYS_HITL_ACTIONS`- of D4-002-floor-upgrade, indien van toepassing)
  HITL_REQUIRED is.
- Voorwaarden (auth, tenant, feature flag): tenant_id en user_id komen uit de JWT/auth-context
  van de oorspronkelijke aanroeper (HTTP-request of achtergrondtaak), nooit uit een
  request-body-veld. Geen feature flag -- dit mechanisme is altijd actief.
- Request-pad: aanroeper -> `deliberate()`/floor-check -> (bij HITL_REQUIRED) ticket-aanmaak op
  de aanroepende laag zelf (niet in `coordinator.py` -- die blijft zuivere verdict-logica).
- Service-stappen: `HITLTicketRepository(db).create_hitl_request(tenant_id, user_id,
  decision_id, reason, action_type, action_params, executing_identity=...)`.
- DB-operaties: 1 INSERT in de HITL-tickets-tabel bij succes. Geen enkele operatie bij een
  `ValueError`/`PermissionError`-weigering (fail-secure: geen halve rij).
- Successtatus + response: varieert per aanroeper -- zie de artefactsecties hieronder voor het
  exacte contract per laag (HTTP 403 met `hitl_request_id`, of een `AgentCouncilOutcome`/
  interne `ticket_ref`-string voor de niet-HTTP-paden).
- Foutpaden: `ValueError` (onbekende tool, OP-90) of `PermissionError` (`executing_identity`
  niet geautoriseerd voor de tool, OP-163) uit `create_hitl_request()` zelf -- overal gevangen,
  gelogd met `exc_info=True`, resulteert in `hitl_ticket_ref = None` (of `null` in de
  HTTP-body), NOOIT in een 500 of een gecrashte achtergrondtaak.
- Eindtoestand (DB, cache, events): bij succes een nieuwe rij in de HITL-tickets-tabel,
  koppelbaar aan `decision_id`. Bij weigering: geen nieuwe rij, wel een WARNING-logregel met
  tenant/actie/foutklasse.

---

## Detaildocumentatie per artefact

---

## [BE-AGT-064-1] `ALWAYS_HITL_ACTIONS`-upgrade dekt ook MODIFIED

### 1. Type

- Agent-/governance-gedrag (interne verdict-aggregatielogica, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/coordinator.py`. Zoek op de symboolnaam
  `ALWAYS_HITL_ACTIONS` en de conditie in `AgentCouncil.deliberate()` direct na de
  `_aggregate()`-aanroep -- geen regelnummer genoemd (dit blok is meermaals gewijzigd binnen
  deze sprint, zie de bekende valkuil in BE-AGT-051's doc dat regelnummers hier snel
  verouderen).
- Klasse / functie: `AgentCouncil.deliberate()`.

### 3. Gerelateerde flow

- BE-FLW-058 (indirect -- deze upgrade bepaalt OF een ticket-aanmaak-pad geraakt wordt, maakt
  zelf geen ticket aan).

### 4. Doel

- Voorkomen dat een actie op `ALWAYS_HITL_ACTIONS` menselijk toezicht omzeilt zodra minstens
  een Officer `APPROVE_WITH_MODIFICATION` in plaats van unaniem `APPROVED` geeft --
  `ComplianceOfficer` doet dit routinematig bij een ontbrekende `ai_disclosure`,
  `EthicsOfficer` bij elke bias-lexicon-treffer.

### 5. Functionele beschrijving

- Voor een `final_verdict` van `APPROVED` OF `MODIFIED` EN `proposal.action_type in
  ALWAYS_HITL_ACTIONS`: het verdict wordt opgetild naar `HITL_REQUIRED` voor `_finalize()`.
  Voorheen gold dit alleen voor `APPROVED`. `BLOCKED`/`DEFERRED`/een reeds bestaand
  `HITL_REQUIRED` worden nooit aangeraakt.
- De officier-voorgestelde `modifications` blijven ongewijzigd meegegeven aan `_finalize()` --
  deze upgrade past ze niet toe en gooit ze niet weg. Wat er met die aanpassingen gebeurt ALS de
  mens straks goedkeurt (oorspronkelijke parameters uitvoeren, aangepaste parameters, of de mens
  laten kiezen) is een eigen, latere ontwerpvraag over het HITL-goedkeuringspad zelf
  (`hitl_router.py`), niet iets dat deze verdict-aggregatie oplost.
- Effect op systeemtoestand vandaag: GEEN -- `ALWAYS_HITL_ACTIONS` is en blijft een lege
  `frozenset`, dus `action_type in ALWAYS_HITL_ACTIONS` is altijd `False`.

### 6. Technische beschrijving

- Conditie: `if final_verdict in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED) and
  proposal.action_type in ALWAYS_HITL_ACTIONS: final_verdict = DecisionVerdict.HITL_REQUIRED`.
- Geen aparte, kleinere subset van MODIFIED-gevallen: de curatie zit in `ALWAYS_HITL_ACTIONS`
  zelf (een bewust, mens-samengesteld beleidsbesluit, OP-164) -- voor een actie die daar staat,
  verdient elke uitkomst behalve een reeds-blokkerende tussenkomst een mens, niet alleen de
  unaniem-goedgekeurde variant.
- `AuditOfficer._generate_explanation()` (BE-AGT-052, ongewijzigd door deze fix) dekte het
  APPROVED-oorsprong-pad van een ongeofficierde HITL_REQUIRED-uitleg al; bevestigd door test
  dat dezelfde fallback ook het nieuwe MODIFIED-oorsprong-pad correct afhandelt.

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. -- interne aggregatielogica, geen HTTP-laag, geen tenant-specifiek gedrag (bewust:
  GDPR art. 22 geldt voor elke tenant gelijk).

### 8-9. Request-/Response-specificatie

- N.v.t. -- geen eigen endpoint. Dit artefact bepaalt alleen de WAARDE van
  `decision.verdict`, die vervolgens door de artefacten BE-AGT-064-2 t/m -6 wordt vertaald
  naar een concreet aanroeper-contract.

### 10. Validaties en constraints

- Exacte-stringvergelijking op `action_type`, geen normalisatie (bewust uitgesteld, zie Out of
  scope).

### 11. Business rules

- Een gelijste actie mag NOOIT als uitsluitend geautomatiseerd (unaniem APPROVED) OF als
  gedeeltelijk geautomatiseerd-met-aanpassing (MODIFIED) doorgaan zonder menselijke
  tussenkomst.

### 12. Afhankelijkheden

- `DecisionVerdict`-enum (`src/core/copilot/council/types.py`), `_aggregate()` (levert het
  canonieke enum-lid, nooit een rauwe string).

### 13. Foutafhandeling

- N.v.t. voor dit artefact zelf (zuivere verdictlogica, geen I/O, geen exception-pad). De
  foutafhandeling voor de ticket-aanmaak die HITL_REQUIRED vervolgens veroorzaakt, staat in
  BE-AGT-064-2 t/m -6.

### 14. Transacties en dataintegriteit

- N.v.t. -- geen DB-schrijfactie in dit artefact zelf.

### 15. Telemetry / logging / tracing

- Geen nieuwe logregel. Bestaande `span.set_attribute("verdict", ...)` draagt automatisch het
  geupgradede verdict.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- `test_deliberate_upgrades_modified_to_hitl_required_for_always_hitl_action` slaagt
  (`test_coordinator.py`).
- `test_deliberate_leaves_modified_unchanged_when_action_not_on_always_hitl_list` slaagt --
  bewijst de NEGATIEVE richting (niet-gelijste actie blijft MODIFIED), toegevoegd in `88acf9f7`
  na een Gate-2-bevinding dat deze richting ontbrak.
- Bestaande `test_deliberate_never_downgrades_a_non_approved_verdict_for_always_hitl_action`
  aangepast: `APPROVE_WITH_MODIFICATION` verwijderd uit de "nooit aangeraakt"-parametrisatie
  (dat was letterlijk de OP-168-bug); VETO/DEFER/REQUIRE_HITL blijven wel beschermd.
- Mutatiebewijs (beide richtingen, uitgevoerd in een wegwerp-`git worktree` op HEAD): de
  `MODIFIED`-toevoeging weghalen uit de conditie maakt de hoofdtest rood; de conditie te breed
  maken (bijv. altijd upgraden) maakt de negatieve-richting-test rood.

### 18. Integratoruitleg

- N.v.t. -- geen publieke API-wijziging op dit artefact zelf.

### 19. Trainingssamenvatting

- **Actor:** Systeem (de Council zelf, tijdens elke `deliberate()`-aanroep).
- **Voorwaarde:** een proposal met `action_type` op `ALWAYS_HITL_ACTIONS` EN een aggregatie die
  APPROVED of MODIFIED zou opleveren.
- **Actie (request):** n.v.t. -- interne aggregatiestap.
- **Systeemverwerking:** verdict wordt opgetild naar HITL_REQUIRED voor `_finalize()`.
- **Succesrespons:** n.v.t. (dit IS het beschermingspad, geen eigen respons).
- **Foutrespons:** n.v.t.
- **Uitzonderingen:** BLOCKED/DEFERRED/een reeds bestaand HITL_REQUIRED worden nooit
  aangeraakt, ook niet als de actie op de lijst staat.

---

## [BE-AGT-064-2] `AgentCouncilOutcome` + zelf-gegarandeerd ticket in `background_gate.py`

### 1. Type

- Agent-/governance-gedrag (transport-neutrale Council-ingang voor achtergrondtaken, geen
  HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/background_gate.py`.
- Klasse / functie: nieuwe `AgentCouncilOutcome`-`NamedTuple` (module-niveau);
  `request_council_decision_for_agent()` (gewijzigde return-waarde en interne logica).

### 3. Gerelateerde flow

- BE-FLW-058.

### 4. Doel

- Voorheen garandeerde deze poort ZELF niets: alleen omdat zijn enige aanroeper
  (`specialist_base.py`) toevallig zelf een ticket aanmaakte, kreeg een HITL_REQUIRED-verdict
  via deze weg een mens te zien. Een tweede, toekomstige aanroeper die dat niet zelf repliceerde
  zou stilzwijgend geen ticket krijgen. Dit artefact verplaatst de garantie naar de poort zelf.

### 5. Functionele beschrijving

- `request_council_decision_for_agent()` retourneert nu een `AgentCouncilOutcome(decision,
  hitl_ticket_ref)` in plaats van alleen een `CouncilDecision`. Zodra het RAUWE
  `decision.verdict` (v\'oor enige aanroeper-specifieke floor-logica) HITL_REQUIRED is, maakt de
  functie zelf een ticket aan.
- Kan `create_hitl_request()` zelf niet aanmaken (onbekende tool, of `executing_identity` niet
  geautoriseerd): `hitl_ticket_ref` wordt `None`, er wordt NOOIT een exception doorgegeven aan
  de aanroeper voor een besluit dat wel degelijk HITL_REQUIRED was.

### 6. Technische beschrijving

- Nieuw type: `class AgentCouncilOutcome(NamedTuple): decision: CouncilDecision;
  hitl_ticket_ref: str | None`.
- `agent_id` wordt doorgegeven aan `build_council(agent_id=...)` (bestaand, AUDIT-007) zodat de
  SecurityOfficer/ToolBroker-permissiecheck het profiel van de AANROEPENDE agent gebruikt, niet
  het hardcoded `"copilot"`-profiel. `ticket_action_params` (optioneel) laat een aanroeper met
  een eigen redactielaag (zoals `specialist_base.py`, BE-AGT-043) de ONGEREDIGEERDE
  parameterwaarden apart doorgeven voor het ticket, terwijl `action_params` zelf richting de
  Council alleen sleutelnamen bevat.
- Ticket-aanmaak via een lazy `importlib.import_module("src.core.tool_broker.hitl_repository")`
  (geen statische import: `src/core/copilot` staat zelf in `agent_runtime`'s
  Ce-koppelingsmeting, empirisch bevestigd, niet aangenomen).
- `try/except (ValueError, PermissionError)` rond `create_hitl_request()`: logt een WARNING met
  `type(exc).__name__`/`exc`/`exc_info=True`, zet `hitl_ticket_ref = None`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (achtergrondingang, geen HTTP-laag). Tenant-context via
  `set_tenant_id()`/`get_tenant_id()`, herstelt de vorige waarde in een `finally`-blok (geen
  lek naar een volgende asynctaak in dezelfde worker).
- Tenant-isolatie: `tenant_id` is een verplichte keyword-only parameter, nooit uit een
  request-body of impliciete context afgeleid.
- Toegang: `executing_identity=agent_id` -- de ToolBroker-permissiecheck van
  `create_hitl_request()` beoordeelt de AANROEPENDE agent, niet een generieke identiteit.

### 8-9. Request-/Response-specificatie

- Geen HTTP-route. "Request" = functieaanroep met keyword-only argumenten (zie Sectie 6 voor de
  volledige signatuur). "Response" = het nieuwe `AgentCouncilOutcome`-`NamedTuple`
  (`decision`, `hitl_ticket_ref`) in plaats van de eerdere kale `CouncilDecision`. Dit is een
  BREKENDE wijziging van het return-type voor bestaande aanroepers -- de enige bekende aanroeper
  (`specialist_base.py`) is in dezelfde sprint (BE-AGT-064-6) bijgewerkt om te unpacken.

### 10. Validaties en constraints

- Geen nieuwe input-validatie. De ticket-aanmaak zelf valideert (`is_known_tool`,
  `is_tool_allowed`) via de bestaande `create_hitl_request()`-logica.

### 11. Business rules

- Elke aanroeper van deze poort krijgt een ticket-garantie zonder zelf de ticket-aanmaaklogica
  te moeten repliceren -- dat was precies het OP-167-gat voor deze functie.

### 12. Afhankelijkheden

- `build_council()` (`factory.py`, ongewijzigd), `HITLTicketRepository.create_hitl_request()`
  (`src/core/tool_broker/hitl_repository.py`, ongewijzigd -- dit artefact vangt alleen zijn
  bestaande exceptions correct), `get_db_session()`.

### 13. Foutafhandeling

- `ValueError` (onbekende tool, OP-90): gevangen, gelogd, `hitl_ticket_ref = None`.
- `PermissionError` (`executing_identity` niet geautoriseerd voor de tool, OP-163): gevangen,
  gelogd, `hitl_ticket_ref = None`.
- Elke andere exception uit `create_hitl_request()` propageert ongewijzigd (bewust -- alleen de
  twee gedocumenteerde, bekende weigeringsgronden worden hier afgevangen; een onbekende fout
  moet zichtbaar blijven).
- Council-crash (`deliberate()` zelf gooit): ongewijzigd, buiten scope van dit artefact
  (`deliberate()`'s eigen fail-secure-pad, zie coordinator.py).

### 14. Transacties en dataintegriteit

- 1 INSERT bij succesvolle ticketaanmaak, binnen de bestaande `async with get_db_session() as
  db`-context van deze functie. Geen halve rij bij een geweigerde aanmaak (de repository gooit
  voor enige schrijfactie).

### 15. Telemetry / logging / tracing

- Nieuwe WARNING-log bij een geweigerde ticketaanmaak: tenant/agent/actie/foutklasse/foutmelding,
  met `exc_info=True`.
- Bestaande INFO-logregels (start/verdict) ongewijzigd.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- Nieuwe/aangepaste tests in `tests/integration/test_council_background_gate.py` (2 nieuw) en
  `tests/unit/als/test_agent_governance_hardening.py` bewijzen: (a) een raw HITL_REQUIRED
  resulteert in `hitl_ticket_ref != None` wanneer de tool bekend en toegestaan is, (b) een
  `ValueError`/`PermissionError` uit de repository resulteert in `hitl_ticket_ref is None`
  zonder dat de functie zelf een exception doorgeeft.
- Herstelde `decision_id`-assertie (verloren gegaan bij een testverschuiving van
  `test_council_gate_per_action.py` naar dit integratiebestand) staat weer op de juiste plek.
- Mutatiebewijs: de `try/except` tijdelijk verwijderd (backup-kopie, nooit `git checkout --`)
  liet de bijbehorende tests ROOD gaan met de daadwerkelijke exception in de traceback; herstel
  liet ze GROEN worden.

### 18. Integratoruitleg

- Voor teams die `request_council_decision_for_agent()` rechtstreeks aanroepen (momenteel alleen
  `specialist_base.py`): het returntype is gewijzigd van `CouncilDecision` naar
  `AgentCouncilOutcome`. Unpack als `decision, hitl_ticket_ref = outcome` of gebruik
  `outcome.decision`/`outcome.hitl_ticket_ref`.
- `hitl_ticket_ref` kan `None` zijn ook al is `decision.verdict == HITL_REQUIRED` -- controleer
  dit expliciet voor je een gebruiker een ticketverwijzing toont.
- Er wordt nooit een `ValueError`/`PermissionError` uit deze functie gegooid vanwege een
  mislukte ticketaanmaak.

### 19. Trainingssamenvatting

- **Actor:** Systeem (een achtergrondtaak/agent die de Council raadpleegt via deze poort).
- **Voorwaarde:** een proposal wordt aan `deliberate()` voorgelegd via deze functie.
- **Actie (request):** aanroep met `tenant_id`, `agent_id`, `user_id`, `action_type`,
  `action_params`, `reasoning`, optioneel `message`/`trigger`/`ticket_action_params`.
- **Systeemverwerking:** Council-deliberatie, en bij een RAUW HITL_REQUIRED-verdict: een poging
  tot ticket-aanmaak.
- **Succesrespons:** `AgentCouncilOutcome(decision, hitl_ticket_ref)` met een niet-lege
  `hitl_ticket_ref` bij een geslaagde ticketaanmaak.
- **Foutrespons:** `AgentCouncilOutcome(decision, hitl_ticket_ref=None)` bij een geweigerde
  ticketaanmaak (onbekende tool of niet-geautoriseerde identiteit) -- GEEN exception.
- **Uitzonderingen:** een Council-crash (buiten dit artefact) resulteert in een fail-secure
  BLOCKED-`CouncilDecision`, ongewijzigd bestaand gedrag.

---

## [BE-AGT-064-3] Ticket-aanmaak bij `submit_proactive_proposal`

### 1. Type

- Service-methode (`AgentCouncil`-consument binnen de Copilot-service, geen eigen
  HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/service.py`.
- Klasse / functie: `CopilotService.submit_proactive_proposal()`, nieuwe
  `_create_proactive_hitl_ticket()` en `_is_known_tool()`-helpers.

### 3. Gerelateerde flow

- BE-FLW-058.

### 4. Doel

- Voorheen gooide `submit_proactive_proposal` een HITL_REQUIRED-verdict ongebruikt weg -- het
  besluit bereikte nooit een mens (AI Act art. 14). Deze fix maakt een ticket aan, met een
  bewust ANDERE foutstrategie dan `handle_turn` (zie Sectie 6).

### 5. Functionele beschrijving

- Na `_execute_decision()`: als `decision.verdict == HITL_REQUIRED`, wordt
  `_create_proactive_hitl_ticket()` aangeroepen. Is `action_type` geen bekende tool (via de
  gedeelde `_is_known_tool()`-helper): een WARNING-logregel, GEEN ticket, GEEN exception -- de
  aanroep van `submit_proactive_proposal` zelf slaagt en retourneert de `CouncilDecision`
  gewoon.

### 6. Technische beschrijving

- `_is_known_tool()` is een gedeelde `@staticmethod`-wrapper rond
  `tool_broker.service.is_known_tool` (lazy import, ADR-036 OP-78) -- een TWEEDE losse
  lokale import op de nieuwe aanroepplek zou `agent_runtime`'s Ce-koppelingsmeting van 227 naar
  228 hebben geduwd (`test_agent_runtime_ce_dag2_final_target`); de gedeelde helper voorkomt dat.
- **Bewust ANDERE strategie dan `handle_turn`'s bestaande HITL-blok:** `handle_turn` gooit een
  `ToolExecutionException` bij een onbekende tool (de HTTP-aanroeper kan dat netjes naar een
  4xx vertalen). `submit_proactive_proposal` heeft als enige productie-aanroeper
  `proactive/monitor.py::propose_to_council`, die GEEN try/except heeft -- een gegooide
  exception hier zou die achtergrondtaak laten crashen. Daarom: loggen en doorgaan.
- **Het bekende restgat:** die enige productie-aanroeper gebruikt altijd
  `action_type="send_notification"`, dat NERGENS in `BusinessToolRegistry`/`HRToolRegistry`
  geregistreerd staat. Voor dat pad produceert deze fix dus vandaag GEEN echt ticket -- alleen
  een correct geclassificeerde log-regel in plaats van de oude, stille weggooi.

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. -- interne service-methode. `executing_identity` gebruikt de service-default (geen
  aparte agent-identiteit zoals bij BE-AGT-064-2, omdat deze aanroeper geen los agent-profiel
  meegeeft).

### 8-9. Request-/Response-specificatie

- Geen HTTP-route. `submit_proactive_proposal(proposal: Proposal) -> CouncilDecision` --
  return-type ONGEWIJZIGD (in tegenstelling tot BE-AGT-064-2). De ticket-aanmaak is een side
  effect, geen deel van de return-waarde.

### 10. Validaties en constraints

- `_is_known_tool(proposal.action_type)` als voorwaarde voor een ticket-aanmaakpoging (voorkomt
  een gegarandeerde `ValueError` uit de repository voor het bekende `send_notification`-geval,
  i.p.v. die te laten gooien en dan te vangen).

### 11. Business rules

- Een HITL_REQUIRED-verdict op een proactief voorstel mag nooit stilzwijgend verdwijnen. Kan er
  geen ticket komen (onbekende tool), dan moet dat MINSTENS zichtbaar zijn in de logs, nooit
  identiek aan een geslaagde, tickettloze afhandeling.

### 12. Afhankelijkheden

- `self._hitl_repo` (bestaande, geinjecteerde repository-referentie op `CopilotService`),
  `tool_broker.service.is_known_tool`.

### 13. Foutafhandeling

- Onbekende tool: gevangen VOOR de aanroep (precheck via `_is_known_tool`), geen exception,
  WARNING-log, geen ticket.
- `self._hitl_repo` niet aanwezig (bijv. in een test-context zonder repository-injectie): vroege
  `return` uit `_create_proactive_hitl_ticket()`, geen crash.
- Elke andere fout uit `create_hitl_request()` (bijv. een `PermissionError` als de default-
  identiteit ooit niet geautoriseerd zou zijn voor een wel-bekende tool): NIET expliciet
  onderzocht in dit artefact als apart geval -- zie Open aannames.

### 14. Transacties en dataintegriteit

- 1 INSERT bij succes, binnen de service's bestaande DB-sessie. Geen schrijfactie bij een
  onbekende tool (precheck voorkomt de aanroep zelf).

### 15. Telemetry / logging / tracing

- Nieuwe WARNING-logregel `copilot.proactive_hitl_no_ticket_unknown_tool` met
  tenant/decision/action_type.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- Nieuwe test in `tests/unit/copilot/test_service.py` bewijst: een HITL_REQUIRED-verdict op een
  bekende tool resulteert in een `create_hitl_request()`-aanroep; op de onbekende
  `send_notification`-actie resulteert in GEEN aanroep en een WARNING-log, zonder dat
  `submit_proactive_proposal` zelf faalt.
- Mutatiebewijs: de `_is_known_tool()`-check tijdelijk verwijderen laat de test voor het
  onbekende-tool-pad rood gaan (propagatie van een ongevangen `ValueError`); herstel maakt hem
  groen.

### 18. Integratoruitleg

- N.v.t. -- geen publieke API. Voor teams die zelf een proactieve-monitor-aanroeper bouwen:
  gebruik een `action_type` die daadwerkelijk in `BusinessToolRegistry`/`HRToolRegistry` staat
  als je een echt ticket wilt, anders krijgt de gebruiker vandaag geen ticket te zien voor een
  HITL_REQUIRED-verdict op die actie.

### 19. Trainingssamenvatting

- **Actor:** Systeem (`proactive/monitor.py::propose_to_council`, de enige productie-aanroeper).
- **Voorwaarde:** een proactief voorstel krijgt een HITL_REQUIRED-verdict van de Council.
- **Actie (request):** n.v.t. -- interne service-aanroep, geen externe request.
- **Systeemverwerking:** poging tot ticket-aanmaak, met een precheck op bekende tool.
- **Succesrespons:** ticket aangemaakt (voor een bekende, geregistreerde tool).
- **Foutrespons:** geen ticket, WARNING-log, GEEN exception -- de aanroep van
  `submit_proactive_proposal` slaagt zelf altijd (`send_notification` vandaag altijd dit pad).
- **Uitzonderingen:** n.v.t.

---

## [BE-AGT-064-4] `require_council_approval` maakt ticket + `hitl_request_id` in de 403-body

### 1. Type

- Auth/governance-poort (`BE-SEC`), hergebruikt door 9 bestaande HTTP-endpoints over 6
  domeinen -- geen NIEUW endpoint.

### 2. Locatie

- Bestandspad: `src/core/copilot/council/governance_gate.py`.
- Klasse / functie: `require_council_approval()`.

### 3. Gerelateerde flow

- BE-FLW-058, plus de bestaande, individuele request/response-flows van elk van de 9
  aanroepende routes (CVA-chat, ALS-taken, Focus Builder AI-suggesties, Agentic Flow, 4
  Agents-routes) -- dit artefact wijzigt GEEN van die bestaande flows qua vorm, alleen qua
  inhoud van de 403-body.

### 4. Doel

- Voorheen behandelde deze gedeelde poort een HITL_REQUIRED-verdict identiek aan BLOCKED: 403,
  geen ticket, geen mens werd ooit gevraagd. Dit is de grootste van de 3 oorspronkelijk kapotte
  aanroeppunten (9 aanroepers achter 1 functie), en dus de belangrijkste fix van deze sprint qua
  aantal geraakte HTTP-routes.

### 5. Functionele beschrijving

- Bij een HITL_REQUIRED-verdict EN een meegegeven `db`-sessie: er wordt een ticket aangemaakt en
  de referentie verschijnt als `hitl_request_id` in de 403-detail-body. Zonder `db` (een
  toekomstige, nog niet bijgewerkte aanroeper): graceful degradation -- geen ticket, geen crash,
  de 403 blijft zoals voorheen (`hitl_request_id` ontbreekt dan niet als sleutel, maar is dan
  altijd `null`, want de conditie zelf wordt nooit bereikt zonder `db`).
- Alle andere niet-APPROVED-verdicten (BLOCKED, MODIFIED, DEFERRED) blijven ongewijzigd: 403
  zonder `hitl_request_id`-poging (die sleutel bestaat wel in de body, maar is dan altijd
  `null`, additief en consistent voor elk verdict-type).

### 6. Technische beschrijving

- Nieuwe optionele parameters: `db: AsyncSession | None = None`,
  `ticket_action_params: dict[str, Any] | None = None`.
- Bij `decision.verdict is DecisionVerdict.HITL_REQUIRED and db is not None`: lazy
  `importlib.import_module("src.core.tool_broker.hitl_repository")`, dan
  `HITLTicketRepository(db).create_hitl_request(...)`, gevangen in `try/except (ValueError,
  PermissionError)` met `exc_info=True`-logging.
- `executing_identity` wordt NIET expliciet meegegeven aan `create_hitl_request()` op deze
  aanroeplaag (blijft de repository-default) -- geverifieerd correct voor alle 9 aanroepers,
  omdat dit gebruikers-geinitieerde HTTP-routes zijn, geen agent-specifiek pad zoals de
  ALS-piloot (die WEL een expliciete `executing_identity` nodig heeft, zie BE-AGT-064-2/-6).
- 9 bekende aanroepers bijgewerkt om `db=` mee te geven (bevestigd via een eigen
  `grep -rn "require_council_approval(" src --include=*.py`, 9 echte aanroepen buiten de eigen
  definitie/docstrings): `agentic_flow_endpoints.py`, `als_tasks_router.py` (2 aanroepen),
  `agents/dependencies.py` (gebruikt door `agent_management_router.py`/
  `agent_execution_router.py`), `cva/dependencies.py` (gebruikt door `legacy_router.py`),
  `cva_service.py` (2 aanroepen), `focus_builder/ai_router.py` (2 aanroepen). Dat is 9 aanroepen
  over **5** herkenbare domeinen: Agentic Flow, ALS, Agents, CVA, Focus Builder. **Correctie
  t.o.v. de dag-2-final-approver-brief:** die brief noemt "9 aanroepers over 6 domeinen" maar
  somt zelf ook maar 5 domeinnamen op (CVA, ALS, Focus Builder, Agentic Flow, Agents) -- het
  cijfer 6 reconcilieert niet met de eigen lijst en is hier niet overgenomen (review-BE-AGT-064
  sectie C.8/D). Twee van deze routegroepen (`ai_router.py::suggest_nodes` en de 4
  `agents`-domein-routes) hadden vooraf HELEMAAL geen databasesessie in scope en kregen een
  nieuwe FastAPI-`Depends()`-dependency erbij.
- **Gevonden tijdens de review van dit document (niet door de sprint zelf), en SINDSDIEN
  GEFIXED in commit `d54bc5c4` (2026-08-25):** `create_hitl_request()` doet intern alleen
  `self._db.add(ticket); await self._db.flush()`
  (`src/core/tool_broker/hitl_repository.py:143-153`) -- NOOIT `commit()`. Direct daarna wierp
  deze functie een `HTTPException(403)` op op DEZELFDE `db`-sessie die via `Depends(get_db)`
  binnenkomt (`src/core/database/database.py::get_db()`, regels 503-515). FastAPI's
  yield-dependency-mechanisme gooit die exception terug IN de `get_db()`-generator op het
  yield-punt; `HTTPException` is een gewone `Exception` en werd gevangen door `except
  Exception: await session.rollback(); raise`. Een `flush()`-only INSERT overleeft die
  rollback niet. **Empirisch bevestigd** tegen de echte testdatabase (poort 5455, zie
  `review-BE-AGT-064.md` sectie C.9 voor het exacte reproductiescript en de uitkomst zoals
  gemeten voor de fix): de ticket-rij bestond na de simulatie NIET meer. Dit raakte ALLE 9
  aanroepers van deze functie zodra hun verdict HITL_REQUIRED was. **Fix:** commit `d54bc5c4`
  voegt een expliciete `await db.commit()` toe op het succespad, in een nieuwe `else:`-clausule,
  VOOR de `raise HTTPException` -- bewezen door de nieuwe integratietest
  `tests/integration/test_governance_gate_hitl_ticket_commit.py` (echte testdatabase, poort
  5455, mutatiegetest in beide richtingen: rood zonder de commit, groen met).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie/rol/scope: ONGEWIJZIGD -- identiek aan wat elke individuele aanroepende
  route al afdwingt vooraf; dit artefact voegt geen eigen auth-laag toe.
- Tenant-isolatie: `tenant_id`/`user_id` komen bij ELKE aanroeper uit de bestaande, geverifieerde
  auth-context van die route (JWT), nooit uit deze functie zelf opnieuw afgeleid.
- Feature flag: geen.

### 8. Request-specificatie

- Geen nieuw endpoint. Voor elk van de 9 bestaande aanroepende routes: ongewijzigde
  methode/route/path/query/body-parameters. Zie de eigen documentatie van elke route voor het
  volledige contract; dit artefact voegt uitsluitend intern een `db`-argument toe aan de
  INTERNE aanroep van `require_council_approval()`, geen wijziging aan wat de CLIENT verstuurt.

### 9. Response-specificatie

- Successtatus: ONGEWIJZIGD (elke route retourneert zijn eigen 200/201-schema bij een
  APPROVED-verdict; dit artefact raakt alleen het foutpad).
- Foutstatus 403 (`GOVERNANCE_BLOCKED`): body ONGEWIJZIGD qua bestaande sleutels (`code`,
  `message`, `decision_id`, `verdict`), met EEN NIEUWE, ADDITIEVE sleutel:
  `"hitl_request_id": str | None`. Waarde is een ticket-referentie-string bij een geslaagde
  aanmaak op een HITL_REQUIRED-verdict, anders altijd `None` (inclusief bij BLOCKED/MODIFIED/
  DEFERRED, en bij een HITL_REQUIRED zonder `db` of met een geweigerde ticketaanmaak).
- Foutstatus 500 (`COUNCIL_UNAVAILABLE`): ONGEWIJZIGD -- deze fix raakt uitsluitend het
  403-pad, niet het Council-crash-pad.

### 10. Validaties en constraints

- Geen nieuwe input-validatie op de 9 aanroepende routes zelf.

### 11. Business rules

- Elke HTTP-route die via deze poort gaat, geeft de client een bruikbare ticketverwijzing zodra
  een mens moet ingrijpen -- de client hoeft niet zelf te weten HOE een ticket wordt aangemaakt.

### 12. Afhankelijkheden

- `HITLTicketRepository.create_hitl_request()`, `AsyncSession` (nu via de
  `cva/dependencies.py`-facade in `legacy_router.py`, ADR-033-fix, zie Build summary).

### 13. Foutafhandeling

- 400/401/404/409/422/429: elk individueel nagelopen tegen de 9 aanroepende routes -- ONGEWIJZIGD
  ten opzichte van elke route's bestaande contract; dit artefact voegt geen nieuwe validatie- of
  auth-laag toe, het raakt uitsluitend het 403-pad van de gedeelde poort.
- 500 (`COUNCIL_UNAVAILABLE`): ONGEWIJZIGD, apart Council-crash-pad, niet geraakt door deze fix.
- 403: zoals hierboven -- nu met de additieve `hitl_request_id`-sleutel.
- `ValueError`/`PermissionError` uit `create_hitl_request()` zelf: gevangen, gelogd met
  `exc_info=True` en `type(exc).__name__` (backend-patterns.md SS10 -- ontbrak in de eerste
  versie van deze fix, gecorrigeerd na een Gate-2-bevinding op 5 plekken tegelijk), resulteert
  in `hitl_request_id: null`, NOOIT in een 500.
- **503**: n.v.t. -- geen downstream-afhankelijkheid die dit specifieke pad toevoegt.

### 14. Transacties en dataintegriteit

- **Zie de Doel-sectie en de review (`review-BE-AGT-064.md` sectie B/C.9, empirisch bevestigd
  tegen de echte testdatabase):** de ticket-aanmaak gebruikte `flush()`, niet `commit()`, en de
  daaropvolgende `HTTPException(403)` op dezelfde `Depends(get_db)`-sessie triggerde een
  `rollback()` in die sessie's eigen exception-afhandeling. **De ticket-rij overleefde dit tot
  commit `d54bc5c4` NIET** -- er werd GEEN duurzame INSERT gedaan ondanks dat de 403-body een
  `hitl_request_id` toonde. Dit was een bewezen code-defect, niet een documentatie-aanname; de
  fix (een expliciete `await db.commit()` na een geslaagde `create_hitl_request()`-aanroep,
  VOOR de `raise`) is doorgevoerd in commit `d54bc5c4` (2026-08-25), buiten de scope van dit
  documentatie-artefact zelf. Bewijs: `tests/integration/test_governance_gate_hitl_ticket_commit.py`
  (echte testdatabase, poort 5455) simuleert exact de `get_db()`-rollback-tak en toont dat de
  rij nu blijft bestaan; mutatiegetest in beide richtingen.

### 15. Telemetry / logging / tracing

- Nieuwe WARNING-log `governance.hitl_ticket_refused` bij een geweigerde ticketaanmaak.
- Bestaande WARNING-log `governance.council_blocked` ongewijzigd.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- Nieuwe tests in `tests/unit/copilot/council/test_governance_gate.py` (o.a. HITL_REQUIRED met
  `db` -> `hitl_request_id` gevuld; zonder `db` -> `None`; `ValueError`/`PermissionError` uit de
  repository -> `None`, geen crash).
- Nieuw testbestand `tests/unit/test_focus_builder_ai_router_council_gate.py` (3 tests) voor de
  enige route die vooraf helemaal geen databasesessie had.
- `tests/unit/test_focus_builder_council_gate.py` (35 regels nieuw) voor de bestaande
  Focus-Builder-aanroepers van deze poort.
- Mutatiebewijs: de `db is not None`-conditie tijdelijk verwijderd laat een test die "geen db,
  dus geen ticket" verwacht rood gaan (poging tot aanmaak zonder sessie); herstel maakt hem
  groen.
- **Geen van deze tests toetste de daadwerkelijke request-levenscyclus** (allemaal `AsyncMock`
  voor `db` en `HITLTicketRepository`) -- vandaar dat het defect in sectie 14 door de bestaande
  suite niet werd gevangen. Sindsdien toegevoegd (commit `d54bc5c4`): de integratietest
  `tests/integration/test_governance_gate_hitl_ticket_commit.py` (echte testdatabase, poort
  5455), die de door de review aanbevolen ontbrekende test daadwerkelijk invult (echte sessie,
  echte `HTTPException`, controle op de rij NA de request). De 10 bestaande mock-gebaseerde
  `service.db`-opstellingen in `test_focus_builder_ai_router_council_gate.py` en
  `test_focus_builder_council_gate.py` zijn in dezelfde commit van `MagicMock` naar `AsyncMock`
  omgezet -- anders faalde het succespad met een `TypeError` op `await service.db.commit()`.

### 18. Integratoruitleg

- Voor koppelende teams die al een 403 met `code: "GOVERNANCE_BLOCKED"` afvangen: er is een
  nieuwe, optionele sleutel `hitl_request_id` bijgekomen. Bestaande foutafhandeling die alleen
  op `code`/`message`/`decision_id`/`verdict` let, blijft zonder wijziging werken.
- Is `verdict == "hitl_required"` EN `hitl_request_id` niet `null`: er is een ticket-referentie
  meegegeven -- deze referentie wijst naar een echt bestaande rij. Zie sectie 14: tot commit
  `d54bc5c4` (2026-08-25) overleefde de onderliggende rij de eigen request niet en wees deze
  referentie naar niets; sindsdien commit de ticket-aanmaak expliciet voor de raise en is de
  referentie betrouwbaar.
- Is `hitl_request_id` `null` bij `verdict == "hitl_required"`: er is GEEN ticket-aanmaakpoging
  gelukt (bijv. een onbekende tool); toon de gebruiker geen ticketverwijzing die niet bestaat.

### 19. Trainingssamenvatting

- **Actor:** Elke ingelogde gebruiker die een actie uitvoert via een van de 9 routes achter
  deze poort.
- **Voorwaarde:** de actie krijgt een HITL_REQUIRED-verdict van de Council.
- **Actie (request):** de bestaande request van die specifieke route (ongewijzigd).
- **Systeemverwerking:** governance-poort roept `deliberate()` aan, maakt bij HITL_REQUIRED een
  ticket aan (indien `db` beschikbaar).
- **Succesrespons:** n.v.t. voor dit verdict-pad (een 403, geen 200 -- succes voor de client
  betekent hier "kreeg een bruikbare foutrespons met ticketverwijzing").
- **Foutrespons:** HTTP 403, `code: "GOVERNANCE_BLOCKED"`, `hitl_request_id` gevuld bij een
  geslaagde `create_hitl_request()`-aanroep, anders `null`. Zie sectie 14: sinds commit
  `d54bc5c4` betekent een gevulde `hitl_request_id` dat de rij de request overleeft (voordien
  was dat niet het geval).
- **Uitzonderingen:** zonder `db`-sessie (theoretisch, alle 9 huidige aanroepers geven hem mee):
  `hitl_request_id` altijd `null`.

---

## [BE-AGT-064-5] `execute_flow` eigen ticket-aanmaak + `hitl_request_id`

### 1. Type

- Endpoint (`BE-EP`) -- bestaande route, geen nieuwe.

### 2. Locatie

- Bestandspad: `src/core/api/v1/focus_builder/execution_router.py`.
- Klasse / functie: `execute_flow()`.

### 3. Gerelateerde flow

- BE-FLW-058, plus de bestaande `execute_flow`-flow (ongewijzigd van vorm, additieve sleutel).

### 4. Doel

- Identiek probleem als BE-AGT-064-4, maar deze route ging bewust NIET via
  `require_council_approval()` (zie Sectie 6) omdat ze al haar EIGEN, afwijkend 403-contract had
  voordat deze sprint begon.

### 5. Functionele beschrijving

- Identiek functioneel effect als BE-AGT-064-4 (ticket bij HITL_REQUIRED), maar op het eigen
  contract van deze route.

### 6. Technische beschrijving

- Eigen `try/except (ValueError, PermissionError)`-blok, zelfde exceptionklassen en
  `create_hitl_request()`-aanroep als BE-AGT-064-4, maar NIET via de gedeelde helper --
  bewuste code-duplicatie. Reden: `require_council_approval()` gebruiken zou dit route's
  bestaande foutcontract (`code: "FLOW_BLOCKED_BY_COUNCIL"`, `reason` i.p.v. `message`, geen
  `verdict`-sleutel) vervangen door het generieke contract (`GOVERNANCE_BLOCKED`/`message`/
  `verdict`) -- een potentiele breaking change voor de Focus Builder-frontend die niets met
  OP-167 te maken heeft. Bewust geaccepteerd als gedocumenteerd drift-risico (Gate 2-bevinding,
  niet gefixt): een toekomstige wijziging aan de gedeelde ticket-aanmaak-logica moet HANDMATIG
  ook hier toegepast worden.
- **Gevonden tijdens de review, gold hier OOK, en is in dezelfde commit gefixed:** `service.db`
  komt via `get_focus_builder_service()` -> `Depends(get_db)` -> dezelfde `database.py::
  get_db()` als BE-AGT-064-4. Omdat de duplicatie hierboven het IDENTIEKE patroon kopieert
  (`create_hitl_request()`'s `flush()`, dan een `HTTPException(403)` op diezelfde sessie),
  deelde `execute_flow` het bewezen defect van BE-AGT-064-4: de ticket-rij overleefde de eigen
  403-respons niet. Niet los apart gereproduceerd voor dit artefact (zelfde `get_db()`-functie,
  zelfde mechanisme, zie `review-BE-AGT-064.md` sectie C.9), maar het mechanisme was identiek en
  dus evenzeer van toepassing. **Fix:** commit `d54bc5c4` (2026-08-25) voegt ook hier een
  expliciete `await service.db.commit()` toe op het succespad, in een nieuwe `else:`-clausule,
  VOOR de `raise HTTPException`. Niet apart met een eigen integratietest bewezen (de nieuwe
  integratietest dekt alleen het `governance_gate.py`-pad), maar wel gedekt door de bestaande
  unit-tests in `tests/unit/test_focus_builder_council_gate.py`, die na de fix hun
  `service.db`-mock van `MagicMock` naar `AsyncMock` moesten omzetten (anders faalde het
  succespad met een `TypeError` op de nieuwe `await`).

### 7. Zichtbaarheids- en toegangsregels

- ONGEWIJZIGD -- identiek aan wat deze route al afdwong.

### 8. Request-specificatie

- ONGEWIJZIGD -- geen wijziging aan methode/route/parameters van `execute_flow`.

### 9. Response-specificatie

- Successtatus: ONGEWIJZIGD.
- Foutstatus 403 (`FLOW_BLOCKED_BY_COUNCIL`): body ONGEWIJZIGD qua bestaande sleutels (`code`,
  `reason`, `decision_id`), met EEN NIEUWE, ADDITIEVE sleutel: `"hitl_request_id": str | None`
  -- zelfde semantiek als BE-AGT-064-4 (gevuld bij geslaagde `create_hitl_request()`-aanroep,
  anders `None`). Zie sectie 14: sinds commit `d54bc5c4` betekent een gevulde waarde dat de rij
  de request overleeft (voordien was dat niet het geval).

### 10-12. Validaties/business rules/afhankelijkheden

- Identiek aan BE-AGT-064-4, toegepast op deze ene route.

### 13. Foutafhandeling

- 400/401/404/409/422/429/503: n.v.t. voor dit artefact (ongewijzigd, niet nieuw geraakt).
  500 (`COUNCIL_UNAVAILABLE`): ONGEWIJZIGD, apart Council-crash-pad.
- `ValueError`/`PermissionError` gevangen met `exc_info=True`, resulteert in
  `hitl_request_id: null`, nooit een 500 -- identiek patroon als BE-AGT-064-4.

### 14. Transacties en dataintegriteit

- **Zie de Doel-sectie en sectie 6 hierboven (empirisch bevestigd voor het identieke mechanisme
  bij BE-AGT-064-4, `review-BE-AGT-064.md` sectie C.9):** `create_hitl_request()` gebruikte
  `flush()`, niet `commit()`; `execute_flow` wierp direct daarna een `HTTPException(403)` op op
  `service.db`, dezelfde `Depends(get_db)`-sessie die bij een exception rollback't. **De
  ticket-rij overleefde dit tot commit `d54bc5c4` (2026-08-25) NIET.** Die commit voegt een
  expliciete `await service.db.commit()` toe op het succespad, VOOR de `raise`, zodat de INSERT
  nu wel duurzaam is.

### 15. Telemetry / logging / tracing

- Nieuwe WARNING-log `execute_flow.hitl_ticket_refused`.

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- Nieuwe tests bewijzen dezelfde matrix als BE-AGT-064-4 (HITL_REQUIRED met/zonder geslaagde
  ticketaanmaak) maar tegen dit route's EIGEN foutcontract-sleutels (`reason` i.p.v. `message`).
- Mutatiebewijs: identiek patroon. **Zelfde beperking als BE-AGT-064-4 gold hier: alle tests
  gebruikten `AsyncMock` voor `db`/`HITLTicketRepository` en toetsten dus niet de echte
  commit/rollback-cyclus -- vandaar dat het defect in sectie 14 niet door de bestaande suite
  werd gevangen.** Sindsdien (commit `d54bc5c4`): de 5 `service.db`-mock-opstellingen in
  `test_focus_builder_council_gate.py` zijn van `MagicMock` naar `AsyncMock` omgezet, en slaagden
  na de fix pas weer nadat die omzetting was doorgevoerd (voordien faalden ze met een 500 in
  plaats van 403, doordat `await service.db.commit()` op een kale `MagicMock` een `TypeError`
  gaf).

### 18. Integratoruitleg

- Voor koppelende teams die al een 403 met `code: "FLOW_BLOCKED_BY_COUNCIL"` afvangen: dezelfde
  additieve `hitl_request_id`-sleuteltoevoeging als bij de generieke poort (BE-AGT-064-4), maar
  dit route's overige sleutelnamen (`reason`, geen `verdict`) blijven ongewijzigd -- BEHANDEL
  DEZE ROUTE NIET ALSOF ZE HETZELFDE CONTRACT HEEFT ALS DE 9 ANDERE. `hitl_request_id` is ook
  hier betrouwbaar sinds het defect in sectie 14 is gefixed in commit `d54bc5c4`
  (2026-08-25).

### 19. Trainingssamenvatting

- Identiek aan BE-AGT-064-4, met dien verstande dat de foutrespons `code: "FLOW_BLOCKED_BY_
  COUNCIL"` en `reason` gebruikt in plaats van `GOVERNANCE_BLOCKED`/`message`. **Foutrespons:
  `hitl_request_id` gevuld betekent dat de rij bestaat -- zie sectie 14 (sinds commit
  `d54bc5c4`; voordien was dat niet gegarandeerd).**

---

## [BE-AGT-064-6] D4-002-HITL-floor dekt ook MODIFIED (skillsgaptraining-piloot)

### 1. Type

- Agent-/governance-gedrag (Annex III/HITL-"floor"-mechanisme binnen de ALS-specialist-agent
  basisklasse, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/als/agents/specialist_base.py`.
- Klasse / functie: de `_council_rejection()`-omgeving rond `effective_verdict`/
  `floor_applied` (D4-002).

### 3. Gerelateerde flow

- BE-FLW-058 (indirect, via de eigen ticket-aanmaak van deze floor-tak, apart van het
  raw-HITL_REQUIRED-pad dat via `outcome.hitl_ticket_ref` van BE-AGT-064-2 komt).

### 4. Doel

- Dit is een APART mechanisme van `ALWAYS_HITL_ACTIONS` (BE-AGT-064-1): een per-skill floor,
  geactiveerd door `human_in_the_loop: hitl` in het skill-manifest. Draait VANDAAG LIVE voor de
  `skillsgaptraining`-piloot-skill (in tegenstelling tot BE-AGT-064-1, dat inert is zolang
  `ALWAYS_HITL_ACTIONS` leeg is). Had exact dezelfde APPROVED-only-bug als OP-168: een
  `APPROVE_WITH_MODIFICATION`-verdict op deze piloot-skill strandde in een kale weigering zonder
  ticket, ook al eist het manifest juist ALTIJD menselijk toezicht.

### 5. Functionele beschrijving

- Voorheen: `effective_verdict = HITL_REQUIRED` (floor toegepast) alleen als
  `decision.verdict == APPROVED` EN het manifest `human_in_the_loop: hitl` heeft. Nu: ook als
  `decision.verdict == MODIFIED`.
- Deze floor maakt zijn EIGEN ticket aan (apart van het raw-HITL_REQUIRED-pad uit
  BE-AGT-064-2, dat via `outcome.hitl_ticket_ref` gaat) -- de `floor_applied`-boolean
  onderscheidt de twee paden om een dubbel ticket te voorkomen.

### 6. Technische beschrijving

- Conditie: `effective_verdict in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED) and
  self.config.get("human_in_the_loop") == "hitl"` -> `effective_verdict =
  DecisionVerdict.HITL_REQUIRED; floor_applied = True`.
- Onderscheid met BE-AGT-064-2: als `floor_applied` is `True`, ontstond het HITL_REQUIRED-verdict
  hier lokaal (niet als raw Council-verdict) en maakt deze code zijn eigen ticket aan, met een
  eigen `ticket_ref` in plaats van `outcome.hitl_ticket_ref`.
- Als `floor_applied` is `False` maar `effective_verdict is HITL_REQUIRED` (het RAUWE
  Council-verdict was al HITL_REQUIRED): gebruikt `outcome.hitl_ticket_ref` (BE-AGT-064-2's
  garantie), maakt GEEN eigen tweede ticket.

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. -- interne agent-logica. `executing_identity` is de skill-specifieke agent-identiteit
  (via `AgentCouncilOutcome`'s `agent_id`-doorgifte, BE-AGT-064-2), niet de generieke
  "copilot"-default.

### 8-9. Request-/Response-specificatie

- N.v.t. -- geen HTTP-laag. Interne effect op de tekst die de piloot-skill teruggeeft aan zijn
  eigen aanroeper (`ExecutionStatusContract`).

### 10. Validaties en constraints

- `self.config.get("human_in_the_loop") == "hitl"` -- exacte stringvergelijking, per
  skill-manifest.

### 11. Business rules

- Een skill die in zijn manifest ALTIJD menselijk toezicht eist, mag dat niet omzeilen bij een
  gedeeltelijk-goedgekeurd (MODIFIED) verdict, net zoals bij een unaniem goedgekeurd verdict.

### 12. Afhankelijkheden

- `AgentCouncilOutcome` (BE-AGT-064-2), de skill-manifest-configuratie
  (`config/tool_permissions.yml`-achtige structuur, per skill).

### 13. Foutafhandeling

- Ticket-aanmaak op deze floor-tak deelt hetzelfde `try/except (ValueError,
  PermissionError)`-patroon als BE-AGT-064-2/-3/-4/-5 (bevestigd tijdens Gate 2, dag 1, als
  bestaande blootstelling die "toch al werd aangeraakt" tegelijk gefixt is).

### 14. Transacties en dataintegriteit

- 1 INSERT bij succes, binnen de floor-tak's eigen DB-sessie. Geen dubbele rij: `floor_applied`
  voorkomt dat zowel de floor-tak als het raw-HITL_REQUIRED-pad allebei een ticket aanmaken voor
  dezelfde deliberatie.

### 15. Telemetry / logging / tracing

- Eindmelding onderscheidt expliciet "ticket aangemaakt: X" van "geen ticket kon worden
  aangemaakt" (gefixt tijdens Gate 2, dag 1 -- voorheen zou een mislukte aanmaak de misleidende
  tekst "(goedkeuringsticket aangemaakt: None)" hebben opgeleverd).

### 16. Caching

- N.v.t.

### 17. Acceptatiecriteria

- Nieuwe test `test_modified_verdict_also_floors_to_a_ticket_for_the_pilot_skill`
  (`test_council_gate_per_action.py`) -- spiegelbeeld van de bestaande APPROVED-floor-test.
- Bestaande `test_a_non_approving_verdict_never_becomes_an_approvable_ticket`-parametrisatie
  verloor `MODIFIED` uit zijn lijst (dat beweerde na deze fix het omgekeerde van de nieuwe
  waarheid).
- Mutatiebewijs (wegwerp-`git worktree` op HEAD): zonder de `MODIFIED`-tak faalt precies de
  nieuwe test (1 failure); met de tak: alle 69 gerichte tests (`tests/unit/als` +
  `tests/architecture`, HITL/council/specialist_base/skillsgaptraining-subset) slagen.

### 18. Integratoruitleg

- N.v.t. -- geen publieke API. Voor beheerders van skill-manifesten: een skill met
  `human_in_the_loop: hitl` krijgt nu GEGARANDEERD een ticket bij elk verdict behalve een reeds
  blokkerend verdict (VETO/DEFER), inclusief een gedeeltelijk-goedgekeurd (MODIFIED) verdict.

### 19. Trainingssamenvatting

- **Actor:** Systeem (de `skillsgaptraining`-piloot-skill, of elke andere skill met
  `human_in_the_loop: hitl` in zijn manifest).
- **Voorwaarde:** de Council geeft `APPROVED` of `MODIFIED` voor een actie van die skill.
- **Actie (request):** n.v.t. -- interne agent-uitvoeringsstap.
- **Systeemverwerking:** floor tilt het verdict op naar HITL_REQUIRED, maakt een eigen ticket
  aan.
- **Succesrespons:** ticket aangemaakt, `floor_applied = True`, eindmelding noemt de
  ticketreferentie.
- **Foutrespons:** geen ticket kon worden aangemaakt (onbekende tool/niet-geautoriseerde
  identiteit) -- eindmelding zegt dit expliciet, geen misleidende "None"-tekst.
- **Uitzonderingen:** VETO/DEFER blijven ongewijzigd geblokkeerd/uitgesteld, de floor raakt ze
  niet.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Elke bestaande 403-respons van een AI-gate (generiek via `require_council_approval`, of het
  eigen contract van `execute_flow`) kan nu een `hitl_request_id`-sleutel bevatten. Bestaande
  foutafhandeling die deze sleutel niet kent, blijft zonder wijziging werken -- het is een
  ADDITIEVE toevoeging, geen breaking change.
- `hitl_request_id` is alleen niet-`null` als het verdict `hitl_required` was EN de
  `create_hitl_request()`-aanroep zelf slaagde. Toon de gebruiker geen ticketverwijzing op basis
  van het `verdict`-veld alleen -- controleer ook `hitl_request_id`.
- **Bevonden tijdens de review (zie Risico's hieronder en artefact BE-AGT-064-4/-5 sectie 14):
  voor de 9 routes achter `require_council_approval` en voor `execute_flow` was een gevulde
  `hitl_request_id` tot commit `d54bc5c4` (2026-08-25) GEEN garantie dat de rij bestond.**
  Sindsdien commit de ticket-aanmaak expliciet voor de raise, en is de referentie betrouwbaar
  -- een gebruikersgerichte "ga naar je ticket"-flow kan hierop bouwen.
- `execute_flow` (Focus Builder) heeft een ANDER foutcontract dan de overige 9 routes
  (`reason`/`FLOW_BLOCKED_BY_COUNCIL` i.p.v. `message`/`GOVERNANCE_BLOCKED`/`verdict`) -- dit was
  al zo voor deze sprint en blijft zo.
- Er is geen nieuwe publieke, door de client aan te roepen actie bijgekomen -- alle wijzigingen
  liggen in het BESTAANDE foutpad van bestaande routes.

---

## Open aannames

- Dat de 5 genoemde aanroepers van `AgentCouncil.deliberate()` (zoals vastgelegd in de
  BE-AGT-051-audit) nog steeds de volledige, actuele aanroepverzameling in productiecode zijn --
  niet opnieuw exhaustief herverifieerd binnen deze sprint zelf (de dagbriefs gaan uit van die
  eerdere telling als basis).
- Dat `service.py::submit_proactive_proposal`'s enige productie-aanroeper
  (`proactive/monitor.py::propose_to_council`) inderdaad de enige is die vandaag bestaat --
  overgenomen uit de dag-1-final-approver-brief, niet opnieuw zelf gegrept voor dit document.

## Open vragen

- **Opgelost (was hier vastgelegd als urgent, uit de review van dit document): de
  commit/rollback-bug in BE-AGT-064-4/-5 (zie Risico's) is gefixed in commit `d54bc5c4`
  (2026-08-25).** Fix: een expliciete `await db.commit()` (governance_gate.py) / `await
  service.db.commit()` (execution_router.py) direct na een geslaagde
  `create_hitl_request()`-aanroep, voor de `raise HTTPException(403)`, plus een nieuwe
  integratietest tegen een echte databasesessie (`tests/integration/
  test_governance_gate_hitl_ticket_commit.py`, geen `AsyncMock`) die de rij na een gesimuleerde
  403 daadwerkelijk opvraagt. Dit was een eigen codewijziging met een eigen Gate 1-3-traject,
  niet iets dat dit documentatie-artefact zelf oploste.
- Wanneer `send_notification` (of een andere actie die via `submit_proactive_proposal` loopt)
  als geregistreerde tool wordt toegevoegd -- dat zou het enige resterende restgat
  (BE-AGT-064-3) daadwerkelijk dichten in plaats van alleen veilig maken. Niet ingepland,
  aan Rakesh.
- Of de code-duplicatie tussen `execute_flow` en `require_council_approval` (BE-AGT-064-5) op
  termijn moet worden opgelost door `execute_flow`'s foutcontract te migreren naar het generieke
  contract (een frontend-brekende wijziging die buiten deze sprint valt).
- Er is GEEN gecombineerde, volledige `tests/unit tests/architecture tests/core -n 4`-run
  gerapporteerd over de SOM van alle 4 sprintdagen samen -- elke dag rapporteerde een eigen,
  gerichte sweep (2642 / 2950 / 69+47+21+2 gerichte tests, alle 0 failed volgens de
  final-approver-briefs van die dag). Een gecombineerde eindrun voor dag 4's eigen
  sluiting-DoD (genoemd in de dag-3-brief als "volgende stap") is een apart actiepunt, niet
  onderdeel van dit documentatie-artefact.

---

## Risico's

- **Gevonden tijdens de documentatie-review van dit artefact (niet door de sprint zelf, niet
  door een van de 5 dagbriefs), en SINDSDIEN GEFIXED in commit `d54bc5c4` (2026-08-25):
  `governance_gate.py::require_council_approval` (BE-AGT-064-4, 9 aanroepers) en
  `execution_router.py::execute_flow` (BE-AGT-064-5) maakten hun HITL-ticket via
  `create_hitl_request()`, die alleen `flush()` doet, en wierpen daarna direct een
  `HTTPException(403)` op op DEZELFDE `Depends(get_db)`-sessie. Die sessie rollback't bij elke
  exception (`src/core/database/database.py::get_db()`), waardoor de net aangemaakte ticket-rij
  NOOIT persisteerde. Empirisch bevestigd tegen de echte testdatabase (zie
  `docs/backend/review/review-BE-AGT-064.md` sectie B/C.9 voor het reproductiescript en de
  uitkomst zoals gemeten voor de fix). De 403-body toonde een `hitl_request_id` die naar een
  niet-bestaande rij verwees -- functioneel ERGER dan de oorspronkelijke OP-167-bug, omdat het
  oogde alsof toezicht geregeld was. Geen bestaande test ving dit (alle tests voor deze 2
  artefacten gebruikten `AsyncMock`). Dit was een CODE-defect, geen documentatiefout. **Fix
  (commit `d54bc5c4`):** een expliciete `await db.commit()` (governance_gate.py) / `await
  service.db.commit()` (execution_router.py) na een geslaagde ticketaanmaak, voor de `raise`, in
  een nieuwe `else:`-clausule op het bestaande `try/except`-blok. Bewijs: nieuwe integratietest
  `tests/integration/test_governance_gate_hitl_ticket_commit.py` tegen de echte testdatabase
  (poort 5455), simuleert `get_db()`'s exception-rollback-tak rechtstreeks op dezelfde sessie,
  mutatiegetest in een wegwerp-worktree (rood zonder de commit, groen met). De bestaande
  mock-gebaseerde unit-tests voor het succespad zijn in dezelfde commit van `MagicMock` naar
  `AsyncMock` omgezet voor `service.db` (anders faalde het succespad met een `TypeError` op de
  nieuwe `await`).**
- Het enige MEDIUM-achtige, door de sprint zelf al gedocumenteerde resterende punt is het
  BE-AGT-064-3-restgat
  (`submit_proactive_proposal`/`send_notification`) -- expliciet gedocumenteerd, niet verhuld,
  geen crash-risico, wel een functioneel gat in het AI Act art. 14-toezicht voor dat ene pad.
- Code-duplicatie tussen `execute_flow` en `require_council_approval` (BE-AGT-064-5) is een
  onderhouds-/drift-risico (een toekomstige wijziging aan de gedeelde logica moet op TWEE
  plekken toegepast worden), bewust geaccepteerd, niet CRITICAL/HIGH.
- Gate-status per dag (uit de final-approver-briefs, niet zelf herverifieerd voor dit document):
  dag 1 -- 248 gerichte tests groen, 2642/0 op de architecture+als+copilot+tool_broker+agents-
  sweep, pyright 0, mypy 0, ruff schoon. Dag 2 -- 86 gerichte tests groen, 2950/0 op een bredere
  sweep, pyright 0, mypy 0, ruff schoon, `agent_runtime` Ce-ceiling 227 ongewijzigd. Dag 3 -- 69
  gerichte tests groen op de HITL/council/specialist_base/skillsgaptraining-subset, pyright 0 op
  de 4 gewijzigde bestanden (7 nieuwe mypy-fouten gemeld, alle drie herleid tot
  `src/core/api/v1/foundation/*` van een gelijktijdige, andere sessie, niet deze sprint's
  bestanden), ruff schoon.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- de 10 bestaande routes/functies behouden hun
      bestaande happy-path-gedrag; dit werk raakt uitsluitend het HITL_REQUIRED-foutpad.
- [x] Alle foutstatus-codes getest -- 403 (met en zonder `hitl_request_id`), 500
      (`COUNCIL_UNAVAILABLE`, ongewijzigd).
- [x] Auth en permissies getest -- `executing_identity`-onderscheid tussen agent-specifieke
      paden (BE-AGT-064-2/-6) en gebruikers-geinitieerde HTTP-routes (BE-AGT-064-4/-5)
      geverifieerd, geen violatie van OP-163's redenering.
- [x] Tenant-isolatie getest -- `tenant_id` komt bij elk artefact uit de auth-context van de
      oorspronkelijke aanroeper, nooit uit een request-body-veld.
- [x] Validaties getest (ongeldige invoer) -- onbekende tool (`ValueError`), niet-geautoriseerde
      identiteit (`PermissionError`), beide mutatiegetest op elke van de 5 aanmaakplekken.
- [x] Edge cases getest (leeg, null, grenzen) -- `db=None` (graceful degradation),
      `ALWAYS_HITL_ACTIONS` leeg (geen gedragswijziging op BE-AGT-064-1), dubbel-ticket-preventie
      via `floor_applied` (BE-AGT-064-6).
- [x] Dataintegriteit en transacties getest voor BE-AGT-064-1/-2/-3/-6 -- geen halve rij bij een
      geweigerde ticketaanmaak, geen dubbele rij bij floor + raw-HITL_REQUIRED tegelijk.
      **[x] Voor BE-AGT-064-4/-5: de review vond het defect in Risico's (ticket-rij overleefde
      de eigen 403-respons niet, geen bestaande test dekte de echte commit/rollback-cyclus). Dit
      is sindsdien gefixed in commit `d54bc5c4`, bewezen door de nieuwe integratietest
      `tests/integration/test_governance_gate_hitl_ticket_commit.py` tegen de echte
      testdatabase.**
- [ ] Performance / load getest -- n.v.t., geen nieuwe hot path, ticket-aanmaak is een enkele
      INSERT binnen een reeds bestaande requesttransactie.
- [ ] Caching getest -- n.v.t., geen caching-laag geraakt.
- [x] Logging en tracing gecontroleerd -- `exc_info=True`/`type(exc).__name__` op alle 5
      except-blokken (backend-patterns.md SS10), nieuwe WARNING-logs per artefact.

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle 6 artefacten geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig per artefact
- [x] Technische beschrijving aanwezig per artefact
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig (BE-AGT-064-4/-5, de artefacten met HTTP-impact)
- [x] Trainingssamenvatting is aanwezig per artefact
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd voor BE-AGT-064-1/-2/-3/-6 (per de final-approver-briefs van dag
      1-3); voor BE-AGT-064-4/-5 bracht de review van dit document zelf een dataintegriteitsdefect
      aan het licht dat de sprint niet had gevonden -- zie Risico's. Dat defect is sindsdien
      gefixed in commit `d54bc5c4` (2026-08-25).
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS na Ronde 2
      (`docs/backend/review/review-BE-AGT-064.md`) -- het defect was een bevinding OVER de code,
      correct en expliciet gedocumenteerd, niet een documentatiegebrek dat de
      APPROVED-WITH-MINOR-GAPS-kwalificatie van dit spec-document zelf in de weg stond. De
      onderliggende CODE-fix is inmiddels doorgevoerd in commit `d54bc5c4`, met een nieuwe
      integratietest als bewijs.
