# BE-GOV-020: AuditService consolidatie naar canoniek hash-chain-pad

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 1 Groep 2
**Datum:** 2026-07-02
**Status:** APPROVED WITH MINOR GAPS
**ADR:** ADR-019, ADR-006

## Probleem

Drie non-canonieke `AuditService`-schrijfpaden bestonden naast het canonieke
`governance/audit.py::AuditService.log_action()` (pg_advisory_xact_lock +
HashChainVerifier): `audit/audit_service.py::log_security_event()` (alleen
logger, geen DB-record), `governance/services/audit_service.py::log_event()`
(21 call-sites, wel DB-record maar geen hash-chain), en
`security/security_audit_service.py::SecurityAuditService` (eigen in-memory
`_last_hash` + JSON `event_metadata`-schema).

## Oplossing

- **Nieuwe Dramatiq-actor** `src/core/tasks/audit_tasks.py::write_audit_log_task`
  (ADR-006, fire-and-forget): de 5 sessieloze hot-path-callers (token_blacklist,
  token_refresh, logout_rate_limiter, session_dashboard, csp_violation_reporter)
  enqueuen nu een echte hash-chained write i.p.v. alleen te loggen. Geregistreerd
  in `src/workers/actors.py` (kritieke fix na code-review: zonder registratie
  verdwijnen writes stil in een nooit-geconsumeerde queue).
- `governance/services/audit_service.py::log_event()`: hash-chain-populatie
  in-place toegevoegd (HashChainVerifier + advisory-lock), `flush()`-not-
  `commit()`-contract (ADR-019) behouden.
- `SecurityAuditService.log_event()`: canonieke HashChainVerifier i.p.v. eigen
  schema. Pre-existing bug tegelijk gefixt: tenant_id als str opgeslagen in een
  Mapped[int]-kolom. `verify_log_integrity()` herschreven om de echte
  audit_hash/previous_hash-kolommen te lezen (las anders stilzwijgend de
  afgeschafte JSON-velden -- tamper-detectie werd een no-op).

## Backlog (falende architecture-tests)

`tests/architecture/test_no_audit_write_without_hash_chain.py` (SP-GOV-ARCH-5):
6 andere modules (GDPR erasure/portability, compliance PDF, billing, Stripe
webhook, GDPR purge) construeren AuditLog zonder hash-chain; 3 leespaden in
security_audit_service.py vergelijken tenant_id nog als str.

## Trainingssamenvatting

- Actor: token_blacklist / token_refresh / logout_rate_limiter / session_dashboard /
  csp_violation_reporter (5 Redis-only hot-path-services zonder DB-sessie)
- Voorwaarde: een van deze services roept `log_security_event()` aan, EN er is een
  tenant_id herleidbaar via de ADR-003 ContextVar
- Actie: security-event wordt gelogd (bijv. token-revocatie, rate-limit-overschrijding)
- Systeemreactie: event wordt direct naar de Python-logger geschreven (fail-open, zoals
  voorheen) EN een hash-chained AuditLog-write wordt asynchroon enqueued via
  `write_audit_log_task` (Dramatiq/ADR-006)
- Succesrespons: een `AuditLog`-record met geldige `audit_hash`/`previous_hash` verschijnt
  in de database (asynchroon, niet in dezelfde request-cyclus)
- Foutrespons: als geen tenant_id herleidbaar is, blijft het event logger-only -- geen
  DB-record (consistent met `governance/audit.py::log_action()`'s eigen tenant-vereiste)
- Uitzonderingen: een enqueue-fout wordt gelogd maar blokkeert de primaire operatie
  nooit (audit-redundantie mag de hoofdactie niet laten falen)

## Test bewijs

```
pytest tests/unit/governance/test_audit_service_consolidation.py tests/unit/security/test_security_audit_service_uses_canonical_hashchain.py tests/unit/test_worker_actor_registration.py tests/architecture/test_security_audit_best_effort.py tests/architecture/test_dramatiq_actors_tenant_id.py -v
33 passed
```

## Reviewers

code-reviewer: eerste ronde CHANGES_REQUESTED (Dramatiq-actor niet
geregistreerd -- kritiek, direct gefixt), na fix GO.
security-reviewer: GO WITH MINOR ISSUES (verify_log_integrity-regressie
gevonden en gefixt, if/elif -> onafhankelijke if-checks voor volledige
tamper-detectie).
