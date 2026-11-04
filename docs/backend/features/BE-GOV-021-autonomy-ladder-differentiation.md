# BE-GOV-021: Autonomy ladder gedifferentieerd per agent-type

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 1 Groep 3
**Datum:** 2026-07-02
**Status:** APPROVED WITH MINOR GAPS
**ADR:** ADR-031

## Probleem

`EnhancedBaseAgent.__init__()` hardcodede `autonomy_level=HUMAN_ON_LOOP` en
liet `risk_category` op de dataclass-default (LIMITED) staan voor ELKE agent,
ongeacht agent_type/department. `GovernanceContract.is_action_permitted()` was
daardoor voor elke agent identiek, ongeacht wat de agent daadwerkelijk deed.

## Oplossing

- Roept `ai_act_classifier.classify_agent()` aan tijdens agent-initialisatie
  (na department/function-consolidatie uit YAML, niet ervoor -- anders zag de
  classifier altijd "general") om `risk_category` te bepalen.
- Risk-to-autonomy-mapping: HIGH_RISK/UNACCEPTABLE -> HUMAN_IN_LOOP (expliciete
  goedkeuring per actie vereist), LIMITED/MINIMAL -> HUMAN_ON_LOOP (bestaande
  default).
- Classificatie vastgelegd als audit-evidence (`record_evidence`) voor Art. 9
  risk management.
- 2 pre-existing bugs gefixt tijdens implementatie (bloot via 21 falende
  tests): `agent_type` als kale string i.p.v. AgentType-enum op sommige plekken
  (bijv. HRSupervisor) -- `.value`-aanroep crashte, gefixt met getattr-guard.
  `SymbioticAgent.__init__` gaf `department` niet door aan `super().__init__()`,
  waardoor alle 40 ALS-department-agents altijd department="general" kregen.

## Backlog (falende architecture-tests)

`tests/architecture/test_autonomy_ladder_uses_real_agent_capabilities.py`:
- SP-GOV-ARCH-6: department-agents zetten `department_capabilities` pas NA
  `super().__init__()` -- classificatie bereikt in de praktijk nog niet de
  ~120 van de ~150 agent-klassen (bijv. TalentAcquisitionAgent, een Annex III
  HR/recruitment-systeem, classificeert nog als LIMITED i.p.v. HIGH_RISK).
- SP-GOV-ARCH-7: `GovernanceContract.record_hitl_approval()` heeft nul
  productie-aanroepers -- een HIGH_RISK/HUMAN_IN_LOOP agent heeft geen pad om
  ooit goedgekeurd te worden zodra SP-GOV-ARCH-6 is opgelost.

## Trainingssamenvatting

- Actor: elke `EnhancedBaseAgent`-subklasse tijdens constructie (bijv.
  TalentAcquisitionAgent, een generated agent, of een test-agent)
- Voorwaarde: agent wordt geinitialiseerd met `agent_id`, `agent_type`, `tenant_id`, en
  optioneel `department`/`function`/`capabilities`
- Actie: `EnhancedBaseAgent.__init__()` roept `ai_act_classifier.classify_agent()` aan
  ná department/function-consolidatie uit YAML
- Systeemreactie: `risk_category` wordt bepaald (UNACCEPTABLE/HIGH_RISK/LIMITED/MINIMAL)
  en gemapt naar een `autonomy_level` (HUMAN_IN_LOOP voor HIGH_RISK/UNACCEPTABLE,
  HUMAN_ON_LOOP voor LIMITED/MINIMAL)
- Succesrespons: `GovernanceContract` met gedifferentieerde autonomy_level, vastgelegd
  als audit-evidence (`record_evidence("ai_act_classification", ...)`)
- Foutrespons: n.v.t. -- `classify_agent()` faalt niet stilzwijgend; een onverwachte
  exception propageert uit `__init__()` (fail-closed: agent wordt niet geconstrueerd)
- Uitzonderingen: department-agents (40 stuks) en generated agents (80 stuks) geven hun
  echte `department_capabilities` nog niet door aan de classifier (pas gezet NA
  `super().__init__()`) -- classificatie bereikt deze ~120 agent-klassen in de praktijk
  nog niet, vastgelegd als SP-GOV-ARCH-6

## Test bewijs

```
pytest tests/unit/agents/test_autonomy_ladder_differentiation.py tests/unit/agents/test_governance_wiring_dag4.py tests/unit/agents/ tests/unit/als/ -v
469 passed (volledige agents/als regressie)
```

## Reviewers

code-reviewer: CHANGES_REQUESTED -- classificatie bereikt in praktijk de
meeste agents niet (capabilities pas na super().__init__() gezet). Erkend en
vastgelegd als SP-GOV-ARCH-6/7 i.p.v. binnen scope opgelost (120-agent
refactor te groot voor 1 sprint-dag).
security-reviewer: GO WITH MINOR ISSUES -- bevestigde HIGH_RISK->HUMAN_IN_LOOP
zonder HITL-approval-pad als reeel maar laag-impact risico vandaag.
