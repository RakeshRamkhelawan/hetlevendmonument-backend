# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-049 (primair), gerelateerd: BE-SEC-047 (secundair, zie artefact 2)
- Feature naam: Annex III/HITL-classificatie wordt een echte floor op het Council-gate (ADR-036 D4-001/D4-002, OP-165)
- Status: GEBOUWD, wacht op review
- Auteur: Claude (sprint-uitvoering, ADR-036 fix-sprint Dag 3)
- Reviewer: onafhankelijke doc-reviewer-agent
- Datum: 2026-08-18
- Gerelateerde user story / ticket: ADR-036 fix-sprint, Dag 3 (`docs/agent-briefs/generated/2026-08-18-sprint-dag-3.md`)
- Gerelateerde router / module: `src.core.als.agents.skill_manifest`, `src.core.als.agents.specialist_base`, `src.core.als.agents.skills.manifests.skillsgaptraining`
- Gerelateerde frontend endpoints: geen (interne governance-logica, geen HTTP-laag)
- Gerelateerde database tabellen: `hitl_tickets` (ongewijzigd schema -- deze fix produceert alleen MEER tickets via een reeds bestaand pad, ADR-036 OP-163)
- Versie: v1

---

## Doel en scope

### Doel

Rakesh heeft eerder in deze sprint expliciet besloten: de piloot-skill (`skillsgaptraining`, die
personeelsgegevens leest en per functie een oordeel over vaardigheidskloven produceert) wordt
gereclassificeerd naar EU AI Act Annex III met verplicht menselijk toezicht
(`human_in_the_loop: hitl`), in plaats van kunstmatig op `hotl` gehouden te worden. Bij het
uitvoeren van die reclassificatie bleek echter dat het manifestveld `human_in_the_loop` GEEN
enkel gevolg had: `SkillManifest.to_config()` parste het veld wel uit de YAML, maar gaf het
nooit door aan `BaseSpecialistAgent.config`, en `_council_rejection()` (het Council-gate dat elke
tool-actie van een skill toetst) had geen enkele logica die dat veld ooit las. Zelfs met de
juiste classificatie zou een unaniem APPROVED-Councilverdict de piloot gewoon direct hebben
laten uitvoeren -- de classificatie was een label, geen grens. Dat is het omgekeerde van wat AI
Act art. 14 eist: een mens moet de output daadwerkelijk kunnen goedkeuren of tegenhouden, niet
dat de Council hem kan overstemmen.

Deze fix maakt de classificatie voor het eerst echt afdwingend: een Annex III/HITL-skill kan
NOOIT meer automatisch doorgaan, ongeacht hoe de Council-officieren stemmen.

### In scope

- `SkillManifest.to_config()`: geeft `annex_iii_classification` en `human_in_the_loop` nu door
  aan de agent-config (beide velden bestonden al op de dataclass en werden al uit YAML
  geparsed, maar ontbraken in de config-projectie).
- `_council_rejection()`: nieuwe "floor" die een APPROVED-verdict optilt naar `HITL_REQUIRED`
  zodra `self.config.get("human_in_the_loop") == "hitl"` -- ALLEEN een upgrade, nooit een
  downgrade van BLOCKED/DEFERRED/MODIFIED.
- `skillsgaptraining.yml`: gereclassificeerd van `annex_iii_classification: none` /
  `human_in_the_loop: hotl` naar `annex_iii` / `hitl` (Rakesh's productbeslissing).
- `test_hr_agents_declare_their_annex_iii_classification.py`: `skillsgaptraining.yml`
  verwijderd uit de `KNOWN_UNDECLARED`-allowlist (sluit OP-144 voor de piloot).
- Zeven ONGERELATEERDE testbestanden herzien: elk gebruikte de piloot-skill als "gewoon een
  echte skill met tools" om een ANDER concern te testen (budgetgrenzen, deelfouten,
  permissieroutering, evaluatieset-gedrag, pack-orchestratie, proposal-vorm) en verwachtte
  daarbij direct-uitvoeren op een APPROVED-verdict. Elk kreeg een expliciete
  `human_in_the_loop`-override op het test-exemplaar met een toelichting waarom (zie
  Artefact 1, sectie 12).

### Out of scope

- De DRIE andere skills die al `annex_iii_classification: annex_iii` / `human_in_the_loop: hitl`
  declareerden (`employeesentiment`, `internalmobility`, `talentacquisition`) worden door deze
  fix ook geraakt (de floor is generiek, niet piloot-specifiek), maar dat heeft VANDAAG geen
  gedragseffect: geen van drieen staat in `packs.py`'s `_PILOT_WIRED_AGENT_IDS`, en het
  generieke OODA-pad kan voor hen (net als voor de overige 131 skills) geen initiator meegeven,
  dus ze bereiken `_council_rejection()` nooit. Zie Risico's.
- De overige elf HR-datatoegangsskills die nog `annex_iii_classification: none` declareren
  (OP-144, nu GEDEELTELIJK -- alleen de piloot is vandaag opgelost).
- `HIGH_RISK_DEPARTMENTS`/`_ComplianceAdapter`'s EIGEN, onafhankelijke risicoclassificatie
  (`governance/ai_act_classifier.py`) -- deze fix raakt die niet; de floor werkt volledig los
  van wat de ComplianceOfficer concludeert.

---

## Build summary

- Nieuw gebouwd: geen nieuwe endpoints, modellen of migraties.
- Gewijzigd:
  - `src/core/als/agents/skill_manifest.py` (`to_config()`)
  - `src/core/als/agents/specialist_base.py` (`_council_rejection()`)
  - `src/core/als/agents/skills/manifests/skillsgaptraining.yml`
  - `tests/architecture/test_hr_agents_declare_their_annex_iii_classification.py`
  - `tests/fixtures/agent_governance.py` (`_ApprovedDecision`-stub kreeg `decision_id`)
  - `tests/unit/als/test_council_gate_per_action.py` (nieuwe/bijgewerkte floor-tests)
  - `tests/unit/als/test_act_partial_tool_failure.py`, `tests/unit/als/test_skill_budget_enforcement.py`,
    `tests/unit/als/test_skillsgaptraining_evaluation_set.py`,
    `tests/unit/als/test_agent_governance_hardening.py` (2 constructieplekken),
    `tests/unit/tool_broker/test_skillsgaptraining_tool_permissions.py`,
    `tests/unit/als/enterprise/test_pack_orchestrator_execute_step.py`,
    `tests/unit/copilot/test_agent_proposal_carries_disclosure_and_message.py`
    (`human_in_the_loop`-override op het test-exemplaar, zie Out of scope-toelichting)
- Verwijderd: niets.
- Beinvloede bestaande flows: elke actie van de piloot-skill die de Council raadpleegt (via
  `execute_with_manifest_prompt()`, het enige gewirede uitvoerpad) -- was al beperkt tot
  `skillsgaptraining` alleen, ongewijzigd door deze fix.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-049 | `_council_rejection()` Annex III/HITL-floor | BE-AGT (agent-gedrag) | `src/core/als/agents/specialist_base.py`, `src/core/als/agents/skill_manifest.py` | Wijziging | BE-FLW-058 (ADR-036 OP-163) |
| BE-SEC-047 | `skillsgaptraining.yml`-reclassificatie naar Annex III/HITL | BE-SEC (classificatie/toegangsbeleid) | `src/core/als/agents/skills/manifests/skillsgaptraining.yml` | Wijziging | BE-FLW-058 |

---

## Detaildocumentatie per artefact

---

## [BE-AGT-049] `_council_rejection()` Annex III/HITL-floor

### 1. Type

- Agent-gedrag (interne methode van `BaseSpecialistAgent`, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/als/agents/specialist_base.py:366-435` (de floor-berekening en de
  APPROVED/HITL_REQUIRED-takken die er gebruik van maken); `src/core/als/agents/skill_manifest.py:94-119`
  (`to_config()`).
- Klasse / functie: `BaseSpecialistAgent._council_rejection()`, `SkillManifest.to_config()`.

### 3. Gerelateerde flow

- BE-FLW-058 (ADR-036 OP-163, Dag 2 van deze sprint) -- deze fix bouwt op dezelfde flow: een
  geflooide actie doorloopt IDENTIEK het bestaande HITL_REQUIRED-ticketpad.

### 4. Doel

- Een skill waarvan het manifest `human_in_the_loop: hitl` declareert, mag NOOIT een actie
  automatisch laten doorgaan, ook niet als de Council unaniem APPROVED geeft.

### 5. Functionele beschrijving

- Voor een Annex III/HITL-skill ontstaat bij ELKE tool-actie een goedkeuringsticket, ongeacht
  het Council-oordeel -- behalve als de Council al BLOCKED/DEFERRED/MODIFIED gaf (die blijven
  ongewijzigd afwijzend). Voor elke andere skill (`human_in_the_loop` afwezig of `hotl`)
  verandert er niets: een APPROVED-verdict laat de actie zoals voorheen direct door.
- Effect op systeemtoestand: identiek aan BE-FLW-058 -- een nieuwe `hitl_tickets`-rij bij een
  APPROVED-verdict op een HITL-skill, waar voorheen de tool gewoon zou zijn uitgevoerd.

### 6. Technische beschrijving

- `SkillManifest.to_config()` (`skill_manifest.py:94-119`) geeft nu ook
  `"annex_iii_classification": self.annex_iii_classification` en
  `"human_in_the_loop": self.human_in_the_loop` door. Beide velden bestonden al op de dataclass
  (regel 55-56) en werden al uit YAML geparsed met defaults `"none"`/`"hotl"` (regel 81-82) --
  deze stap ontbrak alleen in de config-projectie die `BaseSpecialistAgent.__init__` in
  `self.config` zet.
- `_council_rejection()` (regel 376-386): berekent een `effective_verdict`, gelijk aan
  `decision.verdict` behalve wanneer `decision.verdict is DecisionVerdict.APPROVED AND
  self.config.get("human_in_the_loop") == "hitl"`, in welk geval `effective_verdict` wordt
  `DecisionVerdict.HITL_REQUIRED`. Alle downstream controles (regel 383 APPROVED-check, regel
  386 HITL_REQUIRED-tak, regel 426 en 435 in de teruggegeven boodschap) gebruiken consequent
  `effective_verdict`, niet de rauwe `decision.verdict` -- de ECHTE Council-beslissing
  (`decision.explanation_for_user`, `decision.decision_id`) blijft ongewijzigd beschikbaar voor
  logging/ticketinhoud.
- Geen nieuw ticket-mechanisme: een geflooide actie loopt door PRECIES dezelfde
  `HITLTicketRepository.create_hitl_request(..., executing_identity=self.agent_id)`-aanroep als
  een echte Council-HITL_REQUIRED (ADR-036 OP-163, Dag 2) -- inclusief dezelfde
  identiteitscontrole bij aanmaken EN verzilveren.
- Geen externe calls, caching of events buiten wat BE-FLW-058 al beschrijft.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne methode-aanroep).
- Tenant-isolatie: ongewijzigd -- `tenant_id=self.tenant_id`, nooit uit request body of
  modeloutput.
- `self.config.get("human_in_the_loop")` komt UITSLUITEND uit het code-gebundelde YAML-manifest
  van de skill (`SkillManifest.load()`, een vast, relatief bestandspad per skill-klasse) --
  nooit uit request body, database-rij die een tenant kan wijzigen, of modeloutput. Geen
  productie-aanroeper geeft dit veld als override-kwarg mee (geverifieerd: nul treffers voor een
  `human_in_the_loop=`-kwarg-aanroep buiten testcode).

### 8. Request-specificatie

- n.v.t. (geen HTTP-endpoint). Functie-signatuur ongewijzigd:
  `async def _council_rejection(self, tool_name: str, params: dict[str, Any]) -> str | None`.

### 9. Response-specificatie

- Voor een Annex III/HITL-skill met een APPROVED-Councilverdict: identiek aan het bestaande
  HITL_REQUIRED-antwoord (BE-FLW-058) -- een string met de ticketref.
- Voor elke andere skill, of een niet-APPROVED-verdict: ongewijzigd bestaand gedrag.

### 10. Validaties en constraints

- `self.config.get("human_in_the_loop")` wordt met een EXACTE stringvergelijking (`== "hitl"`)
  getoetst, geen truthiness-check. Een ontbrekend, leeg of afwijkend-gespeld veld (bv. `"HITL"`)
  gedraagt zich identiek aan `"hotl"` -- géén floor. Dit is HETZELFDE fail-gedrag als vóór deze
  fix (het veld bereikte `self.config` toen nooit), dus geen regressie; wel een resterend risico
  op een stille typefout in een toekomstig manifest, zie Open aannames.

### 11. Business rules

- De floor is ALLEEN een upgrade (APPROVED -> HITL_REQUIRED), nooit een downgrade. Drie
  aparte mutaties, drie aparte tests: (1) floor-conditie verwijderd -> `test_approved_
  verdict_still_floors_to_a_ticket_for_the_pilot_skill` wordt rood; (2) floor-conditie
  verbreed tot "altijd" -> `test_a_non_hitl_skill_still_executes_directly_on_approval` wordt
  rood; (3) de `effective_verdict is DecisionVerdict.APPROVED`-conjunct laten vallen (zodat
  ELK verdict voor een HITL-skill naar HITL_REQUIRED gaat, ook een Council-BLOCK) ->
  `test_a_non_approving_verdict_never_becomes_an_approvable_ticket` wordt rood. Mutatie (3)
  ontbrak bij de oorspronkelijke dag-3-implementatie -- de blinde review (2026-08-19) toonde
  dat mutaties (1) en (2) de "nooit een downgrade"-belofte niet daadwerkelijk dekten, zie
  Risico's.
- De floor is generiek voor elke skill die `human_in_the_loop: hitl` declareert, niet
  piloot-specifiek in code. Vandaag heeft dat alleen gedragseffect voor de piloot (zie Out of
  scope voor de drie andere skills die het veld al declareerden).

### 12. Afhankelijkheden

- `HITLTicketRepository.create_hitl_request()` (ADR-036 OP-163, ongewijzigd).
- Zeven test-bestanden die de piloot-skill als generiek "echte skill"-testvehikel gebruiken,
  kregen een expliciete `agent.config["human_in_the_loop"] = "hotl"`-override direct na
  constructie (of, voor het orchestrator-pad in
  `test_pack_orchestrator_execute_step.py`, een tijdelijke `SkillManifest.to_config`-patch,
  omdat die test de skill intern via de catalogus construeert en er geen instantie is om na
  constructie te overschrijven). Elk met een comment dat uitlegt WAAROM: die tests toetsen een
  ander concern (budgetgrenzen, deelfouten, permissieroutering, evaluatieset-gedrag,
  proposal-vorm) en zouden anders een echte databasesessie proberen te openen om een ticket aan
  te maken, wat niets zegt over hun eigenlijke onderwerp.

### 13. Foutafhandeling

- Ongewijzigd t.o.v. BE-FLW-058: elke exceptie uit het geflooide pad (DB-fout, `ValueError`,
  `PermissionError`) wordt door `act()`'s bestaande brede `except Exception` afgevangen.

### 14. Transacties en dataintegriteit

- Ongewijzigd t.o.v. BE-FLW-058 (zelfde `get_db_session()`/`HITLTicketRepository`-pad).

### 15. Telemetry / logging / tracing

- Geen nieuwe logregels; bestaand pad hergebruikt.

### 16. Caching

- Geen caching op dit pad. `SkillManifest.load()` leest de YAML vers per skill-instantie, geen
  gedeelde/gecachte manifest-state tussen instanties (geverifieerd: geen class-level cache).

### 17. Acceptatiecriteria

- Een Annex III/HITL-skill met een APPROVED-Councilverdict resulteert in een ticket, niet in
  directe uitvoering (bewezen:
  `tests/unit/als/test_council_gate_per_action.py::TestVerdictIsHonoured::test_approved_verdict_still_floors_to_a_ticket_for_the_pilot_skill`).
- Een NIET-Annex-III/HITL-skill met een APPROVED-verdict blijft direct uitvoeren (bewezen:
  `TestTheFloorOnlyAppliesToAnnexIiiHitlSkills::test_a_non_hitl_skill_still_executes_directly_on_approval`,
  die expliciet `human_in_the_loop: "hotl"` zet, niet slechts afwezig laat -- vangt zo ook een
  presence-check-mutatie van de voorwaarde).
- Drie tool-calls in een invocatie op een geflooide skill leveren drie afzonderlijke tickets op,
  net zoals ze drie afzonderlijke beraadslagingen opleveren (bewezen:
  `test_council_is_consulted_once_per_tool_call`).
- `agent_runtime`'s DSM Ce-ceiling blijft `<= 225` (ongewijzigd door deze fix -- geen nieuwe
  cross-bucket imports).
- Volledige mandatory suite (`tests/unit tests/architecture tests/core -n 4`): 15703 passed, 0
  failed (was 15702 na Dag 2).

### 18. Integratoruitleg

- Geen publieke API-wijziging. Voor teams die een NIEUWE skill met `human_in_the_loop: hitl`
  toevoegen: elke tool-actie van die skill produceert vanaf nu altijd een goedkeuringsticket bij
  een APPROVED-Councilverdict, ongeacht hoe de Council-officieren stemmen.

### 19. Trainingssamenvatting

- Actor: een ALS-skill met `human_in_the_loop: hitl` in haar manifest (vandaag: de piloot
  `skillsgaptraining`).
- Voorwaarde: de Council heeft de voorgestelde actie beoordeeld met verdict `APPROVED`.
- Actie (request): de skill probeert een tool uit te voeren.
- Systeemverwerking: `_council_rejection()` tilt het effectieve verdict op naar `HITL_REQUIRED`
  en maakt een goedkeuringsticket aan via het bestaande OP-163-pad; de tool wordt niet
  uitgevoerd.
- Succesrespons: identiek aan BE-FLW-058 -- een string met de ticketref.
- Foutrespons: identiek aan BE-FLW-058.
- Uitzonderingen: BLOCKED/DEFERRED/MODIFIED-verdicten blijven ongewijzigd afwijzend, ook voor
  een Annex III/HITL-skill; een skill zonder `human_in_the_loop: hitl` merkt niets van deze fix.

---

## [BE-SEC-047] `skillsgaptraining.yml`-reclassificatie naar Annex III/HITL

### 1. Type

- Classificatie/toegangsbeleid (BE-SEC).

### 2. Locatie

- Bestandspad: `src/core/als/agents/skills/manifests/skillsgaptraining.yml:4-5`.

### 3. Gerelateerde flow

- BE-FLW-058.

### 4. Doel

- Het manifest van de piloot-skill eerlijk laten verklaren wat het systeem doet
  (personeelsgegevens lezen, per functie een oordeel produceren), conform Rakesh's expliciete
  productbeslissing eerder in deze sprint.

### 5. Functionele beschrijving

- `annex_iii_classification: none` -> `annex_iii`; `human_in_the_loop: hotl` -> `hitl`. Zonder
  BE-AGT-049 (de floor) zou deze wijziging GEEN gedragseffect hebben -- de twee artefacten zijn
  daarom afhankelijk en samen gebouwd/gereviewd.

### 6. Technische beschrijving

- Zuivere YAML-datawijziging, geen codepad. Het effect ontstaat uitsluitend via BE-AGT-049's
  floor die dit veld nu leest.

### 7. Zichtbaarheids- en toegangsregels

- Ongewijzigd -- dit is een classificatievlag, geen toegangscontrole op zichzelf.

### 8-16. (n.v.t. -- zuivere manifestwaarde, geen eigen request/response/validatie/business-rule/
afhankelijkheid/foutafhandeling/transactie/telemetry/caching los van BE-AGT-049)

### 17. Acceptatiecriteria

- `tests/architecture/test_hr_agents_declare_their_annex_iii_classification.py::test_the_known_gap_is_not_stale`
  slaagt nu dat `skillsgaptraining.yml` niet meer in `KNOWN_UNDECLARED` staat (sluit OP-144 voor
  de piloot).

### 18. Integratoruitleg

- Geen publieke API-wijziging.

### 19. Trainingssamenvatting

- Actor: n.v.t. (statische configuratiewijziging).
- Voorwaarde: n.v.t.
- Actie: n.v.t.
- Systeemverwerking: het manifest declareert vanaf nu `annex_iii`/`hitl`; BE-AGT-049 maakt dat
  afdwingend.
- Succesrespons/Foutrespons: n.v.t.
- Uitzonderingen: geen.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen nieuwe of gewijzigde publieke HTTP-endpoints.
- Voor teams die een nieuwe ALS-skill bouwen met toegang tot persoonsgegevens of
  arbeidsrelevante besluiten: zet `human_in_the_loop: hitl` in het manifest als Annex III van
  toepassing is -- dat veld heeft sinds deze fix een echt, afdwingend gevolg.

---

## Open aannames

- Geen enum-validatie op `human_in_the_loop` in `SkillManifest.load()`: een toekomstige typefout
  in een manifest (bv. `"HITL"` met hoofdletters, of een trailing spatie) zou stil GEEN floor
  opleveren voor die skill, zonder dat een test dat vangt. Dit is een PRE-EXISTING gat (het veld
  had voor deze fix nooit enig gevolg, dus de typefout kon nooit stil iets breken) dat nu voor
  het eerst praktisch relevant wordt. Genoteerd voor een latere sprint; geen actie vandaag, want
  dit vereist een eigen afweging (welke waarden zijn geldig, wat gebeurt er met een ONGELDIGE
  waarde -- fail-closed door de skill te blokkeren, of fail-open zoals vandaag).

## Open vragen

- Geen.

## Risico's

- Geen resterende CRITICAL/HIGH. Gate 2 (code-reviewer + security-reviewer, 2 rondes) bevond:
  geen enkel productiepad kan de floor omzeilen (`effective_verdict` wordt consistent gebruikt,
  geen restant-gebruik van het rauwe `decision.verdict`); de floor werkt identiek voor een
  geflooide actie als voor een echte Council-HITL_REQUIRED (zelfde identiteitscontrole bij
  aanmaken en verzilveren, ADR-036 OP-163). Ronde 1 vond een gemist testbestand
  (`tests/unit/copilot/test_agent_proposal_carries_disclosure_and_message.py`, buiten de drie
  autouse-testbomen, dus niet gedekt door hetzelfde patroon als de andere zes) en een per
  ongeluk verwijderde assertie in `tests/unit/als/test_council_gate_per_action.py::
  TestMissingInitiatorFailsClosed::test_missing_initiator_prevents_execution` (de afsluitende
  `assert result.success is False`, weggevallen doordat de `old_string`-grens van een `Edit`
  die een nieuwe testklasse aan het einde van het bestand toevoegde deze regel van de VORIGE
  test niet meenam) -- beide gefixt en in ronde 2 onafhankelijk herbevestigd.
- **Correctie 2026-08-19, gevonden door de verplichte blinde review na de dag-3-commit.**
  Deze sectie beweerde eerder "`self.config` is niet aanroeper-beinvloedbaar" -- dat is
  strenger dan de code toelaat: elke skill doet `config.update(kwargs)` bij constructie, dus
  een `human_in_the_loop`-kwarg zou de floor in theorie kunnen overschrijven. De juiste,
  geverifieerde claim staat in sectie 7: nul productie-aanroepers geven dit veld als
  override-kwarg mee. Daarnaast beweerde deze sectie dat de twee genoemde mutaties (floor
  ontbrekend / floor te breed) "in beide richtingen" bewezen dat de floor nooit een
  BLOCKED/DEFERRED/MODIFIED-verdict kan downgraden naar een goedkeurbaar ticket -- dat is
  onjuist: beide mutaties raken alleen de upgrade-kant (APPROVED -> HITL_REQUIRED), niet de
  downgrade-belofte. De blinde review construeerde de derde, wel-relevante mutatie (de
  `effective_verdict is DecisionVerdict.APPROVED`-conjunct laten vallen) en toonde dat die
  onopgemerkt bleef: `broker.execute_tool.await_count == 0` en de verdict-naam in de
  foutmelding bleven identiek, dus de bestaande tests bleven groen terwijl een Council-BLOCK
  alsnog een menselijk goedkeurbaar ticket kreeg. Fix: `test_a_non_approving_verdict_never_
  becomes_an_approvable_ticket` (geparametriseerd over BLOCKED/DEFERRED/MODIFIED) toegevoegd,
  zelf mutatiegetest (rood onder exact die mutatie, groen op de shipped code) -- zie ADR-036
  OP-165 voor het volledige verslag.

---

## QA-checks

- [x] Endpoint functioneel getest -- n.v.t. HTTP-endpoint; wel unit- en architecture-tests groen.
- [x] Alle foutstatus-codes getest -- n.v.t., zie BE-FLW-058 (ongewijzigd hergebruikt pad).
- [x] Auth en permissies getest -- identiteitscontrole bij aanmaken/verzilveren ongewijzigd en
      opnieuw bevestigd voor het geflooide pad.
- [x] Tenant-isolatie getest -- ongewijzigd.
- [x] Validaties getest -- exacte-stringvergelijking op `human_in_the_loop`, mutatiegetest.
- [x] Edge cases getest -- niet-HITL-skill blijft ongeraakt; drie tool-calls leveren drie
      tickets; zeven ongerelateerde testbestanden die de piloot als vehikel gebruikten hersteld.
- [x] Dataintegriteit en transacties getest -- ongewijzigd, hergebruikt pad.
- [ ] Performance / load getest -- n.v.t.
- [ ] Caching getest -- n.v.t.
- [x] Logging en tracing gecontroleerd -- geen nieuwe logregels.

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
