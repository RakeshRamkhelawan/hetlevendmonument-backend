# BE-SVC-004: Password Reset Email Service

**Sprint:** SP-E01
**Datum:** 2026-05-28
**Status:** APPROVED

---

## Samenvatting

Implementatie van echte e-mail verzending voor het password reset flow, met verwijdering van PII (token + e-mailadres) uit applicatie-logs.

---

## Trainingssamenvatting

| Veld | Inhoud |
| --- | --- |
| Actor | Niet-ingelogde gebruiker die wachtwoord wil resetten |
| Voorwaarde | Gebruiker kent zijn e-mailadres; SMTP geconfigureerd via env |
| Actie | POST /auth/forgot-password met `{"email": "..."}` |
| Systeemreactie | Genereert reset-token; stuurt e-mail via fire-and-forget task; logt GEEN PII |
| Succesrespons | HTTP 200 + `{"message": "If the email exists, a reset link has been sent"}` |
| Foutrespons | HTTP 422 ongeldige invoer; HTTP 500 systeemerror |
| Uitzonderingen | SMTP leeg: warning + 200; onbekend adres: identieke 200 (enumeratie-preventie) |

---

## Wijzigingen

### Nieuwe functie

- `src/core/services/email.py::send_password_reset_email(to_email: str, reset_url: str) -> None`
  - Gebruikt bestaande `EmailTemplateEngine` met `password_reset.html` template
  - Gebruikt bestaande `get_email_service()` factory (SMTPEmailService in prod, ConsoleEmailService in dev)
  - PII-vrije logging

### Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/api/auth/router.py` | Verwijderd TODO + token logging; toegevoegd `send_password_reset_email` aanroep; rate limiting (3/min forgot, 5/min reset); PTI uit security events verwijderd |
| `src/core/services/email.py` | `send_password_reset_email` toegevoegd; PII logging verwijderd uit `ConsoleEmailService` en `SMTPEmailService`; TLS config gefixt (587=STARTTLS, 465=implicit TLS); `EMAIL_FROM` env var ondersteuning; `SMTP_USER` fallback |
| `src/core/integrations/email_executor.py` | PII logging verwijderd; f-strings in logger vervangen door %s formatting |
| `requirements-base.txt` | `aiosmtplib>=3.0.0` toegevoegd |
| `.env.example` | `EMAIL_FROM` en `FRONTEND_URL` toegevoegd |

---

## Beveiliging

- Rate limiting: forgot-password 3/min, reset-password 5/min
- Fire-and-forget email dispatch normaliseert response tijd (enumeratie-preventie)
- Identieke 200 response voor bekend en onbekend e-mailadres
- Geen token, e-mailadres, of user.id in applicatie-logs
- Security event details bevatten geen raw email (ADR-019)

---

## Tests

| Test | Status |
| --- | --- |
| `test_sp_e01_password_reset_email.py` | 15/15 PASSED |
| `test_email_service.py` | 9/9 PASSED (regressie) |
| `test_neo_auth_endpoints.py` (relevant) | 5/5 PASSED, 1 xpassed (regressie) |

---

ID: BE-SVC-004 | Eigenaar: Rakesh Ramkhelawan
