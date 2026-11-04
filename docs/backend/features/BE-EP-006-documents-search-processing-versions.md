# BE-EP-006: Documents Search, Processing, Status & Versions

| Velding | Waarde |
|---------|--------|
| ID | BE-EP-006 |
| Sprint | SP-B01 Dag 3 |
| Datum | 2026-05-28 |
| Eigenaar | Rakesh Ramkhelawan |
| Status | ✅ Geïmplementeerd |
| ADR-ref | ADR-005 (tenant-isolatie), ADR-006 (Dramatiq) |

---

## 1. Build Summary

Vier nieuwe endpoints toegevoegd aan de v1 Document Management router:

| Endpoint | Methode | Doel |
|----------|---------|------|
| `/api/v1/documents/search` | GET | Zoek documenten by filename (ILIKE) |
| `/api/v1/documents/{id}/process` | POST | Trigger async verwerking via Dramatiq |
| `/api/v1/documents/{id}/status` | GET | Processing status ophalen |
| `/api/v1/documents/{id}/versions` | GET | Versiegeschiedenis (DocumentVersion snapshots) |

Alle endpoints:
- Verplichte tenant-isolatie (`tenant_id` uit JWT + `current_user.tenant_id` check)
- Soft-delete exclusion (`deleted_at IS NULL`)
- `success: true/false` response envelope
- `best_effort` audit logging

---

## 2. Inventory

### 2.1 Endpoints

#### `GET /api/v1/documents/search`

**Query parameters:**
| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `q` | string | verplicht | min_length=1, max_length=200 |
| `limit` | integer | 20 | 1 ≤ limit ≤ 100 |
| `offset` | integer | 0 | offset ≥ 0 |

**Search implementation:**
- Uses PostgreSQL fulltext search: `to_tsvector('english', replace(filename, '_', ' ')) @@ plainto_tsquery('english', q)`
- GIN index on `to_tsvector('english', replace(filename, '_', ' '))` for performance
- `secure_filename()` replaces spaces with underscores; the `replace()` in the index/query normalizes this for tokenization

**Response 200:**
```json
{
  "success": true,
  "data": [{"id": 1, "filename": "report.pdf", ...}],
  "query": "report",
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

**Response 422:** Missing or empty `q` parameter

#### `POST /api/v1/documents/{id}/process`

**Path parameter:** `id` (integer)

**Business rule:**
1. Validates document exists and is accessible
2. Sets `status = "processing"`
3. Schedules Dramatiq actor `process_document_async.send(str(doc.id), tenant_id)`
4. Actor updates status to "ready" or "error" asynchronously

**Response 200:**
```json
{
  "success": true,
  "data": {"id": 1, "status": "processing"}
}
```

#### `GET /api/v1/documents/{id}/status`

**Path parameter:** `id` (integer)

**Response 200:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "status": "processing",
    "version": 3,
    "updated_at": "2026-05-28T20:00:00+00:00"
  }
}
```

#### `GET /api/v1/documents/{id}/versions`

**Path parameters:** `id` (integer)
**Query parameters:** `limit` (default 20, max 100), `offset` (default 0)

**Response 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "document_id": 1,
      "version": 2,
      "snapshot": {"filename": "old.txt", "mime_type": "text/plain", ...},
      "created_at": "2026-05-28T20:00:00+00:00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### 2.2 Schemas

- Geen nieuwe Pydantic schemas toegevoegd — gebruikt bestaande dict responses

### 2.3 Dramatiq Actor

**`process_document_async(document_id: str, tenant_id: int)`**
- Queue: `default`
- Max retries: 3
- Time limit: 5 minutes
- Sets `status = "ready"` on success
- Sets `status = "error"` on failure
- Creates `DocumentVersion` snapshot on success

### 2.4 Security

| Guard | Implementatie |
|-------|--------------|
| Auth | JWT via `get_current_user` |
| Tenant binding | `current_user.tenant_id == tenant_id` → 403 |
| Tenant query filter | `Document.tenant_id == tenant_id` in ALLE queries |
| Soft-delete filter | `Document.deleted_at.is_(None)` in ALLE read queries |

---

## 3. Detailsecties

### 3.1 Transactiegedrag

- Process endpoint: commit status update, then fire-and-forget actor
- Actor: uses `TenantFilterBypass` + `get_db_session()` for worker context
- Version snapshot: created atomically with status update in actor

### 3.2 Foutafhandeling

| Status | Trigger |
|--------|---------|
| 401 | Ongeldige JWT |
| 403 | Tenant mismatch |
| 404 | Document bestaat niet of is soft-deleted |
| 422 | Ontbrekende/lege `q` parameter (search) |

### 3.3 Telemetry

- Audit logs: `document.processing_triggered`
- Actor logging: `document_processing.start/complete/failed`

---

## 4. Afhankelijkheden

| Dependency | Doel |
|------------|------|
| `get_db` | AsyncSession injectie |
| `require_tenant_id` | Tenant context uit JWT |
| `get_current_user` | Geauthenticeerde user + tenant binding check |
| `Document` / `DocumentVersion` ORM | Database queries |
| `process_document_async` actor | Async processing |
| `audit_service` | Best-effort audit logging |

---

## 5. Testdekking

| Test | Type | Aantal |
|------|------|--------|
| Unit tests (incl. Dag 1+2) | Unit | 28 passed, 1 skipped |
| Tenant isolatie | Integration | 3 |
| Fulltext search | Integration | 1 |
| Process + status | Integration | 1 |
| Versions empty | Integration | 1 |
| **Totaal** | | **34** (34 passed) |

---

## 6. Acceptatiecriteria

- [x] `GET /documents/search` retourneert gefilterde resultaten
- [x] `POST /documents/{id}/process` zet status op "processing" en scheduled actor
- [x] `GET /documents/{id}/status` retourneert status + version
- [x] `GET /documents/{id}/versions` retourneert lege lijst voor nieuw document
- [x] Alle endpoints valideren tenant binding (403 bij mismatch)
- [x] Actor `process_document_async` bestaat en is registreerbaar

---

## 7. Trainingssamenvatting

### Flow 1: Document Zoeken
- **Actor:** API Client / Frontend
- **Voorwaarde:** Geldige JWT aanwezig
- **Actie (request):** `GET /api/v1/documents/search?q=trefwoord`
- **Systeemverwerking:** Voert PostgreSQL fulltext search uit op geindexeerde bestandsnamen binnen de tenant-scope
- **Succesrespons:** HTTP 200 met lijst van overeenkomende documenten
- **Foutrespons:** 422 (trefwoord `q` ontbreekt), 401 (geen auth)

### Flow 2: Async Verwerking Triggeren
- **Actor:** API Client / Frontend
- **Voorwaarde:** Document is geüpload en eigendom van tenant
- **Actie (request):** `POST /api/v1/documents/{id}/process`
- **Systeemverwerking:** Zet status op "processing" -> verstuurt taak naar Dramatiq queue (`process_document_async`)
- **Succesrespons:** HTTP 200 met `{"status": "processing"}`
- **Foutrespons:** 404 (document niet gevonden), 403 (tenant mismatch)
- **Uitzonderingen:** Bij herhaaldelijk aanroepen wordt de taak opnieuw in de wachtrij geplaatst

---

## 8. Risico's en mitigaties

| Risico | Impact | Mitigatie |
|--------|--------|-----------|
| Search gebruikt ILIKE (niet fulltext) | Medium | GIN index aanwezig voor toekomstige fulltext upgrade |
| Actor faalt silently | Low | Logging + retry (max 3) + status="error" bij falen |
| DocumentVersion tabel groeit onbeperkt | Medium | Retentie policy gepland voor Sprint 8 |

---

*Laatste update: 2026-05-28*
