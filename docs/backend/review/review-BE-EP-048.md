# Code Review: BE-EP-048 Foundation Contact Form & Support API

**Feature ID:** `BE-EP-048`  
**Onderwerp:** Foundation Contact Formulier en Ondersteuning Endpoint  
**Reviewer:** Red Team / Shadow CEO  
**Datum:** 2026-09-12  
**STATUS: APPROVED**  

---

## 1. Doel & Beoordeling

Het doel van `BE-EP-048` is het bieden van een veilig, robuust en bot-beschermd contact-endpoint voor bezoekers en organisaties van Levend Monument stichtingen.

### Pluspunten
- Validatie van categorie via een strikt Pydantic-enum.
- `@require_hcaptcha` voorkomt scraping, form-spam en Denial of Service op e-mailtransporters.
- Toepassing van `portal_public_write_limit` (max 30 verzoeken per minuut per IP).
- Veilige referentienummer-generatie (`CON-YYYYMMDD-XXXX`).
- Gevoelige berichtteksten worden niet in openbare logs gedumpt; alleen audit-metagegevens (tenant_id, categorie, referentie).

---

## 2. Devil's Advocate (Red Team Mandaat)

### Waarom deze oplossing in de toekomst kan falen
1. **Mailbox Saturatie & Spam Doelwitten:** Zodra hCaptcha in lokale ontwikkel- of testmodus staat met fallback-tokens, kan een geautomatiseerd script de stichtingsmailbox vol laten lopen als er geen strikte e-mail-aflevering deduplicatie is. In productie is hCaptcha met score threshold daarom verplicht.
2. **Onbestelbare Berichten:** Als een stichting een ongeldig `contact_email` instelt in haar instellingen (`FoundationPortalSettings`), kunnen notificaties stil bouncen. De service moet daarom defensief omgaan met afleverfouten en altijd de inzending registreren in de database/audit log zodat geen burgerberichten verloren gaan.

**Oordeel:** GO (STATUS: APPROVED).
