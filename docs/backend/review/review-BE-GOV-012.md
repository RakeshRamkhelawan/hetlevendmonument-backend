# Review BE-GOV-012: LawfulBasisRegistry Hard-Blocking

**Datum:** 2026-06-26
**Sprint:** SP-DLP-003 Dag 1
**Reviewers:** code-reviewer (agent), quality-reviewer (agent)

---

## Gate 2 bevindingen (3 rondes)

### Ronde 1

| Bevinding | Ernst | Status |
|-----------|-------|--------|
| HTTP 403 semantisch fout voor server-side compliance gap | HIGH | FIXED -- 451 (RFC 7725) |
| `detail` dict breekt `http_exception_handler` (verwacht string) | HIGH | FIXED -- plain string |
| Error message lekt interne compliance-gap informatie | LOW | FIXED -- generieke tekst |

### Ronde 2

| Bevinding | Ernst | Status |
|-----------|-------|--------|
| TDD tests: string-scan te zwak, commentaar kan test groen maken | MEDIUM | FIXED -- regex-proximity pattern (re.DOTALL) |
| `logger.warning` te laag voor hard compliance block | MEDIUM | FIXED -- `logger.error` |

### Ronde 3

| Check | Resultaat |
|-------|-----------|
| 451 geaccepteerd door FastAPI/Starlette | OK -- `starlette.status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS` |
| Plain string detail door `http_exception_handler` | OK -- line 78: `"message": exc.detail` |
| `logger.error` + re-raise: geen dubbele logging | OK -- FastAPI-handler logt geen 4xx |
| Pyright: `raise HTTPException(...) from e` | OK -- 0 errors (baseline gehandhaafd) |
| Ruff: geen f-strings, max 100 chars | OK -- All checks passed |
| Propagatie clean: 451 buiten hoofd-try | OK -- alle 4 blokken buiten `except Exception` wrapper |

---

## Verificatie

- `python -m pyright`: 0 errors (baseline gehandhaafd)
- `ruff check src/core/api/v1/privacy/ src/core/api/v1/gdpr_compliance/`: All checks passed
- TDD tests: 3 GROEN (regex-proximity + logger.error check)
- Bestaande registry tests: 14/14 GROEN

---

## Verdict: **APPROVED**

Gate 2 GO -- 451 correct, propagatie clean, tests sterk genoeg voor productie.
