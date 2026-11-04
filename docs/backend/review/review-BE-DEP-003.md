# Review BE-DEP-003 -- ProactiveScheduler 7 app.state Dependencies Wiring

**Reviewer:** Laag A pr-review (geintegreerd)
**Datum:** 2026-06-01
**Status:** APPROVED WITH MINOR GAPS

---

## Scope review

`src/core/app_lifespan.py`, `src/core/copilot/proactive/stub_repos.py`,
`tests/unit/test_sp_we_21_proactive_scheduler_deps.py`.

## Bevindingen

### CRITICAL

Geen.

### HIGH

Geen.

### MEDIUM

- **Stubs leveren geen productie-waarde.** Compliance monitors
  (ConsentExpiry, AuditAnomaly, SensitiveWorkflow) zullen geen signalen emitteren
  totdat echte repositories worden gewired. Dit is gedocumenteerd als
  technische schuld en is geaccepteerd binnen de scope van SP-WE-21 (puur wiring).

### LOW

- `StubPrometheusClient` retourneert nul voor alle metrics. Dit maakt
  `WorkflowLatencyMonitor` en `TokenSpikeMonitor` operationeel maar
  signaal-arm. Acceptabel als brug.
- `_wire_proactive_extras()` heeft geen direct return-value voor test-introspectie;
  tests valideren via `app.state.*`. Acceptabel.

## Verificaties

- [x] Geen `tenant_id` uit request body (geen request gerelateerd; lifespan-code).
- [x] Geen hardcoded URLs of secrets ingevoerd.
- [x] ASCII-only in code en commentaren.
- [x] `try/except`-blokken loggen `type(e).__name__` + message + zijn niet-fataal.
- [x] Geen module-level zware imports; alle stubs en singletons lazy geimporteerd
      binnen functies (`_wire_proactive_extras` doet imports in de blokken).
- [x] Idempotent: bestaande `app.state.X` waarden worden niet overschreven.
- [x] Stubs zijn tenant-veilig: retourneren onvoorwaardelijk leeg / False.
- [x] Aanroepvolgorde: `_init_proactive_deps` voor `_init_proactive_scheduler`
      (statisch geverifieerd in tests).

## Tests

- 19/19 PASS in `tests/unit/test_sp_we_21_proactive_scheduler_deps.py`.
- Geen regressies in `tests/unit/` (excl. pre-existing `pyotp` en
  `test_mypy_audit` issues die geen relatie hebben met deze sprint).

## Conclusie

**APPROVED WITH MINOR GAPS** -- akkoord voor merge. Gaps zijn productie-stubs;
spoor op separate follow-up sprints (technische schuld in feature spec gemarkeerd).

---

*Reviewer notes: alle Definition-of-Done items uit de sprint-brief afgevinkt.*
