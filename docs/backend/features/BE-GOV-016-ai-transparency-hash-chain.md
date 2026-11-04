# BE-GOV-016: Hash Chain in ai_transparency_service.py + cookie_consent.py (ADR-019)

**Sprint:** SP-DLP-004 Dag 1
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`ai_transparency_service.py` (3 inserts) en `cookie_consent.py` (1 insert) schreven AuditLog
entries zonder `audit_hash` of `previous_hash` -- ADR-019 hash chain niet gewired.
SP-DLP-003 sloot met 2 intentioneel RED arch tests die dit bewaken.

## Implementatie

### `src/core/governance/ai_transparency_service.py`

Imports toegevoegd: `import logging`, `timezone`, `text`, `best_effort`.
Module-level `logger = logging.getLogger(__name__)`.

`_populate_hash_chain(audit_entry, tenant_id_int)` private async method:
- `pg_advisory_xact_lock(tenant_id_int)` -- serialiseert chain-writes per tenant
- `begin_nested()` SAVEPOINT -- houdt outer tx in leven bij hash-fout
- SELECT laatste `audit_hash` voor tenant
- `HashChainVerifier._compute_hash()` -- SHA-256
- Fail-safe: `logger.error`, entry zonder hash (degraded mode)

3 insert locaties gewired (elke in `async with best_effort(...)`):
- `log_ai_decision`: `best_effort` + timestamp + `_populate_hash_chain(tenant_id)`
- `request_human_review`: `best_effort` + timestamp + hash chain OVERGESLAGEN (tenant_id=0 bug)
- `set_profiling_opt_out`: `best_effort` + timestamp + `_populate_hash_chain(tenant_id)`

### `src/core/governance/cookie_consent.py`

`text` toegevoegd aan sqlalchemy import.
Inline hash chain toegevoegd in bestaande best-effort try/except voor `self._db.add(audit_entry)`.
Pre-existing fix: `exc_info=True` toegevoegd aan outer except `logger.error`.

## Backlog (intentioneel RED arch test)

- `request_human_review` heeft `tenant_id=0` hardcoded (pre-existing bug) -- SP-DLP-005.
  Bewaakt door `tests/architecture/test_adr019_hash_chain_wired.py::test_request_human_review_audit_has_real_tenant_id`.

## Tests

3 TDD tests GROEN:
- `tests/unit/governance/test_ai_transparency_hash_chain.py::test_ai_transparency_service_has_populate_hash_chain`
- `tests/unit/governance/test_ai_transparency_hash_chain.py::test_ai_transparency_service_populate_hash_chain_sets_audit_hash`
- `tests/unit/governance/test_ai_transparency_hash_chain.py::test_cookie_consent_update_consent_sets_audit_hash`

Arch tests: 4 GREEN + 1 intentioneel RED (tenant_id=0 backlog):
- `test_dsar_service_audit_hash_wired` -- GREEN
- `test_audit_service_log_action_hash_wired` -- GREEN
- `test_ai_transparency_service_audit_hash_wired` -- GREEN
- `test_cookie_consent_audit_hash_wired` -- GREEN
- `test_request_human_review_audit_has_real_tenant_id` -- RED (SP-DLP-005)

## ADR-compliance

- ADR-019: hash chain op alle gewired inserts -- compliant.
- ADR-005: alle queries tenant-scoped -- compliant.
- Pattern 3: audit inserts in `ai_transparency_service.py` gewrapt in `best_effort` -- compliant.


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-DLP-004 Dag 1: hash chain in ai_transparency_service.py (_populate_hash_chain + best_effort, 2/3 inserts) + cookie_consent.py (inline). tenant_id=0 bewaakt door falende arch test (SP-DLP-005). 3 TDD GROEN, 4 arch GREEN + 1 RED. pyright 0. ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-DLP-004 Dag 1: hash chain in ai_transparency_service.py (_populate_hash_chain + best_effort, 2/3 inserts) + cookie_consent.py (inline). tenant_id=0 bewaakt door falende arch test (SP-DLP-005). 3 TDD GROEN, 4 arch GREEN + 1 RED. pyright 0. ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
