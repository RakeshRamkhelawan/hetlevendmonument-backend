# BE-GOV-014: AuditLog Hash Chain Populatie in _create_audit_log() (ADR-019)

**Sprint:** SP-DLP-003 Dag 3
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`AuditLog` heeft `audit_hash` en `previous_hash` kolommen (nullable=True voor migratie-compat),
maar `_create_audit_log()` in `dsar_service.py` vulde ze nooit in -- altijd NULL.
ADR-019 vereist een SHA-256 hash chain voor tamper-evidence bij elke AuditLog insert.

## Implementatie

In `_create_audit_log()` toegevoegd voor `self._db.add(audit_entry)`:

1. `audit_entry.timestamp = datetime.now(timezone.utc)` -- expliciet, niet via server_default,
   zodat de hash consistent is bij verificatie (PostgreSQL bewaart microsecond-precisie).
2. `pg_advisory_xact_lock(tenant_id)` -- serialiseert chain-writes per tenant, voorkomt
   geforkte chain bij gelijktijdige DSAR-operaties.
3. `begin_nested()` (SAVEPOINT) -- houdt de outer transactie in leven als de hash-compute
   mislukt; de audit log wordt alsnog weggeschreven zonder hash (degraded mode).
4. SELECT laatste `audit_hash` voor tenant (tenant-scoped, `ORDER BY timestamp DESC, id DESC`).
5. `HashChainVerifier._compute_hash(entry, previous_hash)` -- berekent SHA-256.
6. `audit_entry.previous_hash` en `audit_entry.audit_hash` ingesteld.

## Fail-semantics

| Situatie | Gedrag |
|----------|--------|
| Hash succesvol berekend | `audit_hash` + `previous_hash` ingesteld |
| DB-fout in hash-query | SAVEPOINT rollback, logger.error, audit log zonder hash |
| Advisory lock fout | outer except, logger.error, audit log zonder hash |
| Geen vorig entry (genesis) | `previous_hash = None`, hash berekend zonder predecessor |

## Tests

2 tests GROEN:
- `tests/unit/governance/test_audit_log_hash_chain.py::test_create_audit_log_populates_audit_hash`
- `tests/unit/governance/test_audit_log_hash_chain.py::test_create_audit_log_sets_previous_hash`

## ADR-compliance

- ADR-019: SHA-256 hash chain op elke insert -- compliant.
- ADR-005: query is tenant-scoped (`AuditLog.tenant_id == tenant_id`) -- compliant.
- Lazy import van `HashChainVerifier` -- geen circulaire dependency.


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DLP-003 Dag 3: ADR-019 hash chain write-side -- _create_audit_log() vult audit_hash+previous_hash in. pg_advisory_xact_lock voor race-safety, begin_nested() SAVEPOINT voor degraded mode, ORDER BY timestamp+id tiebreaker. 2 TDD tests GROEN, 590 governance tests GROEN. pyright 0 errors. ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DLP-003 Dag 3: ADR-019 hash chain write-side -- _create_audit_log() vult audit_hash+previous_hash in. pg_advisory_xact_lock voor race-safety, begin_nested() SAVEPOINT voor degraded mode, ORDER BY timestamp+id tiebreaker. 2 TDD tests GROEN, 590 governance tests GROEN. pyright 0 errors. ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
