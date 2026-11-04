# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-004
- Feature naam: Documents Upload Endpoint
- Status: APPROVED
- Auteur: Sprint Agent (SP-B01)
- Reviewer: code-reviewer + general-purpose subagents
- Datum: 2026-05-28
- Gerelateerde sprint: SP-B01 Dag 1
- Gerelateerde ADR: ADR-005 (tenant isolatie), ADR-013 (config centralisatie)

---

## Doel en scope

### Doel

Implementeren van `POST /api/v1/documents/upload` — een veilige, async file upload endpoint met tenant isolatie, file type whitelist, size limits, en SHA-256 checksum.

### In scope

- Upload endpoint met `UploadFile`
- Tenant binding check (`current_user.tenant_id == tenant_id`)
- File size limit (50MB default, configurable)
- MIME type whitelist (pdf, txt, md, csv, json, png, jpg, docx)
- Path traversal protection (`secure_filename`)
- SHA-256 checksum berekening
- Local storage met tenant-scoped paden (`uploads/{tenant_id}/{doc.id}_{filename}`)
- `best_effort` audit logging
- HTTP 501 voor niet-geconfigureerde storage backends

### Out of scope

- CRUD endpoints (dag 2)
- Fulltext search (dag 3)
- Async document processing via Dramatiq (dag 3)
- Azure Blob / S3 storage (post-MVP)

---

## Technische details

### Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/documents/router.py` | Upload endpoint geimplementeerd |
| `src/core/api/router_registry.py` | Documents router altijd registreren |
| `src/core/api/document_endpoints.py` | Model import verwijderd (conflict fix) |
| `src/core/shared/config.py` | Storage config toegevoegd |

### Security hardening

| Bevinding | Oplossing |
|-----------|-----------|
| Path traversal | `secure_filename()` strippt `/`, `\`, `\x00` |
| File size DoS | 50MB limiet, HTTP 413 bij overschrijding |
| Malicious uploads | MIME type whitelist |
| Tenant spoofing | Expliciete `current_user.tenant_id == tenant_id` check |
| Orphan DB records | DB insert voor file write |

---

## Trainingssamenvatting

### Flow 1: Gebruiker uploadt bestand

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: Geldig JWT, bestand < 50MB, toegestaan MIME type
- Actie: POST /api/v1/documents/upload met multipart file
- Systeemreactie: Tenant check -> size check -> MIME check -> checksum -> DB insert -> file write -> audit log
- Succesrespons: HTTP 200 + `{"success": true, "data": {"id": ..., "status": "processing", ...}}`
- Foutrespons: HTTP 403 (tenant mismatch), 413 (te groot), 400 (ongeldig type), 501 (niet-local storage), 401 (geen auth)
- Uitzonderingen: Async I/O via `aiofiles`; bestand wordt geschreven na DB commit

---

## Tests

- `test_upload_returns_processing_not_ready` — status is "processing"
- `test_upload_returns_success_true` — response format correct
- `test_upload_without_auth_returns_401` — auth vereist
- `test_upload_unsupported_storage_backend_returns_501` — S3 geeft 501

---

## Acceptatiecriteria

- [x] Upload endpoint retourneert status="processing"
- [x] Geen hardcoded paths (config via `get_settings()`)
- [x] Tenant isolatie bewezen (binding check + RLS)
- [x] File security: size limit + MIME whitelist + path traversal fix
- [x] `best_effort` audit logging na commit
- [x] Alle 10 unit tests groen
