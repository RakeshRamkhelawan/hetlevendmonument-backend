# Review BE-SVC-060..067: Compliance Sub-Routers Service Injection

## Datum

2026-07-01

## Reviewer

Self-review (implementatie-agent)

## Status

**APPROVED**

## Checklist

- [x] Alle 8 routers: geen directe `get_db`/`AsyncSession`/`select` imports
- [x] Factory-functies correct gedefinieerd in `dependencies.py`
- [x] `best_effort` gebruikt `flush()`, NIET `commit()` -- `pdf_router.py` gecorrigeerd
- [x] Timezone-guard aanwezig voor naive datetime Query-params -- `integrity_verify_router.py`
- [x] Architecture test GROEN
- [x] 99 unit tests passed, 0 failed
- [x] Pyright 0 errors
- [x] tenant_id altijd uit JWT, nooit uit request body
- [x] Geen datetime.now() of datetime.utcnow() -- altijd timezone.utc
- [x] Geen emoji of non-ASCII in code/comments/logs

## Bevindingen

Geen CRITICAL of HIGH bevindingen.
