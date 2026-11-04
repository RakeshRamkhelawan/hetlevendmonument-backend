# Feature-spec: BE-EP-051 Foundation Notice & Takedown Curation & Resolution API

**ID:** `BE-EP-051`  
**Onderwerp:** Foundation Notice & Takedown Curator Moderatie, Content Statusverwijdering & Notificatiestroom  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1 / P2 Erfgoedportaal Curatie & NTD Compliance  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

In het Levend Monument erfgoedplatform kunnen burgers, rechthebbenden en nabestaanden via het publieke meldpunt (`POST /{tenantSlug}/foundation/takedown`) melding maken van vermeende inbreuken (auteursrecht, portretrecht, smaad, laster, of AVG/privacybezwaren).

Om te voldoen aan **artikel 6:196c lid 4 BW**, de **Nederlandse Gedragscode Notice and Take Down (NTD)** en **artikel 16 en 17 van de EU Digital Services Act (DSA)**, moeten curatoren en beheerders binnengekomen meldingen zorgvuldig kunnen onderzoeken, motiveren en afhandelen:
1. `GET /{tenantSlug}/foundation/admin/curatie/takedowns`: Biedt een gepagineerde en gefilterde lijst (`pending`, `approved`, `rejected`, `escalated`) van alle takedown-verzoeken voor de actieve tenant, inclusief gekoppelde erfgoedcontent-metadata.
2. `GET /{tenantSlug}/foundation/admin/curatie/takedowns/{takedown_id}`: Biedt een diepgaand inspectie-overzicht van een specifiek verzoek, inclusief de volledige beschrijving, media URL en contactgegevens van de melder.
3. `PUT /{tenantSlug}/foundation/admin/curatie/takedowns/{takedown_id}`: Verwerkt het besluit van de curator.
   - Bij `status = APPROVED`: Het erfgoeditem wordt direct op status `ContentStatus.REMOVED` gezet, met vastlegging van `takedown_at = utc_now()` en `takedown_reason = resolution_note`. Het item is per direct niet meer opvraagbaar via publieke endpoints (`/content`, `/map/bbox`, `/sitemap.xml`) en wordt in OAI-PMH harvest gemarkeerd als deleted.
   - Bij `status = REJECTED`: De melding wordt afgewezen als ongegrond. Het erfgoeditem blijft ongewijzigd gepubliceerd.
   - Bij `status = ESCALATED`: De melding wordt in beraad gehouden voor bestuursbesluitvorming of juridisch advies.
   - In alle gevallen wordt de melder per e-mail via Brevo (`send_takedown_resolution`) conform DSA Art. 16 lid 5 geïnformeerd over het besluit inclusief de schriftelijke motivering (`resolution_note`).
4. `POST /{tenantSlug}/foundation/admin/curatie/{content_id}/restore`: Biedt een beheerder/curator de mogelijkheid om een offline gehaald item na een gegrond tegenbericht/bezwaar weer in ere te herstellen (`status = ContentStatus.APPROVED`).

---

## 2. API Contract

### A. Lijst Meldingen: `GET /{tenantSlug}/foundation/admin/curatie/takedowns`
- **Autorisatie:** `require_curator` (Curator of Admin role).
- **Query parameters:** `status: str | None`, `page: int = 1`, `page_size: int = 20`.
- **Respons (200 OK):** `TakedownListResponse`
```json
{
  "items": [
    {
      "id": 10,
      "content_id": 42,
      "content_title": "Havenfoto 1920",
      "content_type": "artwork",
      "content_status": "approved",
      "requester_name": "Pieter Post",
      "requester_email": "pieter@example.com",
      "legal_basis": "Auteursrechtclaim",
      "status": "pending",
      "resolution_note": null,
      "resolved_at": null,
      "created_at": "2026-09-15T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "status_filter": "pending"
}
```

### B. Afhandelen Melding: `PUT /{tenantSlug}/foundation/admin/curatie/takedowns/{takedown_id}`
- **Autorisatie:** `require_curator`.
- **Request Body (`TakedownResolveRequest`):**
```json
{
  "status": "approved",
  "resolution_note": "Auteursrecht geverifieerd via archief; content offline conform art. 6:196c BW.",
  "notify_requester": true
}
```
- **Respons (200 OK):** `TakedownResolveResponse`

### C. Herstellen Item: `POST /{tenantSlug}/foundation/admin/curatie/{content_id}/restore`
- **Autorisatie:** `require_curator`.
- **Respons (200 OK):** `FoundationContentDetail` met status `approved` en gewiste `takedown_reason`.

---

## 3. Beveiliging, Compliance & Kwaliteit

- **Multi-tenant Isolatie:** Verzoeken worden strikt gefilterd op `tenant_id == tenant.id`.
- **Geen Hard Delete:** Inbreukmakend materiaal blijft gearchiveerd op `status = REMOVED` t.b.v. wettelijke bewijslast en geschillenbeslechting.
- **Audit Logging (ADR-019):** Elk besluit logt `takedown_resolved` (severity: "high") in `RequestAuditLog` met identificatie van de behandelend curator.

---

## 4. Trainingssamenvatting

- **Actor**: Stichtingscurator / Moderator
  - **Flow**: De curator opent het beheeroverzicht op `/admin/curatie` en selecteert het tabblad 'Notice & Takedown'. De curator inspecteert een binnengekomen melding, controleert de juridische grondslag en het erfgoeditem, en opent het beoordelingsmodal. Bij gegrondverklaring (`approved`) vult de curator een schriftelijke motivering in (minimaal 5 tekens). Het backend zet het erfgoeditem direct op `REMOVED`, archiveert de reden en het tijdstip, informeert de melder conform DSA Art. 16(5) via Brevo, en logt een high-severity auditlog event.
- **Actor**: Rechtenhouder / Melder
  - **Flow**: De melder dient via het publieke formulier een NTD-verzoek in en ontvangt direct na het curatorbesluit een transparante en gemotiveerde kennisgeving per e-mail over de uitkomst en genomen maatregelen.

