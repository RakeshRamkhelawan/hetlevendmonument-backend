# BE-MDL-007: EU AI Act Compliance ORM Models

## Overzicht

SQLAlchemy ORM modellen voor EU AI Act Article 62 (incident reporting) en
Article 12 + Article 53 (model provenance tracking + transparency), geimplementeerd in
`src/core/governance/models.py` als onderdeel van sprint SP-E04 Dag 1.
Beide modellen gebruiken soft-delete (`deleted_at`) en mogen NOOIT hard-deleted worden
wegens EU AI Act bewaarplicht.

Gerelateerd: BE-SVC-005 (IncidentService + ProvenanceService die deze modellen benaderen).

## Bestanden

| Bestand | Rol |
|---------|-----|
| `src/core/governance/models.py` | ORM modellen `IncidentReportDB` en `ModelProvenanceDB` |
| `src/alembic/versions/20260529c_add_ai_act_incident_reports_table.py` | Migratie: ai_act_incident_reports + RLS |
| `src/alembic/versions/20260529d_add_model_provenance_records_table.py` | Migratie: model_provenance_records + RLS |
| `tests/unit/test_sp_e04_ai_act_db.py` | 21 model + singleton-removal tests |

## Model specificaties

### IncidentReportDB (`ai_act_incident_reports`)

EU AI Act Article 62 -- 10-jaar retentie, soft-delete only.

| Kolom | Type | Constraints | Default |
|-------|------|------------|---------|
| id | UUID | PK | gen_random_uuid() |
| tenant_id | int | NOT NULL, FK(tenants.id RESTRICT), index | -- |
| incident_type | str(100) | NOT NULL | -- |
| severity | str(50) | NOT NULL | -- |
| description | Text | NOT NULL | -- |
| agent_id | str(255) | nullable | -- |
| agent_name | str(255) | nullable | -- |
| eu_reporting_required | bool | NOT NULL | false |
| eu_reported_at | DateTime(tz) | nullable | -- |
| resolution_status | str(50) | NOT NULL | 'open' |
| incident_data | JSONB | nullable | -- |
| created_at | DateTime(tz) | NOT NULL | clock_timestamp() |
| resolved_at | DateTime(tz) | nullable | -- |
| deleted_at | DateTime(tz) | nullable | -- |

Indexen: `ix_incident_tenant_created (tenant_id, created_at)`,
`ix_incident_tenant_status (tenant_id, resolution_status)`,
`ix_incident_tenant_id (tenant_id)`.

Note: `ix_incident_tenant_id` is aangemaakt via `index=True` op de kolom in de ORM
(SQLAlchemy auto-naam: `ix_ai_act_incident_reports_tenant_id`); de migratie maakt deze
expliciet aan als `ix_incident_tenant_id`. Namen verschillen. Gebruik `alembic check`
na elke migratie om drift te bevestigen.

FK is `ondelete="RESTRICT"` -- verwijderen van een tenant met incident records wordt
geblokkeerd. Nooit `CASCADE` voor EU AI Act compliance tables.

### ModelProvenanceDB (`model_provenance_records`)

EU AI Act Article 12 (transparency) + Article 53 (provenance tracking) --
tamper-evident hashes, 6-maanden minimum retentie.

| Kolom | Type | Constraints | Default |
|-------|------|------------|---------|
| id | UUID | PK | gen_random_uuid() |
| tenant_id | int | NOT NULL, FK(tenants.id RESTRICT), index | -- |
| provider | str(100) | NOT NULL | -- |
| model | str(255) | NOT NULL | -- |
| model_version | str(100) | nullable | -- |
| input_hash | str(64) | NOT NULL | -- |
| output_hash | str(64) | NOT NULL | -- |
| user_id | str(255) | nullable | -- |
| retention_until | DateTime(tz) | nullable | -- |
| registered_at | DateTime(tz) | NOT NULL | clock_timestamp() |
| deleted_at | DateTime(tz) | nullable | -- |

Indexen: `ix_provenance_tenant_registered (tenant_id, registered_at)`,
`ix_provenance_tenant_id (tenant_id)`.

`input_hash` en `output_hash` zijn volledige 64-karakter hexadecimale SHA-256 hashes
(geen truncatie). `str(64)` capaciteit is exact correct voor SHA-256 hex.

**Waarschuwing: `retention_until` is nullable in de ORM maar MOET worden gevuld.**
Gebruik altijd `new_provenance_record()` of `ProvenanceRecord.__post_init__()`
om de 6-maanden default te garanderen. Direct ORM-instantiatie zonder `retention_until`
leidt tot records die nooit worden opgepakt door `get_expired_records()`.

## ADR-naleving

- **ADR-005**: `tenant_id NOT NULL` + RLS policy `tenant_isolation` op beide tabellen
- **ADR-031**: Soft-delete only (`deleted_at`) -- geen hard-delete ooit
- **CLAUDE.md §11.5**: `clock_timestamp()` als `server_default` voor concurrent-safe ordering
- **FK RESTRICT**: Blokkeer tenant-verwijdering bij aanwezige compliance records

## Veiligheidsrestricts

- NOOIT `deleted_at` verwijderen of hard-delete uitvoeren op compliance tabellen
- NOOIT `ondelete="CASCADE"` toevoegen -- altijd `RESTRICT`
- NOOIT dummy/test records schrijven buiten de testdatabase

## Acceptatiecriteria

- `alembic check` retourneert 0 drift na beide migraties
- `alembic upgrade head --sql` (offline) slaagt zonder errors voor beide migraties
- Alle 21 tests in `tests/unit/test_sp_e04_ai_act_db.py` PASS
- `_incident_store` en `_provenance_store` zijn afwezig in respectievelijke modules
- Hard-delete (DELETE zonder `deleted_at`) is onmogelijk via de service-laag

## Trainingssamenvatting

### Flow 1: Incident record aanmaken (API path)

| Veld | Inhoud |
|------|--------|
| Actor | Authenticated API user (via POST /api/v1/ai-act/incidents) |
| Voorwaarde | Geldige JWT, `tenant_id` in JWT claim, PostgreSQL beschikbaar |
| Actie | Gebruiker POST incident payload (severity, agent_id, description) |
| Systeemverwerking | `IncidentService.create_incident()` bouwt `IncidentReportDB` row, `db.add()` + `db.commit()`, `eu_reporting_required` automatisch bepaald via `requires_eu_reporting(severity)` |
| Succesrespons | HTTP 201, `incident_id` (UUID string), `severity`, `status` (= "reported"; maps naar DB kolom `resolution_status`) |
| Foutrespons | HTTP 422 bij Pydantic-validatiefout (ongeldige severity in request body); HTTP 400 bij ValueError vanuit service-laag; HTTP 500 bij DB-fout |
| Uitzonderingen | Wanneer `alert_manager.py` intern incidents aanmaakt (buiten REST API), gebruikt het `db.flush()` i.p.v. `db.commit()` zodat de outer transactie intact blijft. De REST-API endpoint roept altijd `db.commit()` aan via `IncidentService.create_incident()`. |

### Flow 2: Provenance record aanmaken

| Veld | Inhoud |
|------|--------|
| Actor | Internal system (LLM pipeline, governance agent) |
| Voorwaarde | LLM call voltooid, `input_data` en `output_data` beschikbaar, `tenant_id` bekend |
| Actie | Aanroeper construeert eerst een `ProvenanceRecord` via `new_provenance_record(provider, model, ...)` of direct; `ProvenanceService.log_provenance(record)` aanroepen |
| Systeemverwerking | `compute_hash()` berekent SHA-256 (64 hex chars) van input en output; `ModelProvenanceDB` row aangemaakt; `retention_until = registered_at + 6 maanden`; `db.add()` + `db.commit()`; retourneert `ModelProvenanceDB` ORM object |
| Succesrespons | Retourneert `ModelProvenanceDB` ORM object; `record_id` als UUID is toegankelijk als `str(db_row.id)` |
| Foutrespons | `ValueError` bij lege input/output strings; `SQLAlchemy OperationalError` bij DB-fout |
| Uitzonderingen | `new_provenance_record()` bouwt `ProvenanceRecord` dataclass ZONDER persisteren -- voor in-memory gebruik en tests |

### Flow 3: Soft-delete retention query

| Veld | Inhoud |
|------|--------|
| Actor | Background job / governance officer |
| Voorwaarde | Records waarvoor `retention_until < now()` en `deleted_at IS NULL` |
| Actie | `ProvenanceService.get_expired_records()` aanroepen |
| Systeemverwerking | Query: `WHERE deleted_at IS NULL AND retention_until < now()` met tenant-filter; resultaat lijst van `ModelProvenanceDB` rows |
| Succesrespons | Lijst van verlopen records voor soft-delete verwerking; lege lijst als geen records verlopen |
| Foutrespons | `SQLAlchemy OperationalError` of `TimeoutError` bij DB-fout; caller moet exception loggen met `exc_info=True` en niet stille lege lijst retourneren |
| Uitzonderingen | Hard-delete NOOIT uitvoeren -- zet alleen `deleted_at = now()` |
