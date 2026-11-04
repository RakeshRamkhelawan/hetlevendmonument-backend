# ADR-031 Addendum -- Fase 5 scopevoorstel: autonomieladder voor `cva_autonomous_trigger.py`

Status: SCOPEVOORSTEL -- geen ontwerpbeslissing. Vereist Rakesh's GO per gemarkeerd punt
voordat enige implementatie start.
Datum: 2026-08-25
Aanleiding: ADR-036 OP-12 (register-item, zie `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`)
Gerelateerd: ADR-031 SS "Migration Plan" (Fase 1-4, alle COMPLETED/gedefinieerd), ADR-031 SS2
"Autonomy ladder as deployment control" (L1-L4, conceptueel)

---

## 1. Waarom dit document bestaat

ADR-031 definieert de autonomieladder (L1 Assistant t/m L4 Autonomous Agent) als concept en
beschrijft een Migration Plan met Fase 1 t/m Fase 4 (allemaal COMPLETED of gedefinieerd). Er
is nergens een Fase 5 vastgelegd -- de naam kwam uitsluitend voor als kale placeholder in het
ADR-036 OP-12-register-item ("wire de autonomie-ladder in Fase 5"), zonder dat er ooit is
opgeschreven wat die fase concreet zou moeten bevatten.

Dat is problematisch omdat `src/core/agents/cva_autonomous_trigger.py` de enige plek in de
hele codebase is die een pad kan starten zonder mens in de lus
(`autonomous_breakthrough`-actie, zie ADR-036 OP-12). Die tak is vandaag bewust fail-closed:
`OversightGate.check()` wordt alleen aangeroepen als `self.oversight_gate is not None`
(regel 288-292), en de enige constructieplek in de repo
(`cva_trigger = CVAAutonomousTrigger()`, regel 1062) geeft die gate niet mee. Zolang niemand
weet WAT Fase 5 moet bevatten, kan niemand ooit veilig beoordelen of het geven van een echte
`oversight_gate` aan die singleton verantwoord is.

**Dit document raakt `cva_autonomous_trigger.py` niet.** Het fail-closed gedrag blijft exact
zoals het is; `tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py` blijft
ongewijzigd groen (bevestigd door de test te draaien zonder enige code-wijziging, zie SS6).

---

## 2. Wat Fase 5 concreet zou moeten bevatten

### 2.1 Autonomieniveau

`autonomous_breakthrough` claimt vandaag impliciet L4 (Autonomous Agent, "end-to-end
automation with rollback and continuous monitoring", ADR-031 SS2) simpelweg omdat er geen
mens in de lus zit -- niet omdat er ooit is vastgesteld dat de actie aan L4's eisen voldoet
(rollback-pad, continue monitoring). **Rakesh's GO nodig:** is L4 het juiste niveau voor deze
actie, of moet ze eerst als L3 (Controlled Agent, "low-risk bounded autonomy under strict
thresholds") draaien met een verplichte downgrade-naar-L2-optie zodra een drempel wordt
overschreden?

### 2.2 Wat "gewired" concreet betekent

Vandaag geeft `OversightGate.check()` een binaire uitkomst door aan
`PolicyEngineAdapter.validate_action()`: mag deze actie starten of niet, getoetst tegen
`AGENT_ENTRYPOINT_ACTIONS`. Een autonomieladder voegt daar een GETRAPTE begrenzing aan toe,
niet alleen een aan/uit-schakelaar. Concreet zou Fase 5 minimaal moeten vastleggen:

- **Budget-begrenzing per doorbraak**: een maximum aantal sub-acties, tokens of
  wall-clock-tijd per autonome sessie (analoog aan `SkillManifest.budget` dat de 135
  ALS-skills al hebben -- `max_steps`, `max_llm_calls`, `timeout_seconds`,
  `prana_cost_limit`, zie `src/core/als/agents/skill_manifest.py`). **Rakesh's GO nodig:**
  welke concrete getallen, en of dat budget per tenant instelbaar moet zijn.
- **Toegestane sub-acties (allowlist, niet denylist)**: welke tools/acties mag een autonome
  doorbraak-sessie zelf aanroepen zonder een nieuwe goedkeuring? Het bestaande
  `ToolPermissionManager`-profielmechanisme (ADR-015) is de voor de hand liggende basis,
  maar een L4-sessie die zichzelf mag opschalen naar een tweede tool is een ander risico dan
  een L2-Copilot-sessie die een mens per stap laat goedkeuren. **Rakesh's GO nodig:** een
  apart, striktere permissieprofiel voor autonome sessies, of hergebruik van het bestaande
  profiel van de aanroepende agent.
- **Tijdsbegrenzing en heartbeat**: een maximale sessieduur plus een verplichte
  "nog steeds actief"-melding (analoog aan de bestaande `COUNCIL_DELIBERATION_SECONDS`-metric
  en circuit-breaker-patronen in `src/core/copilot/council/coordinator.py`), zodat een
  hangende autonome sessie niet onbeperkt door blijft draaien.
- **`oversight_gate`-implementatie voor `CVAAutonomousTrigger`**: vandaag bestaat
  `OversightGate` (met `BREAKTHROUGH_ACTIONS` voor
  `code_generation`/`file_creation`/`database_migration`/`deployment`/`config_change`/
  `permission_change`) al en wordt elders wel degelijk gebruikt. Fase 5 moet vastleggen OF de
  bestaande `OversightGate`-klasse hergebruikt wordt met een aangepaste policy, of een
  aparte, autonomieladder-bewuste variant nodig is die de hierboven genoemde budget-/
  tijdsbegrenzing ook daadwerkelijk afdwingt (vandaag toetst `OversightGate` alleen de zes
  eindoperaties, geen budget/tijd).

### 2.3 Goedkeuringscriteria voor activatie

ADR-031 SS2 stelt al een generieke eis: "No surface may move to a higher level without
explicit approval criteria: eval suite pass, red-team pass, observability coverage, rollback
path, and owner sign-off." Voor `autonomous_breakthrough` specifiek zou dat minimaal moeten
betekenen:

- Een evaluatieset die het gedrag van de autonome sessie test onder de budget-/
  tijdsbegrenzing uit SS2.2 (analoog aan de bestaande evaluatiesets voor ALS-piloot-skills).
- Een rollback-pad: als een autonome sessie een fout sub-resultaat produceert, hoe wordt dat
  teruggedraaid? Dit raakt de zes `BREAKTHROUGH_ACTIONS` rechtstreeks
  (`code_generation`/`file_creation`/`database_migration`/`deployment`/`config_change`/
  `permission_change` zijn allemaal potentieel destructief).
- Observability: minimaal een audit-trail per sub-actie binnen de sessie (niet alleen een
  audit-regel voor de sessie als geheel), zodat een postmortem elke stap kan herleiden.
- **Rakesh's GO nodig op alle vier bovenstaande punten**, plus op de vraag OF een
  feature-flag (uit staat in productie) de voorkeur heeft over volledig wegblijven van de
  wiring totdat alle vier klaar zijn -- de bestaande OP-12-registerrij noemt beide opties
  zonder tussen ze te kiezen.

### 2.4 tenant_id-vraagstuk (blokkerend voor elke HITL-variant)

Rakesh's beslissing van 2026-08-19 (vastgelegd in het OP-12-register-item) benoemt een
concrete technische blokkade: een HITL-ticket voor deze actie zou een `tenant_id` vereisen
die `CVAAutonomousTrigger` niet heeft, tegen de `hitl_tickets.tenant_id NOT NULL`-constraint
(ADR-005) aan. Fase 5 moet dit expliciet oplossen voordat een L2/L3-variant met menselijke
tussenkomst ooit mogelijk is: **Rakesh's GO nodig** op of `CVAAutonomousTrigger` een
tenant-context krijgt (en zo ja, waar die vandaan komt -- de aanroeper heeft mogelijk zelf
geen HTTP-requestcontext), of dat deze actie principieel nooit een per-tenant HITL-ticket
kan krijgen en dus alleen als L3/L4 (geen ticket, wel budget/tijd/allowlist-begrenzing) kan
draaien.

---

## 3. Wat NIET in Fase 5 hoort (scope-afgrenzing)

- **Geen wijziging aan de zes `OversightGate.BREAKTHROUGH_ACTIONS`-eindoperaties.** Die
  blijven de laatste verdedigingslinie, ongeacht wat de autonomieladder verder toevoegt.
- **Geen wijziging aan de ShadowCEO-veto** (ADR-016). De autonomieladder is een aanvullende
  begrenzing, geen vervanging van bestaande vetolagen.
- **Geen wijziging aan `PolicyEngine.AGENT_ENTRYPOINT_ACTIONS`.** Dat blijft de bestaande
  aan/uit-lijst; de autonomieladder voegt een GETRAPTE laag toe binnen "aan", niet een
  vervanging van de lijst zelf.

---

## 4. Openstaande beslissingen (samenvatting voor Rakesh)

| # | Beslissing | Waar in dit document |
|---|---|---|
| 1 | L3 (bounded) of L4 (end-to-end) als startniveau voor `autonomous_breakthrough`? | SS2.1 |
| 2 | Concrete budget-getallen (max sub-acties/tokens/tijd) en per-tenant instelbaarheid? | SS2.2 |
| 3 | Apart permissieprofiel voor autonome sessies, of hergebruik van de aanroeper's profiel? | SS2.2 |
| 4 | Hergebruik bestaande `OversightGate`-klasse (aangepast), of nieuwe autonomieladder-variant? | SS2.2 |
| 5 | Feature-flag (uit in productie) vs. volledig wegblijven van wiring tot alle criteria klaar zijn? | SS2.3 |
| 6 | Tenant-context voor `CVAAutonomousTrigger`: waar vandaan, of principieel nooit een HITL-variant? | SS2.4 |

Zonder deze zes beslissingen is er geen implementeerbaar Fase 5-plan -- dit document is
uitdrukkelijk een scopevoorstel, geen ontwerp.

---

## 5. Verificatie dat dit document geen gedrag wijzigt

```bash
python -m pytest tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py -v
```

Verwacht: ongewijzigd groen, zonder dat dit document of enige productiecode is aangepast --
dit is uitsluitend een documentatie-artefact.

---

*Zie ook: `docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md` OP-12,
`docs/backend/features/BE-GOV-022-entrypoint-action-classification.md` par. Restrisico.*

---

## 6. Addendum 2026-08-25 -- correctie op een extern AI-rapport, gegrond in bestaande code

Een extern AI-rapport (niet dit systeem, aangeleverd door Rakesh ter beoordeling) deed
concrete voorstellen voor de zes SS4-beslissingen, met verzonnen getallen (euro's,
tokens) die niet aansluiten bij dit project se bestaande budgetsysteem, en een antwoord
op SS2.4 (tenant_id) dat de eigenlijke architecturale blokkade niet oploste. Onderstaand
de daadwerkelijk gemeten feiten, ter vervanging van die aannames. Dit blijven nog steeds
Rakesh's beslissingen -- dit addendum verandert de vraag niet, wel het feitenkader
waarop hij beslist.

### 6.1 SS2.4 (tenant_id) -- een echt architecturaal antwoord, geen ontwijking

Het externe rapport stelde: "elke achtergrondtaak moet de tenant_id in de payload
meekrijgen." Dat beantwoordt niet HOE, want `CVAAutonomousTrigger` is een
module-level singleton (`cva_trigger = CVAAutonomousTrigger()`,
`src/core/agents/cva_autonomous_trigger.py:1062`) zonder tenant-context bij constructie.
Gemeten aanroepketen: `trigger_manual_cva_breakthrough(reason)` (regel 1080-1084) ->
`trigger_manual_breakthrough(reason)` (regel 962-966) -> `_add_trigger(...)` ->
`_execute_breakthrough_session(trigger)` (regel 288-345) -> `oversight_gate.check(...)`
zonder `tenant_id` (dus `None`). De code-comment op regel 322-329 bevestigt Rakesh's
eerdere beslissing (2026-08-19): fail-secure blokkeren in plaats van een verzonnen
tenant_id gebruiken.

**Het bestaande, al gebruikte patroon voor precies dit probleem:** een gedeelde
service-instantie die `tenant_id` per AANROEP krijgt, niet bij constructie.
`OversightGate.check()` zelf doet dit al
(`src/core/governance/oversight_gate.py:108-118`, `tenant_id: int | None = None` als
methode-parameter, niet in de constructor). Hetzelfde patroon zit in
`PranaGuard.check_budget(self, tenant_id, ...)` (`src/core/governance/prana_guard.py:22`)
en `BudgetManager.check_budget(self, tenant_id, agent_id, ...)`
(`src/core/agents/budget_manager.py:164-170`). De grondige, in de codebase al bewezen
oplossing is dus: **`trigger_manual_breakthrough(reason: str, tenant_id: int | None = None)`**
uitbreiden met een `tenant_id`-parameter die door de hele keten naar
`oversight_gate.check()` wordt doorgegeven -- geen nieuw patroon, een bestaand patroon
toepassen op deze ene singleton. Dit lost SS2.4 niet automatisch op (WAAR de aanroeper
die tenant_id vandaan haalt bij een systeembrede trigger blijft een echte vraag), maar
geeft wel een concreet, gegrond mechanisme in plaats van een hand-wave.

### 6.2 SS2.2 (budgetgetallen) -- prana, geen euro's

Het externe rapport noemde "max 10 stappen, 50.000 tokens, 120 seconden, EUR 0,50 per
run" zonder enige verwijzing naar het bestaande budgetsysteem. Gemeten: dit project kent
GEEN euro- of token-gebaseerd sessiebudget op agent-niveau. Het bestaande stelsel is
Prana (`src/core/governance/prana_guard.py`, `PranaGuard.check_budget()`/`charge_prana()`
tegen `Tenant.prana_budget`/`Tenant.prana_spent`, ADR-021). `SkillManifest.budget`
(`src/core/als/agents/skill_manifest.py:33-36`) is de bestaande, per-sessie analogie:
`max_steps=8, max_llm_calls=5, timeout_seconds=60, prana_cost_limit=100`. Grep over alle
145 skill-manifest-YAML's bevestigt: **elke ALS-skill gebruikt exact dezelfde
`prana_cost_limit: 100`**, zonder uitzondering -- er is geen "zwaardere" bestaande skill
om een hoger budget aan op te hangen.

Een autonome breakthrough-sessie omvat per definitie meerdere skill-achtige stappen, dus
een gegrond uitgangspunt is een expliciet VEELVOUD van deze bestaande 100-eenheid (bv.
"N x 100 prana", met `max_steps`/`timeout_seconds` in dezelfde orde van grootte als
`SkillBudget`'s defaults, niet in een nieuw, ongerelateerd euro-stelsel). **De concrete
waarde van N blijft Rakesh's beslissing** -- dit addendum stelt geen getal vast, het
stelt vast in welke eenheid en tegen welke bestaande referentie die beslissing genomen
moet worden.

Nevenbevinding: `BudgetManager` (`src/core/agents/budget_manager.py:138-449`) is een
TWEEDE, apart budgetsysteem dat wel in tokens/USD werkt (`max_tokens_per_hour`,
`max_cost_per_hour: Decimal`) -- geen omrekening tussen dit en Prana gevonden. Welk van
de twee systemen een autonome breakthrough-sessie moet gebruiken (of allebei, voor
verschillende doeleinden) is een zevende, nieuwe open vraag die het externe rapport niet
signaleerde.

### 6.3 SS2.2 (OversightGate) -- bevestigd, geen tijd/budgetveld vandaag

Gemeten, niet aangenomen: `OversightGate.check()` (`oversight_gate.py:108-118`) en
`OversightResult` (regel 23-37: alleen `allowed`, `requires_human_approval`,
`risk_level`, `reason`) bevatten geen enkel tijd- of budgetveld, geen
`datetime`/`timedelta`/prana-referentie in het hele bestand. `BREAKTHROUGH_ACTIONS`
(regel 84-91) is een hardcoded ja/nee-set op actienaam. De addendum-claim dat een
budget-bewuste variant nodig is (SS2.2, punt 4) wordt hiermee bevestigd, niet ontkracht.

### 6.4 SS2.3 (feature-flag) -- gecorrigeerd naar de conventie die hier al geldt

Het externe rapport stelde `ENABLE_AUTONOMOUS_BREAKTHROUGH` (een losse env-var), naar
analogie van `src/core/config/production_config.py`. Gemeten: dat bestand ligt niet naast
`cva_autonomous_trigger.py`. De conventie die WEL in dezelfde map geldt (zusterbestanden
`base_agent.py`, `cva_agent.py`, `ethics_agent.py`, `ml_ethics_agent.py`) is het
`FEATURE_FLAGS`-dict-patroon via `get_feature_flag()`
(`src/core/shared/config.py:171-235`, met automatische env-override
`FEATURE_<NAAM>` indien gewenst). `cva_autonomous_trigger.py` zelf heeft vandaag geen
`FEATURE_FLAGS`-koppeling. Gegronde aanbeveling: een nieuwe key in `FEATURE_FLAGS` (bv.
`"autonomous_breakthrough"`), uitgelezen via `get_feature_flag("autonomous_breakthrough")`
-- consistent met de zusterbestanden, niet een nieuw, op zichzelf staand env-var-patroon.

### 6.5 Wat dit addendum NIET doet

Dit lost SS2.1 (L3/L4), SS2.2 punt "apart permissieprofiel of hergebruik", en de
concrete N-waarde uit SS6.2 niet op -- dat blijven Rakesh's beleidsbeslissingen. Het
addendum vervangt alleen de ONGEGRONDE onderbouwing van het externe rapport door
geverifieerde feiten, zodat die beslissingen op een correct fundament genomen worden.

---

## 7. Addendum 2026-08-26 -- tweede extern rapport: juridische verificatie + nieuwe CVA-gaten

Een TWEEDE extern AI-rapport (aangeleverd door Rakesh, andere sessie dan SS6) deed
aanvullende claims over `cva_autonomous_trigger.py` en citeerde specifieke AI Act-
artikelen (art. 14 lid 4, art. 12) als onderbouwing. Op verzoek van Rakesh is dit
onafhankelijk geverifieerd: de codeclaims via twee blinde code-review-agents, de
juridische claims tegen de officiele artikeltekst via WebSearch/WebFetch. Resultaat:
de codeclaims van dit tweede rapport waren grotendeels correct (in tegenstelling tot
het eerste rapport in SS6); de juridische citaten waren correct qua artikelnummer, maar
een implicatie in het rapport (SHA-256-hashketen als wettelijke eis) is overstated.

### 7.1 Juridische verificatie (bron: artificialintelligenceact.eu, geraadpleegd 2026-08-26)

**Art. 14 lid 4(e) -- kill-switch: CORRECT GECITEERD.** De officiele tekst eist dat een
hoog-risico AI-systeem de deployer in staat stelt "in te grijpen via een 'stop'-knop of
vergelijkbare procedure die het systeem veilig tot stilstand kan brengen." Dit geldt
voor ALLE hoog-risico AI-systemen (geen uitzondering voor achtergrondprocessen), niet
alleen voor de biometrische-identificatie-categorie uit lid 5. Het externe rapport se
claim dat `stop_cva_autonomous()` los staat van een centrale alert-/noodstop-koppeling
is dus een legitieme AI Act-observatie, GEGEVEN dat dit systeem zichzelf al elders (de
HR-Annex-III-classificaties, OP-144/OP-165) als hoog-risico AI-systeem behandelt. Bron:
[Article 14: Human Oversight](https://artificialintelligenceact.eu/article/14/).

**Art. 12 -- logging: artikelnummer correct, maar de hashketen-framing is OVERSTATED.**
De officiele tekst (lid 1) eist dat een hoog-risico AI-systeem "technisch de automatische
registratie van gebeurtenissen (logs) mogelijk maakt gedurende de levensduur van het
systeem" -- een vereiste dat logging TECHNISCH MOGELIJK is, met traceerbaarheid als doel
(lid 2). **De wettekst noemt nergens een cryptografische beveiliging, hashketen of
immutability-eis.** Dat is dit project se EIGEN keuze (ADR-019, SHA-256-hashketen), niet
een AI Act-mandaat. Conclusie: `_log_to_sandbox()` (platte tekst naar een lokaal
bestand, `cva_autonomous_trigger.py:940-946`) voldoet WEL aan de kale Art.-12-lid-1-eis
(er wordt automatisch gelogd), maar niet aan dit project se EIGEN, zwaardere
ADR-019-standaard voor tenant-gescheiden, tamper-evident audit-logging. Het gat is dus
reeel en de moeite waard om te dichten, maar het moet benoemd worden als een
**interne-consistentie-gat (project-standaard)**, niet als "overtreedt art. 12" --
die laatste framing zou zelf weer een onbewezen juridische claim zijn, exact het patroon
waar dit project al meerdere keren op gebrand is (zie OP-27/OP-33 in ADR-036). Bron:
[Article 12: Record-Keeping](https://artificialintelligenceact.eu/article/12/).

### 7.2 Nieuwe CVA-gaten, bevestigd door onafhankelijke code-review (2026-08-26)

Onderstaande claims uit het tweede rapport zijn met bestand:regel-bewijs bevestigd en
vullen SS2 (Wat Fase 5 concreet zou moeten bevatten) aan:

- **`TriggerEvent` heeft geen `tenant_id`-veld.** `cva_autonomous_trigger.py:42-48`:
  exact de velden `trigger_type`, `priority`, `trigger_data`, `timestamp`, `processed`
  -- bevestigt de architecturale keten-blokkade uit SS6.1 nog concreter: zelfs als
  `trigger_manual_breakthrough()` een `tenant_id`-parameter krijgt (SS6.1's voorstel),
  moet die ook door `TriggerEvent` heen kunnen, en dat veld bestaat nog niet.
- **Budget-tracking ontbreekt, met een nuance.** `performance_metrics` heeft 4 sleutels
  (`total_triggers`, `successful_breakthroughs`, `system_uptime`, `last_innovation_time`),
  niet de 2 die het rapport noemde -- maar `total_triggers` en `system_uptime` zijn dode
  code (nooit opgehoogd, geverifieerd met grep). De kern van de claim klopt onverkort:
  `max_steps`/`max_llm_calls`/`timeout_seconds`/`prana_cost_limit` komen NUL keer voor in
  dit bestand.
- **`_log_to_sandbox()` bevestigd** (regel 940-946): schrijft platte tekst naar een lokaal
  `sandboxlog.md`-bestand. `_execute_breakthrough_session()` (regel 277-371, de volledige
  breakthrough-flow) logt UITSLUITEND via deze functie -- nul referenties naar
  `tool_audit_logs`/`AuditService`/`compute_audit_hash` in dit bestand.
- **`stop_cva_autonomous()` is een geisoleerde wrapper** (regel 1070-1072) zonder externe
  aanroepers (repo-brede grep: alleen het eigen `__main__`-blok). `AlertManager`
  (`src/core/governance/alert_manager.py`) bestaat al en wordt elders actief gebruikt
  (`compliance_guardian.py`, `app_lifespan.py`, `alert_notification_bridge.py`); het
  WebSocket-pad `/ws/copilot/signals` bestaat echt (`api/copilot_websocket_endpoints.py`).
  Een koppeling zou dus een BESTAAND patroon hergebruiken, geen nieuw concept.

### 7.3 Correctie op een "100% COMPLIANT"-tabel uit hetzelfde rapport (ADR-036-scope, niet Fase 5, hier vastgelegd voor de volledigheid)

Het tweede rapport bevatte ook een compliance-tabel die ADR-036-items citeerde met het
verkeerde OP-nummer en een overstated claim -- vastgelegd hier omdat het rapport OP-12
en OP-24 in dezelfde adem noemde. Zie `.claude/WORKING-CONTEXT.md` voor de correctie:
"OP-164 gesloten (ALWAYS_HITL_ACTIONS)" verwart OP-164 (een apart, nog OPEN item over
`agent_id: unknown` in `/hitl/pending`) met **OP-166** (het daadwerkelijk gesloten
`ALWAYS_HITL_ACTIONS`-mechanisme, `coordinator.py:71-81`, 7 acties gevuld). En
"`query_hr_database` verwijderd" is overstated: de tool bestaat nog volledig
(`hr_registry.py:67`), alleen de toegang van 4 agents is beperkt (uit hun
`allowed_tools` gehaald) -- data-minimalisatie via scoping, niet via verwijdering.

### 7.4 Wat dit addendum NIET doet

Dit stelt niet vast OF `autonomous_breakthrough` formeel onder een Annex III-categorie
valt (dat is elders in het project al impliciet aangenomen via de bredere HR/Annex-III-
classificaties, niet hier apart heronderzocht). Het stelt geen kill-switch-mechanisme of
audit-migratie voor -- dat blijft onderdeel van de zes SS4-beslissingen (met name #4,
OversightGate-variant) zodra Rakesh die neemt.

---

## 8. Addendum 2026-08-26 -- Rakesh's beslissing SS2.4 (tenant_id) + vier dag-1-taken

**Belangrijke aanvulling van Rakesh:** dit platform is niet uitsluitend SaaS multi-tenant
-- het ondersteunt ook een gedocumenteerde single-tenant-multi-user-modus
(`docs/adr/035-single-tenant-deployment-mode.md`, schakelaar `DEPLOYMENT_MODE` in
`src/config.py:15-18`). De tenant-resolutie-oplossing voor SS2.4 moet in BEIDE modi
correct zijn, niet alleen in SaaS.

### 8.1 SS2.4 (tenant_id) -- BESLIST: hergebruik de bestaande DEPLOYMENT_MODE-resolutie, geen nieuwe sentinel

Onderzoek (code-review, bestand:regel-bewijs) wees een risico uit in het eerder
overwogen idee van een vaste "systeem-tenant"-sentinelwaarde: `tenant_id=0` wordt op
sommige plekken informeel als "systeem" gebruikt (`activepieces/client.py:155`,
`middleware/audit_middleware.py:311`), maar tientallen ANDERE plekken behandelen
`tenant_id<=0` expliciet als ONGELDIG (`als/enterprise/packs.py:241`: "no silent
tenant_id=0 fallback", plus `base_agent.py`, `tenant_context.py`,
`governance_contract.py`, `tool_broker/service.py`). Een nieuwe sentinel zou dus
bestaande validatie-guards kunnen breken. Daarnaast bestaat er al een ANDERE
systeem-tenant-conventie (`_SYSTEM_TENANT_ID = 1` in
`src/workers/workflow_worker.py:479`), die in single-tenant-modus TOEVALLIG samenvalt
met de echte, enige klant-tenant (die krijgt via DB-auto-increment altijd id=1,
bevestigd `database/seed.py:147` + ADR-035 regel 22/40/63/93) -- weer een ANDERE
sentinel toevoegen zou de verwarring vergroten, niet verminderen.

**Beslissing: geen nieuwe sentinel. Hergebruik het bestaande, per-modus mechanisme:**

- **In `single_tenant`-modus:** `tenant_context.py:20-21` zet vandaag AL automatisch
  `tenant_id=1` zodra `DEPLOYMENT_MODE=single_tenant`. `trigger_manual_breakthrough()`
  moet dezelfde resolutie aanroepen (bv. `get_tenant_id()`/dezelfde helper) in plaats
  van een eigen fallback te verzinnen. In deze modus is er precies EEN tenant, dus de
  autonome sessie handelt terecht namens die ene tenant -- een mens bij DIE tenant kan
  het HITL-ticket zien en beoordelen.
- **In `saas`-modus:** er is geen enkele veilige, correcte tenant_id om te raden --
  `autonomous_breakthrough` is hier daadwerkelijk systeembreed en tenant-loos. Rakesh's
  bestaande beslissing (2026-08-19, ongewijzigd, bevestigd juist door dit onderzoek):
  fail-closed blijven, geen ticket, geen sentinel-waarde. Dit is dus GEEN gat meer dat
  nog een oplossing nodig heeft in SaaS-modus -- het is de correcte, blijvende toestand
  totdat er een echte tenant-bron ontstaat (bv. een tenant-specifieke trigger-oorzaak
  i.p.v. een systeembrede monitor).

**Concrete wijziging aan de call chain (SS6.1's mechanisme, nu compleet):**
`trigger_manual_breakthrough(reason: str, tenant_id: int | None = None)` ->
`TriggerEvent` krijgt een `tenant_id: int | None`-veld -> `_execute_breakthrough_session()`
geeft `tenant_id` door aan `oversight_gate.check(...)`. Bij `tenant_id is None` EN
`DEPLOYMENT_MODE == "saas"`: fail-closed (ongewijzigd gedrag). Bij `tenant_id is None`
EN `DEPLOYMENT_MODE == "single_tenant"`: resolve via de bestaande
`tenant_context.py`-fallback voordat er iets anders gebeurt.

### 8.2 Vier dag-1-taken (uit Rakesh's "wat ontbreekt er"-lijst, NIET gegate op SS4 #1/#2/#3)

Deze vier zijn onafhankelijk van de nog openstaande SS4-beslissingen #1 (L3/L4), #2
(exacte prana-multiplier -- zie 8.2.3 voor een voorstel), #3 (apart permissieprofiel) en
kunnen daarom als een echte implementatiedag ingepland worden:

1. **Tenant-resolutie** (SS8.1 hierboven): call-chain-wijziging + DEPLOYMENT_MODE-check.
2. **OversightGate-initialisatie:** de singleton-constructieplek
   (`cva_trigger = CVAAutonomousTrigger()`, regel 1062) krijgt een echte
   `oversight_gate`-instantie mee. `OversightGate.check()` neemt `tenant_id` al per
   aanroep (niet bij constructie, `oversight_gate.py:108-118`), dus de gate zelf blijft
   probleemloos een gedeelde instantie -- geen multi-tenant-conflict.
3. **ADR-019-logging-integratie:** `_log_to_sandbox()` (regel 940-946) aanvullen met een
   echte schrijf naar de audit-keten (`AuditService`/`tool_audit_logs`), naast of in
   plaats van de platte-tekst-sandbox-log. Puur een interne-consistentie-fix (SS7.1) --
   geen AI Act-vereiste, wel dit project se eigen ADR-019-standaard.
4. **Prana-budget-wiring (voorstel voor SS4 #2, geen definitief getal):** een echte
   `PranaGuard.check_budget()`-aanroep toevoegen aan `_execute_breakthrough_session()`.
   Concreet voorstel als startpunt: **300 prana per sessie (3x de bestaande
   `SkillManifest`-default van 100)**, omdat een breakthrough-sessie per definitie
   meerdere skill-achtige stappen omvat. Dit is een voorstel, geen vaststaand getal --
   Rakesh kan dit op elk moment bijstellen zonder de wiring zelf te hoeven aanpassen
   (de multiplier wordt een configuratiewaarde, geen hardcoded constante).

Feature-flag (SS2.3/SS6.4, ongewijzigd advies): nieuwe key `"autonomous_breakthrough"`
in `FEATURE_FLAGS`, uitgelezen via `get_feature_flag()` -- staat DEFAULT UIT, dus deze
vier taken veranderen niets aan het huidige, inerte productiegedrag totdat de flag
expliciet aan wordt gezet.

### 8.3 Wat nog steeds openstaat (ongewijzigd)

SS4 #1 (L3 vs L4 als startniveau) en #3 (apart permissieprofiel voor autonome sessies,
of hergebruik van de aanroeper's profiel) blijven Rakesh's beleidsbeslissingen, los van
de vier dag-1-taken hierboven.

### 8.4 Implementatie GESLOTEN (2026-08-26)

Alle vier dag-1-taken zijn geimplementeerd, met een verplichte onafhankelijke blinde
review vooraf (twee fouten gevonden en gecorrigeerd voordat er code werd geschreven,
zie het implementatieplan) en Gate 2 (code-reviewer + quality-reviewer, beiden GO) op
de gevoeligste stap (Fix 2, de guard-chirurgie).

- **Fix 1 (tenant-resolutie):** `TriggerEvent.tenant_id`, `trigger_manual_breakthrough(tenant_id=...)`,
  en een nieuwe `resolve_single_tenant_fallback_id()` in `tenant_context.py` (met
  correctie: de oorspronkelijk voorgestelde `get_tenant_id()`-hergebruik was een
  naamval -- die functie leest alleen de ContextVar, geen fallback).
- **Fix 2 (OversightGate-initialisatie):** de module-singleton krijgt nu een echte
  `OversightGate(policy_engine=PolicyEngineAdapter(), audit_service=AuditServiceAdapter())`.
  De 7-ronde-guard-test `test_the_module_level_singleton_still_gets_no_oversight_gate`
  is bewust vervangen (met uitleg in de moduledocstring); de twee overige guards blijven
  ongewijzigd de inertie bewijzen, zelf mutatiegetest in beide richtingen na de wijziging.
- **Fix 3 (ADR-019-logging):** `_check_governance_and_audit()` +
  `_write_breakthrough_audit_log()`, met een tijdens implementatie zelf gevonden en
  opgeloste bug (`AuditServiceAdapter.log_security_event()` geeft nooit een `db`-sessie
  mee, dus die functie slaat de databaseschrijf stilzwijgend over -- CVAAutonomousTrigger
  schrijft daarom zelf, direct, met een echte sessie).
- **Fix 4 (Prana-budget):** `_check_prana_budget()` + `_charge_prana_for_breakthrough()`,
  met `AUTONOMOUS_BREAKTHROUGH_PRANA_COST = 300` als configuratiewaarde (voorstel, 3x de
  SkillManifest-default, geen vaststaand getal).
- **Taak 5 (feature-flag):** nieuwe `FEATURE_FLAGS["autonomous_breakthrough"]` (default
  False), afgedwongen in `_add_trigger()` -- elke trigger wordt geweigerd zolang de vlag
  uit staat, mutatiegetest in beide richtingen (flag aan laat een trigger wel degelijk
  door).

**Twee tijdens implementatie zelf gevonden en gefixte bugs (niet in het oorspronkelijke
plan):** (1) een `best_effort`-blok dat de sessie-opening zelf niet dekte, waardoor een
`session_factory()`-fout de governance-beslissing ten onrechte blokkeerde in plaats van
alleen de audit-log over te slaan; (2) meerdere unit-tests die stilzwijgend een echte,
gedeelde testdatabase (`sanskritisetu_test_db:5455`) raakten omdat de Prana-/audit-calls
niet als losse, mockbare instantiemethoden waren opgezet -- opgelost door
`_check_prana_budget()`/`_charge_prana_for_breakthrough()`/`_write_breakthrough_audit_log()`
als aparte methoden te maken, zelfde patroon overal toegepast.

Volledige regressie: `tests/unit/agents/` 507 passed, 0 failed. Gerichte OP-12-tests
(7 testbestanden, 23 tests) allemaal rood-voor-groen bewezen. `python -m pyright`/
`python -m mypy` op alle gewijzigde bestanden: 0 errors.
