# Feature-spec: BE-EP-053 Foundation Bulk Curation & Moderation API

**ID:** `BE-EP-053`  
**Onderwerp:** Foundation Bulk Moderatie (Goedkeuren & Afwijzen) met DSA Art. 17 Motiveringsplicht & Partial Success Envelope  
**Aanmaakdatum:** 2026-09-15  
**Status:** Geimplementeerd & Geverifieerd  
**Sprint / Context:** ADR-029 P1 / P2 Erfgoedportaal Curatie & Schaalbaarheid  
**Auteur:** Senior Architect / Developer  

---

## 1. Doel & Context

In het Levend Monument erfgoedplatform kunnen curatoren en stichtingbeheerders ingezonden verhalen, kunstwerken en audiofragmenten beoordelen. Voorheen kon dit uitsluitend één voor één. Bij grootschalige campagnes of erfgoedprojecten met scholen ontstaat echter de behoefte om tientallen inzendingen tegelijk te modereren.

Om te voldoen aan moderne REST standaarden en **artikel 17 van de EU Digital Services Act (DSA)**, biedt de API twee bulk endpoints met gestructureerde resultaten per item:
1. `POST /{tenantSlug}/foundation/admin/curatie/bulk-approve`:
   - Keurt een lijst van content IDs in één enkele database-transactie goed (`status = ContentStatus.APPROVED`).
   - Hanteert een robuust partial-success model (`200 OK` Envelope): items die reeds zijn goedgekeurd of niet bestaan blokkeren geldige items niet, maar worden gerapporteerd in `failed_items`.
2. `POST /{tenantSlug}/foundation/admin/curatie/bulk-reject`:
   - Wijst een lijst van content IDs af (`status = ContentStatus.REJECTED`).
   - Dwingt conform DSA Artikel 17 een motivering af (`rejection_reason`, minimaal 5 tekens, maximaal 1000 tekens).
   - De motivering wordt voor ieder afgewezen item afzonderlijk geregistreerd in het databaserecord en het audittrail.

---

## 2. API Contract

### A. Bulk Goedkeuren: `POST /{tenantSlug}/foundation/admin/curatie/bulk-approve`
- **Autorisatie:** `require_curator` (Curator of Admin role binnen de tenant).
- **Request Body (`BulkApproveRequest`):**
```json
{
  "content_ids": [101, 102, 103]
}
```
- **Respons (200 OK):** `BulkModerationResponse`
```json
{
  "total_requested": 3,
  "processed_count": 3,
  "success_ids": [101, 102],
  "failed_items": [
    { "id": 103, "reason": "Item heeft status 'approved', vereist 'pending'" }
  ],
  "message": "2 item(s) succesvol goedgekeurd. 1 item(s) konden niet worden verwerkt."
}
```

### B. Bulk Afwijzen: `POST /{tenantSlug}/foundation/admin/curatie/bulk-reject`
- **Autorisatie:** `require_curator`.
- **Request Body (`BulkRejectRequest`):**
```json
{
  "content_ids": [201, 202],
  "rejection_reason": "Inzendingen voldoen niet aan de criteria van het erfgoedbeleid."
}
```
- **Respons (200 OK):** `BulkModerationResponse`

---

## 3. Beveiliging, Compliance & Kwaliteit

- **Multi-tenant Isolatie:** Verzoeken worden strikt gefilterd op `tenant_id == tenant.id`. Items van een andere stichting worden geweigerd en gerapporteerd als onvindbaar.
- **DSA Art. 17 Compliance:** Rejection reason is verplicht (min 5 tekens) en wordt per item opgeslagen voor transparantie naar inzenders.
- **Audit Logging (ADR-019):** Beide acties loggen `bulk_content_approved` of `bulk_content_rejected` (severity: "medium") via `AuditService.log_event`.
- **Batch Limiet:** Maximaal 100 items per request om geheugenbeslag en lock-contention op PostgreSQL te voorkomen.

---

## 4. Trainingssamenvatting

- **Actor**: Stichtingscurator / Moderator
  - **Flow**: De curator selecteert in het curatiepaneel via multi-select checkboxes meerdere inzendingen tegelijk. Via de zwevende actiebalk kiest de curator voor "Bulk goedkeuren" of "Bulk afwijzen". Bij afwijzing voert de curator een DSA Art. 17 conforme motivering in. De backend verwerkt de selectie binnen de tenant-grens, registreert de mutaties en motiveringen, schrijft een auditlog-event, en retourneert de resultaten per item.
