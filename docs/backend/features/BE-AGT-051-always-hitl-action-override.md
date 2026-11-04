# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-051 (primair), gerelateerd: BE-AGT-052 (secundair, zie artefact 2 --
  de `audit_officer.py`-explainability-fix gevonden door Gate 2)
- Feature naam: Globale always-HITL-actie-override op het Council-gate (ADR-036 D4-003,
  OP-166, GDPR art. 22, fix-sprint dag 5)
- Status: GEBOUWD, wacht op review
- Auteur: Claude (sprint-uitvoering, ADR-036 fix-sprint Dag 5)
- Reviewer: onafhankelijke doc-reviewer-agent
- Datum: 2026-08-19
- Gerelateerde user story / ticket: ADR-036 fix-sprint, Dag 5
  (`docs/agent-briefs/generated/2026-08-19-sprint-dag-5.md`)
- Gerelateerde router / module: `src.core.copilot.council.coordinator`,
  `src.core.copilot.council.members.audit_officer`
- Gerelateerde frontend endpoints: geen (interne governance-logica, geen HTTP-laag)
- Gerelateerde database tabellen: geen nieuwe (deze fix produceert vandaag GEEN enkele
  extra rij -- de lijst is leeg, zie Doel)
- Versie: v1

---

## Doel en scope

### Doel

ADR-036 D4-003 vraagt om een generiek mechanisme dat GDPR art. 22's "hard rule" afdwingt:
sommige actie-types moeten ALTIJD menselijke tussenkomst vereisen, ongeacht hoe de
Council-officieren stemmen. Het oorspronkelijke plan noemde `hire_employee`/
`terminate_employment`/`credit_assessment` als voorbeeldacties. Exhaustief nagelopen:
geen van deze strings wordt vandaag ooit als `Proposal.action_type` aan de Council
aangeboden (0 treffers in Council-aanroepen). **Correctie na doc-review**: `terminate_
employment` bestaat wel degelijk als string in deze codebase -- als hard-geblokkeerde
`denied_action` in `config/tool_permissions.yml:94` voor de skillsgaptraining-piloot
(ADR-036 D5 "nooit aanraken"-tier, zie BE-AGT-038). Dat mechanisme blokkeert VOOR de
Council-poort en is sterker dan een always-HITL-upgrade (zelfs een HITL-goedkeuring kan
het niet overrulen) -- er bestaat dus geen echte actie die via de Council-route zou
profiteren van `ALWAYS_HITL_ACTIONS`, maar de eerdere "0 treffers repo-breed"-formulering
was te breed en negeerde dit al bestaande, complementaire mechanisme.

**Belangrijke bevinding vóór implementatie**: de plek waar deze upgrade het meest
generiek zou werken -- `AgentCouncil.deliberate()` in `coordinator.py` -- is de gedeelde
ingang voor VIJF verschillende aanroepers. Exhaustief nagelopen hoe elke aanroeper een
HITL_REQUIRED-verdict vandaag afhandelt:

| Aanroeper | HITL_REQUIRED-afhandeling |
|---|---|
| `copilot/service.py:292` (`handle_turn`) | Echt ticket via `HITLTicketRepository.create_hitl_request()` (productie-gewired) |
| `copilot/service.py:318` (`submit_proactive_proposal`) | Niet onderscheiden -- besluit wordt door alle downstream-aanroepers ongebruikt weggegooid |
| `council/governance_gate.py:104` (`require_council_approval`) | Niet onderscheiden -- generieke `!= APPROVED` -> HTTP 403, geen ticket (9 levende aanroepers, repo-breed gegrept op `require_council_approval(`) |
| `council/background_gate.py:124` (`request_council_decision_for_agent`) | Geeft ongewijzigd door; de ALS-skill-aanroeper (`specialist_base.py`, dag 2/3) maakt daar zelf het echte ticket |
| `api/v1/focus_builder/execution_router.py:79` (`execute_flow`) | Niet onderscheiden -- generieke `!= APPROVED` -> HTTP 403, geen ticket (bevestigd levend) |

**Correctie 2026-08-20 (derde blinde-reviewronde):** deze paragraaf zei eerder "slechts 1
van de 5... de andere 4" -- zichzelf tegensprekend, want de tabelrij hierboven voor
`background_gate.py` zegt al dat zijn enige aanroeper (`specialist_base.py`) zelf het
echte ticket maakt. De correcte telling: **2 van de 5** aanroeppaden resulteren vandaag in
een echt goedkeuringsticket bij HITL_REQUIRED (1 direct via `handle_turn`, 1 indirect via
`background_gate.py`'s enige aanroeper) -- de andere **3** niet (`submit_proactive_proposal`,
`governance_gate.py`, `execution_router.py`). Belangrijke nuance: de `background_gate.py`-
gate-FUNCTIE zelf garandeert dit niet -- het is een eigenschap van zijn enige huidige
aanroeper, niet van de gate. Een toekomstige tweede aanroeper zou zelf dezelfde
ticket-logica moeten repliceren, of valt stilzwijgend terug in de categorie van de andere 3.
Zodra een ECHTE actie op de always-HITL-lijst zou staan, zouden die 3 (en een eventuele
toekomstige, niet-repliceerde `background_gate.py`-aanroeper) een voorheen goedgekeurde
actie stil omzetten in een onherstelbaar dood spoor -- het omgekeerde van AI Act art. 14 /
GDPR art. 22 (een mens moet daadwerkelijk kunnen goedkeuren, niet alleen "nee" zonder
vervolg).

**Rakesh's beslissing (2026-08-19), na deze bevinding voorgelegd te krijgen:** bouw het
mechanisme zoals gepland, met een standaard LEGE lijst (dus vandaag verandert er
functioneel niets aan bestaand gedrag), en leg de bevinding hard vast als voorwaarde in
het ADR-036-register (OP-167, apart van OP-166 dat dit mechanisme zelf sluit): niemand mag
een echte actie aan de lijst toevoegen voordat de 3 kapotte aanroepplekken zijn gefixed EN
`background_gate.py` zelf een garantie krijgt die niet van zijn huidige enige aanroeper
afhangt. Dat is een eigen, meerdaags vervolgproject en blijft buiten scope van vandaag.

### In scope

- Nieuwe module-constante `ALWAYS_HITL_ACTIONS: frozenset[str] = frozenset()` in
  `coordinator.py`, bewust leeg, met een WHY-comment die de OP-167-voorwaarde vastlegt.
- Upgrade-logica in `AgentCouncil.deliberate()`: als `final_verdict is
  DecisionVerdict.APPROVED` EN `proposal.action_type in ALWAYS_HITL_ACTIONS`, wordt het
  verdict opgetild naar `HITL_REQUIRED` vóór `_finalize()`. ALLEEN een upgrade, nooit een
  downgrade van BLOCKED/DEFERRED/MODIFIED/een reeds bestaand HITL_REQUIRED.
- Bijvangst gevonden door Gate 2 (code-reviewer): `AuditOfficer._generate_explanation()`
  bouwde een kapotte string ("...vanwege: .") wanneer HITL_REQUIRED zonder een
  REQUIRE_HITL-officierstem ontstaat (precies het pad dat dit mechanisme opent). Gefixt
  met een generieke fallback-tekst, geen info-lek (zie artefact 2).
- Zelf gevonden vóór de blinde review (tijdens het opstellen van de final-approver-brief):
  geen van de nieuwe tests bewees iets over de daadwerkelijk UITGELEVERDE waarde van
  `ALWAYS_HITL_ACTIONS` -- ze monkeypatchen de lijst allemaal tijdelijk. Zonder een directe
  assertie zou een toekomstige toevoeging aan de lijst de OP-167-voorwaarde stilzwijgend
  kunnen omzeilen (de WHY-comment is dan de enige verdediging, en die kan genegeerd worden).
  Nieuwe test `test_always_hitl_actions_ships_empty` asserteert
  `coordinator_module.ALWAYS_HITL_ACTIONS == frozenset()` rechtstreeks -- de eerste
  code-level tripwire voor OP-167, niet alleen een comment. Mutatiegetest: een tijdelijke
  vulling met `"terminate_employment"` maakt deze test rood, herstel maakt hem groen.

### Out of scope

- Het vullen van `ALWAYS_HITL_ACTIONS` met een echte actie -- expliciet uitgesteld tot
  OP-167 EN OP-168 zijn opgelost (zie Doel).
- Het fixen van de 3 aanroeppaden die vandaag geen echt ticket maken bij HITL_REQUIRED,
  plus het geven van een echte garantie aan `background_gate.py` zelf (die vandaag alleen
  werkt omdat zijn enige aanroeper de ticket-logica toevallig zelf repliceert) -- een
  eigen, meerdaags vervolgproject (notificaties, polling/websockets, state-opslag,
  timeout-afhandeling, hervatting per aanroeppad).
- **Het uitbreiden van de upgrade-conditie naar `MODIFIED`-verdicten (OP-168, gevonden
  door de tweede blinde-reviewronde, 2026-08-20)**: `deliberate()` upgradet uitsluitend
  vanaf APPROVED. Een Officer die `APPROVE_WITH_MODIFICATION` geeft (routinematig, niet
  zeldzaam -- bijv. `ComplianceOfficer` bij een ontbrekende `ai_disclosure`,
  `EthicsOfficer` bij een bias-lexicon-treffer) laat een gelijste actie dus zonder ticket
  en zonder mens hangen, zelfs na het oplossen van OP-167. **Correctie 2026-08-20 (derde
  blinde-reviewronde):** de eerdere formulering "laat ... ongehinderd uitvoeren met de
  officier-modificaties toegepast" was onbewezen en onjuist. `copilot/service.py`'s
  `_execute_decision()` begint met `if decision.verdict != DecisionVerdict.APPROVED:
  return None`, dus er vindt GEEN tool-executie plaats voor een MODIFIED-verdict --
  precies zoals voor elk ander niet-APPROVED-verdict. De actie wordt niet stilzwijgend
  uitgevoerd; ze blijft hangen in een `CopilotTurnResponse` met `verdict="modified"` aan
  de aanroeper, zonder ticket en zonder mens. Wat een latere aanroeper daarmee doet
  (opnieuw indienen, direct tonen aan de eindgebruiker) is niet vastgelegd. De
  onderliggende zorg (geen mens, geen ticket, ondanks de "ALTIJD"-belofte) blijft even
  geldig -- alleen het geciteerde mechanisme was fout. Niet vandaag gefixed omdat het een
  eigen ontwerpbeslissing vereist (wat gebeurt er met de officier-voorgestelde
  modificaties bij een upgrade naar HITL_REQUIRED -- weggegooid, of getoond aan de
  goedkeurder?) die per aanroeper kan verschillen. Zolang de lijst leeg is: geen
  gedragseffect, gedekt door dezelfde `test_always_hitl_actions_ships_empty`-tripwire als
  OP-167.
- Normalisatie van `action_type`-stringvergelijking (case/whitespace) -- niet relevant
  zolang de lijst leeg is; aanbevolen te doen zodra OP-167 en OP-168 zijn opgelost en de
  lijst voor het eerst gevuld wordt (Gate 2-bevinding, niet blokkerend voor vandaag).

---

## Build summary

- Nieuw gebouwd: 7 tests in `tests/unit/copilot/council/test_coordinator.py`
  (1x hoofdtest + 1x lege-lijst-regressie + 4x geparametriseerde upgrade-only-regressie +
  1x directe tripwire op de SHIPPED `ALWAYS_HITL_ACTIONS`-waarde, zelf toegevoegd voor de
  blinde review),
  1 test in `tests/unit/copilot/council/members/test_audit_officer.py`
  (explainability-fix). Totaal 8 nieuwe tests.
- Gewijzigd: `src/core/copilot/council/coordinator.py` (nieuwe constante + upgrade-blok in
  `deliberate()`), `src/core/copilot/council/members/audit_officer.py`
  (`_generate_explanation()`-fallback), `_make_proposal()`-testhelper kreeg een optionele
  `action_type`-parameter (default ongewijzigd, backwards compatible).
- Verwijderd: niets.
- Beinvloede bestaande flows: geen -- `ALWAYS_HITL_ACTIONS` is leeg, dus
  `proposal.action_type in ALWAYS_HITL_ACTIONS` is altijd `False` (een eigenschap van een
  lege `frozenset`, geen aanname) en het nieuwe upgrade-blok voert nooit uit.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-051 | Always-HITL-actie-override in `AgentCouncil.deliberate()` | BE-AGT (agent-gedrag) | `src/core/copilot/council/coordinator.py` | Wijziging | geen (n.v.t., interne governance-logica) |
| BE-AGT-052 | `AuditOfficer._generate_explanation()`-fallback voor ongeofficierd HITL_REQUIRED | BE-AGT (agent-gedrag) | `src/core/copilot/council/members/audit_officer.py` | Wijziging | geen |

---

## Detaildocumentatie per artefact

## [BE-AGT-051] Always-HITL-actie-override in `AgentCouncil.deliberate()`

### 1. Type

- Agent-/governance-gedrag (interne methode van `AgentCouncil`, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/coordinator.py` -- de nieuwe constante
  `ALWAYS_HITL_ACTIONS` (module-niveau, met een WHY-comment ervoor) en het upgrade-blok
  in `AgentCouncil.deliberate()` (direct na de `_aggregate()`-aanroep, direct voor de
  `_finalize()`-aanroep). *(Exacte regelnummers bewust NIET meer genoemd sinds
  2026-08-20 (vierde blinde-reviewronde): dit commentaarblok is tijdens de
  reviewrondes van deze dag drie keer gewijzigd, en elke keer verouderde een net
  gecorrigeerd regelnummer hier opnieuw -- zoek op de symboolnamen zelf, niet op een
  regelnummer.)*
- Klasse / functie: `AgentCouncil.deliberate()`.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- dit is een voorwaardelijke uitbreiding van de bestaande
  Council-deliberatieflow, geen nieuwe eindgebruikersflow. De ticket-aanmaakflow zelf
  (voor de aanroepers die dat al doen) is al geregistreerd als `BE-FLW-058` (ADR-036
  OP-163, fix-sprint dag 2).

### 4. Doel

- Een globale, code-gebundelde lijst van actie-types die ALTIJD menselijke goedkeuring
  vereisen, onafhankelijk van de Council-officierstemmen (GDPR art. 22 hard rule).

### 5. Functionele beschrijving

- Voor elke actie waarvan `action_type` op `ALWAYS_HITL_ACTIONS` staat EN waarvoor de
  Council anders APPROVED zou geven, wordt het verdict opgetild naar HITL_REQUIRED. Voor
  elke andere actie (niet op de lijst, of een reeds BLOCKED/DEFERRED/MODIFIED/
  HITL_REQUIRED-verdict) verandert er niets.
- Effect op systeemtoestand vandaag: GEEN -- de lijst is leeg.

### 6. Technische beschrijving

- `ALWAYS_HITL_ACTIONS: frozenset[str] = frozenset()` (module-constante, zie Sectie 2
  voor de zoekwijze -- geen regelnummer): geen runtime-, config-, of tenant-afhankelijke
  bron. Gate 2 security-reviewer bevestigde: geen `os.getenv`, geen DB-lezing, geen
  config-bestand voedt deze lijst; alleen deze letterlijke regel bepaalt de inhoud.
- `deliberate()` (direct na de `_aggregate()`-aanroep, direct voor de
  `_finalize()`-aanroep): `final_verdict, modifications =
  self._aggregate(verdicts, context)` blijft ongewijzigd de bestaande vier
  aggregatieregels (VETO/REQUIRE_HITL/DEFER/MODIFY, in die volgorde). Direct daarna:
  `if final_verdict is DecisionVerdict.APPROVED and proposal.action_type in
  ALWAYS_HITL_ACTIONS: final_verdict = DecisionVerdict.HITL_REQUIRED`. De `is`-vergelijking
  is veilig omdat `DecisionVerdict`-enumleden singletons zijn en `_aggregate()` altijd een
  canoniek enum-lid teruggeeft, nooit een rauwe string.
- Hergebruikt hetzelfde upgrade-only-patroon als Dag 3's `effective_verdict` in
  `specialist_base.py` (ADR-036 D4-002/OP-165) -- geen nieuw mechanisme.

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. -- interne methode-aanroep, geen HTTP-laag. `proposal.action_type` is
  LLM-gegenereerde vrije tekst (via `ProposalBuilder`), geen door de aanroeper
  gecontroleerde autorisatie-waarde -- een upgrade naar MEER menselijk toezicht is geen
  autorisatierisico.

### 8-16. n.v.t

Zuivere in-memory verdict-logica, geen eigen request/response/validatie/business-rule/
afhankelijkheid/transactie/caching-gedrag dat verandert.

### 17. Acceptatiecriteria

- Alle 7 nieuwe tests in `test_coordinator.py` slagen (1 shipped-waarde-tripwire,
  1 hoofdtest, 1 lege-lijst-regressie, 4 geparametriseerd, 27 -> 34 tests in dat bestand):
  - `test_always_hitl_actions_ships_empty` (tripwire: de SHIPPED `ALWAYS_HITL_ACTIONS`
    moet leeg zijn -- zelf gevonden vóór de blinde review, zie Sectie G van
    `review-BE-AGT-051.md`)
  - `test_deliberate_upgrades_approved_to_hitl_required_for_always_hitl_action` (hoofdtest,
    monkeypatcht de lijst met een testwaarde, alle Officers APPROVE -> HITL_REQUIRED)
  - `test_deliberate_leaves_approved_unchanged_when_action_not_on_always_hitl_list`
    (lege-lijst-regressie: normale actie blijft APPROVED)
  - `test_deliberate_never_downgrades_a_non_approved_verdict_for_always_hitl_action`
    (4x geparametriseerd: VETO->BLOCKED, REQUIRE_DEFERRAL->DEFERRED,
    APPROVE_WITH_MODIFICATION->MODIFIED, REQUIRE_HITL->HITL_REQUIRED blijven allemaal
    ongewijzigd, ook met de actie op de lijst)
- Mutatiebewijs (zelf uitgevoerd, beide richtingen): de `APPROVED`-conjunct verwijderen uit
  de voorwaarde maakt 3 van de 4 geparametriseerde regressietests rood; het hele
  upgrade-blok verwijderen maakt de hoofdtest rood. Beide mutaties teruggedraaid,
  hash-bevestigd identiek aan de gefixte staat.

### 18. Integratoruitleg

- N.v.t. -- geen publieke API-wijziging.

### 19. Trainingssamenvatting

- **Actor:** Systeem (de Council zelf, tijdens elke `deliberate()`-aanroep).
- **Voorwaarde:** een proposal met een `action_type` die op `ALWAYS_HITL_ACTIONS` staat
  EN waarvoor de officieren anders unaniem zouden goedkeuren.
- **Actie:** het verdict wordt opgetild naar HITL_REQUIRED vóór `_finalize()`.
- **Systeemreactie:** de aanroeper ontvangt HITL_REQUIRED i.p.v. APPROVED; wat daarna
  gebeurt hangt af van de aanroeper (zie de tabel in Doel -- vandaag inert, lijst is leeg).
- **Succesrespons:** N.v.t. (dit IS het beschermingspad).
- **Foutrespons:** N.v.t.
- **Uitzonderingen:** BLOCKED/DEFERRED/MODIFIED/een reeds bestaand HITL_REQUIRED-verdict
  worden nooit aangeraakt, ook niet als de actie op de lijst staat.

---

## [BE-AGT-052] `AuditOfficer._generate_explanation()`-fallback voor ongeofficierd HITL_REQUIRED

### 1. Type

- Agent-/governance-gedrag (interne methode van `AuditOfficer`, geen HTTP-endpoint).

### 2. Locatie

- Bestandspad: `src/core/copilot/council/members/audit_officer.py:127-143`.
- Klasse / functie: `AuditOfficer._generate_explanation()`.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- interne aanvulling op de bestaande explanation-generatie
  (GDPR art. 13-15).

### 4. Doel

- Voorkomen dat de gebruikersgerichte uitleg-tekst kapot is ("...vanwege: .") wanneer
  HITL_REQUIRED ontstaat zonder dat een Officer REQUIRE_HITL stemde -- precies het pad dat
  BE-AGT-051's always-HITL-mechanisme opent.

### 5. Functionele beschrijving

- Voor HITL_REQUIRED met minstens een REQUIRE_HITL-officierstem: ongewijzigd (citeert de
  officierredenen). Voor HITL_REQUIRED ZONDER enige REQUIRE_HITL-stem (het nieuwe,
  policy-gedreven pad): een generieke, informatieve fallback-tekst i.p.v. een lege join.

### 6. Technische beschrijving

- `if not reasons: return "Deze actie vereist je expliciete goedkeuring vanwege een
  platformbeleidsregel die menselijk toezicht verplicht voor dit type actie."` -- geen
  officier-, tenant-, of actieparameter-informatie in de fallback-string; structureel
  gelijk aan het bestaande, generieke BLOCKED-pad qua specificiteitsniveau.

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. Geverifieerd door Gate 2 security-reviewer: geen `action_params`, `evidence`,
  officiernamen of tenant-data in de nieuwe string -- geen info-lek, vergeleken tegen de
  bestaande `test_explanation_does_not_leak_internal_reasons_on_blocked`-guard.

### 8-16. n.v.t

Zuivere string-generatie, geen eigen request/response/validatie/business-rule/
afhankelijkheid/transactie/caching-gedrag.

### 17. Acceptatiecriteria

- `test_explanation_is_not_broken_when_hitl_required_has_no_officer_reason` slaagt: de
  fallback-tekst bevat "platformbeleidsregel" en eindigt NIET op "vanwege: .".
- Mutatiebewijs: de fallback-tak tijdelijk verwijderen maakt deze test rood met exact de
  voorspelde kapotte string ("...vanwege: ."), teruggedraaid, hash-bevestigd identiek.
- Regressie: `test_explanation_does_not_leak_internal_reasons_on_blocked` (bestaand, BLOCKED-
  pad) blijft ongewijzigd groen -- deze fix raakt alleen de HITL_REQUIRED-tak.

### 18. Integratoruitleg

- N.v.t.

### 19. Trainingssamenvatting

- **Actor:** Systeem (`AuditOfficer.finalize_and_persist()`, aangeroepen na elke
  deliberatie).
- **Voorwaarde:** `final_verdict == HITL_REQUIRED` EN geen enkele officier stemde
  REQUIRE_HITL.
- **Actie:** genereer de gebruikersgerichte uitleg-tekst.
- **Systeemreactie:** een generieke, correcte, niet-kapotte uitlegstring i.p.v. een lege
  join.
- **Succesrespons:** de tekst wordt opgeslagen in `CouncilDecision.explanation_for_user`
  en in de ADR-019-hashketen.
- **Foutrespons:** N.v.t.
- **Uitzonderingen:** de bestaande, officier-redenen-citerende tak blijft ongewijzigd
  wanneer minstens een officier wel REQUIRE_HITL stemde.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- N.v.t. -- geen publieke API, geen frontend-impact.

---

## Open aannames

- Dat de 5 genoemde aanroepers van `Council.deliberate()` de volledige, huidige
  aanroepverzameling van PRODUCTIECODE zijn (gegrept binnen `src` op `.deliberate(`,
  6 treffers, waarvan 1 (`council/__init__.py:19`) bevestigd een docstring-voorbeeld is,
  geen echte aanroep). *(Precisering 2026-08-20, vierde blinde-reviewronde: "repo-breed"
  was te ruim geformuleerd -- een grep over de VOLLEDIGE repo vindt ook
  `scripts/verify_sprint_9.py:65`, een los verificatiescript zonder productiepad, dus
  buiten de "5 echte aanroepers"-claim.)* Een toekomstige, zesde aanroeper die
  HITL_REQUIRED ook niet met een echt ticket afhandelt, zou dezelfde OP-167-voorwaarde
  moeten respecteren maar staat nog niet in de tabel in Doel.

## Open vragen

- Wanneer OP-167 (de 3 onvolledige HITL-aanroeppaden plus een echte garantie voor
  `background_gate.py` zelf) als eigen vervolgproject wordt ingepland -- expliciet
  buiten scope van deze sprint, aan Rakesh om te plannen.

---

## Risico's

- Geen CRITICAL/HIGH. Dit is een upgrade-only mechanisme met een lege default-lijst; Gate 2
  (code-reviewer + security-reviewer) beiden GO na 2 kleine fixes (een ASCII-violatie x2 --
  waarvan een door mij per ongeluk herintroduceerd in de eigen testfix, gevonden door de
  tweede reviewer -- en de `audit_officer.py`-explainability-bug). Mutatiebewijs bevestigt
  in beide richtingen: de upgrade-conditie te breed maken (APPROVED-conjunct weg) maakt 3
  van de 4 regressietests rood; het upgrade-blok volledig weghalen maakt de hoofdtest rood.
- Gate-status: gerichte set (`tests/unit/copilot/council/`) 216 passed / 0 failed (was 208
  vóór dag 5, +6 door de coordinator-tests, +1 door de `audit_officer.py`-regressietest,
  +1 door de zelf-gevonden OP-167-tripwire-test toegevoegd na Ronde 2 van de doc-review =
  +8 totaal). Let op: dit "216" is een toevallige samenloop met het eerder ONJUISTE
  "216"-getal uit de Ronde-1-self-review (dat destijds op 5 tests berustte, niet 6) -- dit
  is een aparte, opnieuw zelf geverifieerde telling op 8 tests, geen terugval naar die oude
  fout (zie `review-BE-AGT-051.md` sectie G). Volledige mandatory suite: 15718 passed /
  0 failed / 219 skipped / 19 xfailed (was 15710 als ware dag-4-eindstand, +8). `python -m
  pyright` 0 errors (baseline ongewijzigd, 54 warnings); `python scripts/run_mypy_audit.py`
  0/0; `ruff check` op alle gewijzigde/nieuwe bestanden: schoon.

---

## QA-checks

- [x] Endpoint functioneel getest -- n.v.t., geen HTTP-endpoint.
- [x] Alle foutstatus-codes getest -- n.v.t.
- [x] Auth en permissies getest -- n.v.t., interne governance-logica.
- [x] Tenant-isolatie getest -- n.v.t., de constante is tenant-onafhankelijk (bewust --
      GDPR art. 22 moet voor ELKE tenant gelden, niet per-tenant overschrijfbaar).
- [x] Validaties getest -- exacte-stringvergelijking op `action_type`, mutatiegetest.
- [x] Edge cases getest -- lege lijst (geen gedragswijziging), alle vier de andere
      verdicten blijven ongewijzigd, ongeofficierde HITL_REQUIRED-explanation.
- [x] Dataintegriteit en transacties getest -- n.v.t., geen DB-schrijfactie in deze fix
      (de upgrade beinvloedt WAT er later geschreven wordt via `_finalize`, niet HOE).
- [ ] Performance / load getest -- n.v.t.
- [ ] Caching getest -- n.v.t.
- [x] Logging en tracing gecontroleerd -- geen nieuwe logregels, bestaande
      `span.set_attribute("verdict", ...)` draagt automatisch het geupgradede verdict.

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle relevante bestanden geinventariseerd
- [x] Relevante edge cases beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Trainingssamenvatting aanwezig
