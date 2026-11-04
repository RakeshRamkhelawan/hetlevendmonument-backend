# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-050
- Feature naam: `autonomous_breakthrough` blijft fail-secure blokkeren zonder een misleidende
  TODO of een halve HITL-ticket-workaround (ADR-036 OP-12/ADR031-001, fix-sprint dag 4)
- Status: GEBOUWD, wacht op review
- Auteur: Claude (sprint-uitvoering, ADR-036 fix-sprint Dag 4)
- Reviewer: onafhankelijke doc-reviewer-agent
- Datum: 2026-08-19
- Gerelateerde user story / ticket: ADR-036 fix-sprint, Dag 4
  (`docs/agent-briefs/generated/2026-08-19-sprint-dag-4.md`)
- Gerelateerde router / module: `src.core.agents.cva_autonomous_trigger`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: geen (deze fix voegt BEWUST GEEN `hitl_tickets`-rij toe)
- Versie: v1

---

## Doel en scope

### Doel

De oorspronkelijke ADR-036-audit (OP-12/ADR031-001) noemde de autonomieladder op
`autonomous_breakthrough` als ontbrekend, met als impliciete aanname dat dit codepad
levend en bereikbaar is. Exhaustief nagelopen vóór implementatie (bestand:regel-bewijs,
geen aanname): `_execute_breakthrough_session()`'s governance-blok draait alleen als
`self.oversight_gate is not None`, en de ENIGE constructieplek in de hele repo
(`cva_autonomous_trigger.py:1055` in de pre-fix bestandsversie, regel `1062` in de huidige
versie na de +7-regelverschuiving door deze fix; statement: `cva_trigger =
CVAAutonomousTrigger()`) geeft geen `oversight_gate` mee. De enige router die dit pad ooit
zou bereiken
(`src/core/api/cva_autonomous_endpoints.py`) is bevestigd dode code (2-regelig stub-bestand,
nooit gemount in het productiepad `src.main:app`). Geen scheduler, actor of startup-hook
triggert het automatisch.

**Correctie na de tweede blinde review (2026-08-19):** OP-12's eigen tweede aanwijzing
(`PolicyEngine.AGENT_ENTRYPOINT_ACTIONS` bevat `"autonomous_breakthrough"`) is GEEN tweede,
onafhankelijke route -- het is de vervolgstap van DEZELFDE keten. `OversightGate.check(
task_action=...)` (regel 292, alleen bereikbaar als `self.oversight_gate is not None`) geeft
`task_action` door aan `PolicyEngineAdapter.validate_action(action=task_action, ...)`
(`governance_helper.py`), die er een `ActionContext(action_name=action, ...)` van bouwt en
PAS DAN tegen `AGENT_ENTRYPOINT_ACTIONS` toetst. Er is dus EEN controlepunt dat de hele
keten aan/uit zet -- of `CVAAutonomousTrigger` een echte `oversight_gate` krijgt -- niet
twee onafhankelijke. (De eerdere formulering "repo-breed nul treffers voor
`action_name="autonomous_breakthrough"`" was zelf een tekst-grep die per definitie nul kon
opleveren, omdat nergens in `src/` een LETTERLIJKE `action_name=`-kwarg met die waarde
staat -- de daadwerkelijke waarde bereikt `ActionContext` altijd via de variabele
`action`/`task_action`, nooit als literal string op de aanroepplek.) Dit is dus vandaag
defense-in-depth, geen actieve-lek-fix, bewaakt door de nieuwe architecture-guard
`tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py` (zie sectie 17,
Acceptatiecriteria).

De `requires_human_approval`-tak had daarnaast een `# TODO: Submit to BoardService for
approval`-comment die impliceert dat er een goedkeuringsmechanisme in aanbouw is. Bij
onderzoek naar wat dat zou vereisen, bleek: `CVAAutonomousTrigger` heeft geen
tenant-context (het is een systeembrede, niet-tenant-gebonden trigger), terwijl
`hitl_tickets.tenant_id` `NOT NULL` is (ADR-005). Er bestaat geen schone "systeem-tenant"-
conventie in deze codebase -- twee andere diensten met precies dezelfde vraag
(`retention_cleanup.py`, `memory_purge_service.py`) kiezen allebei om GEEN tenant te
verzinnen voor een governance-relevante schrijfactie.

**Rakesh's expliciete beslissing (2026-08-19), na deze bevindingen te hebben voorgelegd
gekregen:** geen HITL-ticket bouwen op dit pad. Tenant_id nullable maken op `hitl_tickets`
wijkt af van ADR-005 en is geen dagbeslissing; `tenant_id=1` (Default Tenant) hergebruiken is
technische schuld die later governance/privacy-problemen geeft. In plaats daarvan blijft het
bestaande fail-secure gedrag (`return`, actie wordt gestopt) ONGEWIJZIGD, met een eerlijke
log-marker en comment die uitlegt WAAROM er geen ticket komt, in plaats van een TODO die
onterecht "nog te bouwen" impliceert.

### In scope

- `_execute_breakthrough_session()`'s `requires_human_approval`-tak (vóór de fix regel
  318-326, na de fix regel 318-333):
  log-marker `[APPROVAL_REQUIRED]` -> `[APPROVAL_REQUIRED_NO_TICKET]`; TODO-comment
  vervangen door een WHY-comment die de beslissing en de reden vastlegt.
- Nieuw testbestand dat de ECHTE methode direct aanroept (niet het generieke
  `apply_governance_check()`-patroon uit `test_a2_governance_all_paths.py`, dat de methode
  nooit aanroept en dus geen echte dekking geeft).
- Nieuwe architecture-guard (`tests/architecture/test_op12_autonomous_breakthrough_stays_
  unwired.py`) die de invariant bewaakt waar de OPEN-met-inert-bewijs-status van OP-12 op
  rust: de module-singleton krijgt geen `oversight_gate`, en niemand buiten dit bestand
  roept `start_autonomous_operation()`/`start_cva_autonomous()` aan.

### Out of scope

- Een systeem-breed HITL-mechanisme (bv. een eigen `system_hitl_tickets`-tabel) -- aparte,
  toekomstige architectuurbeslissing, alleen relevant als/wanneer dit pad ooit echt
  bereikbaar wordt EN er een tenant/eigenaarschap-concept voor CVA komt.
- Het BLOCKED-pad (`oversight_result.allowed is False`, regel 309-316) -- was al correct
  fail-closed, blijft ongewijzigd.
- `HITLTicketRepository.create_hitl_request()`/`IHITLRepository`-signaturen -- de
  oorspronkelijke plan-aanname dat `user_id: int -> int | None` nodig was, vervalt: er komt
  geen aanroep vanuit dit pad.
- Het onbereikbaar-zijn van dit pad zelf oplossen (de dode router weer aanzetten, of de
  singleton een echte gate geven) -- dat is een eigen, apart te wegen product/architectuur-
  beslissing, geen onderdeel van deze fix.

---

## Build summary

- Nieuw gebouwd: `tests/unit/agents/test_cva_breakthrough_fails_closed_without_ticket.py`
  (oorspronkelijk 3 tests; de tweede blinde review vond dat geen van de drie het
  daadwerkelijke NIET-uitvoeren bewees -- nu 4 tests, met `_run_cva_breakthrough` gemockt
  en `assert_not_called()` in de drie relevante tests) en
  `tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py` (2 tests, AST-
  gebaseerd, bewaakt de "pad is dood"-invariant zelf).
- Gewijzigd: `src/core/agents/cva_autonomous_trigger.py` (`git diff`: 9 toevoegingen /
  2 verwijderingen -- 1 marker-string-literal gewijzigd, 1 TODO-regel verwijderd, een
  8-regelige WHY-comment toegevoegd; geen gedragswijziging).
- Verwijderd: de misleidende `# TODO: Submit to BoardService for approval`-comment.
- Beinvloede bestaande flows: geen -- dit codepad is vandaag onbereikbaar in productie
  (zie Doel), dus geen enkele levende flow verandert van gedrag.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-050 | `_execute_breakthrough_session()` blijft fail-secure zonder ticket | BE-AGT (agent-gedrag) | `src/core/agents/cva_autonomous_trigger.py` | Wijziging | geen (n.v.t., geen HTTP/DB-flow) |

---

## Detaildocumentatie per artefact

## [BE-AGT-050] `_execute_breakthrough_session()` fail-secure zonder ticket

### 1. Type

- Agent-gedrag (interne methode van `CVAAutonomousTrigger`, geen HTTP-endpoint). Vandaag
  onbereikbaar in productie (zie Doel).

### 2. Locatie

- Bestandspad: `src/core/agents/cva_autonomous_trigger.py:318-333` (de volledige
  `requires_human_approval`-tak in de huidige bestandsversie: if-statement op 318,
  `logger.warning` op 319-321, de nieuwe WHY-comment op 322-329, de
  `_log_to_sandbox()`-aanroep met de hernoemde marker op 330-332, `return` op 333). Vóór
  deze fix liep dezelfde tak van regel 318 t/m 326.
- Klasse / functie: `CVAAutonomousTrigger._execute_breakthrough_session()`.

### 3. Gerelateerde flow

- Geen (n.v.t.) -- er is geen levende flow die dit pad vandaag bereikt.

### 4. Doel

- Een eerlijke, niet-misleidende log-regel en comment voor een codepad dat BEWUST geen
  goedkeuringsticket aanmaakt, in plaats van een TODO die onterecht "nog te bouwen" suggereert.

### 5. Functionele beschrijving

- Ongewijzigd extern gedrag: als `oversight_result.requires_human_approval` waar is, stopt de
  breakthrough-sessie (`return`), precies zoals voorheen. Het enige verschil is de tekst van
  de gelogde regel en een comment in de broncode.

### 6. Technische beschrijving

- `logger.warning(...)` (regel 319-321): ongewijzigd.
- `self._log_to_sandbox(...)` (regel 330-332 na de fix, direct voorafgegaan door de nieuwe
  WHY-comment op 322-329): marker gewijzigd van `[APPROVAL_REQUIRED]` naar
  `[APPROVAL_REQUIRED_NO_TICKET]`. Repo-breed gegrept op de bracket-vorm `[APPROVAL_REQUIRED]`
  (Gate 2 security-reviewer): dit is de enige plek waar deze exacte gelogde string voorkomt --
  de gelijknamige enum-waarden elders (`TaskStatus.APPROVAL_REQUIRED`,
  `IntelligenceLevel.APPROVAL_REQUIRED`, e.d.) zijn een ander formaat en ongerelateerd, dus de
  hernoeming is veilig.
- WHY-comment: legt de tenant_id/NOT NULL-reden vast en verwijst naar ADR-036 OP-12 en
  Rakesh's beslissing (2026-08-19).

### 7. Zichtbaarheids- en toegangsregels

- N.v.t. -- interne methode-aanroep, geen HTTP-laag.

### 8-16. n.v.t

Zuivere log/comment-wijziging op een vandaag-onbereikbaar codepad, geen eigen
request/response/validatie/business-rule/afhankelijkheid/transactie/caching-gedrag dat
verandert.

### 17. Acceptatiecriteria

- Alle vier de tests in `test_cva_breakthrough_fails_closed_without_ticket.py` slagen:
  - `test_no_hitl_ticket_is_created_when_approval_is_required` (geen ticketreferentie of
    "aangemaakt"-claim in de log, EN `_run_cva_breakthrough` niet aangeroepen)
  - `test_the_log_message_explains_why_no_ticket_exists_instead_of_a_todo` (nieuwe marker
    aanwezig -- ROOD voor de fix, GROEN na de fix, zelf mutatiegetest)
  - `test_blocked_path_is_unaffected_by_the_approval_path_fix` (regressie op het BLOCKED-pad,
    EN `_run_cva_breakthrough` niet aangeroepen)
  - `test_approval_required_actually_blocks_execution_not_just_the_log` (BLOCKER-1 uit de
    tweede blinde review: bewijst het GEDRAG direct, niet via de log-tekst -- de `return` op
    de approval-tak verwijderen liet de OORSPRONKELIJKE drie tests groen blijven terwijl
    `_run_cva_breakthrough()` en `_enable_cva_file_management()` echt draaiden, inclusief een
    echt geschreven bestand op disk; zelf gereproduceerd en herbevestigd)
- Alle DRIE tests in `tests/architecture/test_op12_autonomous_breakthrough_stays_
  unwired.py` slagen: `test_the_module_level_singleton_still_gets_no_oversight_gate`,
  `test_nothing_outside_the_module_starts_autonomous_operation` (nu ook
  `trigger_manual_breakthrough`/`trigger_manual_cva_breakthrough` in de functieverzameling,
  ook `__init__.py` en `scripts/` doorzocht -- ronde 2/3 van de blinde review), en
  `test_nothing_outside_the_module_imports_the_singleton_or_its_start_functions` (ronde 4:
  vangt referentie-doorgeven, alias-imports en private-methode-aanroepen op een
  geimporteerde `cva_trigger` via `ast.ImportFrom`; ronde 5: uitgebreid met een
  `ast.Import`-tak voor whole-module-imports (`import ...cva_autonomous_trigger as m`
  gevolgd door `m.cva_trigger._add_trigger(...)`), die de ronde-4-versie nog miste; ronde 6:
  de `ast.ImportFrom`-tak zelf uitgebreid met een check op `alias.name ==
  "cva_autonomous_trigger"` VOOR de module-string-filter, want een whole-module import kan
  OOK via `ast.ImportFrom` gespeld worden (`from src.core.agents import
  cva_autonomous_trigger as m`, of relatief `from . import cva_autonomous_trigger as m` --
  de laatste had `node.module is None`, wat de oude filter zelfs volledig blokkeerde). Met
  nu vier importvormen gedekt is het enige echte externe gebruik, `TriggerType` in
  `mode_manager.py`, nog steeds terecht ongeraakt. Elke test
  zelf mutatiegetest, telkens per genoemd element apart (zie de testdocstrings en de
  moduledocstring voor het volledige mutatie-overzicht).

### 18. Integratoruitleg

- N.v.t. -- geen publieke API-wijziging, geen nieuwe integratorverplichting.

### 19. Trainingssamenvatting

- **Actor:** Systeem (autonome CVA-trigger, geen menselijke aanroeper op dit pad vandaag).
- **Voorwaarde:** `oversight_gate` is gezet (vandaag alleen mogelijk via expliciete
  constructie met een echte gate, niet via de productie-singleton) EN de gate geeft
  `requires_human_approval=True` terug.
- **Actie:** De breakthrough-sessie wordt gestopt (`return`), een waarschuwing wordt gelogd.
- **Systeemreactie:** Geen tool-actie wordt uitgevoerd; geen HITL-ticket wordt aangemaakt;
  een duidelijke log-regel met marker `[APPROVAL_REQUIRED_NO_TICKET]` legt vast dat dit
  BEWUST is (geen tenant-context voor deze systeembrede trigger).
- **Succesrespons:** N.v.t. (dit IS het "succes"-pad: fail-secure blokkeren).
- **Foutrespons:** N.v.t.
- **Uitzonderingen:** Het BLOCKED-pad (`allowed=False`) is een aparte, ongewijzigde tak met
  zijn eigen marker (`[GOVERNANCE_BLOCKED]`).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- N.v.t. -- geen publieke API, geen frontend-impact.

---

## Open aannames

- Dat `cva_trigger`'s `oversight_gate` inderdaad nooit ergens anders gezet wordt (geverifieerd
  via repo-brede grep op `.oversight_gate\s*=`: 2 treffers, waarvan 1 de constructor van
  `CVAAutonomousTrigger` zelf is (`cva_autonomous_trigger.py:66`) en de andere een volledig
  ongerelateerde toewijzing in een ander agent-type betreft
  (`agent_registry.py:140`, `AgentRegistry.__init__`); en op `CVAAutonomousTrigger\(`: precies
  1 treffer, de module-singleton op regel 1062). Zou een toekomstige wijziging dit pad
  ALSNOG bereikbaar maken zonder deze spec te herzien, dan geldt de "fail-secure zonder
  ticket"-beslissing nog steeds correct (het blokkeert), maar de "dit is vandaag
  onbereikbaar"-framing in Doel zou dan achterhaald zijn.

## Open vragen

- Wanneer/of dit pad ooit een echt, systeem-breed HITL-mechanisme moet krijgen (aparte
  architectuurbeslissing, expliciet buiten scope van vandaag, zie Out of scope).

---

## Risico's

- Geen CRITICAL/HIGH. Dit is een comment- en log-string-wijziging op een vandaag dood
  codepad; Gate 2 (code-reviewer + security-reviewer) beiden GO, geen bevindingen die een
  wijziging vereisten. Mutatiebewijs bevestigt: de nieuwe marker-test wordt rood als de
  marker terugveranderd wordt naar de oude tekst, en groen op de shipped code.
- **Tweede blinde review (2026-08-19) vond 2 BLOCKER + 4 MINOR**, allemaal gefixt (zie
  `review-BE-AGT-050.md` sectie G voor het volledige verslag): het ontbreken van een directe
  gedragsassertie (BLOCKER-1, nu een vierde test), het ontbreken van een guard op de
  "pad is dood"-invariant zelf (BLOCKER-2, nu `test_op12_autonomous_breakthrough_stays_
  unwired.py`), en vier documentatie-precisiepunten.
- Gate-status (na alle fixes): gerichte set (impact-analyse Taak 0 + beide nieuwe/gewijzigde
  testbestanden + de register-guard) 88 passed / 3 xfailed / 0 failed; `tests/architecture/
  tests/unit/api/` 909 passed / 0 failed (was 907, +2 door de nieuwe register-guard);
  `python -m pyright` 0 errors (baseline ongewijzigd, 54 warnings); `python
  scripts/run_mypy_audit.py` 0/0; `ruff check` op alle vier gewijzigde/nieuwe bestanden
  (`cva_autonomous_trigger.py`, het testbestand, de nieuwe register-guard, en
  `test_adr036_register_is_parseable.py`): schoon.

---

## QA-checks

- [x] Endpoint functioneel getest -- n.v.t., geen HTTP-endpoint.
- [x] Alle foutstatus-codes getest -- n.v.t.
- [x] Auth en permissies getest -- n.v.t., geen externe aanroeper.
- [x] Tenant-isolatie getest -- n.v.t. (dit is precies de reden dat er GEEN tenant-gebonden
      artefact wordt aangemaakt).
- [x] Validaties getest -- n.v.t.
- [x] Edge cases getest -- BLOCKED-pad blijft ongewijzigd (regressietest).
- [x] Dataintegriteit en transacties getest -- n.v.t., geen DB-schrijfactie.
- [ ] Performance / load getest -- n.v.t.
- [ ] Caching getest -- n.v.t.
- [x] Logging en tracing gecontroleerd -- nieuwe marker geverifieerd uniek in de repo.

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle relevante bestanden geinventariseerd
- [x] Relevante "foutstatussen" (fail-secure pad) beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Trainingssamenvatting aanwezig
