# Review BE-GOV-017: Fix tenant_id=0 in request_human_review

**Datum:** 2026-06-26
**Sprint:** SP-DLP-005 Dag 1
**Reviewer:** self-review (< 20 regels, 1 bestand -- quality-gates.md)

---

## Self-review checklist

| Check | Resultaat |
|-------|-----------|
| `tenant_id` NOOIT uit request body | N.v.t. (lookup uit DB, niet request) |
| `datetime.now(timezone.utc)` | Aanwezig -- `audit_entry.timestamp = datetime.now(timezone.utc)` |
| `best_effort` wrapper | Aanwezig -- lookup valt binnen bestaande `best_effort` block |
| `_maybe_await` voor mock-compat | Aanwezig -- `await _maybe_await(_tid_result.scalar_one_or_none())` |
| `isinstance(int)` fallback | Aanwezig -- degraded mode als decision niet bestaat |
| `logger.warning` bij degraded | Aanwezig |
| `# noqa: PLC0415` op HashChainVerifier import | Aanwezig (via `_populate_hash_chain`) |
| Pyright 0 errors | GROEN |
| Ruff clean | GROEN |

---

## Verificatie

| Check | Resultaat |
|-------|-----------|
| Arch test `test_request_human_review_audit_has_real_tenant_id` | GROEN (was intentioneel RED) |
| Alle 5 arch tests `test_adr019_hash_chain_wired.py` | 5/5 GROEN |
| TDD unit test `test_request_human_review_resolves_tenant_id_from_decision` | GROEN |
| Governance unit suite | 596 GROEN, 0 failures |

---

## Verdict: **APPROVED**

Kleine chirurgische fix (1 methode, 1 bestand). Alle pre-existing tests hersteld.
ADR-019 hash chain volledig gewired voor alle 5 governance AuditLog inserts.
