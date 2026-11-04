# BE-RTR-015 — Audit + Knowledge + Memory Domain Migration naar v1/ (SP-API-003 Dag 5)

**Sprint:** SP-API-003 Dag 5
**Datum:** 2026-06-04
**ADR:** ADR-033
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Migratie van drie legacy flat-file endpoints naar de drie-laags ADR-033 Strangler Fig structuur:

| Flat bestand | Nieuw pad | Endpoints |
|---|---|---|
| `src/core/api/audit_endpoints.py` | `src/core/api/v1/audit/` | GET /api/v1/audit/missions, GET /api/v1/audit/missions/{id}/export |
| `src/core/api/memory_endpoints.py` | `src/core/api/v1/memory/` | GET/PUT /api/v1/memory/config, GET/POST/DELETE /api/v1/memory/index |
| `src/core/api/knowledge_endpoints.py` | `src/core/api/v1/knowledge/` | 8 endpoints via /api/v1/agents prefix |

Registries bijgewerkt: `core_api.py` (audit + memory), `agents.py` (knowledge).
Flat bestanden behouden met `# orphan:exempt reason: legacy flat file, replaced by ...`.

---

## Nieuwe bestanden

### v1/audit/
- `__init__.py` — domain_router met prefix /api/v1
- `router.py` — composite router met prefix /audit
- `missions_router.py` — GET /missions + GET /missions/{id}/export
- `schemas.py` — MissionStatus, AuditEventType, ExportFormat, DataCategory + Pydantic models
- `dependencies.py` — get_tenant(), get_user_id(), sample data helpers

### v1/memory/
- `__init__.py` — domain_router met prefix /api/v1
- `router.py` — composite router met prefix /memory
- `config_router.py` — GET/PUT /config
- `index_router.py` — GET/POST/DELETE /index
- `schemas.py` — EmbeddingModel, ChunkingStrategy, IndexStatus + Pydantic models
- `dependencies.py` — in-memory storage helpers, calculate_index_stats()

### v1/knowledge/
- `__init__.py` — domain_router (geen prefix, agents registry injecteert /api/v1/agents)
- `router.py` — composite router
- `crud_router.py` — POST /create, GET /get, PUT /update, DELETE /delete
- `search_router.py` — GET /, POST /search, GET /categories
- `admin_router.py` — POST /index/rebuild
- `schemas.py` — KnowledgeCreateRequest, KnowledgeUpdateRequest + response models

---

## URL-equivalentie

Alle bestaande URL-paden zijn ongewijzigd (ADR-031 URL-freeze gehandhaafd):
- `/api/v1/audit/missions` ✅
- `/api/v1/audit/missions/{mission_id}/export` ✅
- `/api/v1/memory/config` ✅
- `/api/v1/memory/index` ✅
- `/api/v1/agents/create` ✅ (via /api/v1/agents prefix in registry)
- `/api/v1/agents/get` ✅
- `/api/v1/agents/update` ✅
- `/api/v1/agents/delete` ✅
- `/api/v1/agents/` ✅
- `/api/v1/agents/search` ✅
- `/api/v1/agents/categories` ✅
- `/api/v1/agents/index/rebuild` ✅

---

## Kwaliteitsregels toegepast

- Geen `from __future__ import annotations`
- Geen f-strings in logger — `%s` formatting
- `except Exception as e:` altijd met type + exc_info via `logger.exception()`
- `"/"` niet `""` als leeg route-pad
- Geen directe imports van `src.core.database`, `src.core.governance`, `src.core.agents` in router bestanden
- `# orphan:exempt` commentaar op sub-routers >200r en op flat bestanden

---

## Testuitslag

```
135 passed in 13.82s (tests/architecture/ + tests/unit/api/)
```

3 nieuwe architectuurtests groen:
- `test_audit_flat_file_migrated_to_v1`
- `test_memory_flat_file_migrated_to_v1`
- `test_knowledge_flat_file_migrated_to_v1`

Validate feature docs: `[PASS] All 178 IDs have complete documentation.`

---

## Trainingssamenvatting

### Flow 1: Audit missions lijst ophalen

| Stap | Beschrijving |
|---|---|
| **Actor** | Geauthenticeerde gebruiker met `audit:read` scope |
| **Voorwaarde** | Geldige JWT met tenant_id claim aanwezig |
| **Actie** | GET /api/v1/audit/missions?page=1&page_size=20 |
| **Systeemverwerking** | TenantMiddleware injecteert tenant_id; get_tenant() valideert; generate_sample_missions() filtert per tenant |
| **Succesrespons** | 200 AuditListResponse met missions[], total, page, has_more |
| **Foutrespons** | 400 als geen tenant context; 403 als scope ontbreekt |
| **Uitzonderingen** | status_filter optioneel; page/page_size gevalideerd (ge=1, le=100) |

### Flow 2: GDPR mission export

| Stap | Beschrijving |
|---|---|
| **Actor** | Geauthenticeerde gebruiker met `audit:read` scope |
| **Voorwaarde** | Mission bestaat voor de tenant |
| **Actie** | GET /api/v1/audit/missions/{mission_id}/export?format=json |
| **Systeemverwerking** | get_mission_detail() controleert tenant; export event toegevoegd aan audit trail; GDPRExportMetadata geconstrueerd |
| **Succesrespons** | 200 met Content-Disposition header; JSON/CSV/PDF afhankelijk van format param |
| **Foutrespons** | 404 als mission niet gevonden; 403 bij ontbrekende scope |
| **Uitzonderingen** | PDF retourneert gesimuleerde JSON placeholder (niet echte PDF) |

### Flow 3: RAG configuratie bijwerken

| Stap | Beschrijving |
|---|---|
| **Actor** | Geauthenticeerde gebruiker met `workflows:write` scope |
| **Voorwaarde** | Tenant context aanwezig |
| **Actie** | PUT /api/v1/memory/config met RAGConfig body |
| **Systeemverwerking** | save_tenant_config() slaat op in-memory dict; model_changed detectie voor re-index hint |
| **Succesrespons** | 200 RAGConfigResponse met updated_at en updated_by ingevuld |
| **Foutrespons** | 400 als geen tenant; 403 als scope ontbreekt; 422 bij Pydantic validatiefout |
| **Uitzonderingen** | Embedding model change triggert extra message in response (geen automatisch re-index) |

### Flow 4: Knowledge entry aanmaken

| Stap | Beschrijving |
|---|---|
| **Actor** | Admin gebruiker met `admin:all` scope |
| **Voorwaarde** | TaskDistributor beschikbaar; knowledge_agent geregistreerd |
| **Actie** | POST /api/v1/agents/create met KnowledgeCreateRequest |
| **Systeemverwerking** | TaskAssignmentMessage gedispatched naar knowledge_agent via TaskDistributor |
| **Succesrespons** | 200 KnowledgeResponse met success=True, task_id |
| **Foutrespons** | 500 als agent dispatch faalt; 403 bij ontbrekende admin scope |
| **Uitzonderingen** | TaskDistributor auto-start als niet running |
