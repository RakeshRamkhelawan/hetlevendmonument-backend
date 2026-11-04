# BE-AGT-035: Permissieprofiel ALS-piloot-skill skillsgaptraining (AUDIT-008)

| Veld | Waarde |
| --- | --- |
| Feature ID | BE-AGT-035 |
| Type | AGT (agent-configuratie / security) |
| ADR | ADR-015 (ToolBroker allowlist), ADR-036 §1.2.Q / D10 |
| Bevinding | AUDIT-008 (HIGH/P1) |
| Sprint | ADR-036 Fundament — Fase A, Dag 4 |
| Datum | 2026-07-30 |
| Status | Geïmplementeerd |

---

## 1. Probleem (geverifieerd op HEAD, 2026-07-30)

`config/tool_permissions.yml` bevatte exact 1 agent-profiel (`copilot`). 0 van de 135
ALS-skill-ID's had een eigen profiel, dus elke `TOOL_CALL:`-poging van een skill wordt
door `ToolPermissionManager.is_tool_allowed()` default-deny geweigerd (ADR-015,
`permission_manager.py:106-108`). Dit werd gemaskeerd door een system-prompt-stopgap
in alle 135 skill-manifests ("without attempting a TOOL_CALL", commit `33b4dd8c`),
die skill-executie eerlijk tekst-only hield maar tool-executie structureel onmogelijk
maakte — een blokkade voor D10 Fase 1-2 (de piloot-skill kan zijn gap-analyse niet
verder brengen dan tekstgeneratie) en voor AUDIT-009 (dag 5: de echte
orchestrator-aanroep zou alsnog op default-deny stuklopen).

## 2. Scope

**Binnen scope:**
- Eén permissieprofiel: de piloot-skill `skillsgaptraining`, met een `allowed_tools`
  die exact overeenkomt met de manifest-declaratie (least privilege).
- Verwijdering van de system-prompt-stopgap uit uitsluitend
  `src/core/als/agents/skills/manifests/skillsgaptraining.yml`, vervangen door een
  eerlijke instructie die het TOOL_CALL-formaat en de allowlist-grens benoemt.
- Een architecture-test die de invariant structureel bewaakt (preventie-maatregel
  uit het audit-to-fix plan, regel 316).
- Unit-tests (rood → groen) inclusief een behavioral end-to-end test via
  `BaseSpecialistAgent.act()`.

**Buiten scope (bewust):**
- De overige 134 skills: geen profielen, geen stopgap-wijzigingen. Zij blijven op de
  veilige stopgap tot een latere sprint ze één voor één aansluit (plan-regel 278).
- `ToolPermissionManager` zelf: default-deny is de gewenste staat voor profile-loze
  skills en blijft ongewijzigd.
- Broker-handlers voor de gedeclareerde tools: `query_hr_database`,
  `search_documents`, `generate_text` en `schedule_training` hebben vandaag geen
  handler in `ToolBrokerService` (die faalt daar closed met een duidelijke fout);
  `send_notification` en de task-tools bestaan wel. Handlers implementeren is
  D10/AUDIT-009-scope, niet van deze dag.
- `DomainPackOrchestrator._execute_step` (placeholder) — dat is AUDIT-009, dag 5.

## 3. Beslissingen

| # | Beslissing | Motivatie |
| --- | --- | --- |
| 1 | Profiel `allowed_tools` == manifest `allowed_tools` (exact, 5 tools) | Least privilege (ADR-015): de broker mag nooit meer toestaan dan de skill zelf declareert. Het manifest is de single source of truth voor wat de skill nodig heeft. |
| 2 | Stopgap alleen verwijderd uit het pilot-manifest | De stopgap is de enige barrière voor skills zonder profiel; generiek verwijderen zou 134 skills zonder profiel aan TOOL_CALL-pogingen blootstellen. |
| 3 | Stopgap vervangen door een eerlijke TOOL_CALL-instructie | Het manifest is de gedeclareerde source of truth van de skill-prompt; een profiel zónder passende prompt-instructie maakt de verleende permissies onbruikbaar. |
| 4 | Architecture-test toetst de invariant, niet de huidige toestand | Regel: stopgap verwijderd ⇔ profiel aanwezig ⇔ manifest bestaat; plus profiel ⊆ manifest (least privilege). De test was op HEAD vacuo groen (alle 135 manifests hadden de stopgap, 0 skills hadden een profiel — consistent) en wordt actief zodra iemand een stopgap verwijdert zonder profiel. |
| 5 | `max_tools: 10` voor het pilot-profiel | Voldoende marge boven de 5 gedeclareerde tools; ver onder de copilot-uitzondering (50). |

### Per-tool beargumentatie (least privilege)

| Tool | Waarom nodig voor gap-analyse |
| --- | --- |
| `query_hr_database` | Leest medewerker-/functiedata voor de gap-inventarisatie (tenant-scoped via broker-context). |
| `search_documents` | Vindt trainingsmateriaal en beleidsdocumenten. |
| `generate_text` | Stelt het gepersonaliseerde trainingsadvies samen. |
| `send_notification` | Informeert medewerker/manager over het advies. |
| `schedule_training` | Plant de geadviseerde trainingsmomenten. |

Geen write/exec-tools buiten deze vijf; geen wildcards; `denied_tools` leeg (de
default-deny dekt alles wat niet expliciet is toegestaan).

## 4. Gevolgde flow (BE-FLW-052)

1. LLM-output van de skill bevat `TOOL_CALL: tool_name {params}`.
2. `BaseSpecialistAgent._parse_tool_calls()` filtert op het manifest-niveau
   `allowed_tools` (niet-leeg ⇒ fail-closed voor niet-gedeclareerde tools).
3. `BaseSpecialistAgent.act()` roept `ToolBrokerService.execute_tool(...,
   agent_id="skillsgaptraining")` aan.
4. `ToolPermissionManager.is_tool_allowed("skillsgaptraining", tool)` slaat nu toe
   voor de 5 gedeclareerde tools (voorheen: default-deny).
5. Broker-dispatch: tools zonder handler falen closed met een expliciete fout
   (geen security-issue; handlers zijn dag-5+/D10-scope).

Voor de 134 skills zonder profiel verandert er niets: stap 1 wordt door hun stopgap
niet bereikt, en mocht het LLM toch een TOOL_CALL emitten, dan grijpt stap 4 alsnog
default-deny in.

## 5. Bevindingen tijdens implementatie (pre-existing)

**Dode tekst: het manifest-`system_prompt` wordt nooit geconsumeerd.**
`SkillManifest.to_config()` levert `config["system_prompt"]`, maar geen enkele
consument leest die sleutel: `BaseSpecialistAgent.orient()` bouwt zijn eigen prompt
uit `config["name"]`, `config["description"]` en `allowed_tools`
(`specialist_base.py:104-111`). De stopgap-tekst in alle 135 manifests is dus vandaag
dode tekst; de daadwerkelijke bescherming was en is de broker default-deny plus het
feit dat de `orient()`-prompt het TOOL_CALL-formaat nooit toont.

- **Impact op deze fix:** geen — de beveiligingspostuur hangt niet af van de
  manifest-tekst. De stopgap-verwijdering blijft correct (het manifest is de
  gedeclareerde source of truth; dag 5 heeft correcte tekst nodig bij echte
  executie) en de architecture-test bewaakt de invariant op manifest-niveau.
- **Afhandeling:** NIET opgelost in deze sprint-dag. Het aansluiten van
  `config["system_prompt"]` in `orient()` verandert het LLM-gedrag van álle 135
  skills tegelijk (waaronder 134 stopgaps) — dat is een architectuur-beslissing die
  bij AUDIT-009/D10 hoort, niet bij AUDIT-008. Geëscaleerd naar Rakesh via de
  final-approver brief en meegegeven als input aan de dag-5 brief.

## 6. Tests

| Test | Bestand | Type |
| --- | --- | --- |
| 1.1 Profiel bestaat + == manifest-declaratie | `tests/unit/tool_broker/test_skillsgaptraining_tool_permissions.py` | unit |
| 1.2 Default-deny pin voor profile-loze skills (security) | idem | unit |
| 1.3 Gedeclareerde tools toegestaan | idem | unit |
| 1.4 Niet-gedeclareerde tools geweigerd (security) | idem | unit |
| 1.5 Stopgap weg bij piloot, behouden bij anderen | idem | unit |
| 1.6 Behavioral: `act()` → `execute_tool(agent_id="skillsgaptraining")` + permissielaag laat door | idem | unit (behavioral) |
| Agent-level filter blokkeert niet-gedeclareerde tool vóór de broker (security) | idem | unit (behavioral) |
| Arch: stopgap weg ⇒ profiel vereist | `tests/architecture/test_als_skills_tool_permissions.py` | architectuur |
| Arch: profiel ⇒ manifest + geen stopgap + profiel ⊆ manifest | idem | architectuur |

Rood-groen bewijs: op HEAD faalden 1.1, 1.3, 1.5 en 1.6 (1.6 faalde exact op de
permissie-assert; de act()-routing zelf werkte al). Pins 1.2, 1.4 en de
agent-level-block-test waren op HEAD al groen — dat is de bewuste default-deny-staat.

Resultaten na de fix: 9/9 nieuw groen; 96 gerichte set; 390/390 architectuur-suite
(388 + 2 nieuwe); 1249 passed op copilot/council/service/als/agents-suites;
ruff clean; pyright 0/0; ASCII-scan clean; beide YAML-bestanden valide.

## 7. Security (ADR-015)

- Default-deny voor profile-loze agents: ongewijzigd en gepind (test 1.2).
- Agent-level filter: het pilot-manifest heeft een niet-lege `allowed_tools`, dus het
  fail-open-gat voor lege lijsten (`_parse_tool_calls`, gedocumenteerd in
  AGENTIC-E2E-AUDIT-2026-07-04 §675) is voor deze skill niet van toepassing; gepind
  met een eigen behavioral test.
- Dubbele verdediging: manifest-filter (agent-level) én broker-profiel staan nu
  beide fail-closed voor niet-gedeclareerde tools.
- Tenant-scoping: ongewijzigd; `execute_tool` krijgt `context={"tenant_id": ...}`
  vanuit de agent (`specialist_base.py:255`).

## 8. Rollback

`git revert` van de dag-4 commit herstelt de stopgap in het manifest en verwijdert
het profiel; de architecture-test blijft dan groen (consistente toestand). Er is
geen migratie en geen runtime-state afhankelijk van deze wijziging.

## 9. Trainingssamenvatting

- Actor: ALS-piloot-skill `skillsgaptraining` die namens een tenant een tool wil aanroepen
- Voorwaarde: het skill-manifest declareert `allowed_tools`, er staat een
  permissieprofiel voor dezelfde `agent_id` in `config/tool_permissions.yml`, en de
  system-prompt-stopgap is uit dat manifest verwijderd.
- Actie: de skill produceert een `TOOL_CALL:`-directive in zijn LLM-antwoord.
- Systeemreactie: `act()` filtert eerst tegen het manifest, daarna toetst de
  `ToolPermissionManager` het profiel op `agent_id`, waarna de broker dispatcht --
  elke laag faalt closed.
- Succesrespons: de tool wordt uitgevoerd en het resultaat gaat terug naar de skill.
- Foutrespons: staat de tool niet in het manifest of niet in het profiel, dan wordt de
  aanroep geweigerd (default-deny per ADR-015) zonder de tool te raken.
- Uitzonderingen: een tool zonder handler faalt closed in de broker -- een
  permissieprofiel impliceert geen bestaande implementatie. De overige 134 skills houden
  hun stopgap tot ze hun eigen profiel krijgen; de architecture-test bewaakt die
  invariant.

- ADR-015 default-deny geldt per `agent_id`; skills gebruiken hun eigen skill-ID
  (`manifest.skill_id`), niet `copilot`.
- Een skill activeren voor tool-executie = profiel in `config/tool_permissions.yml`
  (allowed_tools == manifest) + stopgap uit het manifest + de architecture-test
  houdt de invariant `stopgap ⇔ geen profiel` structureel vast.
- De broker faalt closed op tools zonder handler — een permissieprofiel impliceert
  geen bestaande implementatie; handlers zijn aparte scope.
- Het manifest-`system_prompt` is vandaag dode tekst in de runtime (zie §5); de
  actieve bescherming is de permissielaag, niet de prompt.

## 10. Referenties

- `config/tool_permissions.yml` (profiel + header-comment)
- `src/core/als/agents/skills/manifests/skillsgaptraining.yml` (stopgap verwijderd)
- `src/core/tool_broker/permission_manager.py` (default-deny, ongewijzigd)
- `src/core/als/agents/specialist_base.py` (`act()`, `_parse_tool_calls`, ongewijzigd)
- `tests/unit/tool_broker/test_skillsgaptraining_tool_permissions.py`
- `tests/architecture/test_als_skills_tool_permissions.py`
- Audit: `docs/agent-briefs/generated/2026-07-03-audit-to-fix-adr036-fundament.md` (AUDIT-008)
- Pre-existing context: `docs/reports/AGENTIC-E2E-AUDIT-2026-07-04.md` (§38, §675)
