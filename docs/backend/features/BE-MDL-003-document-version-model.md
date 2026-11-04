# BE-MDL-003: DocumentVersion ORM Model

| Velding | Waarde |
|---------|--------|
| ID | BE-MDL-003 |
| Sprint | SP-B01 Dag 3 |
| Datum | 2026-05-28 |
| Status | ✅ Geïmplementeerd |

---

## Build Summary

`DocumentVersion` model toegevoegd voor snapshot-tracking van document wijzigingen.

## Fields

| Veld | Type | Constraints |
|------|------|-------------|
| `id` | Integer | PK, autoincrement |
| `document_id` | Integer | FK documents.id ON DELETE CASCADE, index |
| `tenant_id` | Integer | FK tenants.id ON DELETE CASCADE, NOT NULL, index |
| `version` | Integer | NOT NULL |
| `snapshot` | JSONB | NOT NULL — volledige document snapshot |
| `created_at` | DateTime TZ | server_default=clock_timestamp() |
| `updated_at` | DateTime TZ | server_default=clock_timestamp(), onupdate=clock_timestamp() |

## Security

- RLS policy: `tenant_id = current_setting('app.current_tenant')::int`
- Tenant isolatie via FK + query filter

## Alembic Migratie

- `ade5f970f820_add_document_versions_and_gin_index.py`
- GIN index op `to_tsvector('english', filename)` voor documents tabel
- Werkende `downgrade()`

## Usage

Created by `process_document_async` Dramatiq actor on successful processing.

## Trainingssamenvatting

| Veld | Waarde |
|------|--------|
| **Actor** | Dramatiq Worker (`process_document_async`) |
| **Voorwaarde** | Succesvolle asynchrone verwerking of handmatige wijziging van een document |
| **Actie** | Creatie van een nieuwe `DocumentVersion` record |
| **Systeemverwerking** | Serialiseert de huidige staat van het document naar JSONB; koppelt versie aan `document_id` en `tenant_id` |
| **Succesrespons** | Snapshot gepersisteerd; versiegeschiedenis uitgebreid |
| **Foutrespons** | Database constraint error (bijv. ontbrekende `tenant_id`) blokkeert opslag |

---

*Laatste update: 2026-05-28*
