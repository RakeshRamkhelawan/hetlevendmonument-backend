# BE-DSM-025: SP-DSM-REGRESSIE Dag 2 -- Verse Snapshot + MEDIUM Pairs Quick-Win

## Sprint
SP-DSM-REGRESSIE Dag 2

## Status
APPROVED

## Samenvatting

Verse DSM meting na SP-DSM-REGRESSIE dag 1 + SP-DSM-INFRA-001 dag 1. Delta gedocumenteerd.
Quick-win: src.core.services.rbac_service -> auth (1 MODULE_MAP entry, 5 auth->agent_runtime
backward deps gesloten). Tracking tests voor 4 resterende P2 backlog-paren aangemaakt.

## Wijzigingen

### MODULE_MAP reclassificatie (1 entry -- `scripts/dsm_full_analysis.py`)

| Module | Van | Naar | Reden |
|--------|-----|------|-------|
| `src.core.services.rbac_service` | agent_runtime | auth | RBAC = auth-concern; auth importeert het, geen agent_runtime callers |

### Import fix -- `src/core/auth/scope_validator.py`

Lijn 18: `from src.core.services import rbac_service as rbac_service_module`
→ `import src.core.services.rbac_service as rbac_service_module`

Reden: `from src.core.services import X` gebruikt module-string `src.core.services` (geen
submodule-match in MODULE_MAP). Direct import gebruikt `src.core.services.rbac_service`
(long-prefix match -> auth). Identiek gedrag, correcte DSM-classificatie.

### Nieuwe arch-tests

| Bestand | Tests | Type |
|---------|-------|------|
| `tests/architecture/test_dsm_auth_rbac_sdp_fix.py` | 1 (ROOD->GROEN) | SDP fix |
| `tests/architecture/test_dsm_medium_pairs_tracking.py` | 6 (tracking max) | P2 backlog |

### Nieuw rapport

`docs/reports/DSM-AUDIT-2026-06-24.md` -- delta update t.o.v. audit 2026-06-23.

## Metrieken na fixes (dag 2)

- auth -> agent_runtime backward deps: 5 -> 0
- Circulaire MEDIUM paren: 3 -> **1** (alleen agent_runtime<->integrations resteert)
- arch-tests: 210 -> **217 passed**, 13 xfailed, 0 failed
- Pyright: 0 errors

## Delta vs audit 2026-06-23 (cumulatief)

| Metriek | Audit 2026-06-23 | Nu | Delta |
|---------|------------------|----|-------|
| infra SDP-schendingen | 12 | 0 | -12 |
| governance -> agent_runtime | 10 | 0 | -10 |
| auth -> agent_runtime | 5 | 0 | -5 |
| agent_runtime <-> tenancy heen | 22 | 0 | -22 |
| agent_runtime <-> domain_pack heen | 16 | 11 | -5 |

## P2 Backlog (na dag 2)

| Paar | Heen | Terug | Sprint | Vereiste |
|------|------|-------|--------|---------|
| agent_runtime <-> integrations | 30 | 13 | SP-DSM-010 | ADR-025 event-bus |
| agent_runtime <-> domain_pack | 11 | 7 | SP-DSM-011 | DI-aanpassing |
| agent_runtime <-> tool_broker | 15 | 1 | SP-DSM-012 | Kleine reclassificatie |
| tenancy -> agent_runtime | 0 | 1 | SP-DSM-012 | Kleine reclassificatie |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-REGRESSIE Dag 2: verse snapshot + rbac_service->auth quick-win (5 auth->agent_runtime backward deps gesloten). 6 tracking tests voor P2 backlog-paren. Audit 2026-06-24 bijgewerkt. Circulaire MEDIUM paren 3->1. 217 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-REGRESSIE Dag 2: verse snapshot + rbac_service->auth quick-win (5 auth->agent_runtime backward deps gesloten). 6 tracking tests voor P2 backlog-paren. Audit 2026-06-24 bijgewerkt. Circulaire MEDIUM paren 3->1. 217 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
