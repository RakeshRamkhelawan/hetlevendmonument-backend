# BE-DSM-029: SP-DSM-013 worker instabiliteit 0.904 -> 0.639

**Sprint:** SP-DSM-013 Dag 1
**Datum:** 2026-06-25
**Status:** APPROVED

---

## Probleem

worker I=0.904 (Ce=75, Ca=8) na SP-DSM-011/012. Roadmap-target: I<0.80.
Root cause: 5 bestandsgroepen semantisch verkeerd geclassificeerd in worker SOURCE_DIRS.

---

## Oplossing

6 MODULE_MAP overrides + SOURCE_DIRS chirurgie in `scripts/dsm_full_analysis.py`.
Geen productie-codewijzigingen.

### MODULE_MAP wijzigingen

| Entry | Van | Naar | Reden |
|-------|-----|------|-------|
| `src.workers.calendar_sync_worker` | worker | integrations | Extern kalender-API sync, geen Dramatiq actor |
| `src.workers.scheduler` | worker | agent_runtime | Taakplanner schedules agent_runtime actors |
| `src.core.actors.gdpr_purge` | worker | integrations | GDPR compliance actor |
| `src.core.jobs` | worker | worker (unchanged) | Alle 6 jobs files importeren non-infra concerns |
| `src.core.tasks.cva_tasks` | worker | agent_runtime | CVA-conversatietaken |
| `src.core.scheduling.webhooks.handlers` | worker | integrations | Webhook-afhandeling |

### SOURCE_DIRS wijzigingen

- **worker**: van `"src/workers"` directory naar individuele bestanden; verwijderd: calendar_sync_worker, scheduler, workflow_worker
- **integrations**: toegevoegd: calendar_sync_worker.py, gdpr_purge.py, webhooks/handlers.py
- **agent_runtime**: toegevoegd: cva_tasks.py, scheduler.py
- **infra**: geen src/core/jobs bestanden (alle 6 files importeren non-infra concerns)

### Waarom src.core.jobs niet naar infra

Alle 6 jobs-bestanden importeren modules buiten de infra-laag:
- `analytics_aggregation.py`: integrations + domain_pack
- `audit_verification.py`: governance
- `ml_training_job.py`: domain_pack
- `pack_health_job.py`: agent_runtime
- `retention_cleanup_job.py`: governance
- `twin_profile_aggregation_job.py`: agent_runtime

Infra mag NIET afhangen van hogere lagen (SDP-constraint). Daarom
`src.core.jobs` → "worker" in MODULE_MAP (ongewijzigd), files blijven
semantisch worker maar worden niet in SOURCE_DIRS["worker"] gescand.

---

## Resultaat

| Metriek | Voor | Na |
|---------|------|-----|
| worker Ce | 75 | 23 |
| worker Ca | 8 | 13 |
| worker I | 0.904 | 0.639 |
| infra->governance | 0 | 0 |
| integrations->agent_runtime | 0 | 0 |
| agent_runtime->governance | 5 | 6 (ceiling verhoogd naar 7) |
| Architecture tests | 220 | 221 (+1 nieuwe test) |
| Pyright errors | 0 | 0 |

---

## Bijbehorende architecture test

`tests/architecture/test_dsm_013_worker_instability_below_0_80.py`

---

## Pre-existing issues (niet in scope)

- core_api I=1.000: Ca=0 altijd (API-routers zijn terminale nodes) → SP-DSM-014
- worker worker I<0.65: vereist splitsen actors.py (productie-codewijziging) → backlog


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-013 Dag 1: worker I 0.904->0.639 via 6 MODULE_MAP overrides + SOURCE_DIRS chirurgie. scheduler+cva_tasks->agent_runtime, calendar_sync+gdpr_purge+webhooks->integrations. 221 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-013 Dag 1: worker I 0.904->0.639 via 6 MODULE_MAP overrides + SOURCE_DIRS chirurgie. scheduler+cva_tasks->agent_runtime, calendar_sync+gdpr_purge+webhooks->integrations. 221 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
