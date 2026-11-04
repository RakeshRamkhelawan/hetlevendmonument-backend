# BE-DSM-008 -- SP-DSM-002 Dag 4: governance.audit + database.* + services big batch (100->64)

## Context

ADR-033 vereist dat `router.py` bestanden nooit direct importeren uit: `database`, `governance`,
`learning`, `agents`, `workflow`, `llm`, `services`, `ml`, `als`, `semantic_router`, `copilot`.
Het fix-patroon is: move forbidden import naar domein's `dependencies.py` facade, re-export via
`__all__`, router importeert uitsluitend via de facade.

Dag 4 heeft 3 batches uitgevoerd met 100->64 violations (-36).

## Wijzigingen

### Batch A -- governance.audit facade (-14 violations)

**documents/dependencies.py**: `audit_service` toegevoegd + `__all__`  
**documents/crud_router.py**: governance.audit inline -> facade  
**documents/processing_router.py**: governance.audit inline (in async def body) -> facade top-level  
**documents/upload_router.py**: governance.audit inline -> facade top-level  
**tenant_management/dependencies.py**: `get_db`, `TenantFilterBypass`, `audit_service` + `__all__`  
**tenant_management/crud_router.py**: 3 directe imports -> tenant_management.dependencies  
**user_management/dependencies.py**: `TenantFilterBypass`, `audit_service` + `__all__`  
**user_management/crud_router.py**: 3 directe imports -> user_management.dependencies  
**user_management/profile_router.py**: 3 directe imports -> user_management.dependencies  

### Batch B -- services.rbac + admin volledig (-13 violations)

**rbac/dependencies.py**: `Permission`, `RBACService` + `__all__`  
**rbac/assignment_router.py + permissions_router.py + roles_router.py**: services.rbac_service -> rbac.dependencies  
**admin/dependencies.py**: complete uitbreiding met `RBACService`, `log_security_event`, `AuditLog`,
  `Experiment`, `ExperimentVariant`, `ExperimentService`, `get_db` + `__all__`  
**admin/users_router.py**: 3 directe imports (database.database, services.audit_service, services.rbac_service) -> admin.dependencies  
**admin/monitoring_router.py**: 2 directe imports (database.database, governance.models.AuditLog) -> admin.dependencies  
**admin/experiments.py**: 3 directe imports (database.database, database.models.experiment, services.experiment_service) -> admin.dependencies  

### Batch C -- database.database easy-wins (-9 violations)

**company/dependencies.py**: `DatabaseManager`, `get_db`, `ExperimentService` toegevoegd  
**company/board_router.py**: database.database -> company.dependencies (governance.policy_engine + copilot.* deferred)  
**company/external_agent_router.py**: database.database -> company.dependencies  
**company/onboarding_router.py**: database.database -> company.dependencies  
**company/pack_selector_router.py**: database.database + services.experiment_service -> company.dependencies  
**company/template_router.py**: database.database -> company.dependencies  
**health/dependencies.py**: `get_db` toegevoegd  
**health/checks_router.py**: database.database -> health.dependencies  
**copilot_intent/parse_router.py**: database.database -> copilot_intent.dependencies  
**experimentation/experiments_router.py**: database.database -> experimentation.dependencies  
**cva/conversations_router.py**: database.database + services.cva_service -> cva.dependencies  
**cva/management_router.py**: database.database + services.llm.service -> cva.dependencies  

### Architecture tests + ceiling

**tests/architecture/test_dsm_api_violations.py**: ceiling 100 -> 65 (actual 64)  
**tests/architecture/test_dsm002_groep_c_deferred.py**: xfail CI-anker voor cva/dependencies.py agents.*-koppeling  
**.importlinter**: 21 nieuwe facade-edges gedocumenteerd (Dag 4 sectie)  

## Kwaliteitsmaatregelen

- `no_implicit_reexport = true`: alle nieuwe dependencies.py re-exports via expliciete `__all__`
- `python -m pyright`: 0 errors voor en na elke batch (baseline: 0 errors)
- DSM-scanner eindtelling: 64 violations (doel was ~65)
- Architecture tests: 6 passed, 2 xfailed (beide xfails zijn verwachte CI-ankers voor pending ADR-beslissingen)

## Bekende deferred items (CI-anker aanwezig)

- `cva/dependencies.py`: `src.core.agents.ultimate_cva.system_prompt` -- scanner-blind-spot,
  xfail test in `test_dsm002_groep_c_deferred.py::test_cva_dependencies_agents_import_pending_adr`
- `company/board_router.py`: `governance.policy_engine` (line 58) + `copilot.council.metrics` (line 95) -- deferred naar Dag 5
- `admin/experiments.py`: `src.core.ml.monitoring` (line 577) -- lazy inline, deferred


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DSM-002 Dag 4: governance.audit + database.\* + services big batch (100->64 violations, -36) is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DSM-002 Dag 4: governance.audit + database.\* + services big batch (100->64 violations, -36).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
