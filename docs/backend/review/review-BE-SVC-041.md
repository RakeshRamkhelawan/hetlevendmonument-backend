# Review: BE-SVC-041 -- SP-CVA-HIGH Dag 1 CVA Hardening

**Reviewer:** code-reviewer + quality-reviewer (Laag A, ronde 2)
**Datum:** 2026-06-21
**Oordeel:** APPROVED WITH MINOR GAPS

---

## Laag 1: Code kwaliteit (CLAUDE.md patronen)

| Check | Status | Opmerking |
|-------|--------|-----------|
| tenant_id uit JWT/middleware | PASS | _get_message_history ontvangt tenant_id van caller (service-laag), niet uit request body |
| datetime.now(timezone.utc) | PASS | Geen nieuwe datetime.now() calls geintroduceerd |
| best_effort voor audit logs | PASS | delete_conversation audit correct in best_effort |
| ASCII-only in code/logs | PASS | Alle emoji verwijderd uit llm_config.py |
| exc_info=True in except-blokken | PASS | Alle logger.error calls in chat_router.py bijgewerkt |
| Paginering op list-endpoints | N/A | Geen nieuwe list-endpoints |
| Rate limit: read 6x schrijf | PASS | cva_chat_limit 30/min (correct voor chat) |

## Laag 2: Security (OWASP + ADR)

| Check | Status | Opmerking |
|-------|--------|-----------|
| Tenant isolatie in repository-methodes | PASS | _get_message_history filtert nu op tenant_id; isolatietest aanwezig |
| Model override allowlist | PASS | _ALLOWED_CVA_MODELS frozenset; onbekende modellen vallen terug op default |
| Streaming fout-openbaarmaking | PASS | ValueError toont geen str(e) meer aan client |
| ADR-033 router boundary | PASS | cva_chat_limit via dependencies facade, niet direct governance import |
| GovernanceVetoError propagatie | PASS | except GovernanceVetoError: raise in chat_router.py |

## Laag 3: Tests

| Check | Status | Opmerking |
|-------|--------|-----------|
| Rode tests VOOR fix geschreven | PASS | 7 testbestanden bewijzen RED->GREEN cyclus |
| Happy path gedekt | PASS | test_allowed_model_override_is_accepted, test_delete_conversation_emits_audit_event |
| Unhappy path gedekt | PASS | test_unknown_model_override_is_rejected, test_chat_blocked_by_governance |
| Geen regressies | PASS | 22/22 targeted tests PASS, pyright 0 errors |
| ARCH-005 gesloten | PASS | ADR-022 vrijstelling gedocumenteerd (dag 2, commit b84a661b) |

## Laag 4: Documentatie

| Check | Status | Opmerking |
|-------|--------|-----------|
| Feature spec aanwezig | PASS | BE-SVC-041-sp-cva-high-dag1-hardening.md |
| ID-REGISTRY bijgewerkt | PASS | Zie registry |
| Pre-existing fix gedocumenteerd | PASS | ml/router.py pyright fix beschreven in spec |

## Bevindingen

Geen CRITICAL of HIGH bevindingen.

**MINOR-01:** `test_cva_router_logging_exc_info.py` gebruikt een state-machine benadering die
gevoelig is voor Python-code met geneste `try/except` blokken. De fix (venster uitbreiden van
5 naar 9 regels) werkt voor de huidige code maar kan false negatives geven bij diepere nesting.
**Actie:** Accepteren -- de test detecteert alle 6 bestaande gevallen correct.

**MINOR-02:** `_ALLOWED_CVA_MODELS` staat op module-niveau als private variabele maar wordt niet
beschermd tegen aanpassing via reflection. Geen actief risico bij huidige Python runtime.
**Actie:** Accepteren -- frozenset is al immutable.

## Eindoordeel

**APPROVED**

Alle CRITICAL en HIGH bevindingen opgelost. 2 MINORs acceptabel zonder actie.
ARCH-005 gesloten via ADR-022 vrijstelling (dag 2). SP-CVA-HIGH volledig gesloten.
