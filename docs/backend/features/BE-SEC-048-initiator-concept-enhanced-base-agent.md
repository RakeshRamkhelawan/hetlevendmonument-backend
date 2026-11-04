# BE-SEC-048 -- Ontwerpvoorstel: initiator-concept op `EnhancedBaseAgent`

Status: GEIMPLEMENTEERD achter een uitgeschakelde feature-flag (commit `ded5b236`,
2026-08-26). SS1 t/m SS9 zijn de ONTWERPFASE en staan er ongewijzigd bij als
besluitgeschiedenis -- lees SS10 voor de gemeten stand van vandaag voordat je iets uit
SS3, SS4 of SS9.3 als openstaand overneemt.
Datum: 2026-08-25 (ontwerp), 2026-08-26 (implementatie), 2026-09-01 (SS10 nagemeten)
Aanleiding: ADR-036 OP-24 (register-item, `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`)

---

## 1. Het gat, exact geciteerd

`EnhancedBaseAgent.execute_tool()` (`src/core/agents/base_agent.py:355-390`) heeft sinds
fix-sprint dag 8 (BE-AGT-057) een D5-denylist-precheck, maar de docstring-comment op regel
373-374 zegt het zelf: "Geen Council- of initiator-check hier: die twee blijven de echte, nog
open OP-24-gaten (Fase D, geen equivalent-veld voor initiator hier)." Vergelijk
`src/core/als/agents/specialist_base.py:230-267` (`BaseSpecialistAgent._reject_before_council()`,
`_council_rejection()`), dat WEL `self._initiated_by_user_id` heeft en zonder een bekende
initiator een actie fail-closed weigert (AI Act art. 14: geen mens, geen actie).

**Het concept bestaat dus al** -- alleen niet op `EnhancedBaseAgent` zelf, maar op
`BaseSpecialistAgent`, een zustertak in de klassenhierarchie
(`BaseSpecialistAgent -> SymbioticAgent -> EnhancedBaseAgent`). Elke klasse die rechtstreeks
van `EnhancedBaseAgent` erft (of van `SymbioticAgent` zonder via `BaseSpecialistAgent` te
gaan) heeft geen enkele vorm van dit concept.

---

## 2. Impact-analyse (gemeten, niet geschat)

```bash
grep -rn "EnhancedBaseAgent" src/ --include="*.py"
```

**28 bestanden** matchen. Opgesplitst naar wat ze daadwerkelijk zijn:

| Categorie | Aantal | Voorbeeld |
|---|---|---|
| `BaseSpecialistAgent`-subklassen (135 ALS-skills, via `SymbioticAgent`) | 135 | `taskmanager.py`, `skillsgaptraining.py`, ... |
| Directe `EnhancedBaseAgent`-subklassen in `src/core/agents/` (los van de ALS-boom) | 13 | `AgentHealthMonitorAgent`, `AnalyzerAgent`, `CVAAgent`, `CodeAgent`, `ExecutorAgent`, `MockEthicsAgent`, `FinancialAgent`, `MasterOrchestratorAgent`, `MarketingAgent`, `MLEthicsAgent`, `ResearchAgent`, `ProductAgent`, `SecurityAgent`, `PlannerAgentWithAgency`, `AgentWrapper`, `AgentRouterAgent` |
| `SymbioticAgent`-subklassen buiten `BaseSpecialistAgent` | 4 | `SymbioticResearchAgent`, `SymbioticCodeAgent`, `SymbioticAnalyzerAgent`, `DepartmentAgent` |
| `BaseSupervisor(SymbioticAgent)` + subklassen (buiten de guard's `AGENT_ROOTS`-scope, al genoteerd in OP-24) | 1 + 11 | `src/core/als/supervisors/*.py` |
| Overig (`ExternalAgentBridge`, scheduling-agents) | 3 | `external_agent_bridge.py`, `voice/agent.py`, `orchestrator_agent.py` |

**De 135 skills hebben het gat feitelijk NIET** -- ze lopen via `BaseSpecialistAgent`, dat het
concept al heeft. De echte, ongedekte oppervlakte is de tweede en derde rij: **ongeveer 17-20
directe `EnhancedBaseAgent`/`SymbioticAgent`-subklassen** (13 + 4, exclusief de supervisors die
al als een apart, bestaand P2-punt in OP-24 staan) die `self.execute_tool()` kunnen aanroepen
zonder dat er ooit een verantwoordelijke mens is vastgelegd.

**Wat dit oplevert dat nog niet bekend was:** de oorspronkelijke OP-24-registerrij noemde
"tientallen afgeleide klassen" zonder onderscheid. Dat is feitelijk grotendeels de 135 skills,
die het probleem al niet hebben. Het echte werk is een orde van grootte kleiner (~17-20
klassen), maar wel verspreid over losstaande subsystemen (agent-orchestratie,
scheduling-agents, company-integratie) die elk hun eigen aanroepconventie hebben -- vandaar
nog steeds een eigen implementatiedag, niet een kwestie van "een paar regels."

---

## 3. Ontwerpvoorstel (concept, geen definitieve keuze)

### 3.1 Het veld zelf

Analoog aan `specialist_base.py`:

```python
class EnhancedBaseAgent:
    _initiated_by_user_id: int | None = None
```

Gezet door de aanroeper voordat `execute_tool()` wordt aangeroepen, nooit door de agent zelf
verzonnen (zelfde eis als bij `BaseSpecialistAgent`: zonder bekende initiator wordt de actie
niet uitgevoerd -- fail-closed, geen sentinel-waarde).

### 3.2 De check in `execute_tool()`

Analoog aan `_reject_before_council()`'s tweede grond (specialist_base.py:236-240): direct na
de bestaande D5-denylist-precheck, voor de broker-aanroep:

```python
if self._initiated_by_user_id is None:
    raise ToolExecutionException(
        tool_name=tool_name,
        error_detail="geen initiator bekend (AI Act art. 14)",
    )
```

**Open vraag 1 (Rakesh's GO nodig):** moet dit ook een Council-raadpleging toevoegen (zoals
`_council_rejection()` doet), of alleen de initiator-eis? De oorspronkelijke OP-24-bevinding
noemde beide als losse gaten. Een Council-raadpleging per `execute_tool()`-aanroep op
`EnhancedBaseAgent` zou een nieuwe, generieke aanroep naar
`request_council_decision_for_agent()` betekenen voor ~17-20 klassen tegelijk -- een grotere,
eigen beslissing dan alleen de initiator-eis, en heeft dezelfde aard als de OP-167/OP-168
Council-brede vraagstukken (zie de open-punten-opruiming-brief van vandaag, Taak 2).
**Aanbeveling van dit document: eerst alleen de initiator-eis, Council-raadpleging als
aparte, latere beslissing** -- dat splitst het gat in twee onafhankelijk te beoordelen delen,
in plaats van een enkele, grotere wijziging die twee besluiten samenvoegt.

### 3.3 Welke aanroepers moeten het veld gaan zetten?

Voor elke klasse in de tweede en derde rij van de tabel in SS2: wie roept `execute_tool()`
aan, en heeft die aanroeper vandaag al een `user_id` beschikbaar?

- `AgentRouterAgent`, `MasterOrchestratorAgent`: orchestratie-agents die andere agents
  aansturen -- hebben zij zelf een initiator, of moeten ze die doorgeven van HUN aanroeper?
  **Open vraag 2:** is er een keten nodig (initiator propageert door meerdere
  orchestratie-lagen), of is elke laag verantwoordelijk voor zijn eigen initiator-bron?
- `CVAAgent`: heeft mogelijk al een `user_id` uit de CVA-flow beschikbaar (vergelijkbaar met
  hoe `cva_autonomous_trigger.py` dat NIET heeft, zie de OP-12-addendum van vandaag) --
  **vereist een aparte check per klasse, niet aangenomen.**
- `ExternalAgentBridge`, scheduling-agents (`SchedulingVoiceAgent`,
  `SchedulingOrchestratorAgent`): mogelijk geen directe menselijke aanroeper in de keten
  (vergelijkbaar met het OODA-pad dat OP-21 al beschrijft voor de ALS-skills) -- **vereist
  vaststellen of deze klassen `execute_tool()` vandaag daadwerkelijk aanroepen, of dat het
  pad al elders geblokkeerd is** (net zoals bij OP-24's D5-helft bleek dat de "denylist"-helft
  al door de broker werd gedekt voordat er ooit geimplementeerd werd).

**Dit document beantwoordt deze vragen niet** -- dat vereist per klasse de aanroepketen lezen,
wat een eigen implementatiedag is, geen documentatiedag.

---

## 4. Wat dit NIET is

- **Geen wijziging aan `specialist_base.py`.** Dat heeft het concept al; dit voorstel gaat
  over de klassen die het NIET hebben.
- **Geen wijziging aan `KNOWN_UNGATED`** in `tests/architecture/test_agent_actions_pass_council.py`.
  Zonder een echte `_council_rejection()`-aanroep zou de guard ROOD worden (zelfde les als
  BE-AGT-057 empirisch bevestigde) -- dat is precies waarom dit een apart implementatievoorstel
  is en geen documentatie-only wijziging.
- **Geen beslissing over Council-raadpleging.** Zie open vraag 1.

---

## 5. Openstaande beslissingen (samenvatting voor Rakesh)

| # | Beslissing | Waar |
|---|---|---|
| 1 | Alleen initiator-eis nu, Council-raadpleging als aparte latere beslissing? (aanbevolen) | SS3.2 |
| 2 | Initiator-propagatie door orchestratie-lagen, of per-laag-verantwoordelijkheid? | SS3.3 |
| 3 | Voor welke van de ~17-20 klassen is er vandaag al een echte menselijke initiator in de keten, en voor welke niet (analoog aan OP-21's OODA-pad-conclusie)? | SS3.3 |

---

## 6. Verificatie dat dit document geen gedrag wijzigt

```bash
python -m pytest tests/architecture/test_agent_actions_pass_council.py -v
```

Verwacht: ongewijzigd groen, `KNOWN_UNGATED` niet aangeraakt.

---

*Zie ook: `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md` OP-24,
`docs/agent-briefs/generated/2026-08-25-sprint-dag-open-punten-opruiming.md` Taak 3.*

---

## 7. Addendum 2026-08-25 -- Rakesh's beslissing: BEIDE (initiator-eis EN Council-raadpleging)

Rakesh heeft, na het lezen van de dagbrief `2026-08-25-sprint-dag-op12-op24.md`, gekozen
voor de bredere variant op open vraag 1 (SS3.2): niet alleen de initiator-eis, maar ook
een generieke Council-raadpleging op `EnhancedBaseAgent.execute_tool()`. Dat wijkt af van
de aanbeveling in dit document. Onderstaand de gemeten technische consequenties van die
keuze, zodat de vervolgstap op feiten gebaseerd is, niet op het eerdere scopevoorstel.

### 7.1 Wat de Council-aanroep concreet vereist (gemeten, niet aangenomen)

`request_council_decision_for_agent()` (`src/core/copilot/council/background_gate.py:60-79`)
bouwt een `Proposal` (`src/core/copilot/council/types.py:82-119`) met verplichte velden
zonder default: `tenant_id`, `user_id`, `trigger`, `action_type`, `action_params`,
`reasoning`, `data_classification`, `confidence`, `model_id`, `model_version`,
`context_snapshot`. **`__post_init__` faalt hard (raise) bij `tenant_id<=0` of
`user_id<=0`** -- dit is geen soft-fail of skip, het is een crash bij aanroep.

`EnhancedBaseAgent.execute_tool()` heeft vandaag `self.tenant_id` en `self.agent_id`,
maar generiek GEEN `user_id`/initiator, GEEN `action_type`/`reasoning`/`message`-conventie
(alleen `tool_name`, `payload`, `timeout` als parameters). Concreet gevolg: **de
initiator-eis is niet langer een onafhankelijk voor te bereiden stap naast de
Council-eis -- het is een HARDE PREREQUISITE ervoor.** Zonder een geldige
`user_id` (>0) crasht elke Council-aanroep vanuit een klasse zonder vastgestelde
initiator, in plaats van netjes te weigeren. Open vraag 3 (welke van de ~17-20 klassen
hebben vandaag al een echte initiator in de keten) moet daarom PER KLASSE zijn opgelost
VOORDAT de Council-aanroep in die klasse live gaat -- niet, zoals SS3.3 eerder toestond,
als iets dat "expliciet gedocumenteerd" kan blijven staan terwijl de check fail-closed
weigert. Een fail-closed weigering op ontbrekende initiator is prima; een crash op een
ontbrekende `user_id` in een `Proposal`-constructie is dat niet.

### 7.2 HITL-pad is al gedekt

Goed nieuws: een `HITL_REQUIRED`-verdict op dit pad maakt sinds OP-167 (gesloten
2026-08-25) altijd een echt ticket, ongeacht welke van de 5 `deliberate()`-aanroepers het
gebruikt (`background_gate.py:159-207`, `HITLTicketRepository.create_hitl_request()`).
Een generieke Council-aanroep vanuit `EnhancedBaseAgent` zou dus GEEN eigen HITL-ticket-
logica hoeven te bouwen (in tegenstelling tot de situatie voor OP-163/167).

### 7.3 De reden achter de oorspronkelijke aanbeveling blijft staan als afweging

`AgentCouncil.deliberate()` doet per aanroep een parallelle deliberatie over 7 stemmende
Officers via `asyncio.gather` (`coordinator.py:127,327`) plus een DB-sessie. Bij
`specialist_base.py` is dit per-skill fijnmazig aan/uit te zetten via
`SkillManifest.human_in_the_loop`/`annex_iii_classification` (D4-002-floor). Een
generieke aanroep op ALLE ~17-20 `EnhancedBaseAgent`-klassen tegelijk heeft dat
per-klasse schakelmechanisme nog niet -- dat is zelf een ontwerpkeuze (vlag per klasse?
per tool? altijd aan?) die dit document nog niet beantwoordt. **Dit is geen bezwaar tegen
Rakesh's beslissing, maar een expliciete vervolgvraag** die bovenop de drie
oorspronkelijke open vragen (SS5) komt.

### 7.4 Bewakende test, exacte plek

`tests/architecture/test_agent_actions_pass_council.py`, `KNOWN_UNGATED`-dict (regel
50-64) bevat de sleutel `"src/core/agents/base_agent.py::EnhancedBaseAgent.execute_tool"`.
Implementatie vereist: een `_council_rejection()`-analoge aanroep toevoegen in
`execute_tool()` EN die regel uit `KNOWN_UNGATED` verwijderen in dezelfde commit --
zonder de aanroep blijft de guard vals-groen, met de aanroep maar zonder verwijdering
blijft hij onterecht rood (`test_known_ungated_list_is_not_stale()`, regel 194-199).

### 7.5 Herziene openstaande beslissingen (vervangt SS5, met vraag 3 nu als harde prerequisite)

| # | Beslissing | Status |
|---|---|---|
| 1 | Initiator-eis EN Council-raadpleging (niet alleen initiator) | **BESLIST 2026-08-25 (Rakesh)** |
| 2 | Initiator-propagatie door orchestratie-lagen (`AgentRouterAgent`, `MasterOrchestratorAgent`), of per-laag-verantwoordelijkheid? | Nog open |
| 3 | Per klasse (~17-20): is er een echte initiator EN kan de Council-aanroep dus veilig, of moet de klasse fail-closed blijven weigeren? | **Nog open, nu HARDE PREREQUISITE per klasse -- geen crash-risico toestaan** |
| 4 (nieuw) | Schakelmechanisme voor de Council-aanroep per klasse/tool (analoog aan `SkillManifest.human_in_the_loop`), of altijd-aan voor alle ~17-20 klassen? | Nog open, ontstaan uit SS7.3 |

Zonder vraag 2, 3 en 4 is er nog steeds geen implementeerbaar plan voor de Council-helft --
dezelfde conclusie als eerder, nu met een scherpere reden (crash-risico, niet alleen
onvolledigheid).

---

## 8. Addendum 2026-08-26 -- uitrol- en noodschakelaar-ontwerp (industriestandaard, met bron)

Onderzocht via WebSearch tegen erkende engineering-bronnen (Google SRE Workbook,
Flagsmith/Featureflow), niet verzonnen. Beide beslissingen zijn tenant-mode-onafhankelijk
-- de initiator/Council-eis gaat over WIE een actie startte (een gebruiker), niet over
WELKE tenant, dus single-tenant-multi-user-modus (`docs/adr/035-...md`) verandert dit
ontwerp niet: elke gebruiker heeft nog steeds een eigen `user_id`, ongeacht hoeveel
tenants er zijn.

### 8.1 Uitrolvolgorde: ring-based, niet strikt een-voor-een, niet in een keer

Bron: [Google SRE Workbook -- Canarying Releases](https://sre.google/workbook/canarying-releases/).
Vervangt de eerdere, te grove aanbeveling "een klasse per keer". Concreet voor de
~17-20 klassen uit SS2's tabel:

1. **Ring 0 (canary): 1 klasse** met een lage productie-impact en een bekende,
   makkelijk te verifieren initiator-bron (bv. een klasse die uitsluitend via een
   interactieve, menselijke sessie wordt aangeroepen). Observatieperiode: minimaal 48
   uur, nul onverwachte `ToolExecutionException`-crashes op de initiator-check.
2. **Ring 1: klein groepje (3-5 klassen)** met vergelijkbaar risicoprofiel als de
   canary. Observatieperiode: 48-72 uur.
3. **Ring 2: de resterende klassen**, inclusief de orchestratie-lagen
   (`AgentRouterAgent`, `MasterOrchestratorAgent`) die afhankelijk zijn van open vraag 2
   (propagatie) -- deze horen bewust in de LAATSTE ring, omdat ze het meest complexe
   initiator-vraagstuk hebben.
4. **Stopcriterium per ring, vooraf vastgelegd** (niet ter plekke verzinnen tijdens een
   incident): "meer dan 0 onverwachte crashes op de initiator-check in de
   observatieperiode" -> die ring niet doorzetten, terugdraaien naar de vorige ring via
   de noodschakelaar (SS8.2), root cause onderzoeken voor verder te gaan.

### 8.2 Noodschakelaar: EEN centraal punt, niet verspreid over 17-20 klassen

Bron: [Featureflow -- Feature Flag Kill Switches](https://www.featureflow.com/blog/feature-flag-kill-switches),
[Emergency Kill Switches for Incident Response](https://beefed.ai/en/kill-switches-incident-response-feature-flags).
Kernprincipe uit de bron: "wrap de flag-evaluatie op het instappunt van de feature, niet
verspreid over meerdere componenten -- een omschakeling moet het hele oppervlak
uitschakelen."

**Concreet ontwerp:** de initiator-check EN de Council-aanroep worden BEIDE achter een
enkele feature-flag-check geplaatst, op de ENE plek waar toch al alle ~17-20 klassen
doorheen lopen: `EnhancedBaseAgent.execute_tool()` zelf (`base_agent.py:355-390`), niet
in elke subklasse apart. Nieuwe `FEATURE_FLAGS`-key (zelfde conventie als
`get_feature_flag()` elders in dit project, zie ADR-031-addendum SS6.4):
`"enhanced_base_agent_initiator_check"`. Bij uitgeschakeld: het bestaande gedrag van
vandaag (geen initiator-check, geen Council-aanroep) blijft ongewijzigd -- de flag is
dus ook meteen het uitrol-mechanisme per ring uit SS8.1 (een aparte, per-ring-lijst van
klassen kan bepalen of de vlag voor DIE klasse al aan staat, of een simpele allowlist in
de flag-config).

**Vooraf vastgelegd stopcriterium** (uit dezelfde bron): "uitzetten als meer dan 1% van
de `execute_tool()`-aanroepen op de betrokken klassen een `ToolExecutionException` door
de initiator-check geeft, gemeten over een venster van 10 minuten." Dit getal is een
startpunt, geen dogma -- Rakesh kan het bijstellen.

### 8.3 Wat dit NIET oplost

Dit ontwerp beantwoordt niet open vraag 2 (initiator-propagatie door orchestratie-lagen)
of vraag 3 (per-klasse initiator-audit) -- dat blijft het daadwerkelijke onderzoekswerk
van de implementatiedag (Taak 0/1 in de dagbrief), niet iets dat een uitrolstrategie kan
vervangen.

---

## 9. Addendum 2026-08-26 -- Taak 0 uitgevoerd: het gat is theoretisch, net als D5

Impact-analyse per klasse (4 parallelle onderzoeken, alle 20 klassen uit SS2, plus een
afsluitende repo-brede zoektocht) is uitgevoerd VOORDAT er code werd geschreven, zoals
Taak 0 van de implementatiedag voorschreef. Uitkomst wijkt fundamenteel af van de
aanname achter dit hele ontwerp.

### 9.1 Bevinding

**Geen van de 16 directe `EnhancedBaseAgent`-subklassen of 4 `SymbioticAgent`-subklassen
roept `self.execute_tool()` ergens in zijn eigen code aan** (grep per klasse, 0
treffers in alle 20 bestanden). Een afsluitende repo-brede zoektocht naar EXTERNE
aanroepen (`.execute_tool(` op een instantie van buiten de eigen klasse) vond 17
treffers in totaal -- **geen enkele daarvan roept de methode aan op een instantie van
een van de 20 klassen.** Alle 17 treffers gaan naar een broker-object
(`IToolBroker`/`ToolBrokerService`/`ToolBrokerClient`/`AgentToolBrokerClient`), een
ANDERE `execute_tool`-methode (broker-niveau, signatuur `tool_name/payload/agent_id/context`)
dan de agent-wrapper-methode in `base_agent.py:355` die de D5-precheck bevat en het
OP-24-doelwit is.

**Dit is dezelfde uitkomst als OP-24's D5-denylist-helft** (ADR-036-register, "de
'geen D5-denylist'-helft hield niet stand -- er was nooit een scenario waarin een
denylist-tool via execute_tool() daadwerkelijk uitvoerde"): de initiator-/Council-check
zou een methode beveiligen die door NIEMAND buiten zijn eigen definitie wordt
aangeroepen op deze 20 klassen. Enkele bijvangsten uit het onderzoek:

- 3 van de 20 klassen (`ResearchAgent`, `ProductAgent`, `SecurityAgent`) lijken volledig
  orphaned -- geen productie-imports gevonden buiten hun eigen bestand.
- `AgentWrapper` (+ subklassen) heeft alleen test-callers, geen productiepad.
- De 4 `SymbioticAgent`-pilot-klassen (`SymbioticResearchAgent`/`SymbioticCodeAgent`/
  `SymbioticAnalyzerAgent`) retourneren hardcoded gesimuleerde resultaten -- geen
  echte tool-executie uberhaupt.
- `SymbioticAgent` zelf heeft, bevestigd door directe inspectie, GEEN
  `_initiated_by_user_id`-achtig attribuut (in tegenstelling tot `BaseSpecialistAgent`) --
  dit bevestigt de eerdere SS2-bevinding.
- `PlannerAgentWithAgency` heeft wel een echte `user_id` in zijn HTTP-keten
  (`current_user.id` via FastAPI-dependency), maar dispatcht via een aparte
  `AgencyCapabilityRegistry`, niet via `execute_tool()`.
- `ExecutorAgent` (`executor_agent.py:29`) voert acties DIRECT uit via `aiohttp`/
  `subprocess`, buiten het broker-pad om -- een apart, nieuw governance-gat, LOS van
  OP-24, niet hier opgelost (zie SS9.3).
- `MasterOrchestratorAgent`/`AgentRouterAgent` geven alleen `tenant_id` door in hun
  `TaskData`, nooit een `user_id` -- als deze orchestratie-agents ooit wel
  `execute_tool()` gaan aanroepen, ontbreekt de initiator-bron sowieso nog.

### 9.2 Wat dit betekent voor de implementatie

De oorspronkelijke aanname (Rakesh's beslissing voor "initiator EN Council", SS7.1) ging
uit van een LEVEND aanvalsoppervlak dat een crash-risico met zich meebracht zodra de
check zou worden toegevoegd. Dat risico blijft juist AL het pad ooit live wordt -- maar
er is vandaag geen enkele aanroeper om te breken. Concreet:

- De ring-based-uitrol (SS8.1) en de centrale noodschakelaar (SS8.2) blijven zinnig als
  ONTWERP voor de dag dat een van deze klassen wel `execute_tool()` gaat aanroepen, maar
  een PRODUCTIE-uitrol met observatieperiodes tussen rings is vandaag zonder object: er
  is niets om te observeren.
- Ring 2/3 zijn feitelijk ring 0: alle 20 klassen zijn vandaag even inert.

### 9.3 Aanbevolen aanpak (herzien, vervangt de eerdere ring-planning)

Analoog aan hoe OP-24's D5-helft is behandeld (agent-laag precheck toegevoegd als
architecturale consistentie, runtimegedrag ongewijzigd omdat de broker al blokkeerde):

1. **Implementeer de initiator-eis EN de Council-aanroep in `EnhancedBaseAgent.execute_tool()`
   zelf, in EEN keer, geen ring-based gefaseerde uitrol** -- er is geen live risico om
   tegen te faseren. De feature-flag (SS8.2) blijft wel bestaan als schakelaar voor de
   dag dat dit pad live gaat, maar het "canary -> ring 1 -> ring 2"-observatieproces is
   overbodig zolang er geen aanroeper is.
2. **Verwijder `"src/core/agents/base_agent.py::EnhancedBaseAgent.execute_tool"` uit
   `KNOWN_UNGATED`** (`tests/architecture/test_agent_actions_pass_council.py`) zodra de
   check erin staat -- dit is de daadwerkelijke sluiting van OP-24.
3. **Registreer het nieuwe ExecutorAgent-governance-gat (SS9.1) apart** als een nieuw
   OP-nummer in ADR-036 -- niet stilzwijgend laten liggen, niet hier oplossen (buiten
   scope van OP-24, dat gaat over `execute_tool()`-toegang, niet over het omzeilen ervan
   via directe `aiohttp`/`subprocess`-aanroepen).
4. **Open vraag 2 (initiator-propagatie) en vraag 3 (per-klasse initiator-audit) zijn nu
   beantwoord door dit onderzoek**: er is geen enkele klasse met een levende
   execute_tool-aanroep, dus er is ook geen propagatie-vraagstuk op te lossen vandaag.
   Zodra `AgentRouterAgent`/`MasterOrchestratorAgent` ooit wel `execute_tool()` gaan
   aanroepen, moet `user_id` eerst worden toegevoegd aan hun DI-keten (`get_agent_router`/
   `get_master_orchestrator` geven vandaag alleen `tenant_id` door) -- vastgelegd als
   voorwaarde, niet als taak van vandaag.

**Dit is een aanbeveling, geen eigen beslissing** -- Rakesh's keuze voor "initiator EN
Council" (SS7.1) was gebaseerd op de aanname van een crash-risico bij een levend pad.
Nu dat pad niet blijkt te bestaan, is de vraag of hij nog steeds de volledige
Council-implementatie wil (als architecturale consistentie/toekomstbestendigheid), of
dat een lichtere aanpak (alleen `KNOWN_UNGATED`-documentatie bijwerken met deze
bevinding, zoals bij een deel van OP-24's D5-traject) volstaat.

---

## 10. Implementatiestand (nagemeten 2026-09-01) -- dit vervangt SS4 en SS9.3

Dit document is op 2026-08-25 geschreven als ontwerpvoorstel en is daarna NOOIT bijgewerkt
toen het voorstel werd gebouwd. De koptekst zei tot 2026-09-01 nog steeds "geen
implementatie", terwijl commit `ded5b236` (2026-08-26, "feat(agents): OP-24 -- initiator-eis
+ Council-raadpleging op EnhancedBaseAgent") de volledige implementatie al bevatte. Wie
alleen SS1 t/m SS9 las, concludeerde dat OP-24 openstond. Deze sectie legt de gemeten stand
vast; SS1 t/m SS9 blijven ongewijzigd staan als besluitgeschiedenis.

### 10.1 Wat er daadwerkelijk in de code staat

Alle vijf onderstaande regels zijn nagemeten op 2026-09-01 op branch
`worktree-agent-a4bf751726d1f51a2` (afgeleid van `develop`), met de commando's eronder.

| Wat | Gemeten stand | Bewijs |
|---|---|---|
| Het veld uit SS3.1 | `self._initiated_by_user_id` (int of None, default None) | `src/core/agents/base_agent.py:93` |
| De check uit SS3.2 | Aanwezig, gevolgd door de Council-aanroep | `base_agent.py:396-447` |
| De noodschakelaar uit SS8.2 | `"enhanced_base_agent_initiator_check": False` | `src/core/shared/config.py:237` |
| `KNOWN_UNGATED` uit SS4/SS7.4 | `KNOWN_UNGATED: dict[str, str] = {}` -- leeg | `tests/architecture/test_agent_actions_pass_council.py:71` |
| Tests | 7 stuks | `tests/unit/agents/test_enhanced_base_agent_council_consultation.py` |

```bash
grep -n "_initiated_by_user_id\|enhanced_base_agent_initiator_check" src/core/agents/base_agent.py
grep -n "KNOWN_UNGATED" tests/architecture/test_agent_actions_pass_council.py
git log --oneline -1 -S enhanced_base_agent_initiator_check -- src/core/agents/base_agent.py
```

### 10.2 Welke uitspraken in SS1 t/m SS9 daarmee ACHTERHAALD zijn

- **SS4, bullet 2** ("Geen wijziging aan `KNOWN_UNGATED` ... zonder een echte
  `_council_rejection()`-aanroep zou de guard ROOD worden"): achterhaald. De guard is in
  `ded5b236` juist wel gewijzigd -- `COUNCIL_MARKERS` erkent nu ook de DIRECTE aanroep
  `request_council_decision_for_agent`, en `KNOWN_UNGATED` is daarna leeggemaakt. Dat is een
  derde weg die dit document in SS4 niet overwoog.
- **SS9.3, punten 1, 2 en 4**: uitgevoerd, geen aanbeveling meer. Punt 3 (het
  `ExecutorAgent`-gat apart registreren) is ook uitgevoerd: het staat als **OP-173** in
  `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`, STATUS=OPEN.
- **SS7.5, vragen 2, 3 en 4**: SS9.4 beantwoordde 2 en 3 al met "niet van toepassing zolang
  er geen levende aanroeper is". Vraag 4 (schakelmechanisme per klasse/tool) is NIET
  beantwoord maar wel omzeild: de feature-flag is proces-breed, niet per klasse of per tool.
  Dat is de enige beslissing uit SS7.5 die vandaag nog echt openstaat.
- **De ADR-036-registerrij OP-24** is wel bijgewerkt en staat op STATUS=GESLOTEN
  (GEVERIFIEERD=2026-08-26). De ADR en dit document spraken elkaar dus vijf dagen tegen.

### 10.3 Wat NOG STEEDS niet waar is, en dus niet uit deze sectie gelezen mag worden

- **Er draait vandaag niets van dit mechanisme.** De flag staat op `False` en er is geen
  aanroeper die hem aanzet. Elke bewering dat OP-24 "in productie afgedwongen wordt" is
  onjuist: gesloten betekent hier "geimplementeerd en getest", niet "actief".
- **De ~17-20 klassen zijn niet per stuk geauditeerd op een initiator-bron.** SS9.1 stelde
  vast dat geen van hen `execute_tool()` aanroept; dat maakt de audit vandaag overbodig,
  niet gedaan. Zodra een van die klassen de methode wel gaat aanroepen, komt open vraag 3
  terug -- inclusief het crash-risico uit SS7.1.
- **SS2's telling klopt niet met SS2's eigen voorbeeldkolom.** De rij "Directe
  `EnhancedBaseAgent`-subklassen" zegt 13 en noemt er 16. Nagemeten met een AST-scan over
  2242 bestanden in `src/` op 2026-09-01: 20 directe subklassen van `EnhancedBaseAgent`
  (waarvan er een `SymbioticAgent` zelf is, en waarvan 16 in `src/core/agents/` staan), 6
  directe subklassen van `SymbioticAgent`, 135 van `BaseSpecialistAgent`. De totalen "~17-20"
  en "alle 20 klassen" komen daarmee uit op 16 + 4; `ExternalAgentBridge`,
  `SchedulingVoiceAgent` en `SchedulingOrchestratorAgent` staan in SS2 in de rij "Overig"
  terwijl ze evengoed directe `EnhancedBaseAgent`-subklassen zijn. Ook de openingszin "28
  bestanden matchen" is vandaag 30. Zie het issue-register in
  `docs/backend/review/review-BE-SEC-048.md` (bevindingen M-1 en M-2).

---

## 11. Trainingssamenvatting

Twee flows, want het gedrag hangt volledig af van de feature-flag
`enhanced_base_agent_initiator_check` (`src/core/shared/config.py:237`, default `False`).
Flow 1 is wat er vandaag gebeurt; flow 2 is wat er gebeurt zodra de flag aangaat. Beide zijn
gemeten tegen `src/core/agents/base_agent.py:358-447`, niet overgenomen uit het
ontwerpvoorstel in SS3.

### Flow BE-SEC-048-FLW-001 -- flag UIT (de stand van vandaag)

- Actor: een subklasse van `EnhancedBaseAgent` (of van `SymbioticAgent`) die
  `self.execute_tool(tool_name, payload)` aanroept.
- Voorwaarde: er is een `ToolBroker` beschikbaar en
  `get_feature_flag("enhanced_base_agent_initiator_check")` geeft `False`.
- Actie (request): interne methodeaanroep, geen HTTP-endpoint. Parameters `tool_name: str`,
  `payload: dict[str, object]`, `timeout: int = 30`.
- Systeemverwerking: de D5-denylist-precheck
  (`ToolPermissionManager.is_denied(agent_id, tool_name)`) draait; de initiator- en
  Council-blokken worden OVERGESLAGEN; de aanroep gaat naar
  `broker.execute_tool(..., context={"tenant_id": self.tenant_id})`.
- Succesrespons: het resultaat van de broker (een dict), plus een `tool_executed`-event met
  `agent_id`, `tool_name`, `duration_seconds`, `success=True`.
- Foutrespons: `ToolExecutionException` als de tool op de denylist staat;
  `RuntimeError("ToolBroker not available")` als er geen broker is; elke andere fout uit de
  broker propageert na een `tool_failed`-event.
- Uitzonderingen: `_initiated_by_user_id` wordt NIET gecontroleerd. Een agent zonder
  verantwoordelijke mens kan in deze stand een toegestane tool uitvoeren -- dat is de
  bewuste, gedocumenteerde stand, niet een omissie (SS9.1: er is geen levende aanroeper).

### Flow BE-SEC-048-FLW-002 -- flag AAN (nog nergens geactiveerd)

- Actor: dezelfde aanroeper, plus de aanroepende laag die vooraf
  `agent._initiated_by_user_id` moet zetten op de `user_id` van de mens die de uitvoering
  startte.
- Voorwaarde: `get_feature_flag("enhanced_base_agent_initiator_check")` geeft `True`. Er is
  vandaag geen omgeving waarin dat zo is.
- Actie (request): identiek aan flow 1.
- Systeemverwerking: na de D5-precheck faalt de aanroep hard als `_initiated_by_user_id`
  `None` is -- VOOR er ook maar een `Proposal` wordt gebouwd, want `Proposal.__post_init__`
  gooit op `user_id<=0` (SS7.1). Anders volgt `request_council_decision_for_agent(...)` met
  `action_type=tool_name` en `action_params={"tool": ..., "arg_keys": sorted(payload)}`.
  Alleen de SLEUTELNAMEN van de payload gaan naar de Council (BE-AGT-043-patroon); de
  volledige payload gaat als `ticket_action_params` mee naar een eventueel HITL-ticket.
- Succesrespons: bij `DecisionVerdict.APPROVED` gaat de aanroep door naar de broker en is de
  respons gelijk aan flow 1.
- Foutrespons: `ToolExecutionException` met `error_detail="geen initiator bekend (AI Act
  art. 14)"` bij een ontbrekende initiator; `ToolExecutionException` met
  `"Council-verdict <verdict>: <explanation_for_user>"` bij elk niet-APPROVED verdict. Bij
  `HITL_REQUIRED` staat de referentie van het al aangemaakte ticket in de melding.
- Uitzonderingen: `MODIFIED` wordt geWEIGERD, niet uitgevoerd met de aangepaste parameters --
  anders zou de Council-controle juist omzeild worden. `HITL_REQUIRED` maakt geen eigen
  ticket aan: de gate doet dat al sinds ADR-036 OP-167. Er is geen schakelaar per klasse of
  per tool; de flag is proces-breed (open vraag 4 uit SS7.5).
