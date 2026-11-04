# Backend Feature Specification

## Metadata

- Feature ID: BE-MDL-002
- Feature naam: Document ORM Model Extension
- Status: APPROVED
- Auteur: Sprint Agent (SP-B01)
- Reviewer: code-reviewer + general-purpose subagents
- Datum: 2026-05-28
- Gerelateerde sprint: SP-B01 Dag 1
- Gerelateerde ADR: ADR-005 (tenant_id NOT NULL + RLS), ADR-010 (Gunicorn multi-worker)

---

## Doel en scope

### Doel

Uitbreiden van het bestaande `Document` ORM model in `src/domains/documents/models.py` met soft-delete, status tracking, versioning, en JSONB content. Dit vervangt de oude `is_deleted` boolean en maakt het model compliant met projectconventies (`clock_timestamp()`, RLS, tenant isolatie).

### In scope

- `deleted_at` (DateTime, nullable) voor soft delete
- `status` (String 50, NOT NULL, server_default="pending")
- `version` (Integer, NOT NULL, server_default="1")
- `content` (JSONB, nullable)
- `created_at` server_default gewijzigd naar `clock_timestamp()`
- Alembic migratie met data backfill (`is_deleted=true` -> `deleted_at=now()`)
- RLS policy op documents tabel
- Indexen op `status` en `deleted_at`

### Out of scope

- DocumentVersion tabel (dag 2)
- Fulltext search index (dag 3)
- Azure Blob/S3 storage backends (post-MVP)

---

## Technische details

### Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/domains/documents/models.py` | Nieuwe kolommen + indexen |
| `src/alembic/versions/47ca3df1f5e6_extend_documents_table.py` | Migratie + RLS + data backfill |

### Voor en na

**Voor:**
```python
is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
```

**Na:**
```python
is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")  # deprecated
status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))
```

---

## Trainingssamenvatting

### Flow 1: Document upload met nieuw model

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: Geldig JWT, bestand aanwezig
- Actie: POST /api/v1/documents/upload
- Systeemreactie: Document record aangemaakt met status="processing", created_at=clock_timestamp()
- Succesrespons: HTTP 200 + document metadata
- Foutrespons: HTTP 413 (te groot), HTTP 400 (ongeldig type), HTTP 501 (niet-local storage)
- Uitzonderingen: SQLite tests zetten created_at expliciet in Python (clock_timestamp() is PostgreSQL-only)

---

## Tests

- `test_document_model_exists` — model importeerbaar
- `test_document_tenant_id_not_null` — ADR-005 compliance
- `test_document_deleted_at_is_nullable` — soft delete structuur
- `test_document_status_has_server_default` — default "pending"
- `test_document_created_at_uses_clock_timestamp` — serializable ordering
- `test_document_id_is_primary_key` — PK aanwezig

---

## Acceptatiecriteria

- [x] Alembic migratie slaagt (`alembic upgrade head`)
- [x] `alembic check` toont 0 drift
- [x] RLS policy aanwezig op documents
- [x] Data backfill: oude `is_deleted=true` records hebben `deleted_at` gezet
- [x] Werkende downgrade
