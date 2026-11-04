# BE-AGT-036: Echte skill-executie in DomainPackOrchestrator voor de piloot (AUDIT-009)

| Veld | Waarde |
| --- | --- |
| Feature ID | BE-AGT-036 |
| Type | AGT (agent-orchestratie / reliability) |
| ADR | ADR-036 D10 (bouwvolgorde stap 4), ADR-015 (ToolBroker), ADR-005 (tenant-safety) |
| Bevinding | AUDIT-009 (HIGH/P1) + pre-existing `tenant_id=0`-fallback (ADR-005) |
| Sprint | ADR-036 Fundament — Fase A, Dag 5 |
| Datum | 2026-07-30 |
| Status | Geïmplementeerd |

---

## 1. Probleem (her-verifieerd op HEAD, 2026-07-30)

`DomainPackOrchestrator._execute_step()` (`src/core/als/enterprise/packs.py:283-291`)
was een placeholder: letterlijk `await asyncio.sleep(0.01)` gevolgd door
`return ExecutionResult(task_id="t1", success=True)` — ongeacht `agent_id`,
`tenant_id` of `params`. De SLA-timeout, retry-logica en ROI-logging eromheen zijn
echt; alleen de kern ontbrak. Gevolg: de complete pack-executie-flow voerde feitelijk
niets uit maar rapporteerde succes, inclusief "succesvolle" ROI-regels in
`_run_single_step` — precies de stille-succes-zonde die het D10-piloot-harnas
onmogelijk maakte.

**Extra aandachtspunt (bij her-verificatie gevonden, niet in de originele audit):**
`_execute_single_agent` (`packs.py:177`) deed
`tenant_id_int = int(tenant_id_str) if tenant_id_str.isdigit() else 0` — een stille
`tenant_id=0`-fallback. Tenant 0 bestaat niet (ADR-005). Per de aangescherpte
pre-existing regel was deze fix verplicht onderdeel van deze dag.

Root cause: de orchestrator is ooit als scaffolding geschreven om de pack-flow te
kunnen testen; de placeholder is nooit vervangen.

## 2. Scope

**Binnen scope:**
- `_execute_step` voert de piloot-skill (`skillsgaptraining`) echt uit via de
  catalog-loader (`EnterpriseCatalogLoader.get_agent_instance`).
- Expliciete foutpaden, nooit stil succes: onbekende agent → `success=False`;
  catalog-agent zonder wiring → `success=False`; skill-exception of
  instantiatie-fout → `success=False` met echte `error_message`.
- Keuzepunt K1 (dag-4-erfenis), optie A: piloot-specifieke methode
  `SkillsGapTrainingSkill.execute_with_manifest_prompt()` die de
  manifest-`system_prompt` (met het TOOL_CALL-contract) wél aan de LLM meegeeft,
  zonder `BaseSpecialistAgent.orient()` voor alle 135 skills te wijzigen.
- `tenant_id=0`-fallback verwijderd: niet-numerieke tenant-string in het
  `_execute_single_agent`-pad geeft een expliciet error-resultaat.
- 11 unit-tests (rood → groen), waaronder 2 behavioral end-to-end tests via
  `run_pack` met ROI-verificatie.

**Buiten scope (bewust):**
- De overige 134 skills: geen executie-wiring. Zij falen expliciet ("unwired-agent")
  tot een latere sprint ze één voor één aansluit — geen tweede stille placeholder.
- `orient()` globaal aansluiten op `config["system_prompt"]` (K1 optie B): raakt het
  LLM-gedrag van alle 135 skills tegelijk (inclusief 134 stopgaps) —
  architectuurbeslissing voor Rakesh, geëscaleerd via de dag-4 brief.
- Broker-handlers voor 4 van de 5 profiel-tools (`query_hr_database`,
  `search_documents`, `generate_text`, `schedule_training`): die falen vandaag
  fail-closed met een expliciete fout in `result_data.errors` — zichtbaar, nooit
  gefilterd naar stil succes (dag-4 spec §2; D10-scope).
- Prana-governance in het pack-pad (`BaseSpecialistAgent._execute_task` doet
  budget-check + charge): niet vereist door de dag-5 brief; de ROI-logging in
  `_run_single_step` blijft het enige financiële spoor in dit pad.

## 3. Beslissingen

| # | Beslissing | Motivatie |
| --- | --- | --- |
| 1 | `_PILOT_WIRED_AGENT_IDS = frozenset({"skillsgaptraining"})` als expliciete wiring-lijst | Zelfde patroon als de tool-permissieprofielen (ADR-015): een skill komt pas op de lijst als zijn executiepad gebouwd én gereviewd is. Mechanisme generiek, rollout niet. |
| 2 | Onbekende agent én unwired agent zijn verschillende expliciete fouten (`unknown-agent` / `unwired-agent` task_id) | Een typo in een pack-step moet anders rapporteren dan een bekende-maar-nog-niet-aangesloten skill; beide fail-closed. |
| 3 | K1 optie A: manifest-prompt-pad op de piloot-skill, niet in `orient()` | De dag-4 dode-tekst-bevinding (`orient()` consumeert `config["system_prompt"]` nooit, `specialist_base.py:104-111`) betekent dat een echte LLM-aanroep het TOOL_CALL-formaat anders nooit ziet. De manifest-prompt bevat sinds dag 4 de eerlijke TOOL_CALL-instructie. Globaal `orient()` wijzigen (optie B) raakt alle 135 skills — STOP-voorwaarde. |
| 4 | Resolutie via `catalog.get_agent_instance()`, geen directe import | De catalog-loader is de bestaande instantiatieroute (validatie + skill-import); de orchestrator gebruikt die al voor pack-discovery. Geverifieerd: `_normalize_agent_key("SkillsGapTrainingAgent")` → `"skillsgaptraining"` → module `src.core.als.agents.skills.skillsgaptraining` → klasse `SkillsGapTrainingSkill`. |
| 5 | Niet-numerieke tenant = error-resultaat, geen raise | Het `_execute_single_agent`-pad rapporteert via status-dicts aan `execute_pack`; een error-dict maakt de fout zichtbaar in de rapportage (PARTIAL/FAILED) zonder de gather-flow te breken. |
| 6 | Lege pack-params → manifest-goal als task-context | De `hr.reskilling_engine` step heeft geen params; de manifest-goal is dan de eerlijke taakcontext. Nooit een gefabuleerde taakbeschrijving ("Never invent data", manifest-contract). |

## 4. Gevolgde flow (BE-FLW-053)

1. `run_pack` → `_run_single_step` (SLA-timeout `asyncio.wait_for` rond de stap).
2. `_execute_step(agent_id, tenant_id, params)`:
   - agent niet in catalog → `ExecutionResult(success=False, task_id="unknown-agent")`.
   - agent niet in `_PILOT_WIRED_AGENT_IDS` → `success=False, task_id="unwired-agent"`.
   - piloot: `catalog.get_agent_instance("skillsgaptraining", tenant_id)` instantieert
     `SkillsGapTrainingSkill` (manifest-config blijft leidend: `agent_id="skillsgaptraining"`,
     `allowed_tools` = 5 manifest-tools).
3. `execute_with_manifest_prompt(params)` (K1 optie A): LLM-call MET de
   manifest-`system_prompt` (TOOL_CALL-contract zichtbaar) → decision-string.
4. `act(decision)`: manifest-filter → `ToolBrokerService.execute_tool(agent_id="skillsgaptraining")`
   → permissieprofiel (dag 4) → dispatch; tools zonder handler falen closed en
   zichtbaar in `result_data.errors`.
5. Exception ergens in 2-4 → `ExecutionResult(success=False, error_message=str(exc))`.
6. Alleen bij `res.success`: `_run_single_step` logt ROI via `ROIService.log_execution`
   met het echte `task_id` van de skill — bij falen geen ROI-regel.

Legacy-pad (`execute_pack` → `_execute_with_retry` → `_execute_single_agent`):
niet-numerieke tenant-string → expliciet error-dict; numerieke string → `int` en
hetzelfde `_execute_step`-contract.

## 5. Pre-existing issues afgehandeld vandaag

| Issue | Afhandeling |
| --- | --- |
| `tenant_id=0`-fallback (`packs.py:177`, ADR-005) | **Opgelost** — expliciete fout bij niet-numerieke tenant; gepind door 2 unit-tests. |
| Placeholder-pinnende bestaande tests | **N.v.t. (geverifieerd):** grep op `_execute_step`/`DomainPackOrchestrator` over `tests/` toont dat alle bestaande tests de placeholder mocken (`tests/unit/als/enterprise/test_domain_packs.py`, `tests/unit/enterprise/test_domain_pack_orchestrator.py`) of geskipt zijn (`tests/e2e/test_fase3_domain_packs.py`, module-level skip). Geen enkele test pinde `task_id="t1"` of altijd-succes — er was dus niets te herschrijven. `tests/core/company/test_goal_alignment_wiring.py` gebruikt een andere orchestrator (`src.core.procedures.domain_pack_orchestrator`). |

## 6. Tests

| Test | Bestand | Type |
| --- | --- | --- |
| 1.1a Skill geïnstantieerd + aangeroepen, resultaat van skill | `tests/unit/als/enterprise/test_pack_orchestrator_execute_step.py` | unit |
| 1.1b Volledige keten met echte skill-klasse (LLM + broker aan de grens gemockt); LLM-call bevat manifest-`system_prompt` met TOOL_CALL | idem | unit (behavioral) |
| 1.2a Skill-exception → success=False + echte error_message | idem | unit (unhappy) |
| 1.2b Instantiatie-fout → success=False | idem | unit (unhappy) |
| 1.3a Onbekende agent faalt expliciet | idem | unit (unhappy) |
| 1.3b Bekende-maar-unwired skill faalt expliciet | idem | unit (unhappy) |
| 1.4a Skill krijgt tenant_id=1 als int | idem | unit |
| 1.4b Niet-numerieke tenant → expliciete fout, `_execute_step` niet aangeroepen | idem | unit (security, ADR-005) |
| 1.4c Numerieke tenant-string → int doorgegeven | idem | unit |
| 1.5a Behavioral: `run_pack` → ROI ziet echt resultaat (task_id, agent, tenant) | idem | unit (behavioral) |
| 1.5b Behavioral: gefaalde skill → geen succes-ROI-regel | idem | unit (behavioral, unhappy) |

Rood-groen bewijs: op HEAD faalden 10 van de 11 tests (1.1 t/m 1.5); alleen de
pin-test 1.4c (numerieke tenant) was al groen — dat gedrag bestond al.

Resultaten na de fix: 11/11 nieuw groen; 661 gerichte set (incl. dag 1-4
regressieset: tenant-cleanup x3, council agent_id, memory purge, tool_broker,
scripts-pinning); 390/390 architectuur-suite; 1260 passed op
copilot/council/service/als/agents-suites (1249 + 11 nieuwe); ruff clean;
pyright 0 errors; ASCII-scan clean.

## 7. Security (ADR-005, ADR-015)

- **Tenant-safety:** geen enkel pad produceert nog `tenant_id=0`; niet-numerieke
  tenants falen expliciet. De skill krijgt de tenant ongewijzigd als `int`.
- **Fail-closed:** onbekende agents, unwired skills, skill-exceptions en
  broker-fouten zijn allemaal zichtbaar in `ExecutionResult` — geen
  `try/except: pass`, geen `success=True` bij fouten.
- **Permissieketen intact:** `execute_tool` wordt aangeroepen met
  `agent_id="skillsgaptraining"` (manifest `skill_id`), zodat het dag-4 profiel
  geldt; 4/5 tools zonder handler falen closed en zichtbaar.
- **Prompt-injection:** pack-params komen uit vertrouwde pack-config
  (`config/domain_packs.yaml`), niet uit gebruikersinput.

## 8. Rollback

`git revert` van de dag-5 commit herstelt de placeholder. Er is geen migratie en
geen runtime-state afhankelijk van deze wijziging. Let op: rollback herstelt óók
de `tenant_id=0`-fallback (ADR-005-schending) — niet wenselijk.

## 9. Trainingssamenvatting

- Actor: Geauthenticeerde tenant-gebruiker of achtergrondproces dat een domain pack start
- Voorwaarde: Het pack bestaat in de catalog en de betrokken skill staat in
  `_PILOT_WIRED_AGENT_IDS`; de tenant-context is numeriek (geen `tenant_id=0`-fallback meer).
- Actie: `run_pack("hr.reskilling_engine")` (of `run_pack_by_id`) voert de
  pack-stappen uit via `_execute_step`.
- Systeemreactie: `_execute_step` resolveert de agent via de catalog, instantieert
  de echte skill en roept `execute_with_manifest_prompt()` aan, die de
  manifest-`system_prompt` met TOOL_CALL-contract aan de LLM meegeeft; tool-calls
  lopen via de broker met het permissieprofiel van de skill.
- Succesrespons: `ExecutionResult.success = True` met het echte skill-resultaat;
  ROI-logging wordt alleen dan geschreven.
- Foutrespons: Drie expliciete uitkomsten -- `unknown-agent` (niet in de catalog),
  `unwired-agent` (bekend maar niet aangesloten) en `error` (skill faalde). Geen
  van deze schrijft ROI-regels.
- Uitzonderingen: Stil succes bestaat niet meer in dit pad; een niet-numerieke
  tenant levert een expliciete fout in plaats van tenant 0 (ADR-005).

- Een pack-step activeren = skill op `_PILOT_WIRED_AGENT_IDS` in `packs.py` +
  een executiepad op de skill (zie `execute_with_manifest_prompt` als patroon) +
  rood-groen tests zoals dit bestand.
- `_execute_step` kent drie expliciete uitkomsten naast succes: `unknown-agent`,
  `unwired-agent`, `error` — stil succes bestaat niet meer in dit pad.
- ROI-logging is afhankelijk van `ExecutionResult.success`: een gebroken contract
  (succes bij falen) vertaalt zich direct in valse ROI-regels.
- De manifest-`system_prompt` wordt alleen geconsumeerd via het piloot-pad
  (K1 optie A); `orient()` gebruikt hem nog steeds niet (geëscaleerde
  architectuurkeuze voor alle 135 skills).

## 10. Referenties

- `src/core/als/enterprise/packs.py` (`_execute_step`, `_execute_single_agent`,
  `_PILOT_WIRED_AGENT_IDS`)
- `src/core/als/agents/skills/skillsgaptraining.py` (`execute_with_manifest_prompt`)
- `src/core/als/agents/loader.py` (`get_agent_instance`, ongewijzigd)
- `src/core/als/agents/specialist_base.py` (`act()`, ongewijzigd)
- `config/domain_packs.yaml` (`hr.reskilling_engine`, echte aanroeper)
- `tests/unit/als/enterprise/test_pack_orchestrator_execute_step.py`
- Audit: `docs/agent-briefs/generated/2026-07-03-audit-to-fix-adr036-fundament.md` (AUDIT-009)
- Voorganger: `docs/backend/features/BE-AGT-035-als-skill-tool-permissions.md` (dag 4)
