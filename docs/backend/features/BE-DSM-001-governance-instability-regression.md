# Feature Spec: BE-DSM-001 -- SP-DSM-REGRESSIE Dag 1

## Samenvatting

Correctie van governance I-regressie (0.28 -> 0.42) en infra backward deps naar governance
via MODULE_MAP reclassificatie in `scripts/dsm_full_analysis.py`. Tevens pre-existing GDPR-bug
gefixed in `dsar_service.py` (`Workflow.created_by_id` -> `Workflow.created_by`).

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `scripts/dsm_full_analysis.py` | 4 MODULE_MAP entries toegevoegd (shared + integrations reclassificaties) |
| `src/core/governance/dsar_service.py` | 3x `created_by_id` -> `created_by` (GDPR Art. 15/17 fix) |
| `tests/architecture/test_dsm_governance_regression.py` | Nieuwe arch-tests (governance->agent_runtime = 0, infra->governance = 0) |

## MODULE_MAP reclassificaties

| Prefix | Van | Naar | Reden |
|--------|-----|------|-------|
| `src.core.governance.models` | `governance` | `shared` | AuditLog = ORM model-definitie; zelfde patroon als `src.core.auth.models` |
| `src.core.services.email` | `agent_runtime` | `integrations` | Externe email-communicatie, niet agent-runtime logica |
| `src.core.workflow.models` | `agent_runtime` | `shared` | C7Workflow = SQLAlchemy model-definitie (foundational data) |
| `src.core.learning.loop` | `agent_runtime` | `shared` | LearningInsight/AdaptationRule = Pydantic data-modellen (foundational data) |

## GDPR fix

Pre-existing bug: `C7Workflow.created_by_id` bestaat niet -- het correcte veld is `created_by`
(mapped_column in workflow/models.py:148). Werd stil geslikt door `except Exception` blokken,
waardoor workflows ontbraken in DSAR Art. 15 (access) en Art. 17 (erasure) exports.

Locaties gefixed:
- Line 318 (select -- Art. 15 access)
- Line 617 (delete -- Art. 17 hard delete)
- Line 652 (update -- Art. 17 soft delete / mark inactive)

## Testresultaten

- `test_governance_no_agent_runtime_runtime_import`: ROOD voor fix, GROEN na fix
- `test_infra_no_governance_import`: ROOD voor fix, GROEN na fix
- `test_dsm_grade_a_plus.py`: 18 passed, 1 xfailed (verwacht: core_api XFAIL)
- `tests/unit/governance/`: 569 passed
- `tests/unit/ -k dsar`: 62 passed, 4 skipped
- `python -m pyright`: 0 errors (baseline intact)

## ADR-koppeling

- ADR-034: agent_runtime 5-laags model (shared bucket exclusie in instability berekening)
- ADR-033: 3-laags router boundary (niet direct geraakt)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-REGRESSIE Dag 1: MODULE_MAP reclassificatie (governance.models+workflow.models+learning.loop->shared, services.email->integrations) + GDPR fix created_by_id->created_by (3x dsar_service.py). governance->agent_runtime=0, infra->governance=0. 19 arch tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-REGRESSIE Dag 1: MODULE_MAP reclassificatie (governance.models+workflow.models+learning.loop->shared, services.email->integrations) + GDPR fix created_by_id->created_by (3x dsar_service.py). governance->agent_runtime=0, infra->governance=0. 19 arch tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
