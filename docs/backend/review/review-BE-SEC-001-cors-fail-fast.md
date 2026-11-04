# Review BE-SEC-001-cors: CORS Fail-Fast Validatie (ADR-035 D4)

**Datum:** 2026-07-01
**Sprint:** AUDIT-SINGLE-TENANT-DB01 S6
**Reviewer:** code-reviewer + security-reviewer (subagents)

## Verdict: APPROVED WITH MINOR GAPS

Twee blockers zijn verwerkt na eerste CHANGES_REQUESTED. Minor gap (dead-code class)
is gedocumenteerd als TODO met backlog-item.

## Verwerkte blockers

| Bevinding | Severity | Status |
|-----------|----------|--------|
| `CORS_ALLOWED_ORIGINS` naam-conflict met bestaand `ALLOWED_ORIGINS` pad | HIGH | FIXED: geen nieuwe env var |
| `CORSMiddleware.__init__` aanpassen breekt `TestCORSMiddlewareDefaults` | HIGH | FIXED: class niet aangeraakt |
| staging `allow_headers: ["*"]` + `allow_credentials: True` ongeldige combinatie | HIGH | FIXED: expliciete headers |
| `validate_cors_config()` verkeerde locatie | HIGH | FIXED: in `security_headers.py` |

## Bekende minor gap (buiten scope S6)

`CORSMiddleware` dead-code class in `security_middleware.py:250-329` heeft nog
wildcard-defaults. Fix vereist red-first commit voor `TestCORSMiddlewareDefaults`.
TODO: volgende sprint.

## Post-fix

| Check | Status |
|-------|--------|
| 4/4 nieuwe CORS tests GROEN | PASS |
| Bestaande `TestCORSMiddlewareDefaults` ongewijzigd GROEN | PASS |
| pyright 0 nieuwe errors | PASS |
| ruff clean | PASS |
| ADR-035 D4 staging wildcard fix | COMPLIANT |
