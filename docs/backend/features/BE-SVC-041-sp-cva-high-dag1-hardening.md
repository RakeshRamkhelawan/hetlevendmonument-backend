# BE-SVC-041: SP-CVA-HIGH Dag 1 -- CVA Security & Architecture Hardening

**Sprint:** SP-CVA-HIGH Dag 1
**Status:** APPROVED
**Datum:** 2026-06-21

---

## Samenvatting

11 HIGH audit-bevindingen (gegroepeerd in 4 batches) verholpen in de CVA chat pipeline.
Scope: SEC-002/003/008/010/013, BE-003, ARCH-003/005/008/011.

---

## Batch A: Logging en streaming veiligheid

**SEC-003 + SEC-013 (streaming ValueError niet blootstellen):**
`chat_with_cva_streaming()` ving `ValueError` maar stuurde `str(e)` terug als SSE-foutmelding.
Fix: generiek "Chat processing error. Please retry." zonder stack trace.

**BE-003 (exc_info=True in alle except-blokken):**
6 `logger.error()` calls in `chat_router.py` misten `exc_info=True`.
Fix: `exc_info=True` toegevoegd aan alle except-blokken (TimeoutError, LLMTimeoutError, LLMServiceError, ValueError, RateLimitError + streaming equivalenten).

**ARCH-008 (emoji in llm_config.py logs):**
7 logger-aanroepen in `src/core/llm/llm_config.py` bevatten emoji (verboden per CLAUDE.md).
Fix: alle emoji verwijderd; f-string-stijl vervangen door %-format met exc_info=True.

Bestanden: `src/core/api/v1/cva/chat_router.py`, `src/core/llm/llm_config.py`

---

## Batch B: Rate limiter ADR-033 compliance

**SEC-010 (CVA endpoints moeten cva_chat_limit gebruiken, niet consent_update_limit):**
Beide POST-endpoints in `chat_router.py` en het GET-endpoint in `conversations_router.py`
gebruikten `consent_update_limit` (10/min) i.p.v. de juiste `cva_chat_limit` (30/min).

**ADR-033 (geen directe governance imports in router.py):**
`chat_router.py` importeerde `consent_update_limit` direct vanuit `src.core.governance.rate_limiter`.
Fix: `cva_chat_limit` gedefinieerd in `rate_limiter.py`, geexporteerd via `dependencies.py` facade,
geimporteerd in `chat_router.py` en `conversations_router.py` via de facade.

Bestanden: `src/core/governance/rate_limiter.py`, `src/core/api/v1/cva/dependencies.py`,
           `src/core/api/v1/cva/chat_router.py`, `src/core/api/v1/cva/conversations_router.py`

---

## Batch C: Service-laag veiligheid

**SEC-008 (_get_message_history tenant_id filter ontbreekt):**
`CVAService._get_message_history()` filterde NIET op `tenant_id` -- cross-tenant lekrisico.
Fix: `tenant_id: int` toegevoegd als verplichte parameter; WHERE-clausule uitgebreid met
`ConversationMessage.tenant_id == tenant_id`. Beide callers bijgewerkt.

**SEC-002 (model override allowlist ontbreekt):**
`CVAService.chat()` en `chat_stream()` stuurden elk opgegeven model direct naar `LLMService`.
Fix: `_ALLOWED_CVA_MODELS: frozenset[str]` gedefinieerd op module-niveau. Check `model in _ALLOWED_CVA_MODELS` VOOR de `LLMService`-constructie. Onbekende modellen gebruiken de default LLM zonder override.

**ARCH-003 + ARCH-011 (delete_conversation mist audit trail):**
`CVAService.delete_conversation()` soft-deletete zonder audit event.
Fix: `best_effort("cva delete_conversation audit")` wrapping een `governance_bus.emit(AuditLogEmitEvent(...))` na de primaire commit.

Bestanden: `src/core/services/cva_service.py`

---

## Batch D: Test-suite governance fix

**Herstel van test_cva_chat_governance.py:**
De `TestCvaChatGovernance` klasse was volledig `@pytest.mark.skip` vanwege verkeerde patch-targets
(`src.core.api.v1.cva.chat_router.build_council` bestaat niet -- `build_council` zit in `cva_service`).
Fix: skip-marker verwijderd; patches verplaatst naar `src.core.api.v1.cva.chat_router.CVAService`;
`HTTPException(403)` assertions vervangen door `GovernanceVetoError` assertions.

Bestand: `tests/unit/test_cva_chat_governance.py`

---

## Pre-existing fix (out-of-scope, zero-deferral)

**ml/router.py pyright errors:**
`src/core/api/v1/ml/router.py` had 2 pyright `reportUndefinedVariable` errors voor `get_tool_predictor`
(geintroduceerd in commit 5470df2d na de pyright baseline). De `train_predictor()` endpoint had al
een lazy import op regel 73; de andere twee endpoints misten die import.
Fix: `from .dependencies import get_tool_predictor` toegevoegd als lazy import in beide endpoints.

---

## Tests

| Testbestand | Resultaat | Bevinding |
|-------------|-----------|-----------|
| `tests/unit/api/v1/cva/test_sp_cva_sec_streaming_error_disclosure.py` | 3 PASS | SEC-003+013 |
| `tests/unit/services/test_cva_message_history_tenant_isolation.py` | 1 PASS | SEC-008 |
| `tests/unit/api/v1/cva/test_cva_router_logging_exc_info.py` | 2 PASS | BE-003 |
| `tests/unit/api/v1/cva/test_cva_rate_limit_decorator.py` | 5 PASS | SEC-010 + ADR-033 |
| `tests/unit/services/test_cva_soft_delete_audit.py` | 2 PASS | ARCH-003+011 |
| `tests/unit/services/test_cva_model_allowlist.py` | 4 PASS | SEC-002 |
| `tests/unit/test_cva_chat_governance.py` | 4 PASS | ARCH-003+ADR-031 |
| `tests/architecture/test_cva_learning_mixin_decision.py` | 1 PASS | ARCH-005 GESLOTEN (dag 2) |

Totaal: 23 PASS, 0 intentional FAILs (SP-CVA-HIGH volledig gesloten)

---

## ARCH-005 GESLOTEN (SP-CVA-HIGH dag 2, commit b84a661b)

`CVAService` heeft een gedocumenteerde ADR-022 vrijstelling gekregen:
`# ADR-022 exempt: service-laag, geen agent. Learning via council agents in call chain.`

Architecture test `tests/architecture/test_cva_learning_mixin_decision.py` is GROEN.
SP-CVA-HIGH volledig gesloten: alle 11 HIGH bevindingen gefixed.


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-CVA-HIGH Dag 1: 11 HIGH bevindingen (4 batches). SEC-003+013 streaming fout-openbaarmaking. BE-003 exc_info. ARCH-008 emoji-cleanup llm_config. SEC-010+ADR-033 cva_chat_limit via facade. SEC-008 get_message_history tenant_id filter. SEC-002 ALLOWED_CVA_MODELS allowlist. ARCH-003+011 delete_conversation audit. Batch D governance test herschreven. Pre-existing ml/router.py pyright fix. 22/22 PASS. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-CVA-HIGH Dag 1: 11 HIGH bevindingen (4 batches). SEC-003+013 streaming fout-openbaarmaking. BE-003 exc_info. ARCH-008 emoji-cleanup llm_config. SEC-010+ADR-033 cva_chat_limit via facade. SEC-008 get_message_history tenant_id filter. SEC-002 ALLOWED_CVA_MODELS allowlist. ARCH-003+011 delete_conversation audit. Batch D governance test herschreven. Pre-existing ml/router.py pyright fix. 22/22 PASS..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
