# BE-AGT-057 -- Agent-laag denylist-precheck in execute_tool() (ADR036-ADR015-001/OP-24)

## Metadata

- **Sprint:** ADR-036 fix-sprint -- P0 + P1 uit de volledige audit (2026-08-18), dag 8 van 8 (laatste dag)
- **ADR:** ADR-036 OP-24 (Fase D)
- **Datum:** 2026-08-21
- **Branch:** develop

---

## Doel en scope

### Doel

`EnhancedBaseAgent.execute_tool()` (die `BaseSpecialistAgent`, en daarmee alle 135 skills,
erft) roept `ToolBrokerService.execute_tool()` rechtstreeks aan zonder een eigen
agent-laag-permissiecheck. OP-24 (gevonden 2026-08-02) noemde dit een bypass van "D5-denylist,
Council, en initiator". **Exhaustieve investigatie vooraf**
(`docs/agent-briefs/generated/2026-08-21-sprint-dag-8.md`) toonde dat de D5-denylist-helft van
die claim niet standhoudt onder meting: `ToolBrokerService.execute_tool()` blokkeert
`denied_actions`/`denied_tools` al via `is_tool_allowed()` (`service.py:198`) voordat een
agent-laag-check ooit relevant wordt. Er was dus nooit een scenario waarin een denylist-tool
via `execute_tool()` daadwerkelijk uitvoerde. Deze dag voegt de precheck toch toe, niet om een
actieve bypass te dichten, maar als **defense-in-depth en architecturale consistentie** met
`BaseSpecialistAgent._reject_before_council()`'s D5-helft -- en om de vroegere afwijzing (geen
broker-round-trip) als daadwerkelijke, meetbare winst te leveren.

### In scope

- Een nieuwe `_get_execute_tool_permission_manager()`-helper op `EnhancedBaseAgent`
  (`src/core/agents/base_agent.py`), die de broker's `ToolPermissionManager` hergebruikt
  (analoog aan `specialist_base.py::_get_permission_manager()`), met een `isinstance`-guard-
  fallback voor test-doubles die geen echt manager-attribuut hebben.
- Een `is_denied()`-precheck in `execute_tool()`, VOOR de `await broker.execute_tool(...)`
  -aanroep, die bij een treffer `ToolExecutionException` gooit (hetzelfde uitzonderingstype als
  de broker's eigen weigeringspad -- een enkel foutoppervlak i.p.v. twee).
- `KNOWN_UNGATED`'s reden in `tests/architecture/test_agent_actions_pass_council.py`
  herschreven (niet verwijderd -- verwijderen breekt de guard, zie sectie 6 hieronder) om de
  gecorrigeerde bevinding en de dag-8-fix vast te leggen.
- ADR-036 OP-24-registerrij bijgewerkt met de gecorrigeerde bevinding en de dag-8-fix.
- Twee nieuwe tests in `tests/unit/agents/test_base_agent_toolbroker.py`: een die bewijst dat
  de broker-aanroep NOOIT bereikt wordt bij een denylist-treffer (de daadwerkelijke
  gedragsverandering), en een regressietest die bevestigt dat een niet-geweigerde tool nog
  steeds normaal doorgaat.

### Out of scope

- **Council-consultatie en initiator-check** blijven OPEN onder OP-24. `execute_tool()` heeft
  geen equivalent van `_reject_before_council()`'s initiator-veld, en de methode wordt ook
  door niet-ALS-agents gebruikt (`ExternalAgentBridge`, `SchedulingOrchestratorAgent`,
  `SchedulingVoiceAgent`, en -- bijvangst van de investigatie -- `BaseSupervisor` + 11
  subklassen in `src/core/als/supervisors/`) -- dichtzetten daar vraagt een eigen
  impact-analyse die buiten de scope van deze laatste sprintdag valt.
- Geen wijziging aan `ToolBrokerService.execute_tool()` zelf -- die blokkeert de denylist al
  correct en is niet aangeraakt.

---

## Build summary

- Nieuw gebouwd: `EnhancedBaseAgent._get_execute_tool_permission_manager()` (helper-methode);
  2 nieuwe tests in `test_base_agent_toolbroker.py`.
- Gewijzigd: `execute_tool()` (precheck ingebouwd), `KNOWN_UNGATED`'s reden-string
  (`test_agent_actions_pass_council.py`), ADR-036 OP-24-registerrij.
- Productiecode gewijzigd: `src/core/agents/base_agent.py` (import + helper + precheck, 42
  regels toegevoegd, geen regels verwijderd).
- Rood-voor-fix bewezen: de nieuwe short-circuit-test tijdelijk gedraaid tegen de
  gecommitte (pre-fix) versie van `base_agent.py` (via `git show HEAD:...` + `cp`, nooit
  `git checkout --`) -- 1 failed (exact de nieuwe test), 7 passed. Na herstel van de fix:
  8 passed.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-057 | `EnhancedBaseAgent._get_execute_tool_permission_manager()` | Interne methode | `src/core/agents/base_agent.py` | Nieuw | generiek agent-tooluitvoerpad |
| BE-AGT-057 | `EnhancedBaseAgent.execute_tool()` | Interne methode | `src/core/agents/base_agent.py` | Wijziging | generiek agent-tooluitvoerpad |
| BE-AGT-057 | `KNOWN_UNGATED` (OP-24-entry) | Testdata/documentatie | `tests/architecture/test_agent_actions_pass_council.py` | Wijziging | n.v.t. |

---

## Detaildocumentatie per artefact

## [BE-AGT-057] Agent-laag denylist-precheck

### 1. Type

- Agentgedrag (interne methode, geen HTTP-endpoint) + architecture-guard-documentatie.

### 2. Locatie

- `src/core/agents/base_agent.py` (`_get_execute_tool_permission_manager()`, `execute_tool()`);
  `tests/architecture/test_agent_actions_pass_council.py` (`KNOWN_UNGATED`);
  `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md` (OP-24-rij).

### 3. Gerelateerde flow

- Geen apart Flow-ID -- een defense-in-depth-precheck binnen een bestaand uitvoerpad, geen
  nieuwe flow.

### 4. Doel

- Vroegere, agent-laag afwijzing van een D5-denylist-tool voordat de broker-round-trip
  (inclusief eventuele HITL/audit-bijwerkingen daarvan) wordt gestart. Architecturale
  consistentie met het ALS-pad, dat deze check al op agent-niveau doet.

### 5. Functionele beschrijving

- `execute_tool(tool_name, payload, timeout)` raadpleegt, direct na het oplossen van de
  broker en voor de `await broker.execute_tool(...)`-aanroep, `is_denied(agent_id, tool_name)`.
  Bij een treffer: `ToolExecutionException` (dezelfde soort als de broker's eigen
  `is_tool_allowed()`-weigering), gevangen door de bestaande `except Exception`-tak die al een
  `tool_failed`-event emit en de exception doorgooit -- het observeerbare gedrag (een
  `tool_failed`-event, een gegooide exception) is dus identiek aan een broker-laag-weigering,
  alleen eerder in de tijdlijn.
- Bij geen treffer: ongewijzigd gedrag, de broker-aanroep vindt plaats zoals voorheen.

### 6. Technische beschrijving

- **Manager-hergebruik**: `_get_execute_tool_permission_manager(broker)` cachet op
  `self._execute_tool_permission_manager`. Leest `getattr(broker, "permission_manager", None)`
  en valt terug op een verse `ToolPermissionManager()` als dat attribuut geen echte instantie
  is (`isinstance`-guard) -- essentieel voor bestaande tests die `agent._tool_broker` door een
  `AsyncMock()` vervangen: die levert bij attribuutopvraging een auto-mock op, en die is
  waarheidig, dus zonder de guard zou `is_denied()` ALLES blokkeren (bevestigd: zonder de
  guard falen `test_execute_tool_delegates_to_broker` en `test_execute_tool_emits_event`).
- **`KNOWN_UNGATED` NIET verwijderd.** De investigatie toonde empirisch (de guard's eigen
  AST-helper rechtstreeks aangeroepen, geen bestand gewijzigd) dat `execute_tool()` in
  `KNOWN_UNGATED` staat omdat de AST-walker matcht op de ATTRIBUUTNAAM `execute_tool`
  (`broker.execute_tool(...)` telt mee), en dat `test_agent_tool_execution_passes_the_council`
  een letterlijke `_council_rejection`-aanroep eist. Deze fix voegt zo'n aanroep niet toe (dat
  is bewust buiten scope -- geen initiator-veld), dus verwijdering van de uitzondering zou de
  guard ROOD maken, niet OP-24 sluiten. De reden-string is daarom herschreven (nieuwe datum,
  gecorrigeerde D5-claim, vermelding van de dag-8-fix), de entry zelf blijft staan.
- **Bijvangst geregistreerd, niet gefixed**: `BaseSupervisor` + 11 subklassen in
  `src/core/als/supervisors/` erven `EnhancedBaseAgent.execute_tool` ook, en zitten (net als de
  3 al-bekende klassen) buiten de guard's `AGENT_ROOTS`-scan. Vandaag leeg (0
  `execute_tool`-aanroepen, bevestigd via grep) -- zelfde P2-notitie als de 3 bestaande
  klassen, geen nieuwe registerrij nodig (het is een uitbreiding van een al bekend
  guard-scope-gat, geen nieuwe bevinding).

### 6a. Gate 2 -- bevindingen en fixes (2026-08-21)

**Security-reviewer: GO, geen CRITICAL/HIGH/MEDIUM.** Zelfstandig herverifieerd (niet
aangenomen): de "broker blokkeert al"-claim klopt (`service.py:198` checkt
`is_tool_allowed()` als eerste stap, voor risk-classificatie/HITL); geen nieuwe bypass door
de isinstance-guard-fallback (een geweigerde/gemanipuleerde precheck valt terug op de
broker's eigen, onafhankelijke `is_tool_allowed()`-check -- zwakker maken van de precheck
kan de daadwerkelijke handhaving niet omzeilen); `agent_id` is de vaste, eigen identiteit
van de agent (nooit uit task-payload); geen audit-regressie (dezelfde `tool_failed`-event
via dezelfde `except`-tak, in beide gevallen). Een LOW-bevinding, niet gefixed deze
sprintdag: de nieuwe foutmelding ("Denylist-geweigerd") is iets specifieker dan de broker's
generieke "not authorized" -- een kleine enumeratie-oracle die een aanroeper laat
onderscheiden "expliciet denylisted" van "geen profiel/niet op allowlist". Geen PII/geheime
data, expliciet LOW, geen fix vereist.

**Code-reviewer: eerste poging vastgelopen (agent-watchdog-timeout na 600s), tweede poging
CHANGES_REQUESTED, beide bevindingen gefixt in dezelfde sessie.** De vastgelopen eerste
poging liet een verontrustende, onvolledige claim achter ("genuine regression... pin down
which import causes it") -- zelf eerst onderzocht voor verder te gaan: bevestigd dat
`base_agent.py` niet gecorrumpeerd was achtergelaten (`git diff --stat` exact 42 regels,
identiek aan de eigen backup), geen circulaire import (`python -c "import
src.core.agents.base_agent"` en een volledige `pytest --collect-only` over alle 20.058
tests slaagden, met precies 1 vooraf-bestaand, ongerelateerd collectiefout in
`tests/contracts/`). De TWEEDE poging vond de daadwerkelijke oorzaak, hoogstwaarschijnlijk
wat de eerste poging aanvoelde zonder het af te ronden:

1. **CRITICAL, bevestigd via mutatie in beide richtingen**:
   `tests/architecture/test_dsm_008_reclassification.py::test_agent_runtime_ce_dag2_final_target`
   faalde op de working-tree-versie, slaagde op de gecommitte (`HEAD`) versie. De twee
   nieuwe, bewuste imports (`ToolExecutionException` top-level, `ToolPermissionManager`
   binnen de helper) tellen als twee nieuwe `agent_runtime -> tool_broker`-edges in de
   DSM-coupling-scanner (die alleen `TYPE_CHECKING`-blokken uitsluit, geen
   functie-lokale imports) -- Ce ging van 225 (het toenmalige plafond, zonder marge) naar
   227. **Fix:** het plafond verhoogd naar 227 met een gedateerde, beargumenteerde
   toelichting (zelfde patroon als de al-bestaande SP-DSM-009-precedent in dezelfde
   docstring), na zelf te hebben gemeten dat de instability-drempel niet raakt: `I =
   227/(227+193) = 0,5405`, ruim onder de ACTUELE 0,55-drempel uit SP-DSM-014 (de
   `I<=0,50`-vermelding in de oude docstring was zelf al verouderd en werd door geen
   enkele test afgedwongen -- zelf bevestigd door alle Grade-A+-tests te draaien).
2. **CRITICAL, zelf-veroorzaakte documentatiefout**: mijn eigen ADR-036 OP-24-rij-bewerking
   (in dezelfde diff) brak
   `tests/architecture/test_adr036_register_is_parseable.py` op twee punten:
   `STATUS=GEDEELTELIJK GEDICHT` staat niet in `VALID_STATUSES` (`GESLOTEN`, `OPEN`,
   `DUPLICAAT`, `ONGEVERIFIEERD`) en miste een `GEVERIFIEERD=<datum>`-veld; en
   `BEWIJS=...BE-AGT-057-....md` matchte geen enkel machinaal controleerbaar patroon (een
   los `.md`-pad in backticks is bewust NIET een geaccepteerd bewijstype -- alleen
   `path:regel`, een node-id, een commit-hash, of een commando met argument). **Fix:**
   `STATUS=OPEN GEVERIFIEERD=2026-08-21 BEWIJS=tests/unit/agents/test_base_agent_toolbroker.py::test_execute_tool_denylist_precheck_short_circuits_before_broker`
   (een node-id die de guard's eigen `_evidence_is_checkable()` daadwerkelijk verifieert:
   bestand bestaat, functie bestaat).

Beide bevindingen zijn EIGEN regressies in de architecture-suite, gevonden voordat commit --
niet bevindingen over de kernlogica (die was al in de eerste Gate-2-poging en de
security-review onveranderd goedgekeurd).

### 6b. Verplichte blinde eindreview -- ronde 1 -- bevindingen en fixes (2026-08-21)

**Oordeel: GO WITH MINOR ISSUES.** Drie eigen mutaties uitgevoerd (de precheck omdraaien,
`KNOWN_UNGATED` legen, de isinstance-guard in de cache-check vervangen door een kale
waarheidstoets) -- alle drie precies gevangen zoals de documentatie beweerde. Beide
Gate-2-fixes (DSM-plafond, ADR-STATUS/BEWIJS) zelfstandig herrekend en bevestigd correct.
Twee MINOR-bevindingen, beide gefixed:

**Bevinding 1: een nieuwe mypy-fout, en de final-approver-brief's mypy-regel was feitelijk
onjuist.** `_get_execute_tool_permission_manager()`'s cache-check (`return cached` na een
kaal `getattr(..., None); if cached is not None:`) laat `Any` weglekken uit een functie die
`ToolPermissionManager` belooft (`no-any-return`). Bevestigd NIEUW via een `git worktree` op
de parent-commit (`f0d70388`): daar 0 mypy-fouten, hier 1. De final-approver-brief markeerde
mypy als PASS met de reden "niet apart herdraaid... geen mypy-relevante typewijzigingen" --
die reden was onjuist; er was wel een mypy-relevante wijziging, en hij was niet gedraaid.
**Fix:** de cache-check gebruikt nu dezelfde `isinstance(cached, ToolPermissionManager)`-
toets als de fallback ernaast (i.p.v. `cached is not None`), wat het type voor mypy narrowt
zonder de retourwaarde naar `Any` te moeten verzwakken (en zonder de Any-gate-teller aan te
raken, in tegenstelling tot het alternatief -- de analoge `specialist_base.py`-methode
declareert `-> Any` met een `# TODO(TYPE)`-marker, maar deze methode had al een strikter
type en dat is de moeite van het narrowen waard). `python -m mypy
src/core/agents/base_agent.py` -> Success; `python scripts/run_mypy_audit.py` -> 0 errors,
baseline 0.

**Bevinding 2: ID-REGISTRY's "Volgende beschikbare ID per prefix"-tabel was niet
bijgewerkt, en de brief's claim daarover was onjuist.** De teller voor `BE-AGT-###` stond
nog op 057 terwijl deze exacte commit die ID al verbruikte -- elke eerdere sprintdag
(dag 6, dag 7) had deze teller wel bijgewerkt in dezelfde commit die het ID consumeerde. De
final-approver-brief beweerde expliciet "teller 057->058", wat niet overeenkwam met het
bestand. **Fix:** teller bijgewerkt naar 058.

**NIT, geen actie:** de module-docstring van `test_dsm_008_reclassification.py` (regel 1-5,
niet door deze diff aangeraakt) noemt nog "I<=0,50" -- al verouderd voor deze dag, en de
functie-docstring die WEL is bewerkt zegt dit zelf al expliciet ("de I<=0,50-vermelding...
was al voor vandaag verouderd... en werd door geen enkele test afgedwongen"). Zuiver
cosmetisch, geen enkele test handhaaft dat getal.

**Herverificatie na de fixes (zelf gedraaid):**

```text
python -m mypy src/core/agents/base_agent.py -> Success: no issues found in 1 source file
python scripts/run_mypy_audit.py -> Total errors: 0, Baseline errors: 0

python -m pytest tests/unit/agents/test_base_agent_toolbroker.py tests/architecture/test_agent_actions_pass_council.py -v --timeout=60
-> 13 passed

python -m pyright -> 0 errors, 54 warnings (baseline ongewijzigd)
ruff check src/core/agents/base_agent.py -> All checks passed!
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 2 van de verplichte
blinde review volgt.

### 6c. Verplichte blinde eindreview -- ronde 2 -- bevinding en fix (2026-08-21)

**Oordeel: GO WITH MINOR ISSUES.** Ronde 2's opdracht was expliciet: neem ronde 1's fixes
als correct aan, en jaag op wat rondes 1 en Gate 2 nog niet hadden gevonden. Drie eigen
mutaties (het hele hergebruik-en-cache-mechanisme verwijderen, `KNOWN_UNGATED` legen, de
isinstance-guard verwijderen) plus een volledige herrekening van alle numerieke claims.

**Bevinding (MINOR): de manager-hergebruik- en cache-logica werd door geen enkele test
daadwerkelijk uitgeoefend, ondanks een acceptatiecriterium dat het tegendeel beweerde.**
Sectie 17's eerste criterium beweerde "geverifieerd tegen zowel een echte
`ToolPermissionManager` als een `AsyncMock`-broker" -- maar de twee nieuwe tests uit de
oorspronkelijke implementatie mocken de helper zelf weg (`agent.
_get_execute_tool_permission_manager = MagicMock(...)`), en de twee oudere,
niet-gemockte broker-delegatietests gebruiken een `AsyncMock()`-broker, die ALTIJD op de
fallback-constructietak valt (de isinstance-toets faalt op een auto-mock-attribuut) --
nooit op het ECHTE hergebruikpad, en geen enkele test riep de helper tweemaal aan om de
cache-hit-tak te raken. Bewezen met een live mutatie: de hele hergebruik-en-cache-
mechaniek verwijderen (altijd een verse `ToolPermissionManager()` bouwen, geen cache, geen
broker-attribuutlezing) liet alle 232 op dat moment relevante tests groen.

**Fix:** een nieuwe test
`test_get_execute_tool_permission_manager_reuses_and_caches_the_real_manager` toegevoegd
die BEIDE takken afdwingt: (1) een broker met een ECHTE `ToolPermissionManager` op
`.permission_manager` geeft DAT exemplaar terug (identiteit); (2) een tweede aanroep -- met
een ANDERE, eigen echte manager op een andere broker -- geeft nog steeds het EERSTE
(gecachte) exemplaar terug, wat bewijst dat de cache daadwerkelijk geraadpleegd wordt in
plaats van de broker opnieuw te lezen. Zelf mutatiegetest: exact ronde 2's mutatie
(hergebruik-en-cache-mechaniek verwijderen) herhaald op de eigen machine -- de nieuwe test
ging ROOD; herstel maakte hem weer GROEN, `git diff --stat` bevestigde een lege diff na
herstel.

**Herverificatie na de fix (zelf gedraaid):**

```text
python -m pytest tests/unit/agents/test_base_agent_toolbroker.py -v --timeout=60
-> 9 passed (8 bestaand + 1 nieuw)

python -m pyright -> 0 errors, 54 warnings (baseline ongewijzigd)
ruff check tests/unit/agents/test_base_agent_toolbroker.py -> All checks passed!
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 3 van de verplichte
blinde review volgt.

### 6d. Verplichte blinde eindreview -- ronde 3 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Opdracht: neem rondes 1-2 als correct aan, jaag verder.
Drie eigen mutaties (een klasse-brede cache i.p.v. instantie-brede, ronde 1's oorspronkelijke
bug herhaald ter bevestiging, het hele mechanisme opnieuw verwijderd ter bevestiging) plus
een volledige herrekening van elk numeriek document-claim, inclusief de volledige mandatory
suite (zelf gedraaid: 15744 passed, exact +1 t.o.v. de 15743 van voor ronde 2's ene nieuwe
test).

**Bevinding 1 (MINOR): ronde 2's eigen nieuwe test bewees de cache-SCOPE niet zelfstandig.**
Een mutatie naar een klasse-brede cache (`type(self)._execute_tool_permission_manager = manager`
i.p.v. `self.`) werd in het VOLLEDIGE testbestand gevangen -- maar uitsluitend doordat een
ANDERE, eerder gedefinieerde test (`test_execute_tool_delegates_to_broker`) de klassebrede
cache al had gevuld voordat ronde 2's test zelfs maar draaide. In ISOLATIE gedraaid bleef die
mutatie ONGEVANGEN. **Fix:** een derde tak toegevoegd aan dezelfde test: een TWEEDE,
onafhankelijke agent-instantie mag nooit de EERSTE agent's gecachte manager teruggeven. Zelf
mutatiegetest, in isolatie: de klasse-brede-cache-mutatie herhaald, nu ZELFSTANDIG (los van
testvolgorde) ROOD; herstel GROEN, `git diff --stat` leeg na herstel.

**Bevinding 2 (MINOR): de volledige mandatory suite was nooit herdraaid na ronde 2's fix --
elk document citeerde nog het cijfer van voor die fix.** Ronde 2's eigen herverificatie
draaide alleen een deelverzameling (713 passed), niet de volledige
`tests/unit tests/architecture tests/core -n 4`-suite die sectie 17's eigen acceptatie-
criterium citeert. **Fix:** zelf gedraaid, bevestigd 15744 passed (exact +1 t.o.v. 15743,
consistent met ronde 2's ene nieuwe testfunctie) -- alle documentverwijzingen naar "15743"
bijgewerkt.

**Bevinding 3 (MINOR): `review-BE-AGT-057.md` was sinds Gate 2 niet meer bijgewerkt en
sprak zichzelf tegen** (sectie C.1 zei "Coverage gaps: Geen" terwijl ronde 2 er juist een
vond en fixte). **Fix:** een pointer-paragraaf toegevoegd (zelfde patroon als dag 7's
`review-BE-AGT-056.md`), zonder de historische Gate-2-snapshot zelf te herschrijven.

**Herverificatie na de fixes (zelf gedraaid):**

```text
python -m pytest "tests/unit/agents/test_base_agent_toolbroker.py::test_get_execute_tool_permission_manager_reuses_and_caches_the_real_manager" -v --timeout=60
-> 1 passed (in isolatie, niet alleen in het volledige bestand)

python -m pytest tests/unit/agents/test_base_agent_toolbroker.py -v --timeout=60
-> 9 passed

python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short --ignore=tests/core/agents/test_focus_builder_chat_agent.py
-> 15744 passed, 219 skipped, 22 xfailed, 0 failed. Dit is de EERSTE keer dat de volledige
   suite draait sinds ronde 2's nieuwe testfunctie (die zelf nooit tegen de volledige suite
   herverifieerd was) -- +1 t.o.v. het laatst-gemeten "15743" (van na commit c7da08bc, voor
   ronde 2), exact de ene testfunctie die ronde 2 toevoegde. Ronde 3's eigen fix (de derde
   tak in dezelfde testfunctie) voegt geen nieuwe testfunctie toe, dus de telling blijft
   15744.
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 4 van de verplichte
blinde review volgt.

### 6e. Verplichte blinde eindreview -- ronde 4 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Elke numerieke claim uit rondes 1-3 herrekend en exact
bevestigd (inclusief de volledige mandatory suite: 15744 passed, exact zoals ronde 3
beweerde). Eigen mutaties: `is_denied()` altijd `False` laten teruggeven, een klasse-brede-
cache-mutatie opnieuw getraceerd (bevestigt ronde 3's eigen bewijs, geen nieuwe bug), een
naamcollisie-check op `_execute_tool_permission_manager` (geen), en een override-check op
`execute_tool` (geen subklasse overschrijft hem).

**Bevinding 1 (MINOR): geen enkele test liet de ECHTE `is_denied()`-beslissing door de
ECHTE `execute_tool()`-weg lopen.** De twee precheck-tests mocken
`_get_execute_tool_permission_manager` zelf weg; de cache-test roept `is_denied()` nooit
aan; het pre-existing `test_denied_actions_hard_denylist.py` test alleen
`ToolPermissionManager` rechtstreeks, nooit via `EnhancedBaseAgent.execute_tool()`. Bewezen
met een live mutatie: `is_denied()` (`permission_manager.py:133-152`) altijd `False` laten
teruggeven liet alle 24 op dat moment relevante tests groen. Geen actieve bypass (de broker
blokkeert de denylist onafhankelijk ook al via `is_tool_allowed()`), maar de precheck's
EIGEN, meetbare belofte had nul end-to-end gedragsdekking. **Fix:** nieuwe test
`test_execute_tool_denies_a_real_denylisted_tool_end_to_end` -- een ECHTE
`ToolPermissionManager` met een handmatig geinjecteerd denylist-profiel (geen YAML-bestand
nodig), `execute_tool()` volledig ongemockt (alleen de broker zelf is een dubbel om de
round-trip-telling te bevestigen). Zelf mutatiegetest: exact dezelfde mutatie herhaald,
rood; herstel groen, `git diff --stat` leeg na herstel.

**Bevinding 2 (MINOR, zelfreferentieel): ronde 3's eigen claim "alle documentverwijzingen
naar '15743' bijgewerkt" was zelf onjuist voor sectie 17 in HETZELFDE document.** Sectie 17
(Acceptatiecriteria, een LEVEND criterium, geen tijdstip-snapshot) citeerde nog "15743...
+2" -- inconsistent met sectie 6d, twee alinea's hoger in hetzelfde bestand, die al "15744"
had gecorrigeerd. **Fix:** sectie 17 herschreven om te verwijzen naar "het actuele,
laatst-gemeten cijfer" in de nieuwste ronde-sectie, in plaats van een hardcoded getal dat
bij een volgende ronde opnieuw kan verouderen.

**Herverificatie na de fixes (zelf gedraaid):**

```text
python -m pytest tests/unit/agents/test_base_agent_toolbroker.py -v --timeout=60
-> 10 passed (9 bestaand + 1 nieuw)

python -m pytest tests/unit/agents/test_base_agent_toolbroker.py tests/unit/tool_broker/test_denied_actions_hard_denylist.py -q --timeout=60
-> 20 passed

python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short --ignore=tests/core/agents/test_focus_builder_chat_agent.py
-> 15747 passed, 217 skipped, 22 xfailed, 0 failed. Totaal (15986) klopt exact met +1 t.o.v.
   ronde 3's 15985 -- geen extra/verdwenen test. **Correctie na ronde 5**: de mechaniek van
   de 219->217-verschuiving is gemeten (`sanskritisetu_redis_integration`/
   `_postgres_integration` draaien, en
   `tests/unit/core/database/test_the_redis_pool_survives_a_new_event_loop.py`'s
   module-brede `skipif` op poort 6380 plus zijn 2 testfuncties verklaren de verschuiving
   mechanisch exact) -- maar WIE die containers startte is NOOIT vastgesteld (`docker ps`
   toont alleen DAT ze draaien, niet WIE). Geen regressie (0 failed in beide gevallen), geen
   relatie met deze diff.
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 5 van de verplichte
blinde review volgt.

### 6f. Verplichte blinde eindreview -- ronde 5 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Elke numerieke claim uit rondes 1-4 herrekend en exact
bevestigd. Eigen mutaties: een verkeerde `agent_id` op de `is_denied()`-aanroepplek
(gevangen), `is_denied()` vervangen door `not is_tool_allowed()` (gevangen), en de
bevinding hieronder.

**Bevinding 1 (MINOR): het spiegelbeeld van ronde 4's eigen bevinding -- geen enkele test
bewees dat een NIET-geweigerde tool nog doorgaat naar de broker wanneer de ECHTE manager
een ECHT, NIET-LEEG profiel heeft.** Ronde 4's nieuwe end-to-end-test vraagt toevallig
alleen de WEL-geweigerde tool op; de bestaande "allow"-test mockt de manager zelf weg.
Bewezen met een live mutatie: `is_denied()` zo veranderen dat elk BESTAAND profiel alles
weigert (i.p.v. specifiek de genoemde tool) -- verwart "heeft dit profiel OVERHAUPT een
denylist" met "staat DEZE tool erop" -- liet alle 10 toen-bestaande tests groen. **Fix:**
nieuwe test `test_execute_tool_allows_a_different_tool_on_the_same_real_profile_end_to_end`
-- hetzelfde echte profiel als ronde 4's test, maar vraagt een ANDERE, niet-geweigerde tool
op. Zelf mutatiegetest: dezelfde mutatie herhaald, rood; herstel groen.

**Bevinding 2 (MINOR, procesmatig -- de belangrijkste van deze ronde): ronde 4's eigen
documentatie schreef een ONBEWEZEN oorzaak toe als vaststaand feit, precies de fout die
`.claude/rules/code-quality.md` verbiedt.** De 219->217-skipverschuiving werd toegeschreven
aan "de andere parallelle sessie die de containers startte voor zijn eigen werk" -- maar
`docker ps` toont alleen DAT de containers draaien, niet WIE ze startte; die attributie was
nooit onderzocht, alleen de UITKOMST (0 failed, arithmetisch kloppend) was gemeten. **Fix:**
zowel deze spec (sectie 6e) als de final-approver-brief (ronde 4) gecorrigeerd: het GEMETEN
mechanisme (de poort-6380-`skipif` + de 2 testfuncties in
`test_the_redis_pool_survives_a_new_event_loop.py`) blijft staan als bewezen; de
attributie-claim is vervangen door een expliciete erkenning dat de oorzaak van de
container-start ONVASTGESTELD blijft.

**Herverificatie na de fixes (zelf gedraaid):**

```text
python -m pytest tests/unit/agents/test_base_agent_toolbroker.py -v --timeout=60
-> 11 passed (10 bestaand + 1 nieuw)

python -m pytest tests/unit/agents/test_base_agent_toolbroker.py tests/unit/tool_broker/test_denied_actions_hard_denylist.py -q --timeout=60
-> 21 passed

python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short --ignore=tests/core/agents/test_focus_builder_chat_agent.py
-> 15748 passed, 217 skipped, 22 xfailed, 0 failed (+1 t.o.v. ronde 4's 15747, exact ronde
   5's ene nieuwe testfunctie)
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 6 van de verplichte
blinde review volgt.

### 6g. Verplichte blinde eindreview -- ronde 6 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Expliciet gevraagd om ronde 5's eigen correctie (het
onbewezen-oorzaak-probleem) zelf te controleren -- die houdt stand. Eigen mutaties: `is_denied()`
altijd `True` laten teruggeven voor het "geen profiel"-pad (incidenteel al gevangen door
bestaande AsyncMock-broker-tests), module/klasse-state-lek-check op de twee nieuwe echte-
manager-tests (geen), een onafhankelijke herbevestiging van "0 productie-aanroepers" via een
eigen grep. Geen nieuwe functionele of security-bevinding.

**Bevinding 1 (MINOR): deze brief's eigen "Gewijzigde bestanden"-lijst was zelf feitelijk
onjuist.** Noemde `2026-08-21-sprint-dag-8.md` (nooit in dit dag-8-commitbereik gewijzigd --
dat is de investigatie-brief uit de voorafgaande, eigen commit `f0d70388`) en liet het
bestand weg dat WEL in elke van de 6 commits is herschreven: deze brief zelf. **Fix:** de
lijst gecorrigeerd, zelf bevestigd via `git diff f0d70388..HEAD --stat` en `git log
--oneline` op beide bestanden.

**Bevinding 2 (NIT): de ADR-036 OP-24-rij's `BEWIJS=` wees naar de ZWAKSTE test (die
`is_denied()` zelf mockt), niet naar de sterkere, echte end-to-end-tests die rondes 4/5
juist toevoegden om dat exacte gat te dichten.** **Fix:** `BEWIJS=` bijgewerkt naar
`test_execute_tool_denies_a_real_denylisted_tool_end_to_end` (ronde 4's echte-manager-test),
`GEVERIFIEERD` bijgewerkt naar 2026-08-22. `test_adr036_register_is_parseable.py` blijft
groen (zelf herbevestigd, 6 passed).

**Herverificatie na de fixes (zelf gedraaid):**

```text
python -m pytest tests/architecture/test_adr036_register_is_parseable.py -v --timeout=60
-> 6 passed
```

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 7 van de verplichte
blinde review volgt.

### 6h. Verplichte blinde eindreview -- ronde 7 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Expliciet gevraagd een harde, laatste poging te doen
voor een eventuele conclusie van "niets nieuws" -- twee eigen mutaties die geen eerdere
ronde had geprobeerd (de precheck NA de broker-aanroep laten draaien i.p.v. ervoor; de
EVIDENCE_FIELD-regex handmatig tegen ronde 6's eigen parenthetische correctietekst
getoetst, om te bevestigen dat de "--" daarin de extractie niet stiekem afknot) -- beide
bevestigden bestaand, correct gedrag, geen nieuwe functionele bevinding. Een onafhankelijke
telling vanaf nul (elke commit los gediffed op nieuwe `def test_`-regels) bevestigde de
lopende testtelling exact: 2+0+1+0+1+1+0 = 5 nieuwe functies over de dag, 8/8/9/9/10/11
oplopend -- komt exact overeen met elke eerdere rondesectie's eigen telling.

**Bevindingen (MINOR, MINOR, NIT): drie plekken met verouderde cijfers/placeholders,
dezelfde herhalende fout een niveau verder.**
1. Deze briefs eigen kopsecties ("Tests die moeten slagen", de DoD-lijst, Laag 3) waren
   nooit bijgewerkt na ronde 1 en citeerden nog "8 passed"/"15743" terwijl elke latere
   rondesectie zelf al de juiste, oplopende cijfers droeg.
2. Sectie 17 hierboven verwees naar "sectie 6e" voor het actuele cijfer -- maar 6e zelf was
   alweer ingehaald door 6f (ronde 5) tegen de tijd dat een lezer die verwijzing volgde.
   Precies de fout die ronde 4 dacht te hebben gefixed, een niveau dieper: de vaste
   VERWIJZING (een sectieletter) veroudert net zo makkelijk als een vast GETAL.
3. De brief's `Commits:`-veld stond nog op de placeholder ondanks 7 echte commit-hashes.

**Fix:** de briefs kopsecties gecorrigeerd met een pointer naar de actuele stand (in plaats
van opnieuw een hardcoded getal dat een volgende ronde kan achterhalen); sectie 17
herschreven om naar "de laatste sectie" te verwijzen in plaats van een specifieke letter --
dit is een bewuste structurele fix, niet alleen een cijfercorrectie, om te voorkomen dat dit
patroon een vierde keer terugkomt. `Commits:`-veld ingevuld.

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten -- ronde 8 van de verplichte
blinde review volgt.

### 6i. Verplichte blinde eindreview -- ronde 8 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Drie bevindingen, waarvan de eerste twee opnieuw dezelfde
zelf-refererende documentatie-verouderingsfout een niveau verder tonen, en de derde een
echte, pre-existing testdekkingslacune die door deze diff relevanter wordt.

**Bevinding 1 (MINOR):** `docs/backend/review/review-BE-AGT-057.md`'s "Pointer"-paragraaf
(regels 116-127 destijds) noemde zichzelf "bijgewerkt bij elke volgende ronde" maar citeerde
tegelijk een vaste rondereeks ("rondes 1-5") en een vast sectiebereik ("6b t/m 6f") -- beide
al ingehaald doordat rondes 6-7 nadien plaatsvonden zonder dat dit bestand werd aangepast.
**Fix:** de paragraaf herschreven zonder rondenummers of sectieletters te noemen -- verwijst
nu generiek naar "alle secties onder '6.', tot de laatst-toegevoegde" en naar "alle 'Ronde
N'-secties" in de final-approver-brief.

**Bevinding 2 (MINOR):** de final-approver-brief's ronde-7-toegevoegde pointer-notitie (na
"Tests die moeten slagen") was slechts half generiek: hij citeerde toch een concreet cijfer
("11 tests", "15748 passed...") als actuele stand, terwijl hij in dezelfde zin beweerde
"bewust NIET meer per ronde bijgewerkt" te worden -- exact het patroon dat hij zei te
voorkomen, een niveau dieper (een hardcoded CIJFER in plaats van een hardcoded SECTIELETTER).
**Fix:** het cijfer verwijderd; de paragraaf verwijst nu naar het tellen van `def test_` in
het testbestand en het opnieuw draaien van de suite, in plaats van een cijfer te citeren dat
zelf weer kan verouderen.

**Bevinding 3 (NIT, wel gefixt conform het drempelmodel -- geisoleerd, 1 testbestand, < 15
min):** `is_denied()` (`permission_manager.py`) weigert op `denied_actions` OF de legacy-
alias `denied_tools`, maar geen enkele test in de repo oefende de `denied_tools`-tak uit --
bevestigd met een live mutatie (de `or tool_name in profile.denied_tools`-clausule
verwijderen liet alle 663 op dat moment relevante tests groen). `permission_manager.py` is
zelf niet gewijzigd door deze diff (dus geen regressie van vandaag), maar de diff voegt wel
een TWEEDE productie-aanroeper toe (`EnhancedBaseAgent._get_execute_tool_permission_manager`
naast `specialist_base.py`'s bestaande `_reject_before_council()`) die op deze functie leunt
-- de blootstelling van het gat verdubbelt daardoor.

**Fix:** nieuwe test `test_execute_tool_denies_a_tool_on_the_legacy_denied_tools_alias_end_
to_end` toegevoegd (`tests/unit/agents/test_base_agent_toolbroker.py`), spiegelbeeld van
`test_execute_tool_denies_a_real_denylisted_tool_end_to_end` maar met `denied_tools=[...]`
in plaats van `denied_actions=[...]`. Mutatiebewijs in beide richtingen zelf herhaald: (a)
de `or`-clausule verwijderd uit `is_denied()` -> alleen de nieuwe test wordt rood, alle 11
overige tests (inclusief de `denied_actions`-variant) blijven groen, wat bewijst dat de
nieuwe test specifiek de `denied_tools`-tak dekt en niet toevallig meelift op de
`denied_actions`-tak; (b) bestand herstel via `cp`-backup (niet `git checkout --`, wegens de
gedeelde working-copy met een andere parallelle sessie), `git diff --stat` leeg bevestigd na
herstel.

**Herverificatie na alle drie de fixes (zelf gedraaid):**

- `python -m pytest tests/unit/agents/test_base_agent_toolbroker.py tests/unit/tool_broker/
  -q --timeout=60` -> 231 passed.
- `python -m pytest tests/architecture/test_agent_actions_pass_council.py
  tests/architecture/test_adr036_register_is_parseable.py
  tests/architecture/test_dsm_grade_a_plus.py tests/architecture/test_dsm_007_scanner_
  quality.py tests/architecture/test_dsm_008_reclassification.py tests/architecture/
  test_dsm014_agt_rt_no_laag_circulars.py -q --timeout=60` -> 38 passed.
- `python -m pyright` (geen args) -> 0 errors, 54 warnings (baseline ongewijzigd).
- `ruff check tests/unit/agents/test_base_agent_toolbroker.py src/core/tool_broker/
  permission_manager.py` -> All checks passed.
- ASCII-scan (programmatisch, niet visueel) op alle drie gewijzigde bestanden -> schoon.
- `python scripts/validate_feature_docs.py` -> 685/710, geen nieuwe incomplete IDs.
- Volledige mandatory regressiesuite: zie final-approver-brief voor de exacte cijfers.

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten totdat ronde 9 van de
verplichte blinde review een schoon oordeel geeft (GO, nul nieuwe bevindingen) -- die ronde
volgt na dit commit.

### 6j. Verplichte blinde eindreview -- ronde 9 -- bevindingen en fixes (2026-08-22)

**Oordeel: GO WITH MINOR ISSUES.** Ronde 8's drie fixes zijn zelf onafhankelijk herverifieerd
en bevestigd correct (mutatiebewijs op `is_denied()`'s `denied_tools`-tak herhaald: exact 1
test rood, 230 groen; pyright/ASCII/testtellingen exact zoals geclaimd). Maar ronde 8 heeft
het defect-patroon dat het zelf bestreed niet overal weggehaald -- twee bevindingen.

**Bevinding 1 (MEDIUM): sectie 17 (Acceptatiecriteria) had dezelfde vervallende-cijfer-fout
die ronde 8 elders al fixte.** Sectie 17 is expliciet gemarkeerd als "een LEVEND criterium,
geen tijdstip-snapshot" -- maar citeerde na de generieke "zie de laatste sectie, niet een
vaste letter"-instructie toch een hardcoded cijfer ("Ronde 7's eigen, zelf herbevestigde
meting: 15748 passed..."), terwijl de werkelijke stand na ronde 8's eigen commit al 15749
was. Ronde 8 verifieerde/fixte dit exacte patroon in `review-BE-AGT-057.md` en de
final-approver-brief, maar miste de identieke instantie in zijn EIGEN document, in precies de
sectie waar de hele dag zijn "levend criterium"-discipline om gebouwd is. **Fix (door de
ronde-9-reviewer zelf, documentatie-only):** de zin herschreven zonder enig cijfer, in geen
vorm -- verwijst nu naar "tel `def test_` in het testbestand en draai de mandatory suite
opnieuw", consistent met de generieke vorm elders.

**Bevinding 2 (LOW/NIT): `review-BE-AGT-057.md`'s pointer-paragraaf sprak zichzelf letterlijk
tegen.** De historische toelichting tussen haakjes zei "Deze paragraaf noemt daarom bewust
GEEN rondenummers of sectieletters meer" terwijl diezelfde toelichting "ronde 8", "rondes 6
en 7", "rondes 1-5" en "6b t/m 6f" noemt -- vier keer. Het vooruitwijzende deel NA de
toelichting is wel degelijk generiek (geen enkele stale verwijzing daar), dus dit was geen
functioneel risico, alleen een letterlijke tegenspraak. **Fix:** de toelichting verduidelijkt
-- de historische toelichting mag rondenummers noemen als feit over het verleden (dat is
gedateerd en blijft zo staan), de belofte "geen vaste verwijzing meer" geldt uitsluitend voor
het vooruitwijzende deel erna.

**Herverificatie na beide fixes (zelf gedraaid):**

- `python -m pytest tests/architecture/test_adr036_register_is_parseable.py
  tests/architecture/test_agent_actions_pass_council.py -q --timeout=60` -> 11 passed.
- `python scripts/validate_feature_docs.py` -> 685/710, geen nieuwe incomplete IDs.
- ASCII-scan (programmatisch) op beide gewijzigde bestanden -> schoon.
- Geen code- of testbestand gewijzigd deze ronde (alleen documentatie), dus geen nieuwe
  pyright/ruff-run nodig; de vorige meting (0 errors/54 warnings, All checks passed) blijft
  van toepassing.

Dag 8 (en daarmee de gehele 8-daagse sprint) is NIET gesloten totdat een ronde met nul
sessiecontext een schoon oordeel geeft (GO, nul nieuwe bevindingen) -- die ronde volgt na
dit commit.

### 7. Zichtbaarheids- en toegangsregels

- Geen wijziging. Geen nieuw HTTP-schema, geen nieuw leespad. De precheck is een interne
  controle binnen een reeds-bestaande interne methode.

### 8-16. n.v.t

### 17. Acceptatiecriteria

- [x] `_get_execute_tool_permission_manager()` hergebruikt de broker's manager met een
  isinstance-guard-fallback, geverifieerd tegen zowel een echte `ToolPermissionManager` als
  een `AsyncMock`-broker (bestaande tests blijven groen).
- [x] Een denylist-treffer voorkomt de broker-aanroep volledig (`assert_not_awaited()`),
  bewezen met een dedicated test.
- [x] Een niet-geweigerde tool gaat nog steeds normaal door naar de broker (regressietest).
- [x] Rood-voor-fix bewezen op de gecommitte (pre-fix) code, niet aangenomen.
- [x] `KNOWN_UNGATED` blijft bestaan met een gecorrigeerde, gedateerde reden; de guard blijft
  groen (`test_agent_tool_execution_passes_the_council`, `test_known_ungated_list_is_not_stale`).
- [x] ADR-036 OP-24-rij bijgewerkt met de gecorrigeerde D5-bevinding en de dag-8-fix.
- [x] Volledige mandatory regressiesuite groen (dit is een LEVEND criterium, geen
  tijdstip-snapshot -- gecorrigeerd door ronde 4 na een eigen bevinding dat deze exacte
  regel na ronde 3's fix nog het VERSCHOVEN "15743"-cijfer citeerde, terwijl sectie 6d
  twee alinea's hoger al "15744" had gecorrigeerd -- de "alle documentverwijzingen zijn
  bijgewerkt"-claim uit ronde 3 dekte deze levende sectie zelf niet):
  `python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short --ignore=tests/core/agents/test_focus_builder_chat_agent.py`
  -> **correctie na ronde 8**: de vorige versie van deze regel verwees naar "sectie 6e"
  voor het cijfer, en had dat sindsdien al twee keer moeten bijwerken (6e -> 6f -> 6h) --
  exact dezelfde vaste-verwijzing-fout die deze regel zelf al signaleerde. Deze regel citeert
  daarom bewust GEEN getal meer, in geen vorm (niet als cijfer, niet als sectieletter): tel
  `def test_` in `tests/unit/agents/test_base_agent_toolbroker.py` en draai de mandatory
  suite opnieuw voor het actuele resultaat -- lees geen getal uit deze sectie of uit een
  eerdere rondesectie als actueel. `python -m pyright` (canoniek,
  geen args) -> 0 errors, 54 warnings (baseline ongewijzigd).

### 18. Integratoruitleg

- N.v.t. -- geen publieke API-wijziging. `execute_tool()` is een interne agentmethode.

### 19. Trainingssamenvatting

- **Actor:** een agent (elke `EnhancedBaseAgent`-subklasse, inclusief alle 135 ALS-skills) die
  `execute_tool(tool_name, payload)` aanroept.
- **Voorwaarde:** de agent heeft een geinitialiseerde `tool_broker`.
- **Actie:** de agent vraagt uitvoering van `tool_name` aan.
- **Systeemreactie:** als `tool_name` op de D5-harde-denylist van het agent-profiel staat,
  wordt de aanvraag NU al op agent-niveau afgewezen (`ToolExecutionException`, een
  `tool_failed`-event), zonder dat de broker ooit wordt aangeroepen. Staat de tool niet op de
  denylist, dan verloopt de aanvraag ongewijzigd via de broker.
- **Succes:** de tool wordt uitgevoerd (ongewijzigd pad) of correct geweigerd (nu vroeger in
  de tijdlijn dan voorheen).
- **Fout:** een denylist-treffer resulteert in een `ToolExecutionException`, gevangen en
  doorgegeven door de bestaande foutafhandeling.
- **Uitzonderingen:** Council-consultatie en initiator-verificatie zijn hier NIET aanwezig --
  dat blijft een openstaand, bewust uitgesteld deel van OP-24 (Fase D).
