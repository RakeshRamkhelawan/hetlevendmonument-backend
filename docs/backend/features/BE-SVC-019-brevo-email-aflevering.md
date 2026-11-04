# Feature-spec: BE-SVC-019 Brevo Transactional Email Service & Webhook Monitoring

**ID:** `BE-SVC-019` / `BE-EP-049`  
**Onderwerp:** Brevo E-mailaflevering, Contactnotificaties, Magic-Link Routering & Bounce Webhooks  
**Aanmaakdatum:** 2026-09-14  
**Status:** Geïmplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1-5 Brevo Transactionele E-mail Integratie  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

Voor Het Levend Monument (ADR-029) is betrouwbare e-mailaflevering essentieel voor:
1. **Magic Link Inloggen:** Bezoekers en curatoren kunnen wachtwoordloos inloggen via een unieke cryptografische token.
2. **Notice & Takedown (NTD):** Bevestigingen van meldingen van ongepaste content conform de NTD-gedragscode.
3. **Nieuwsbrief:** Double opt-in bevestigingsmail met veilige HMAC/SHA-256 uitschrijflink.
4. **Contactformulier & Community Support:** Ontvangstbevestiging naar de indiener met referentie (`CON-YYYYMMDD-XXXX`) en notificatie naar de stichtingscurator (`FoundationPortalSettings.contact_email`).
5. **Brevo Webhook & Bounce Monitoring:** Callback endpoint voor verwerking van hard bounces, spam-klachten en uitschrijvingen, ter bescherming van de verzendreputatie en naleving van de AVG/GDPR.

---

## 2. Architectuur & Componenten

### 2.1 Connector & Service Laag

- **`BrevoClient` (`src/core/connectors/brevo.py`):**
  - Directe asynchrone HTTP client voor Brevo REST API v3 (`https://api.brevo.com/v3/smtp/email`).
  - Veilige dev/test simulatiemodus met in-memory registratie (`sent_emails`) en automatische PII-e-mailmaskering (`u***@e***.com`).
  - `reply_to` ondersteuning voor notificaties zodat de curator direct kan antwoorden op de indiener.

- **`BrevoEmailService` (`src/core/services/brevo_email_service.py`):**
  - Biedt templates en methoden voor alle erfgoedportal stromen:
    - `send_magic_link`
    - `send_takedown_confirmation`
    - `send_newsletter_confirmation`
    - `send_contact_confirmation`
    - `send_contact_notification`

### 2.2 Magic-Link Browser Flow & Routering

- E-mails bevatten een link naar de frontend applicatie:  
  `{base_url}/inloggen?token={raw_token}&tenant={tenantSlug}`
- Mocht een gebruiker of mailclient toch rechtstreeks het backend endpoint openen via een `GET`-verzoek, dan vangt `GET /{tenantSlug}/foundation/auth/magic-link/verify` dit op en stuurt een `HTTP 307 Temporary Redirect` naar de frontend inlogpagina.

### 2.3 Webhook & Bounce Monitoring (`BE-EP-049`)

- **Endpoint:** `POST /{tenantSlug}/foundation/webhooks/brevo`
- **Authenticatie:** Optioneel configureerbaar via `BREVO_WEBHOOK_SECRET` (`X-Webhook-Secret` of `X-Brevo-Secret` header).
- **Verwerking:**
  - `hard_bounce`, `blocked`, `spam` -> Update `NewsletterSubscription.status = NewsletterStatus.BOUNCED`
  - `unsubscribe`, `unsubscribed` -> Update `NewsletterSubscription.status = NewsletterStatus.UNSUBSCRIBED`
  - Audit logging via `AuditService.log_event` voor alle bounce- en veiligheidsevents.

---

## 3. Verificatie & Testdekking

- **Unit tests connector & service:** `tests/unit/test_brevo_email.py`
- **Unit tests contact integratie:** `tests/unit/test_foundation_contact.py`
- **Integratietests webhooks & magic-link redirect:** `tests/integration/api/v1/foundation/test_brevo_webhook.py`

---

## 4. Trainingssamenvatting

- **Actor**: Beheerder / E-mail Gateway (Brevo Webhook)
  - **Flow**: Brevo triggert `POST /{tenantSlug}/foundation/webhooks/brevo` bij statuswijzigingen (hard bounces, spam complaints of uitschrijvingen). De webhook verwerkt de payload, markeert het abonneerecord in PostgreSQL als `BOUNCED` of `UNSUBSCRIBED`, en legt een auditlog vast ter bescherming van de verzendreputatie.
- **Actor**: Portaalbezoeker
  - **Flow**: De bezoeker vraagt een magic-link inlogverzoek aan. BrevoEmailService genereert en verzendt een e-mail met een beveiligde frontend link. Indien de gebruiker rechtstreeks de backend URL opent, stuurt het endpoint een 307 redirect naar de frontend inlogomgeving.

