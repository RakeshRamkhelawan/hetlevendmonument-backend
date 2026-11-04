# Feature-spec: BE-EP-048 Foundation Contact Form & Support API

**ID:** `BE-EP-048`  
**Onderwerp:** Foundation Contact Formulier en Ondersteuning Endpoint  
**Aanmaakdatum:** 2026-09-12  
**Status:** In Review  
**Sprint / Context:** ADR-029 P2 Contact & Community Support  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

In het Levend Monument erfgoedplatform hebben burgers, nabestaanden, docenten en culturele partners behoefte aan een betrouwbaar contactpunt voor vragen over archiefmateriaal, verhalen, gastlessen of samenwerkingsverbanden.

Voorheen ontbrak een publiek contactendpoint en was de frontend niet aangesloten op de backend. Dit endpoint (`POST /{tenantSlug}/foundation/contact`) voorziet in:
- Categorisering van contactvragen (`algemeen`, `educatie`, `donatie`, `archief`, `samenwerking`).
- Anti-bot en form-spam mitigatie via hCaptcha (`@require_hcaptcha`).
- Rate limiting via `portal_public_write_limit` (max 30 verzoeken per minuut).
- Toewijzing van een uniek referentie-ID (`CON-YYYYMMDD-XXXX`) voor follow-up communicatie.
- Doorgifte naar de geconfigureerde contactpersoon van de stichting (`FoundationPortalSettings.contact_email`).
- Gestructureerde audit logging (`log_audit_event`).

---

## 2. API Contract

### Endpoint: `POST /{tenantSlug}/foundation/contact`

**Public pad:** Ja (geregistreerd in `public_registry.py`).  
**Rate limit:** `portal_public_write_limit`.  
**Bot guard:** `@require_hcaptcha`.  

**Request Body (`ContactSubmissionRequest`):**
```json
{
  "name": "Jan de Vries",
  "email": "jan@voorbeeld.nl",
  "subject": "Vraag over foto archief Ketikoti",
  "category": "archief",
  "message": "Geachte redactie, ik heb een vraag over een foto uit 1975...",
  "hcaptcha_token": "optional-mock-or-live-token"
}
```

**Validatieregels:**
- `name`: String, 2 - 120 tekens, niet-leeg na strip.
- `email`: String, conform RFC e-mail regex, lowercase genormaliseerd.
- `subject`: String, 3 - 200 tekens.
- `category`: Enum (`algemeen`, `educatie`, `donatie`, `archief`, `samenwerking`).
- `message`: String, 10 - 5000 tekens.
- `hcaptcha_token`: Optioneel (verplicht in productie met geactiveerde hCaptcha).

**Response Body (`ContactSubmissionResponse`):**
```json
{
  "reference_id": "CON-20260912-A1B2",
  "status": "received",
  "message": "Uw bericht is succesvol ontvangen. Ons team neemt zo spoedig mogelijk contact met u op.",
  "created_at": "2026-09-12T11:00:00Z"
}
```

---

## 3. Beveiliging & Tenant-Isolatie

- **Tenant Resolutie:** Slug wordt gevalideerd via `get_current_tenant_id()` en `validate_slug()`.
- **Bot Protectie:** hCaptcha verificatie via `@require_hcaptcha` voorkomt scraping en geautomatiseerde mailbombing.
- **Audit Logging:** Contactverzoeken worden audit-proof geregistreerd met tenant-id en categorie (zonder gevoelige berichtbody in open logs).

---

## 4. Trainingssamenvatting

- **Actor**: Bezoeker / Indiener (Burger, Docent of Onderzoeker)
  - **Flow**: De bezoeker navigeert naar het contactformulier op `/contact`, vult naam, e-mailadres, onderwerp, categorie en bericht in en lost optioneel de hCaptcha-uitdaging op. Bij het verzenden stuurt de frontend een POST verzoek naar `/{tenantSlug}/foundation/contact`. Het endpoint valideert de tenant, rate limiting en hCaptcha, kent een traceerbaar referentienummer (`CON-YYYYMMDD-XXXX`) toe en logt een gestructureerd audit-event. De bezoeker ontvangt een HTTP 200 met het referentie-ID en ontvangstbevestiging.
- **Actor**: Stichtingsbeheerder / Curator
  - **Flow**: De beheerder ontvangt een notificatie over het contactverzoek en kan de follow-up direct koppelen aan het unieke referentienummer `CON-YYYYMMDD-XXXX`.
