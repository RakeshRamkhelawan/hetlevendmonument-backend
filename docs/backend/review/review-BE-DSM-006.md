# Code Review: BE-DSM-006 -- api/learning.py Strangler Fig

**Reviewer:** Claude (code-reviewer + quality-reviewer subagents)
**Sprint:** SP-DSM-002 Dag 2 + Dag 2b (security hardening)
**Datum:** 2026-06-16
**Verdict:** APPROVED

---

## Dag 2 -- Bevindingen opgelost voor commit bb1b70f1

| # | Ernst | Bevinding | Status |
|---|-------|-----------|--------|
| C-1 | CRITICAL | HAS_DB anti-pattern verwijderd | OPGELOST |
| C-2 | CRITICAL | tenant_id="default" -> require_tenant_id() + str() cast | OPGELOST |
| C-3 | CRITICAL | f-string loggers -> %s + exc_info=True | OPGELOST |
| C-4 | CRITICAL | Inline imports -> top-level via dependencies.py | OPGELOST |
| C-5 | CRITICAL | db: Any -> db: AsyncSession = Depends(get_db) | OPGELOST |
| H-1 | HIGH | db is None guards verwijderd (dead code na C-1 fix) | OPGELOST |
| F1 | BLOCKER | process_feedback bestaat niet op module-niveau in feedback.py | OPGELOST (verwijderd uit dependencies.py) |
| F2 | BLOCKER | router.py > 200 regels (337 regels) | OPGELOST (hook splitste in rules_router + analytics_router) |

---

## Dag 2b -- Onafhankelijke review bevindingen opgelost voor commit 85dd9fa8

| # | Ernst | Bevinding | Status |
|---|-------|-----------|--------|
| SEC-C1 | CRITICAL | submit_feedback: geen auth + geen tenant_id in queue-payload | OPGELOST |
| SEC-C2 | CRITICAL | Alle 6 analytics endpoints: geen auth, geen tenant-isolatie | OPGELOST |
| SEC-H1 | HIGH | GET /rules: hardcoded limit=100, geen paginering | OPGELOST |
| SEC-H2 | HIGH | rule_type + feedback_type: open str, geen allowlist | OPGELOST (Literal) |
| SEC-H3 | HIGH | Geen max_length op string-inputs (DoS + prompt-injection) | OPGELOST |
| SEC-H4 | HIGH | GET /regional/context: deployment-topologie zonder auth | OPGELOST (require_tenant_id) |
| SEC-H5 | HIGH | created_at: placeholder datetime.now() ipv ORM-waarde | OPGELOST |
| SEC-M1 | MEDIUM | require_tenant_id() binnen try-block: auth-fout -> HTTP 500 | OPGELOST |
| SEC-L1 | LOW | hourly_cost: geen upper bound | OPGELOST (le=10000) |
| SEC-L2 | LOW | RuleResponse.Config: Pydantic v1-stijl | OPGELOST (ConfigDict) |

---

## Openstaande bevindingen (pre-existing / backlog)

| # | Ernst | Bevinding | Actie |
|---|-------|-----------|-------|
| OG-1 | NOTE | OversightGate re-export in agentic/dependencies.py | GESLOTEN: websocket.py is legitieme caller via ADR-033 eigen-domein facade. Correct patroon. |
| BL-1 | MEDIUM | get_learning_metrics + get_roi_report: cross-tenant aggregates | Backlog: analytics.py moet tenant_id accepteren (service-laag aanpassing) |
| BL-2 | MEDIUM | Geen rate limiting op endpoints | Backlog SP-SEC-xxx |
| BL-3 | LOW | list_insights: stub retourneert [] | Backlog: implementatie vereist DB-query |
| BL-4 | LOW | FeedbackProcessingService: in dependencies.py, nooit gebruikt | Backlog: opruimen bij volgende DSM-sprint |

---

## ADR-033 check

- [x] dependencies.py als Facade aggregation layer
- [x] router.py <= 200 regels (16 regels)
- [x] rules_router.py <= 200 regels (167 regels)
- [x] analytics_router.py <= 200 regels (171 regels)
- [x] Geen directe forbidden imports in router-bestanden
- [x] 5 nieuwe ignore_imports entries in .importlinter

## ADR-003 check

- [x] require_tenant_id() op ALLE endpoints (raises 401 bij None)
- [x] str(tenant_id) voor AdaptationRuleService (verwacht str, krijgt int van JWT)
- [x] tenant_id geinjected in feedback queue-payload

## Kwaliteitscheck

- [x] ruff check: All checks passed
- [x] pyright: 0 errors (baseline gehandhaafd)
- [x] ASCII-only: geen emoji/non-ASCII
- [x] Logger: %s patroon + exc_info=True
- [x] Geen hardcoded secrets
- [x] Literal types voor enum-achtige string fields
- [x] max_length constraints op alle user-input strings

## Architectuurcheck

- [x] Violation scanner: 127 -> 117 (-10)
- [x] test_api_learning_py_violations_zero: PASSED
- [x] 3 overige xfails intact (main.py, lifecycle.py, prana)
- [x] 150 architecture tests passed, 19 xfailed

---

**Conclusie:** APPROVED. Alle CRITICAL en HIGH bevindingen opgelost. Backlog-items
gedocumenteerd. OversightGate gesloten: re-export is correct (websocket.py is legitieme caller).
