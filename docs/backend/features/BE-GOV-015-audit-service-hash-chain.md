# BE-GOV-015: AuditService.log_action() Hash Chain Populatie (ADR-019)

**Sprint:** SP-DLP-003 Dag 4
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`AuditService.log_action()` is de centrale governance audit writer -- gebruikt door
billing, stripe, API endpoints, en actors -- maar zette `audit_hash` en `previous_hash`
nooit in. ADR-019 vereist een SHA-256 hash chain op elke AuditLog insert.

## Implementatie

In `log_action()` toegevoegd na `log_entry = AuditLog(...)`, voor `if session: session.add()`:

1. `log_entry.timestamp = datetime.now(timezone.utc)` -- expliciet voor reproduceerbare hash.
2. `pg_advisory_xact_lock(tenant_id_int)` -- serialiseert chain-writes per tenant.
3. `begin_nested()` (SAVEPOINT) -- houdt de caller-transactie in leven bij hash-fout.
4. SELECT laatste `audit_hash` voor tenant (`ORDER BY timestamp DESC, id DESC`).
5. `HashChainVerifier._compute_hash(log_entry, previous_hash)` -- SHA-256.
6. `log_entry.previous_hash` en `log_entry.audit_hash` ingesteld.

Identiek patroon als `dsar_service._create_audit_log()` (BE-GOV-014, goedgekeurd).

## Fail-semantics

| Situatie | Gedrag |
|----------|--------|
| Hash succesvol | `audit_hash` + `previous_hash` ingesteld |
| DB-fout in hash-query | SAVEPOINT rollback, `logger.error`, entry zonder hash |
| Advisory lock fout | outer except, `logger.error`, entry zonder hash |
| Geen vorig entry | `previous_hash = None`, hash berekend zonder predecessor |
| Geen session | `logger.warning`, return None (bestaand gedrag) |

## Backlog (intentioneel RED arch tests)

- `ai_transparency_service.py`: 3 AuditLog inserts zonder hash chain -- SP-DLP-004
- `cookie_consent.py`: 1 AuditLog insert zonder hash chain -- SP-DLP-004

Beide bewaakt door falende arch tests in `tests/architecture/test_adr019_hash_chain_wired.py`.

## Tests

2 TDD tests GROEN:
- `tests/unit/governance/test_audit_service_hash_chain.py::test_log_action_populates_audit_hash`
- `tests/unit/governance/test_audit_service_hash_chain.py::test_log_action_sets_previous_hash`

4 arch tests (2 GREEN, 2 intentioneel RED):
- `tests/architecture/test_adr019_hash_chain_wired.py::test_dsar_service_audit_hash_wired` -- GREEN
- `tests/architecture/test_adr019_hash_chain_wired.py::test_audit_service_log_action_hash_wired` -- GREEN
- `tests/architecture/test_adr019_hash_chain_wired.py::test_ai_transparency_service_audit_hash_wired` -- RED (SP-DLP-004)
- `tests/architecture/test_adr019_hash_chain_wired.py::test_cookie_consent_audit_hash_wired` -- RED (SP-DLP-004)

## ADR-compliance

- ADR-019: SHA-256 hash chain op centrale writer -- compliant.
- ADR-005: query is tenant-scoped (`AuditLog.tenant_id == tenant_id_int`) -- compliant.
- Lazy import van `HashChainVerifier` -- geen circulaire dependency bij module-load.


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DLP-003 Dag 4: centrale audit writer AuditService.log_action() vult audit_hash+previous_hash in. Zelfde patroon als BE-GOV-014. 2 TDD tests GROEN, 592 governance tests GROEN. 2 arch tests GREEN + 2 intentioneel RED (ai_transparency+cookie_consent backlog SP-DLP-004). pyright 0 errors. ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DLP-003 Dag 4: centrale audit writer AuditService.log_action() vult audit_hash+previous_hash in. Zelfde patroon als BE-GOV-014. 2 TDD tests GROEN, 592 governance tests GROEN. 2 arch tests GREEN + 2 intentioneel RED (ai_transparency+cookie_consent backlog SP-DLP-004). pyright 0 errors. ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
