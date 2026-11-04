# Review: BE-EP-047 Foundation Settings & White-Label Branding Endpoints

**Feature ID:** `BE-EP-047`  
**Reviewer:** Senior Architect & Security Officer  
**Datum:** 2026-09-12  
**STATUS: APPROVED**  

---

## 1. Doel & Beoordeling
Deze review toetst de backend-implementatie van `BE-EP-047` (`PUT /{tenantSlug}/foundation/admin/settings` en het `PortalSettingsUpdateRequest` schema). De implementatie stelt beheerders en curatoren in staat om white-label branding, contactgegevens en huisstijlen te configureren voor hun erfgoedstichting.

### Sterke Punten:
- **Strikte Hex Validatie:** Kleuren worden gevalideerd via regex `^#[0-9a-fA-F]{6}$`, waarmee CSS/HTML injection via kleurwaarden onmogelijk wordt gemaakt.
- **Tenant Scope & RBAC:** Uitsluitend gebruikers met rol `admin` of `curator` die daadwerkelijk behoren tot de opgevraagde tenant (`current_user.tenant_id == tenant.id`) kunnen de instellingen updaten.
- **Upsert Veiligheid:** Bestaande instellingen worden bijgewerkt via `session.flush()`, en indien voor een nieuwe tenant nog geen instellingenrecord bestaat, wordt een nieuw `FoundationPortalSettings` record aangemaakt.

---

## 2. Devil's Advocate (Red Team Uitdaging)
- **Risico van Gebroken Externe Assets:** Als een beheerder een ongeldige of niet-beschikbare URL invult voor `logo_url` of `favicon_url`, kan dit resulteren in gebroken afbeeldingen in de portal UI of browser console mixed-content waarschuwingen (indien http:// i.p.v. https:// wordt ingevoerd).
  - *Mitigatie:* In het frontend formulier en in Pydantic wordt gecontroleerd dat URL's valide zijn, en de frontend gebruikt fallback avatars en veilige img error handlers (`onError`).
- **Contrast & Toegankelijkheid:** Een beheerder zou een te lichte primaire kleur kunnen instellen met witte tekst, wat de WCAG contrastratio nadelig beïnvloedt.
  - *Mitigatie:* De live preview in `FE-PAGE-014` toont direct het visuele contrast en adviseert contrasterende tinten.
