# BE-SVC-069: DigitalTwinService (ADR-033 S5 -- DB-14b)

## Overzicht

Nieuw `digital_twin` domein (agent-level) met onveranderlijke consent-logging (ADR-026)
en LLMFallbackChain-integratie. Separeert van de bestaande user-level twin in
`src/api/v1/endpoints/digital_twin.py`.

## Sprint

AUDIT-SINGLE-TENANT-DB01 S5

## Datum

2026-07-01

## Nieuwe bestanden

| Bestand | Rol |
|---------|-----|
| `src/core/api/v1/digital_twin/__init__.py` | Package init |
| `src/core/api/v1/digital_twin/models.py` | `AgentTwinConsentEvent` SQLAlchemy model (Optie B) |
| `src/core/api/v1/digital_twin/service.py` | `DigitalTwinService` + `ConsentSettings` |
| `src/core/api/v1/digital_twin/router.py` | 4 endpoints (ADR-033 Laag 1, geen DB-imports) |
| `src/core/api/v1/digital_twin/dependencies.py` | `get_digital_twin_service` factory |
| `src/alembic/versions/e6e3b419355d_audit_db14b_agent_twin_consent_events.py` | Alembic migratie |

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/registries/agentic.py` | `digital_twin_router` opgenomen via `prefix=/api/v1` |

## Endpoints

| Methode | Path | Omschrijving |
|---------|------|--------------|
| POST | `/api/v1/digital-twin/consent` | Consent instellen (INSERT, nooit UPDATE) |
| GET | `/api/v1/digital-twin/agents/{id}/state` | Huidige twin-state ophalen |
| GET | `/api/v1/digital-twin/agents/{id}/consent-history` | Consent-log (gepagineerd) |
| GET | `/api/v1/digital-twin/health` | Service health |

## ADR-conformiteit

- **ADR-026**: `update_consent()` gebruikt `db.add(new_event)` + `commit()` -- NOOIT `execute(update(...))`
- **ADR-026**: `_build_llm_failover_chain()` gebruikt `LLMFallbackChain` uit `src.core.llm.fallback_chain`
- **ADR-033**: `router.py` bevat geen verboden DB-imports
- **ADR-005**: `tenant_id NOT NULL` in `agent_twin_consent_events` tabel
- **ADR-003**: `tenant_id` via `Depends(require_tenant_id)`, nooit uit request body
- **Security**: `_verify_agent_ownership` controleert dat `agent_id` van de juiste tenant is voor elke consent-mutatie (IDOR-preventie)

## Database

Nieuwe tabel `agent_twin_consent_events`:

| Kolom | Type | Constraint |
|-------|------|-----------|
| `id` | Integer | PK, autoincrement |
| `agent_id` | Integer | NOT NULL, index |
| `tenant_id` | Integer | NOT NULL, index |
| `observe` | Boolean | NOT NULL |
| `created_at` | DateTime(timezone=True) | NOT NULL |

Indices: `ix_atce_tenant_agent` (tenant_id, agent_id) + `ix_atce_agent_id` (agent_id)

## Tests

| Test | Type | Status |
|------|------|--------|
| `test_digital_twin_router_exists` | architecture | GROEN |
| `test_digital_twin_router_no_direct_db_imports` | architecture | GROEN |
| `test_digital_twin_service_exists` | architecture | GROEN |
| `test_digital_twin_dependencies_exists` | architecture | GROEN |
| `test_digital_twin_service_file_exists` | architecture (ADR-026) | GROEN |
| `test_no_dummy_observer_in_digital_twin_service` | architecture (ADR-026) | GROEN |
| `test_no_dummy_observer_in_production_src` | architecture (ADR-026) | GROEN |
| `test_digital_twin_service_importable` | unit | GROEN |
| `test_digital_twin_service_accepts_db_and_tenant_id` | unit | GROEN |
| `test_consent_update_inserts_new_record_not_update` | unit | GROEN |
| `test_consent_update_never_uses_db_execute_update` | unit | GROEN |
| `test_agent_twin_consent_event_model_importable` | unit | GROEN |

## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met geldige JWT en opgeloste tenant.
- Voorwaarde: Agent bestaat in `src.core.agents.models.Agent` en behoort tot de tenant; `get_digital_twin_service` factory is beschikbaar.
- Actie (request): Verstuur `POST /api/v1/digital-twin/agents/{agent_id}/consent` met body `{"observe": true}`.
- Systeemverwerking: De factory maakt `DigitalTwinService(db=db, tenant_id=tenant_id)`; `update_consent` roept `_verify_agent_ownership(agent_id)` aan (checkt `Agent.id` en `Agent.tenant_id`), maakt een nieuw `AgentTwinConsentEvent` record, voegt deze toe en commit (INSERT, nooit UPDATE per ADR-026).
- Succesrespons: HTTP 200 met body `{"success": True, "data": {"agent_id": ..., "tenant_id": ..., "observe": true}}`.
- Foutrespons: HTTP 404 `Agent niet gevonden` als de agent niet tot de tenant behoort; HTTP 401 indien tenant ontbreekt.
- Uitzonderingen: `GET /agents/{agent_id}/state` leest het laatste consent-event; `GET /agents/{agent_id}/consent-history` retourneert een gepagineerde lijst van events.
