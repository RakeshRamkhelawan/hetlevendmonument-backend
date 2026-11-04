# BE-SVC-005: EU AI Act Compliance Services

## Overzicht

Async PostgreSQL-backed service classes voor EU AI Act Article 62 (IncidentService)
en Article 53 (ProvenanceService). Vervangt de verwijderde module-level dict-singletons
`_incident_store` en `_provenance_store`. Geimplementeerd als onderdeel van sprint SP-E04 Dag 2.

Gerelateerd: BE-MDL-007 (ORM modellen die deze services benaderen).

## Bestanden

| Bestand | Rol |
|---------|-----|
| `src/core/governance/incident_service.py` | `IncidentService`, `classify_severity()`, `requires_eu_reporting()` |
| `src/core/governance/model_provenance.py` | `ProvenanceService`, `compute_hash()`, `new_provenance_record()` |
| `src/core/api/v1/ai_act/incident_router.py` | FastAPI router (DB-backed, dependency injection) |
| `src/core/governance/alert_manager.py` | Direct ORM write bij CRITICAL alerts (flush-based) |
| `src/core/governance/governance_agent/integration.py` | Art. 12 provenance placeholder (inject ProvenanceService) |
| `tests/unit/test_sp_e04_ai_act_db.py` | 21 service- en model-tests |
| `tests/unit/governance/test_incident_api.py` | Router API tests (AsyncMock + dependency overrides) |
| `tests/unit/governance/test_model_cards_provenance.py` | Provenance unit tests |
| `tests/unit/governance/test_sprint6a_hardening.py` | Alert manager integration tests |

## Service specificaties

### IncidentService(db: AsyncSession, tenant_id: int)

| Methode | Signature | Beschrijving |
|---------|-----------|--------------|
| `create_incident` | `(incident: IncidentReport) -> IncidentReportDB` | Persisteert incident, voegt `resolution_status` en `eu_reporting_required` toe |
| `list_incidents` | `(status: str \| None, limit: int, offset: int) -> list[IncidentReportDB]` | Tenant-gefilterd, paginering, optioneel op status |
| `get_incident` | `(incident_id: str) -> IncidentReportDB \| None` | UUID lookup met tenant-filter |
| `update_status` | `(incident_id: str, new_status: str) -> IncidentReportDB \| None` | Status-update; zet `resolved_at = now()` bij 'resolved', reset naar `None` bij andere statussen |
| `mark_eu_reported` | `(incident_id: str) -> IncidentReportDB \| None` | Zet `eu_reported_at = now()` |
| `get_eu_reporting_queue` | `() -> list[IncidentReportDB]` | `eu_reporting_required=True AND eu_reported_at IS NULL` |

### ProvenanceService(db: AsyncSession, tenant_id: int)

| Methode | Signature | Beschrijving |
|---------|-----------|--------------|
| `log_provenance` | `(record: ProvenanceRecord) -> ModelProvenanceDB` | Persisteert provenance record; aanroeper bouwt eerst `ProvenanceRecord` via `new_provenance_record()` |
| `list_provenance` | `(limit: int, offset: int) -> list[ModelProvenanceDB]` | Tenant-gefilterd, paginering |
| `get_expired_records` | `() -> list[ModelProvenanceDB]` | Records waar `retention_until < now()` en `deleted_at IS NULL` |

### Utility functies

| Functie | Beschrijving |
|---------|--------------|
| `compute_hash(data: str) -> str` | SHA-256 hex digest, 64 karakters, deterministic |
| `new_provenance_record(...)-> ProvenanceRecord` | Bouwt dataclass ZONDER persisteren; voor tests en in-memory gebruik |
| `classify_severity(impact, scope, reversibility) -> str` | Matrix-gebaseerde severity classificatie |
| `requires_eu_reporting(severity: str) -> bool` | True voor 'critical' en 'high' |

## Router registratie

`incident_router.py` is geregistreerd via `_register_ai_act_incidents()` in
`src/core/api/router_registry.py`. De router heeft zelf `prefix="/api/v1/ai-act"` --
geen extra prefix toevoegen bij registratie. Registratie is NIET in een try/except
gewikkeld omdat EU AI Act compliance endpoints niet stil mogen falen.

## Dependency injection

```
incident_router.py
  POST /incidents -> IncidentService(db, tenant_id)
  GET  /incidents -> IncidentService(db, tenant_id)
  GET  /incidents/eu-reporting/pending -> IncidentService(db, tenant_id)
  GET  /incidents/{incident_id} -> IncidentService(db, tenant_id)
```

`tenant_id` altijd afgeleid van `get_current_user()` (JWT), NOOIT uit request body.
`db` uit `get_db()` dependency (async SQLAlchemy session).

## Route ordering

`/eu-reporting/pending` is gedeclareerd VOOR `/{incident_id}` om te voorkomen dat
FastAPI de string "eu-reporting" matcht als `incident_id` path parameter.

## ADR-naleving

- **ADR-005**: Alle queries bevatten `tenant_id` filter
- **ADR-031**: Soft-delete only -- `deleted_at` zetten, nooit hard-delete
- **CLAUDE.md regel 6**: `tenant_id` altijd uit JWT/middleware, nooit uit request body
- **CLAUDE.md valkuil (Sprint 4 Dag 2)**: Geen `from __future__ import annotations` in `incident_router.py` -- dit breekt FastAPI Pydantic body-param detectie bij `functools.wraps` decorators

## Veiligheidsregels

- NOOIT `tenant_id` in Pydantic request schema's -- altijd uit `get_current_user()`
- Alert manager gebruikt `db.flush()` niet `db.commit()` -- outer transaction blijft open
- `_FailClosedAudit` patroon: foutende audit mag primaire operatie NIET blokkeren

## Trainingssamenvatting

### Flow 1: POST /api/v1/ai-act/incidents (incident melden)

| Veld | Inhoud |
|------|--------|
| Actor | Authenticated user (agent operator, compliance officer) |
| Voorwaarde | Geldige JWT, PostgreSQL beschikbaar, severity in [low, medium, high, critical] |
| Actie | POST payload: `{severity, agent_id, agent_name, description, details}` |
| Systeemverwerking | `IncidentService.create_incident()` aanroepen; `eu_reporting_required` automatisch `True` voor high/critical; `resolution_status = "reported"`; row persist en commit |
| Succesrespons | HTTP 201, `{incident_id, severity, status, eu_reporting_required}` |
| Foutrespons | HTTP 422 bij ontbrekende velden of ongeldige severity |
| Uitzonderingen | Severity "invalid" geeft 422; `agent_name` en `details` zijn optioneel |

### Flow 2: GET /api/v1/ai-act/incidents/eu-reporting/pending

| Veld | Inhoud |
|------|--------|
| Actor | Compliance officer, EU reporting pipeline |
| Voorwaarde | Geldige JWT, tenant heeft incidents met `eu_reporting_required=True` |
| Actie | GET zonder query params |
| Systeemverwerking | `IncidentService.get_eu_reporting_queue()`: `WHERE eu_reporting_required=True AND eu_reported_at IS NULL AND deleted_at IS NULL AND tenant_id = ?` |
| Succesrespons | HTTP 200, `{incidents: [...]}` |
| Foutrespons | HTTP 200 met lege lijst bij geen pending items |
| Uitzonderingen | Route VOOR `/{incident_id}` gedeclareerd -- anders matcht "eu-reporting" als incident UUID |

### Flow 3: compute_hash / provenance tamper-evidence

| Veld | Inhoud |
|------|--------|
| Actor | Internal LLM pipeline |
| Voorwaarde | LLM call voltooid, `input_data` en `output_data` als strings beschikbaar |
| Actie | `compute_hash(data)` aanroepen voor input en output |
| Systeemverwerking | `hashlib.sha256(data.encode()).hexdigest()` -- deterministisch, 64 hex chars, geen truncatie |
| Succesrespons | 64-karakter lowercase hex string |
| Foutrespons | n.v.t. -- pure functie zonder I/O |
| Uitzonderingen | Identieke input geeft altijd identieke hash (deterministic); `new_provenance_record()` persisteert NIET -- alleen voor test/in-memory gebruik |
