# BE-EP-005: Documents CRUD Endpoints

| Velding | Waarde |
|---------|--------|
| ID | BE-EP-005 |
| Sprint | SP-B01 Dag 2 |
| Datum | 2026-05-28 |
| Eigenaar | Rakesh Ramkhelawan |
| Status | ✅ Geïmplementeerd |
| ADR-ref | ADR-005 (tenant-isolatie), ADR-013 (config hardening) |

---

## 1. Build Summary

Vier CRUD endpoints toegevoegd aan de v1 Document Management router:

| Endpoint | Methode | Doel |
|----------|---------|------|
| `/api/v1/documents` | GET | Lijst documenten met paginering + status filter |
| `/api/v1/documents/{id}` | GET | Ophalen enkel document |
| `/api/v1/documents/{id}` | PUT | Update metadata (bump version +1) |
| `/api/v1/documents/{id}` | DELETE | Soft-delete (deleted_at timestamp) |

Alle endpoints:
- Verplichte tenant-isolatie (`tenant_id` uit JWT + `current_user.tenant_id` check)
- Soft-delete exclusion (`deleted_at IS NULL` in ALLE queries)
- `success: true/false` response envelope
- `best_effort` audit logging

---

## 2. Inventory

### 2.1 Endpoints

#### `GET /api/v1/documents`

**Query parameters:**
| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `limit` | integer | 20 | 1 ≤ limit ≤ 100 |
| `offset` | integer | 0 | offset ≥ 0 |
| `status` | string | null | max 50 chars |

**Response 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "tenant_id": 1,
      "filename": "report.pdf",
      "mime_type": "application/pdf",
      "file_size_bytes": 1024,
      "status": "ready",
      "version": 2,
      "storage_backend": "local",
      "checksum_sha256": "abc123...",
      "deleted_at": null,
      "created_at": "2026-05-28T20:00:00+00:00",
      "updated_at": "2026-05-28T20:00:00+00:00"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

**Response 403:** Tenant mismatch
**Response 401:** Geen geldige JWT

#### `GET /api/v1/documents/{doc_id}`

**Path parameter:** `doc_id` (integer)

**Response 200:** Enkel document met `content` (JSONB) en `storage_path`
**Response 404:** Document niet gevonden of soft-deleted
**Response 403:** Tenant mismatch

#### `PUT /api/v1/documents/{doc_id}`

**Request body (DocumentUpdateRequest):**
| Veld | Type | Vereist | Constraints |
|------|------|---------|-------------|
| `filename` | string | nee | 1-500 chars, sanitized |
| `status` | string | nee | max 50 chars |
| `metadata` | object | nee | JSON key-value |

**Business rule:** Elke update verhoogt `version` met +1 en zet `updated_at` op `datetime.now(timezone.utc)`.

**Response 200:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "filename": "renamed.txt",
    "status": "ready",
    "version": 3,
    "updated_at": "2026-05-28T20:05:00+00:00"
  }
}
```

**Response 404:** Document niet gevonden of soft-deleted
**Response 403:** Tenant mismatch

#### `DELETE /api/v1/documents/{doc_id}`

**Business rule:** Soft-delete — zet `deleted_at = now()` en `is_deleted = true`. Record blijft in database.

**Response 200:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "deleted_at": "2026-05-28T20:10:00+00:00"
  }
}
```

**Response 404:** Document niet gevonden of al soft-deleted
**Response 403:** Tenant mismatch

### 2.2 Schemas

- `DocumentResponse` — bestaand, aangepast om `version`, `deleted_at`, `content` te bevatten
- `DocumentListResponse` — `{ data, total, limit, offset }`
- `DocumentUpdateRequest` — nieuw, velden: `filename`, `status`, `metadata_` (alias `metadata`)

### 2.3 Security

| Guard | Implementatie |
|-------|--------------|
| Auth | JWT via `get_current_user` |
| Tenant binding | `current_user.tenant_id == tenant_id` → 403 |
| Tenant query filter | `Document.tenant_id == tenant_id` in ALLE queries |
| Soft-delete filter | `Document.deleted_at.is_(None)` in ALLE queries |

---

## 3. Detailsecties

### 3.1 Transactiegedrag

- Update en delete doen `await db.commit()` direct
- Audit logging via `best_effort()` — faalt silently, blokkeert request niet
- Version bump gebeurt atomisch in dezelfde commit

### 3.2 Foutafhandeling

| Status | Trigger | Response body |
|--------|---------|---------------|
| 400 | Ongeldig MIME type bij upload | `{success: false, error: {code, message}}` |
| 401 | Ongeldige of ontbrekende JWT | FastAPI default |
| 403 | Tenant mismatch | `{detail: "Tenant mismatch"}` |
| 404 | Document bestaat niet of is soft-deleted | `{success: false, error: {code: "NOT_FOUND"}}` |
| 413 | File > max_upload_size_bytes | `{detail: "File too large"}` |
| 501 | Storage backend != local | `{success: false, error: {code: "STORAGE_NOT_CONFIGURED"}}` |

### 3.3 Telemetry

- Audit logs: `document.uploaded`, `document.updated`, `document.deleted`
- Geen Prometheus metrics toegevoegd (volgt in Sprint 8 observability)

---

## 4. Afhankelijkheden

| Dependency | Doel |
|------------|------|
| `get_db` | AsyncSession injectie |
| `require_tenant_id` | Tenant context uit JWT |
| `get_current_user` | Geauthenticeerde user + tenant binding check |
| `Document` ORM model | Database queries |
| `audit_service` | Best-effort audit logging |

---

## 5. Testdekking

| Test | Type | Aantal |
|------|------|--------|
| Model tests | Unit | 6 |
| Upload endpoint | Unit | 4 |
| List endpoint | Unit | 3 |
| Get endpoint | Unit | 2 |
| Update endpoint | Unit | 2 |
| Delete endpoint | Unit | 3 |
| Tenant isolatie | Integration | 3 |
| **Totaal** | | **23** (20 passed, 1 skipped, 3 integration) |

---

## 6. Acceptatiecriteria

- [x] `GET /documents` retourneert gepagineerde lijst
- [x] `GET /documents` sluit soft-deleted documenten uit
- [x] `GET /documents/{id}` retourneert 404 voor onbekend/verwijderd ID
- [x] `PUT /documents/{id}` verhoogt version met +1
- [x] `DELETE /documents/{id}` zet `deleted_at` zonder DB-row te verwijderen
- [x] Tenant A kan geen documenten van Tenant B zien/wijzigen/verwijderen
- [x] Alle endpoints valideren tenant binding (403 bij mismatch)

---

## 7. Trainingssamenvatting

| Veld | Waarde |
|------|--------|
| **Actor** | API Client / Frontend |
| **Voorwaarde** | Geldige JWT; documentID behoort tot de actieve tenant |
| **Actie (request)** | `GET/PUT/DELETE /api/v1/documents/{id}` |
| **Systeemverwerking** | Valideert JWT en tenant-binding; voert DB-query uit met `deleted_at IS NULL` filter; schrijft best-effort audit log |
| **Succesrespons** | HTTP 200 met document metadata of succes-bevestiging |
| **Foutrespons** | 404 (niet gevonden of verwijderd), 403 (andere tenant), 401 (ongeldige token) |
| **Uitzonderingen** | `GET /documents` (lijst) retourneert lege lijst bij 0 resultaten in plaats van 404 |

---

## 8. API-flow voorbeeld

### Happy path: CRUD lifecycle

```
1. POST /upload → {success: true, data: {id: 1, status: "processing"}}
2. GET /documents/1 → {success: true, data: {id: 1, ...}}
3. PUT /documents/1 {filename: "new.txt"} → {success: true, data: {version: 2}}
4. GET /documents → {data: [{id: 1, ...}], total: 1}
5. DELETE /documents/1 → {success: true, data: {deleted_at: "..."}}
6. GET /documents/1 → 404
7. GET /documents → {data: [], total: 0}
```

---

## 8. Risico's en mitigaties

| Risico | Impact | Mitigatie |
|--------|--------|-----------|
| Upload laadt volledige file in memory | Medium | 50MB limiet; streaming refactor gepland |
| Geen RLS policy test op document list | Low | Integration test via PostgreSQL + override |
| Tenant isolatie alleen op app-laag | Medium | RLS policy aanwezig in migratie, maar integratietest gebruikt override |

---

*Laatste update: 2026-05-28*
