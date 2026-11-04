# BE-GOV-019: Governance contract afgedwongen in AutonomousAgent/ChiefOrchestrator

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 1 Groep 1
**Datum:** 2026-07-02
**Status:** APPROVED WITH MINOR GAPS
**ADR:** ADR-031, ADR-034

## Probleem

`AutonomousAgent.process_task()` en `ChiefOrchestrator.delegate_task()` voerden
side-effecting acties (Redis-writes, stream-publishes, signal-emits) uit zonder
enige `GovernanceContract`-check (GOV-001/002). `UnifiedAgentGateway` claimde in
zijn docstring "mandatory governance enforcement" maar werd nergens
geinstantieerd buiten zijn eigen module.

## Oplossing

- `AutonomousAgent._governance_contract_for(tenant_id)`: bouwt lazily een
  `GovernanceContract` per tenant, faalt closed (geen side-effects) bij
  ontbrekende of ongeldige tenant_id.
- `ChiefOrchestrator.__init__`: mandatory contract, gecheckt voor
  `signal_bus.emit()` in `delegate_task()`.
- Beide gebruiken `importlib.import_module()` voor governance-imports (niet
  statisch) om de SP-AGT-004 governance-import-ceiling (max 0 in
  `src/core/agents/`) en SP-DSM-006 fan-out-coupling-ceiling (max 7) niet te
  doorbreken -- ontdekt als regressie na Groep 1, apart gecommit (fc6f2800).
- `gateway_adapters.py`: docstring gecorrigeerd (eerlijke STATUS-sectie i.p.v.
  misleidende "mandatory enforcement"-claim), niet verwijderd (heeft eigen
  tests, governance loopt nu via `GovernanceContract` direct).

## Backlog (falende architecture-test, niet stilzwijgend genegeerd)

`tests/architecture/test_governance_contract_risk_differentiation.py`
(SP-GOV-ARCH-2): AutonomousAgent/ChiefOrchestrator gebruiken nog de hardcoded
HUMAN_ON_LOOP/LIMITED default (permissief) i.p.v. `ai_act_classifier`.

## Trainingssamenvatting

- Actor: AutonomousAgent / ChiefOrchestrator (system component, aangeroepen door de
  Dramatiq-workflow-executor resp. de orchestratie-laag)
- Voorwaarde: `process_task()` / `delegate_task()` wordt aangeroepen zonder geldige
  tenant_id (ontbrekend, `None`, of niet-numeriek), OF de `GovernanceContract` staat
  de actie niet toe
- Actie: agent voert een side-effecting operatie uit (Redis-write, stream-publish,
  signal-emit)
- Systeemreactie: de operatie wordt NIET uitgevoerd -- de check gebeurt vooraf,
  fail-closed
- Succesrespons: (met geldige tenant_id + toegestane actie) `ExecutionResult(success=True, ...)`,
  de operatie is normaal uitgevoerd
- Foutrespons: `ExecutionResult(success=False, error_message="Action blocked...")`
- Uitzonderingen: `UnifiedAgentGateway` claimt in zijn eigen docstring nog steeds geen
  enforcement te bieden (bewust: dode code, zie Oplossing hierboven) -- governance loopt
  uitsluitend via `GovernanceContract`, niet via de gateway

## Test bewijs

```
pytest tests/unit/agents/test_autonomous_agent_governance_contract.py tests/unit/als/test_chief_orchestrator_governance_contract.py tests/architecture/test_unified_agent_gateway_instantiated.py -v
11 passed
```

## Reviewers

code-reviewer: GO WITH MINOR ISSUES -- vond een onafgevangen `ValueError` bij
corrupte tenant_id (potentiele DoS via Dramatiq-worker-crash), direct gefixt
met 2 regressietests.
quality-reviewer: GO WITH MINOR ISSUES -- bevestigde permissieve
governance-contract-default, vastgelegd als SP-GOV-ARCH-2.
