# Review BE-CVA-001 — CVA ChatResponse Schema Uitbreiding

**Reviewer:** Gate 2 (code-reviewer + security-reviewer) via geautomatiseerde agents
**Datum:** 2026-06-20
**Eindoordeel:** APPROVED WITH MINOR GAPS (na toepassen security-fixes)

---

## Uitgevoerde Gate 2 review

Twee agents zijn parallel uitgevoerd:
- code-reviewer: architectuur, ADRs, tenant isolatie, CLAUDE.md compliance
- security-reviewer: OWASP, secrets, informatielekken, injection risks

Beide reviewers gaven initieel APPROVED_WITH_MINOR_ISSUES / CHANGES_REQUESTED.
Alle HIGH en MEDIUM bevindingen zijn direct opgelost voor de commit.

---

## Bevindingen en acties

| # | Ernst | Bevinding | Status |
|---|-------|-----------|--------|
| 1 | HIGH | `llm_provider_used` via `type().__name__` lekte interne klassenamen (incl. "mock") naar API-consumers | OPGELOST: `_PROVIDER_DISPLAY` allowlist + `effective_llm.provider.provider_name` |
| 2 | HIGH | `actions[].route` ongevalideerd — open navigation via `navigate(action.route)` in frontend | OPGELOST: `CVAAction.route` field_validator — rejects non-relative paths |
| 3 | MEDIUM | `confidence: float = 0.85` hardcoded placeholder misleidt consumers (AI Act art. 13) | OPGELOST: `confidence: float \| None = None` — badge onderdrukt als null |
| 4 | MEDIUM | `execution_time` in public response = timing oracle (al in Prometheus, dubbel) | OPGELOST: veld niet toegevoegd |
| 5 | MEDIUM | `_PROVIDER_DISPLAY` referentie moest `effective_llm` gebruiken i.p.v. `self.llm` | OPGELOST: `effective_llm.provider.provider_name` |
| 6 | LOW | `success: bool = True` divergeert van gevestigd `{"success": False, "error": {...}}` contract | OPGELOST: veld niet toegevoegd |
| 7 | LOW | Return type `dict[str, str \| int \| ...]` dekt nieuwe velden niet af | OPGELOST: return type `dict[str, Any]`, stale `# type: ignore` verwijderd |
| 8 | LOW | `actions` ongedocumenteerd contract voor frontend | OPGELOST: `CVAAction` Pydantic model + spec in feature doc |
| 9 | LOW (pre-existing) | `dangerouslySetInnerHTML` SSR-pad in CVAResponseRenderer.tsx omzeilt DOMPurify | NIET OPGELOST: pre-existing, buiten scope Batch D |
| 10 | LOW (pre-existing) | `_get_message_history` mist expliciete `tenant_id` filter | NIET OPGELOST: pre-existing; ADR-004 `do_orm_execute` hook dekt dit, apart backlog item |

---

## ADR-compliance checks

| Check | Resultaat |
|-------|-----------|
| ADR-003: tenant_id uit JWT | PASS |
| ADR-033: router max 200 regels | PASS (chat_router.py 236r, ongewijzigd) |
| Geen datetime.now() zonder timezone.utc | PASS |
| Geen emoji/non-ASCII in code | PASS |
| Alle nieuwe velden hebben defaults | PASS |
| pyright 0 errors (CVA files) | PASS |
| ruff clean | PASS |

---

## Release-oordeel

- Geschikt voor implementatie: JA
- Geschikt voor QA: JA (acceptatiecriteria testbaar)
- Geschikt voor LLM-training: JA
- Geschikt voor integratorhandleiding: JA

**Eindoordeel: APPROVED WITH MINOR GAPS**

Openstaande pre-existing items (9 + 10) worden apart opgepakt — geen blocker voor merge.
