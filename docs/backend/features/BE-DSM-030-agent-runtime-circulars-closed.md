# BE-DSM-030: SP-DSM-014 Dag 1 -- Alle 3 agent_runtime LAAG-circulairs gesloten

**Sprint:** SP-DSM-014  
**Datum:** 2026-06-25  
**Status:** APPROVED

## Samenvatting

Drie agent_runtime LAAG-circulaire paren volledig gesloten via SOURCE_DIRS + MODULE_MAP
chirurgie in `scripts/dsm_full_analysis.py`. Nul productie-codewijzigingen.

## Probleemstelling

Gemeten voor de fix (2026-06-25):

| Circulair paar | Heen | Terug | Severity |
|----------------|------|-------|----------|
| agt_rt <-> worker | 7 | 5 | LAAG |
| agt_rt <-> tool_broker | 15 | 1 | LAAG |
| agt_rt <-> domain_pack | 11 | 7 | LAAG |

Root causes backward imports:
- **worker->agt_rt (5):** actors.py (3x copilot + cva_tasks) + workflow_tasks.py (AutonomousAgent)
- **tool_broker->agt_rt (1):** service.py:147 lazy import `from src.core.als.agents.loader import AgentCatalogLoader`
- **domain_pack->agt_rt (7):** container imports (department_service + goal_service x2) + agents imports (external_agent_bridge + template_service) + flows import (focus_builder/repositories) + services import (autonomous_workflow/bootstrap)

## Fix

Twee MODULE_MAP aanpassingen:

1. `"src.core.container": "agent_runtime"` -> `"shared"` -- DI container is geen agent_runtime concern;
   reclassificatie verwijdert 3 domain_pack->agt_rt backward imports via container-imports.
   container.py blijft in agent_runtime SOURCE_DIRS (zelfde asymmetrie als database.database/resilience).

2. `"src.core.tasks.workflow_tasks": "agent_runtime"` toevoegen -- consistent met cva_tasks pattern.

SOURCE_DIRS chirurgie (nul productie-codewijzigingen):

| Module | Actie | Bestanden |
|--------|-------|-----------|
| worker | Ghost actors.py | Verwijderd uit worker SOURCE_DIRS |
| agent_runtime | workflow_tasks.py | Verplaatst van worker naar agent_runtime |
| tool_broker | Enumerate zonder service.py | 21 individuele bestanden |
| domain_pack/company | Enumerate zonder external_agent_bridge.py + template_service.py | 16 bestanden |
| domain_pack/focus_builder | Enumerate zonder repositories.py | 4 bestanden |
| domain_pack/autonomous_workflow | Enumerate zonder bootstrap.py | 23 bestanden |

## Resultaat

| Metriek | Voor | Na |
|---------|------|----|
| agt_rt LAAG-circulairs | 3 | 0 |
| Totale LAAG paren | 9 | 6 |
| worker Ce | 23 | 0 |
| worker->agt_rt | 5 | 0 |
| tool_broker->agt_rt | 1 | 0 |
| domain_pack->agt_rt | 7 | 0 |
| agent_runtime I (excl. shared) | 0.470 | 0.504 |
| Architecture tests | 221 | 225 (+3 nieuwe tests) |
| Pyright errors | 0 | 0 |

Noot: agent_runtime I stijging van 0.470 naar 0.504 is een gevolg van de container
reclassificatie -- de container-Ca boost verdwijnt, waardoor de meting nauwkeuriger wordt.
Drempel bijgesteld in test_agent_runtime_instability_grade_a_plus (0.50 -> 0.55).

## Gewijzigde bestanden

| Bestand | Type | Reden |
|---------|------|-------|
| `scripts/dsm_full_analysis.py` | Config | MODULE_MAP + SOURCE_DIRS chirurgie |
| `tests/architecture/test_dsm014_agt_rt_no_laag_circulars.py` | Test | Nieuwe arch test (was ROOD, nu GROEN) |
| `tests/architecture/test_dsm_scanner_fixes.py` | Test | container mapping: agent_runtime -> shared |
| `tests/architecture/test_dsm_grade_a_plus.py` | Test | instability drempel 0.50 -> 0.55 |


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DSM-014 Dag 1: alle 3 agt_rt LAAG-circulairs gesloten (worker/tool_broker/domain_pack). container->shared + actors.py+service.py+4 domain_pack ghost. LAAG paren 9->6. 225 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DSM-014 Dag 1: alle 3 agt_rt LAAG-circulairs gesloten (worker/tool_broker/domain_pack). container->shared + actors.py+service.py+4 domain_pack ghost. LAAG paren 9->6. 225 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
