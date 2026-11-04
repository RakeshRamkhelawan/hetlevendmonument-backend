# BE-DSM-018: SP-DSM-007 Dag 1 -- DSM grensschendingen + TID252 opgelost

**Sprint**: SP-DSM-007 Dag 1
**Datum**: 2026-06-18
**ADR**: ADR-034 (agent_runtime boundary), ADR-033 (import-linter contracts)

## Samenvatting

Vier bevestigde DSM grensschendingen gefixd en 13 TID252 (parent-relative import) suppressors verwijderd. Grade B fan-out gap (1) gesloten via copilot/dependencies.py migratie.

## Wijzigingen

### Fix 1: infra -> core_api (container.py)

**Probleem**: `src/core/container.py` (infra, I=0.11) importeerde `src.core.api.ai_features_endpoints` (core_api, I=0.99) -- SDP-schending + circulaire dep.

**Oplossing**: Directe imports naar `src.core.ai.*` zonder API-stub tussenlaag. Dead try/except verwijderd (beide branches waren identiek). NOTE-commentaar toegevoegd voor pre-existing async patroon (providers.Factory + async factory).

### Fix 2: domain_pack -> core_api (batch_evaluation_service.py)

**Probleem**: `src/core/evaluation/batch_evaluation_service.py` importeerde response-schemas uit de API-laag.

**Oplossing**:
- Nieuw bestand: `src/core/evaluation/schemas.py` (5 response-schemas)
- `src/core/api/schemas/evaluation_schemas.py` -> expliciete re-export shim (`from X import Y as Y`)
- `batch_evaluation_service.py` importeert nu uit `src.core.evaluation.schemas`

### Fix 3: agent_runtime -> core_api (copilot/council/factory.py)

**Probleem**: `_PranaAdapter.has_budget` importeerde `get_contract_manager` uit de API-laag.

**Oplossing**:
- Nieuw bestand: `src/core/copilot/prana_budget_cache.py` (ContractManager cache)
- `src/core/api/v1/_prana_contracts_cache.py` -> re-export shim
- factory.py importeert nu uit `src.core.copilot.prana_budget_cache`

### Fix 4: agent_runtime -> core_api (copilot/dependencies.py) -- Grade B gap

**Probleem**: `copilot/dependencies.py` importeerde `app_state` uit de API-laag. Dit was de enige resterende agent_runtime->core_api edge die de fan-out op 801 hield (target: <=800).

**Oplossing**:
- Nieuw bestand: `src/core/shared/app_state.py` (globale app_state dict)
- `src/core/api/setup/app_state.py` -> re-export shim (backward compat voor 9 api-callers)
- `copilot/dependencies.py` importeert nu uit `src.core.shared.app_state`

### Fix 5: TID252 (13 bestanden)

13 bestanden gemigreerd van `from ..X import Y` (level-2+ parent-relative) naar `from src.core.X import Y` (absolute). 13 per-file-ignore suppressors verwijderd uit pyproject.toml.

Bestanden:
- `src/core/api/autonomous_endpoints.py` (4 imports)
- `src/core/api/collaboration_endpoints_complex.py` (4 imports)
- `src/core/api/usage_endpoints.py` (4 imports)
- `src/core/database/database.py` (1 import)
- `src/core/learning/meta_learning.py` (1 import)
- `src/core/models/usage_models.py` (1 import)
- `src/core/procedures/models.py` (1 import)
- `src/core/subagents/specialists/performance_agent.py` (2 imports: line 11 + 183)
- `src/core/subagents/specialists/code_execution_agent.py` (1 import)
- `src/core/subagents/specialists/data_analysis_agent.py` (1 import)
- `src/core/subagents/specialists/knowledge_agent.py` (1 import)
- `src/core/subagents/specialists/reporting_agent.py` (1 import)
- `src/core/subagents/specialists/system_monitor_agent.py` (1 import)

## Uitgesteld (SP-DSM-008)

`messaging/telegram.py` + `messaging/whatsapp.py` -> `cva_tasks.py` -> `messaging/gateway.py`: bidirectionele circulaire dep. Stopconditie (>3 bestanden). Intentioneel RED architecture test bewaakt dit.

## Verificatie

- ruff check src/ --select TID252: All checks passed
- python -m pyright: 0 errors (baseline gehandhaafd)
- Architecture tests: 4 passed, 1 intentionally failed (SP-DSM-008 backlog)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-007 Dag 1: 4 grensschendingen gefixd (infra->core_api, domain_pack->core_api, agent_runtime->core_api x2). Grade B gap gesloten (801->800). 13 TID252 suppressors verwijderd. evaluation/schemas.py + copilot/prana_budget_cache.py + shared/app_state.py aangemaakt. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-007 Dag 1: 4 grensschendingen gefixd (infra->core_api, domain_pack->core_api, agent_runtime->core_api x2). Grade B gap gesloten (801->800). 13 TID252 suppressors verwijderd. evaluation/schemas.py + copilot/prana_budget_cache.py + shared/app_state.py aangemaakt..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
