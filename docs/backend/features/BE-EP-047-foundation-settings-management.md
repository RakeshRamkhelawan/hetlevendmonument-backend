# Feature Specification: BE-EP-047 Foundation Portal Settings & White-Label Branding Endpoints

**Feature ID:** `BE-EP-047`  
**Onderdeel:** Backend Foundation API (`src/core/api/v1/foundation/settings.py`, `src/core/api/v1/foundation/schemas.py`)  
**Sprint / Taak:** ADR-029 White-Label Branding & Settings Management  
**Status:** In Development  

---

## 1. Doel & Scope
Het Levend Monument / SanskritiSetu platform host diverse culturele en historische erfgoedorganisaties in een multi-tenant architectuur. Om het platform werkelijk white-label te maken voor stichtingen zoals Stichting Ketikoti Vlaardingen, moeten curatoren en beheerders de merk- en presentatie-instellingen van hun stichting zelfstandig kunnen beheren via de API.

Deze specificatie dekt:
1. `PortalSettingsUpdateRequest` Pydantic v2 validatieschema (hex-kleurformaat `#RRGGBB`, tekstlengtes).
2. `PUT /{tenantSlug}/foundation/admin/settings`: Beveiligd endpoint met curator/admin RBAC (`require_curator`).
3. Upsert-mechanisme in PostgreSQL voor `foundation_portal_settings` gekoppeld aan de huidige `tenant_id`.
4. Behoud van publieke `GET /{tenantSlug}/foundation/settings` voor niet-geauthenticeerde portalbezoekers.

---

## 2. API Contracten

### PUT `/{tenantSlug}/foundation/admin/settings`
- **Beveiliging:** JWT met scope `portal_uploader` en rol `admin` of `curator` (`require_curator`).
- **Request Body (`PortalSettingsUpdateRequest`):**
  - `platform_name_nl`: optioneel `str`, 1..120 tekens.
  - `platform_name_en`: optioneel `str`, max 120 tekens.
  - `primary_color`: optioneel `str`, regex `^#[0-9a-fA-F]{6}$`.
  - `accent_color`: optioneel `str`, regex `^#[0-9a-fA-F]{6}$`.
  - `logo_url`: optioneel `str`, max 500 tekens.
  - `favicon_url`: optioneel `str`, max 500 tekens.
  - `guidelines_nl`: optioneel `str`.
  - `guidelines_en`: optioneel `str`.
  - `about_nl`: optioneel `str`.
  - `about_en`: optioneel `str`.
  - `contact_email`: optioneel `str`, max 255 tekens.
- **Response (`PortalSettingsResponse`):** Status 200 OK met de bijgewerkte instellingen.

---

## 3. Beveiliging & Tenant Isolatie
- Geen `tenant_id` in de request payload. De `tenant_id` wordt uitsluitend verkregen uit `public_tenant_scope(tenantSlug, session)`.
- De gebruiker moet geautoriseerd zijn (`require_curator`) en moet behoren tot de opgevraagde tenant (`current_user.tenant_id == tenant.id`).
- Foutafhandeling:
  - 401: Niet ingelogd of ongeldig token.
  - 403: Onvoldoende rechten (rol `visitor`, of andere tenant).
  - 422: Validatiefout (bijvoorbeeld ongeldige hex-code).

---

## Trainingssamenvatting

- **Actor**: Stichtingscurator of Beheerder
  - **Flow**: Curator logt in via magic link en navigeert naar de instellingenpagina in het beheerportaal. Curator past de platformnaam aan naar "Stichting Ketikoti Vlaardingen" en stelt de primaire kleur in op `#8b0000`. De frontend verstuurt een PUT-verzoek naar `/{tenantSlug}/foundation/admin/settings`. De backend verifieert de curator-rechten en tenant-isolatie, valideert het hex-formaat en slaat de gegevens op. Bezoekers zien direct de bijgewerkte huisstijl en platformnaam op de publieke portal.
