# BE-API-041: SP-API-011 Dag 1 -- ADR-033 import consolidatie (3 xfails -> 0)

## Samenvatting

SP-API-011 Dag 1: drie openstaande arch-test xfails gesloten door ADR-beslissingen te formaliseren
en verboden lazy imports naar hun `dependencies.py` te verplaatsen.

## Wijzigingen

### 1a. cva/dependencies.py -- ADR-033 goedkeuringscomment (1 xfail gesloten)

**Bestand:** `src/core/api/v1/cva/dependencies.py`
**Wijziging:** `# ADR-033: dependencies.py mag domeinlagen importeren` toegevoegd boven de
`src.core.agents.*` imports op regels 13-14.
**Beslissing:** de imports zijn conform ADR-033 par. 2 (dependencies.py files mogen domeinlagen
importeren). De CI-ankertest `test_cva_dependencies_agents_import_pending_adr` is verwijderd
omdat het patroon nu als GOEDGEKEURD geldt.

### 1b. Governance lazy imports -> dependencies.py (1 xfail gesloten)

Drie router-bestanden hadden verboden lazy imports (`src.core.governance.*`) inside function
bodies. Verplaatst naar de respectieve `dependencies.py`:

| Router | Import(s) verplaatst | Naar |
|--------|---------------------|------|
| `gdpr_compliance/explanation_router.py` | `AIDecision` | `gdpr_compliance/dependencies.py` |
| `governance/governance_monitoring_router.py` | `GovernanceAlert`, `AccuracyMonitor`, `RiskEntry` | `governance/dependencies.py` |
| `governance/governance_quality_router.py` | `QualityGate`, `AuthorityReport` | `governance/dependencies.py` |

De xfail-marker van `test_star_router_files_have_no_forbidden_imports` is verwijderd; de test
slaagt nu normaal.

### 1c. stats_router sibling-imports -> dependencies.py (1 xfail gesloten)

**Bestand:** `src/core/api/v1/orchestration/stats_router.py`
**Wijziging:** imports van `get_health_monitor` (via `health_router`) en
`get_agent_router`/`get_master_orchestrator` (via `workflow_router`) zijn vervangen door directe
imports uit `orchestration/dependencies.py`, waar deze factory-functies al gedefinieerd stonden.
De xfail-marker van `test_stats_router_does_not_import_from_sibling_routers` is verwijderd.

## Gewijzigde bestanden

**Broncode (9 bestanden):**
- `src/core/api/v1/cva/dependencies.py` (comment toegevoegd)
- `src/core/api/v1/governance/dependencies.py` (5 governance model imports toegevoegd)
- `src/core/api/v1/gdpr_compliance/dependencies.py` (AIDecision toegevoegd)
- `src/core/api/v1/gdpr_compliance/explanation_router.py` (lazy import verwijderd)
- `src/core/api/v1/governance/governance_monitoring_router.py` (3 lazy imports verwijderd)
- `src/core/api/v1/governance/governance_quality_router.py` (2 lazy imports verwijderd)
- `src/core/api/v1/orchestration/stats_router.py` (sibling imports vervangen)

**Tests (2 bestanden):**
- `tests/architecture/test_dsm002_groep_c_deferred.py` (xfail test verwijderd, pytest import opgeruimd)
- `tests/architecture/test_sp_api_010_backlog.py` (2 xfail markers verwijderd)

## Verificatie

```
Architecture tests: 285 passed, 0 failed, 9 xfailed (was 283/0/12)
Targeted unit tests: 773 passed, 0 failed
pyright: 0 errors, 57 warnings (baseline gehandhaafd)
```

## DoD

- [x] Alle deliverables op verwachte paden
- [x] Architecture tests: xfail 12 -> 9 (Dag 1 target)
- [x] pyright 0 errors
- [x] Geen regressies in gerichte tests (773 passed)
- [x] Feature spec aangemaakt
- [x] ID-REGISTRY bijgewerkt


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-API-011 Dag 1: ADR-033 import consolidatie -- 3 xfails gesloten. cva/dependencies.py ADR-beslissing GOEDGEKEURD. 5 governance lazy imports -> dependencies.py (GovernanceAlert/AccuracyMonitor/RiskEntry/QualityGate/AuthorityReport). AIDecision -> gdpr_compliance/dependencies.py. stats_router sibling-imports -> orchestration/dependencies.py. Arch: 285 passed, 9 xfailed (was 12). pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-API-011 Dag 1: ADR-033 import consolidatie -- 3 xfails gesloten. cva/dependencies.py ADR-beslissing GOEDGEKEURD. 5 governance lazy imports -> dependencies.py (GovernanceAlert/AccuracyMonitor/RiskEntry/QualityGate/AuthorityReport). AIDecision -> gdpr_compliance/dependencies.py. stats_router sibling-imports -> orchestration/dependencies.py. Arch: 285 passed, 9 xfailed (was 12). pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
