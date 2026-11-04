# BE-WRK-001: SP-WE-18 Dramatiq Actor Worker Imports Fix

**Sprint:** SP-WE-18 (P0 one-off fix)
**Status:** COMPLETED
**Datum:** 2026-06-11

---

## Samenvatting

3 Dramatiq actor modules werden nooit geimporteerd door de worker entrypoint
(`src/workers/actors.py`). Berichten gestuurd via `.send()` landden in Redis maar werden
nooit verwerkt: de worker kende de actor niet. Twee van de originele 5 gevallen waren al
eerder gefixed (`integrity_check_actor`, `cva_tasks`). Drie bleven open.

---

## Root Cause

`src/workers/actors.py` importeert actor modules als side-effect zodat de Dramatiq broker
de actor-namen leert. De volgende 3 modules ontbraken in dat import-blok:

| Actor | Module | Queue |
|-------|--------|-------|
| `notify_tenant_admins_of_contest` | `src/core/copilot/api/contest_service.py` | notifications |
| `generate_audit_report` | `src/core/copilot/audit/report_jobs.py` | audit_reports |
| `execute_workflow_step` | `src/core/tasks/workflow_tasks.py` | default |

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/workers/actors.py` | 3 import regels + 3 entries in re-registratie blok |
| `tests/architecture/test_actor_worker_imports.py` | Nieuwe architecture test (RED->GREEN) |

---

## Verificatie

```bash
python -m pytest tests/architecture/test_actor_worker_imports.py -v --timeout=30
# 1 passed

python -m pytest tests/unit/test_workers_actors.py tests/unit/test_actors_import.py tests/unit/test_worker_actor_registration.py -q --timeout=30
# 16 passed (identiek aan baseline)

python -m pytest tests/architecture/ tests/unit/api/ -q --tb=short --timeout=30
# 192 passed, 12 xfailed

python -m pyright
# 0 errors
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
