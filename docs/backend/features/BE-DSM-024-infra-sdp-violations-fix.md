# BE-DSM-024: SP-DSM-INFRA-001 Dag 1 -- infra SDP-schendingen opgelost

## Sprint
SP-DSM-INFRA-001 Dag 1

## Status
APPROVED

## Samenvatting

infra (I=0.039) had 12 SDP-schendende imports naar hogere lagen: tenancy=6,
domain_pack=2, integrations=3, worker=1. Na MODULE_MAP + SOURCE_DIRS fixes
zijn alle 12 gesloten. 4 arch-tests toegevoegd en GROEN.

## Wijzigingen

### MODULE_MAP reclassificaties (5 entries -- `scripts/dsm_full_analysis.py`)

| Module | Van | Naar | Reden |
|--------|-----|------|-------|
| `src.core.middleware.tenant_context` | tenancy | shared | ContextVar + FastAPI dep-functies -- zero src.* imports, cross-cutting foundation |
| `src.core.procedures.models` | domain_pack | shared | SQLAlchemy ORM-definitie -- zelfde patroon als governance.models, workflow.models |
| `src.core.events.pubsub_manager` | integrations | infra | Redis pub/sub primitief -- zero non-shared imports, blijft in SOURCE_DIRS["integrations"] (asym.) |
| `src.core.observability.alert_notification_bridge` | infra | integrations | Bridge naar notification channels = integrations-concern |
| `src.core.scheduling.webhooks.handlers` | infra | worker | Triggert Dramatiq workers -- worker-laag concern |

### SOURCE_DIRS wijzigingen

- `SOURCE_DIRS["infra"]`: `src/core/observability` (dir) -> 10 individuele bestanden (excl. alert_notification_bridge.py)
- `SOURCE_DIRS["infra"]`: `src/core/scheduling/webhooks` (dir) -> 4 individuele bestanden (excl. handlers.py)
- `SOURCE_DIRS["integrations"]`: + `src/core/observability/alert_notification_bridge.py`
- `SOURCE_DIRS["worker"]`: + `src/core/scheduling/webhooks/handlers.py`

### Bijgewerkt bestand

- `src/core/scheduling/webhooks/__init__.py`: `CalendarWebhookHandler` re-export verwijderd uit __init__
  (alle callers importeren direct vanuit handlers.py; WebhookSecurityError was geen actieve re-export)

## Arch-tests (nieuw)

Bestand: `tests/architecture/test_dsm_infra_sdp_violations.py`

| Test | Voor | Na |
|------|------|----|
| `test_infra_no_tenancy_import` | ROOD (6) | GROEN (0) |
| `test_infra_no_domain_pack_import` | ROOD (2) | GROEN (0) |
| `test_infra_no_integrations_import` | ROOD (3) | GROEN (0) |
| `test_infra_no_worker_import` | ROOD (1) | GROEN (0) |

## Metrieken na fix

- infra fan-out (excl. shared): 12 -> 0 (SDP-schendingen gesloten)
- infra fan-out totaal: 74 -> 62 (bewaard: budget 80)
- worker fan-out: 73 -> ~75 (handlers.py krijgt 2 infra-imports bijgeschreven; budget 80)
- integrations fan-out: 57 -> ~59 (bridge krijgt 2 infra-imports bijgeschreven; budget 60)
- Architecture tests: 210 passed, 13 xfailed, 0 failed
- Pyright: 0 errors (baseline behouden)

## Gate 2 bevindingen (opgelost)

- BLOCKER-001: `__init__.py` re-exporteerde `CalendarWebhookHandler` uit `handlers.py`; na
  reclassificatie van handlers.py -> worker zou dit infra->worker worden. Opgelost door de
  re-export te verwijderen.
- QR-003: pubsub_manager entry heeft inline comment met uitleg van SOURCE_DIRS-asymmetrie.
- MINOR-002: tenant_context MODULE_MAP comment vermeldt "ContextVar + FastAPI dep functions".


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-DSM-INFRA-001 Dag 1: infra SDP-schendingen opgelost (12->0). MODULE_MAP: tenant_context+procedures.models->shared, pubsub_manager->infra, alert_notification_bridge->integrations, handlers->worker. SOURCE_DIRS: observability+webhooks uitgebreid. 4 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-DSM-INFRA-001 Dag 1: infra SDP-schendingen opgelost (12->0). MODULE_MAP: tenant_context+procedures.models->shared, pubsub_manager->infra, alert_notification_bridge->integrations, handlers->worker. SOURCE_DIRS: observability+webhooks uitgebreid. 4 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
