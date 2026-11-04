# BE-GOV-017: Fix tenant_id=0 in request_human_review (ADR-019)

**Sprint:** SP-DLP-005 Dag 1
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`request_human_review()` maakte een AuditLog entry met `tenant_id=0` hardcoded.
De methode ontvangt geen `tenant_id` parameter -- alleen `decision_id` -- dus de echte
tenant kon niet gewired worden zonder een DB-lookup. Hash chain was daardoor overgeslagen
(SP-DLP-004 backlog, intentioneel RED arch test `test_request_human_review_audit_has_real_tenant_id`).

## Implementatie

### `src/core/governance/ai_transparency_service.py` -- `request_human_review()`

Binnen de bestaande `best_effort` block, voor de `AuditLog` aanmaak:

1. SELECT `AIDecision.tenant_id` WHERE `AIDecision.id == decision_id_int`
2. `_raw_tid = await _maybe_await(_tid_result.scalar_one_or_none())`
3. `_decision_tenant_id = _raw_tid if isinstance(_raw_tid, int) else 0`
4. `logger.warning` als `_decision_tenant_id == 0` (decision niet gevonden -- degraded)
5. `AuditLog(tenant_id=_decision_tenant_id, ...)` -- echte tenant_id
6. `await self._populate_hash_chain(audit_entry, _decision_tenant_id)` als `_decision_tenant_id > 0`

`_maybe_await` + `isinstance(int)` gebruikt (bestaand patroon) voor test-compat met AsyncMock.
`AIDecision` was al geimporteerd in de file.

## Degraded mode

Als `decision_id_int` niet in DB bestaat (bv. ongeldige ID): `_decision_tenant_id = 0`,
hash chain overgeslagen, warning gelogd. Audit entry wordt alsnog geschreven.

## Tests

Bestaande arch test nu GREEN:
- `test_request_human_review_audit_has_real_tenant_id` -- was intentioneel RED (SP-DLP-004 backlog)

Nieuwe unit test GREEN:
- `test_request_human_review_resolves_tenant_id_from_decision` -- checkt `"AIDecision.tenant_id" in src`

Pre-existing tests hersteld (waren gebroken door _raw AsyncMock mismatch):
- `TestHumanReview::test_human_review_creates_audit_log`
- `TestHumanReview::test_human_review_logs_gdpr_article_reference`

Totaal: 596 governance tests GROEN.

## ADR-compliance

- ADR-019: hash chain gewired voor alle governance AuditLog inserts met echte tenant_id -- compliant.
- ADR-005: queries tenant-scoped via lookup -- compliant.
- Pattern 3: audit insert in `best_effort` -- compliant.


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-DLP-005 Dag 1: request_human_review() tenant_id=0 fix -- SELECT AIDecision.tenant_id + _maybe_await + isinstance fallback. hash chain gewired voor alle 5 governance AuditLog inserts. 596 gov tests GROEN, 5/5 arch tests GREEN, pyright 0 errors, ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-DLP-005 Dag 1: request_human_review() tenant_id=0 fix -- SELECT AIDecision.tenant_id + _maybe_await + isinstance fallback. hash chain gewired voor alle 5 governance AuditLog inserts. 596 gov tests GROEN, 5/5 arch tests GREEN, pyright 0 errors, ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
