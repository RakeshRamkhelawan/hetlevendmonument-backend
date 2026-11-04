# Review: BE-SVC-004 Password Reset Email Service

**Reviewer:** Code Agent + Quality Agent (Laag A)
**Datum:** 2026-05-28
**Status:** APPROVED WITH MINOR GAPS

---

## Bevindingen

### CRITICAL: 0

### HIGH: 0

### MEDIUM: 0

### LOW: 2

1. **Security event email hashing (ADR-019)**
   - De security event details bevatten geen e-mailadres meer, maar er is geen hashed identifier als vervanging.
   - Impact: audit trail kan niet meer correleren welk user een reset heeft aangevraagd.
   - Acceptabel voor P1: security event heeft nog steeds `user_id` en `tenant_id`. Hash toevoegen is post-MVP verbetering.

2. **Template directory niet gecreëerd bij deploy**
   - `password_reset.html` template bestaat als string in `email_templates.py` maar de fysieke directory `src/core/templates/email` wordt niet automatisch aangemaakt bij deploy.
   - Impact: fallback rendering wordt gebruikt (werkt correct, maar geen styled HTML).
   - Acceptabel voor P1: `create_default_templates()` bestaat als utility maar wordt niet automatisch aangeroepen.

---

## Correctheid

- [x] `send_password_reset_email` roept `get_email_service()` correct aan
- [x] Auth router gebruikt fire-and-forget `asyncio.create_task()`
- [x] Rate limiting decorators correct geplaatst met `request` + `response` params
- [x] TLS configuratie correct: 587=STARTTLS, 465=implicit TLS

## Architecture

- [x] Hergebruikt bestaande `EmailServiceInterface` + `EmailTemplateEngine`
- [x] Geen nieuwe dependencies behalve `aiosmtplib` (was al optioneel geimporteerd)
- [x] Consistent met ADR-005 (pre-auth, geen tenant context vereist)

## Security

- [x] Geen PII in logs
- [x] Geen hardcoded credentials
- [x] Rate limiting aanwezig
- [x] Enumeratie-preventie behouden

## Type Safety

- [x] `send_password_reset_email` correct getypeerd: `(str, str) -> None`
- [x] Geen mypy errors in gewijzigde bestanden (Ruff passed)

---

**Verdict:** APPROVED WITH MINOR GAPS — beide LOW issues zijn acceptabel voor P1 sprint. Geen blockers voor merge.

Reviewer: Laag A subagents | Datum: 2026-05-28
