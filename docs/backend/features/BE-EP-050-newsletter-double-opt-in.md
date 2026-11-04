# Feature-spec: BE-EP-050 Foundation Newsletter Double Opt-in Verification API

**ID:** `BE-EP-050`  
**Onderwerp:** Foundation Nieuwsbrief Dubbele Opt-in Verificatie & Bevestigingsstroom  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1 / P2 Erfgoedportaal Nieuwsbrief  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

In het Levend Monument erfgoedplatform kunnen burgers, nabestaanden en geinteresseerden zich aanmelden voor de periodieke nieuwsbrief met erfgoedverhalen en aankondigingen.

Om te voldoen aan artikel 7 lid 1 AVG (actieve bewijslast voor ondubbelzinnige toestemming) en om te voorkomen dat willekeurige e-mailadressen van derden worden ingeschreven, is de aanmeldstroom ingericht als een volledige **Double Opt-in** flow:
1. `POST /{tenantSlug}/foundation/newsletter/subscribe`: Initialiseert de inschrijving met status `PENDING_OPT_IN`, legt toestemmingsmetadata vast (`consent_ip`, `consent_user_agent`, `created_at`), genereert een cryptografisch veilig 32-byte confirm token (gehasht via SHA-256 opgeslagen) en verstuurt een verificatie-e-mail via Brevo met een verificatieknop.
2. `POST /{tenantSlug}/foundation/newsletter/confirm`: Valideert het `confirm_token` tegen `confirm_token_hash`, controleert de 7-dagen TTL, wist `confirm_token_hash = None` (bescherming tegen replay-aanvallen), zet status op `SUBSCRIBED` met `confirmed_at = utc_now()`, genereert een unieke `unsubscribe_token_hash` en verstuurt de welkomstmail inclusief uitschrijflink via Brevo.
3. `GET /{tenantSlug}/foundation/newsletter/confirm`: Retourneert een `HTTP 307 Temporary Redirect` naar de frontend portal `/nieuwsbrief?confirm={token}&email={email}&tenant={tenantSlug}`. Muteert geen databasestatus op GET (beschermt tegen automatische linkscanners van anti-spam firewalls zoals Outlook SafeLinks).
4. `GET /{tenantSlug}/foundation/newsletter/unsubscribe`: Retourneert een `HTTP 307 Temporary Redirect` naar de frontend portal `/nieuwsbrief?unsubscribe=true&email={email}&token={token}&tenant={tenantSlug}`.
5. `POST /{tenantSlug}/foundation/newsletter/unsubscribe`: Valideert de `unsubscribe_token_hash`, zet status op `UNSUBSCRIBED` met `unsubscribed_at = utc_now()` en logt een audit-event.

---

## 2. API Contract

### A. Aanmelden: `POST /{tenantSlug}/foundation/newsletter/subscribe`
- **Public pad:** Ja (`public_registry.py`).
- **Rate limit:** `require_portal_newsletter_rate_limit` (3/uur per IP).
- **Bot guard:** `@require_hcaptcha`.
- **Request Body:** `{"email": "naam@voorbeeld.nl", "hcaptcha_token": "..."}`
- **Respons (201 Created):** `{"message": "Subscription request received."}` (geen e-mail enumeratie).

### B. Bevestigen: `POST /{tenantSlug}/foundation/newsletter/confirm`
- **Public pad:** Ja.
- **Rate limit:** `require_portal_newsletter_rate_limit`.
- **Request Body (`NewsletterConfirmRequest`):**
```json
{
  "email": "naam@voorbeeld.nl",
  "token": "<32-byte-token>"
}
```
- **Respons (200 OK):** `{"message": "Subscription confirmed."}`

### C. Redirect Links (Scanners Safe):
- `GET /{tenantSlug}/foundation/newsletter/confirm?email={email}&token={token}` -> `307 Redirect` naar `{portal_url}/nieuwsbrief?confirm={token}&email={email}&tenant={tenantSlug}`
- `GET /{tenantSlug}/foundation/newsletter/unsubscribe?email={email}&token={token}` -> `307 Redirect` naar `{portal_url}/nieuwsbrief?unsubscribe=true&email={email}&token={token}&tenant={tenantSlug}`

### D. Uitschrijven: `POST /{tenantSlug}/foundation/newsletter/unsubscribe`
- **Request Body (`NewsletterUnsubscribeRequest`):** `{"email": "naam@voorbeeld.nl", "token": "<unsub-token>"}`
- **Respons (200 OK):** `{"message": "Unsubscribe request received."}`

---

## 3. Beveiliging, Privacy & Compliance (AVG / Telecommunicatiewet)

- **Actieve bewijslast (art. 7 lid 1 AVG):** Vastlegging van `consent_ip`, `consent_user_agent`, `created_at` en `confirmed_at`.
- **Replay Attack Preventie:** `confirm_token_hash` wordt na validatie onmiddellijk op `None` gezet.
- **Token Expiratie:** 7 dagen Time-to-Live (TTL) vanaf registratietijdstip.
- **Anti-Enumeratie:** Alle responsen geven neutrale succesmeldingen terug.
- **Anti-Bot Click Bescherming:** Statusmutaties vinden uitsluitend plaats via `POST`; `GET`-verzoeken van e-mailscanners muteren geen status.
- **Audit Logging:** Elk opt-in verzoek, bevestiging en uitschrijving wordt vastgelegd via `AuditService.log_event` met gemaskeerd e-mailadres (`u***@e***.nl`).

---

## 4. Trainingssamenvatting

- **Actor**: Portaalbezoeker / Nieuwsbriefabonnee
  - **Flow**: De bezoeker meldt zich aan op `/nieuwsbrief` en ontvangt een verificatiemail via Brevo. Na het klikken op de verificatielink wordt de gebruiker via een scanner-veilige GET-redirect naar de frontend geleid, waar een POST naar `/newsletter/confirm` de inschrijving bevestigt en de status activeert conform AVG artikel 7.
- **Actor**: Beheerder
  - **Flow**: De beheerder kan inzien dat abonnees aantoonbaar dubbel opt-in zijn bevestigd met tijdstip en IP-vastlegging, zonder risico op ongeldige inschrijvingen door derden.

