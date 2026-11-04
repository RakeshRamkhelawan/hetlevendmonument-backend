# BE-TSK-010 -- Dramatiq Actor Registratie Verificatietests (SP-WE-18 sluiting)

**ID:** BE-TSK-010
**Sprint:** SP-WE-18 + SP-DB-01 (1 dag sprint)
**Datum:** 2026-06-14
**ADR:** ADR-006 (Dramatiq + Redis)

## Samenvatting

Formele sluiting van SP-WE-18. Alle 6 Dramatiq actors waren al geimporteerd in
`src/workers/actors.py` (SP-WE-19a, 2026-06-01), maar 3 actors hadden geen
registratietest en SPRINT_TRACKER was nooit bijgewerkt.

### Wijzigingen

| Bestand | Wijziging |
|---------|-----------|
| `tests/unit/test_worker_actor_registration.py` | 3 registratietests toegevoegd voor notify, generate_audit_report, execute_workflow_step |
| `src/workers/actors.py` | `_actor = None` initialisatie voor for-loop; `del _actor` toegevoegd -- verhelpt module-scope lek |

### Nieuwe tests

- `test_notify_tenant_admins_of_contest_is_registered` -- sync + actor_name aanwezig
- `test_generate_audit_report_is_registered` -- sync + actor_name aanwezig
- `test_execute_workflow_step_is_registered` -- sync + actor_name aanwezig

### Actor registratie overzicht (volledig)

| Actor | Module | Sync wrapper | Test aanwezig |
|-------|--------|-------------|---------------|
| `check_hash_chain_integrity_actor` | `copilot/audit/integrity_check_actor.py` | ja | BE-TSK-009 |
| `process_cva_message` | `core/tasks/cva_tasks.py` | ja | BE-TSK-009 |
| `cleanup_council_decisions` | `core/governance/retention_cleanup.py` | ja | BE-TSK-009 |
| `notify_tenant_admins_of_contest` | `copilot/api/contest_service.py` | ja | BE-TSK-010 |
| `generate_audit_report` | `copilot/audit/report_jobs.py` | ja | BE-TSK-010 |
| `execute_workflow_step` | `core/tasks/workflow_tasks.py` | ja | BE-TSK-010 |

## Testresultaten

```text
tests/unit/test_worker_actor_registration.py -- 9 tests, 9 PASS (1.03s)
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
