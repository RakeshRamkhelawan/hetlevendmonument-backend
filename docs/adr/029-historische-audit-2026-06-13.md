# ADR-029 Foundation Portal — Hernieuwde Audit

**Datum:** 2026-06-13
**Gebaseerd op:** ADR-029 v0.4 (2026-05-24) + codebase stand post-ADR-033 refactoring
**Refactoring-impact:** ADR-033 (API Layer Service Boundary, 2026-06-02–12) + ADR-032 (Frontend Page Architecture, 2026-05-28)

---

## Samenvatting

De **data-laag (Fase 1)** van ADR-029 is intact gebleven tijdens de refactoring. De **API-laag en frontend** zijn echter volledig afwezig — niet verdwenen, maar simpelweg nooit gebouwd. De ADR-033 refactoring heeft de structuur waarin ze hadden moeten landen (`src/core/api/v1/<domein>/`) nu wel correct neergezet, maar de Foundation Portal domeinmap (`v1/foundation/`) ontbreekt volledig.

**Conclusie:** ADR-029 is ~**20% compleet**. Fase 1 (modellen, migraties, tests) is af. Fase 2–5 (services, API, frontend, security, launch) zijn 0%.

---

## 1. Wat is WEL klaar ✅

### 1.1 Data-laag (Fase 1 — intact gebleven)

| Onderdeel | Locatie | Status | Opmerking |
|---|---|---|---|
| **7 modellen** | `src/core/models/foundation_content.py` | ✅ | Niet gewijzigd sinds vorige audit |
| **5 Alembic-migraties** | `src/alembic/versions/20260524a-e` | ✅ | Chain intact, single-head |
| **Model registry** | `src/core/database/model_registry.py:82` | ✅ | `core.foundation` groep geregistreerd |
| **Tenant resolver** | `src/core/services/foundation_tenant_resolver.py` | ✅ | **Gemigreerd** met `TenantFilterBypass` fix (regel 53) |
| **12 Exceptions** | `src/core/exceptions/foundation.py` | ✅ | Onveranderd |
| **Slug-validatie** | `src/core/schemas/validators.py` | ✅ | `FOUNDATION_RESERVED_SLUGS` + `strict=True` |
| **6 Rate-limiters** | `src/core/governance/rate_limiter.py:313` | ✅ | `_ip_key`, `_email_key`, 6 decorators |
| **Public prefix** | `src/core/shared/public_registry.py:54` | ✅ | `/api/v1/public/` geregistreerd; bestand **verplaatst** van `middleware/` → `shared/` (ADR-033 circulaire dep fix) |

### 1.2 Tests (Fase 1 — intact)

| Test | Locatie | Status |
|---|---|---|
| Model unit tests | `tests/unit/test_foundation_models.py` | ✅ 24 tests |
| Tenant resolver tests | `tests/unit/test_foundation_tenant_resolver.py` | ✅ 9 tests |
| Rate limiter tests | `tests/unit/test_foundation_rate_limiters.py` | ✅ 10 tests |
| Exception tests | `tests/unit/test_foundation_exceptions.py` | ✅ 11 tests |
| Public registry tests | `tests/unit/test_public_endpoint_registry.py` | ✅ 4 tests |
| Migration integratie | `tests/integration/foundation/test_migrations.py` | ✅ 31 tests |
| RLS security | `tests/integration/security/test_foundation_rls.py` | ✅ 7 tests |
| Slug validatie | `tests/unit/test_slug_validation.py` | ✅ Deels foundation-gerelateerd |

**Totaal: ~96 tests groen** (voor zover verifieerbaar zonder DB).

### 1.3 Runbooks & Documentatie (procedureel, geen code)

| Onderdeel | Locatie | Status |
|---|---|---|
| Runbook index | `docs/runbooks/foundation-portal/README.md` | ✅ Aanwezig |
| Onboard tenant | `docs/runbooks/foundation-portal/onboard-tenant.md` | ✅ Aanwezig |
| Deprovision tenant | `docs/runbooks/foundation-portal/deprovision-tenant.md` | ✅ Aanwezig |
| Backup/restore | `docs/runbooks/foundation-portal/backup-restore.md` | ✅ Aanwezig |
| Incident response | `docs/runbooks/foundation-portal/incident-response.md` | ✅ Aanwezig |
| Content takedown | `docs/runbooks/foundation-portal/content-takedown.md` | ✅ Aanwezig |
| Monitoring | `docs/runbooks/foundation-portal/monitoring-alerting.md` | ✅ Aanwezig |
| Release checklist | `docs/runbooks/foundation-portal/release-checklist.md` | ✅ Aanwezig |

### 1.4 Nieuwe architectuurstructuren die ADR-029 faciliteren

De ADR-033 refactoring heeft de infrastructuur neergezet waarin ADR-029 nu correct kan worden geïmplementeerd:

| Nieuwe structuur | Waarde voor ADR-029 |
|---|---|
| `src/core/api/v1/<domein>/` patroon | Foundation portal kan nu landen als `v1/foundation/` |
| `router.py` + `schemas.py` + `dependencies.py` + `gateway.py` | Duidelijke template voor public endpoints |
| `import-linter` Contract 1 | Voorkomt dat foundation routers direct domeinlogica importeren |
| `registries/` splitsing | Foundation registry kan worden toegevoegd zonder God-bestand |
| Orphan-detectie via AST | Een nieuwe foundation router die niet geregistreerd is, wordt direct gedetecteerd |

---

## 2. Wat moet nog gedaan worden ❌

### 2.1 Backend — API-laag (Fase 3)

**Kritieke bevinding:** Er is **geen `src/core/api/v1/foundation/` directory**. De Foundation Portal heeft geen enkele endpoint in de nieuwe ADR-033 structuur. Dit is de grootste lacune.

| Vereist endpoint | ADR-029 specificatie | Status |
|---|---|---|
| `GET /api/v1/public/{slug}/content` | Publieke content lijst | ❌ Niet gebouwd |
| `GET /api/v1/public/{slug}/content/{id}` | Content detail | ❌ Niet gebouwd |
| `POST /api/v1/public/{slug}/magic-link` | Magic-link aanvraag | ❌ Niet gebouwd |
| `GET /api/v1/public/{slug}/verify?token=` | Token verify + JWT | ❌ Niet gebouwd |
| `POST /api/v1/public/{slug}/content` | Upload (multipart) | ❌ Niet gebouwd |
| `POST /api/v1/public/{slug}/takedown` | NTD aanvraag | ❌ Niet gebouwd |
| `POST /api/v1/public/{slug}/newsletter/subscribe` | Newsletter | ❌ Niet gebouwd |
| `GET /api/v1/public/{slug}/settings` | Portal branding | ❌ Niet gebouwd |
| `GET /api/v1/public/{slug}/me/export` | DSAR export | ❌ Niet gebouwd |
| `POST /api/revalidate` | ISR on-demand | ❌ Niet gebouwd |
| Admin endpoints | Curatie queue, approve/reject | ❌ Niet gebouwd |

### 2.2 Backend — Services (Fase 2)

| Service | ADR-029 specificatie | Status |
|---|---|---|
| **Magic-link auth service** | JWT `scope=portal_uploader`, SHA-256 verify | ❌ |
| **Brevo e-mail client** | Transactional magic-link + newsletter | ❌ |
| **hCaptcha integratie** | Vóór magic-link aanvraag | ❌ |
| **Azure Blob storage** | Upload, magic-bytes, SAS-URL's | ❌ |
| **AI-tagging Dramatiq worker** | Ollama `mistral:7b-instruct` | ❌ |
| **DSAR export service** | Portal-user data export | ❌ |
| **ISR revalidatie service** | HMAC-signed POST naar Next.js | ❌ |

### 2.3 Frontend — Next.js Portal (Fase 4)

**Kritieke bevinding:** ADR-032 (Frontend Page Architecture) definieert **22 interne dashboard pagina's** (00-21). Geen enkele is een Foundation Portal pagina. Er is **geen aparte Next.js 14 repo** voor het portal.

De huidige `frontend/` map bevat uitsluitend het SanskritiSetu interne dashboard:
- Landing page, Login, Register, Demo, Dashboard, Agents, Compliance, Instellingen, Admin, etc.
- **Geen** portal homepage, content browse, upload flow, magic-link login, kaartweergave, etc.

### 2.4 Cat 3 & Cat 4 Subsidie-uitbreidingen

Deze vijf uitbreidingen zijn **volledig afwezig** in zowel model als API:

| Uitbreiding | ADR-029 v0.4 eis | Status |
|---|---|---|
| **Educatieve leeromgeving** | `EducationalAccess` model, access-code flow, `visibility: edu` | ❌ |
| **Kaartweergave + geo** | `latitude`/`longitude` in `FoundationContent`, `GET /map/bbox` | ❌ |
| **Polymorfe content-types** | 11 types (nu 6), `metadata` JSONB per type | ❌ |
| **OAI-PMH endpoint** | `GET /oai-pmh?verb=ListRecords` Dublin Core | ❌ |
| **School-/docententoegang** | `PortalUser.role` = `teacher`, edu curatie-queue | ❌ |
| **Archivering (BagIt)** | Wekelijkse Dramatiq-job | ❌ |

### 2.5 Tier-upgrade & commerciële flow (post-MVP)

| Onderdeel | Status |
|---|---|
| Stripe Checkout + webhook | ❌ |
| `Tenant.plan` upgrade via console | ❌ |
| FeatureFlagManager portal-features | ❌ |

---

## 3. Wat is er GEREFACTORED sinds de vorige audit 🔧

### 3.1 Verplaatste bestanden (ADR-033 impact)

| Oud pad | Nieuw pad | Reden |
|---|---|---|
| `src/core/middleware/public_registry.py` | `src/core/shared/public_registry.py` | Circulaire dep auth ↔ tenancy opgelost |
| `src/core/api/public_endpoints.py` | `src/core/shared/public_registry.py` (re-export) | Idem; oude file is shim |

### 3.2 Toegevoegde fixes in bestaande foundation-code

| Bestand | Wijziging | Waarom |
|---|---|---|
| `foundation_tenant_resolver.py:53` | `TenantFilterBypass()` toegevoegd rond tenant lookup | ADR-033 fix: anders blokkeert de ORM-hook de tenant-resolutie zelf |

### 3.3 Nieuwe infrastructuur die ADR-029 nu kan gebruiken

| Infrastructuur | Waarde |
|---|---|
| `src/core/api/v1/` domeinstructuur | Foundation kan nu als `v1/foundation/` worden geïmplementeerd |
| `import-linter` | Voorkomt dat foundation routes direct DB/services importeren |
| `router_registry.py` (~65r) | Foundation registry kan worden toegevoegd zonder merge-conflicts |
| `src/core/shared/public_registry.py` | Centrale bron voor public prefixes; `/api/v1/public/` staat erin |
| `tenant_middleware.py` | Sluit `PublicEndpointRegistry.is_public()` correct af |

### 3.4 Architectuur-patronen die ADR-029 moet volgen

Uit ADR-033 en ADR-032 zijn deze patronen nu verplicht voor nieuwe ADR-029 code:

```
# CORRECT — thin delivery (ADR-033 §0)
@router.post("/content")
async def create_content(
    request: CreateContentRequest,
    svc: FoundationService = Depends(get_foundation_service),
) -> ContentResponse:
    return await svc.create(request, tenant_id=current_user.tenant_id)

# FOUT — directe DB in route (nu geblokkeerd door import-linter Contract 1)
@router.post("/content")
async def create_content(db: AsyncSession = Depends(get_db)): ...
```

```
# CORRECT — v1 domeinstructuur (ADR-033 §1)
src/core/api/v1/foundation/
├── __init__.py         # composite router
├── router.py           # alleen routes (max 200r)
├── schemas.py          # Pydantic models
├── dependencies.py     # FastAPI Depends
└── gateway.py          # cross-module interface
```

---

## 4. Impact-analyse: wat wordt er geraakt?

### 4.1 Nieuwe bestanden die ADR-029 nog moet aanmaken

| Bestand | Doel | Schatting |
|---|---|---|
| `src/core/api/v1/foundation/__init__.py` | Composite router | 30 regels |
| `src/core/api/v1/foundation/router.py` | Public endpoints (max 200r) | 150-200 regels |
| `src/core/api/v1/foundation/schemas.py` | Pydantic request/response | 100-150 regels |
| `src/core/api/v1/foundation/dependencies.py` | `get_portal_user`, `require_uploader` | 50-80 regels |
| `src/core/api/v1/foundation/gateway.py` | Application service facade | 100 regels |
| `src/core/api/registries/foundation.py` | Registry registratie | 20 regels |
| `src/core/services/foundation_service.py` | Core business logica | 200-300 regels |
| `src/core/services/magic_link_service.py` | Token generatie + verificatie | 100 regels |
| `src/core/services/brevo_client.py` | E-mail verzending | 80 regels |
| `src/core/services/azure_blob_service.py` | Blob upload + SAS | 100 regels |
| `src/workers/ai_tagging_worker.py` | Dramatiq + Ollama | 80 regels |
| `tests/unit/test_foundation_router.py` | Route tests | 50-100 regels |
| `tests/unit/test_foundation_service.py` | Service tests | 50-100 regels |
| `tests/integration/test_foundation_api.py` | E2E API tests | 100-150 regels |
| `tests/security/test_foundation_tenant_isolation.py` | Cross-tenant isolation (7 modellen) | 100 regels |

**Totaal geschat: ~1.500-2.000 regels backend code + tests.**

### 4.2 Frontend: apart project

ADR-029 eist een **aparte MIT-repo** `levend-monument-portal`. Dit valt buiten de huidige `frontend/` map. Schatting:

| Onderdeel | Regels |
|---|---|
| Next.js 14 App Router setup | 200 |
| 14 pagina's (homepage, browse, detail, upload, login, etc.) | 1.400 |
| Shared components (header, footer, content cards, map) | 600 |
| API client hooks (TanStack Query) | 300 |
| Tailwind / Radix UI theming | 200 |
| **Totaal geschat** | **~2.700 regels** |

### 4.3 Bestaande bestanden die ADR-029 aanraakt

| Bestand | Huidige wijziging | Toekomstige wijziging |
|---|---|---|
| `src/core/api/router_registry.py` | Geen foundation | Registreer `foundation` registry |
| `src/core/shared/public_registry.py` | `/api/v1/public/` aanwezig | Mogelijk: custom-domain prefix (fase 2) |
| `src/core/governance/rate_limiter.py` | 6 foundation decorators | Mogelijk: extra rate-limiters voor nieuwe endpoints |
| `src/core/feature_flags/features.py` | `FREE`/`STARTER`/`PRO`/`ENTERPRISE` | Mogelijk: `FOUNDATION_PORTAL` feature toevoegen |
| `src/core/middleware/tenant_middleware.py` | `is_public()` check | Geen wijziging nodig |
| `src/core/database/model_registry.py` | 7 modellen geregistreerd | Mogelijk: `EducationalAccess` toevoegen (Cat 3) |

---

## 5. Risico's & Blockers

| Risico | Ernst | Mitigatie |
|---|---|---|
| **Geen v1/foundation/ directory** betekent dat ADR-029 code niet in de nieuwe ADR-033 structuur past | Hoog | Bij implementatie: volg `v1/<domein>/` patroon vanaf dag 1 |
| **24 flat files** in `src/core/api/` zijn nog niet gemigreerd (SP-API-011) — nieuwe foundation code moet niet als flat file worden toegevoegd | Medium | Gebruik `v1/foundation/` direct |
| **Frontend is 100% intern dashboard** — geen portal | Hoog | Apart Next.js project starten; geen mixing met huidige frontend |
| **Cat 3/4 uitbreidingen ontbreken** in model — migratie nodig | Medium | 1-2 extra Alembic migraties na Fase 1 |
| **import-linter Contract 1** blokkeert directe imports van `src.core.services` vanuit routers | Laag | Gebruik `gateway.py` + `dependencies.py` patroon |

---

## 6. Aanbevelingen

### 6.1 Implementatievolgorde (gezien ADR-033 context)

1. **Stap 0:** Creëer `src/core/api/v1/foundation/` met lege `__init__.py`, `router.py`, `schemas.py`, `dependencies.py`, `gateway.py`
2. **Stap 1:** Registreer in `src/core/api/registries/foundation.py` + `router_registry.py`
3. **Stap 2:** Bouw `gateway.py` (application service) + `dependencies.py`
4. **Stap 3:** Bouw `router.py` met `GET /public/{slug}/content` en `GET /public/{slug}/settings`
5. **Stap 4:** Voeg services toe: `foundation_service.py`, `magic_link_service.py`
6. **Stap 5:** Voeg overige endpoints toe (upload, takedown, newsletter)
7. **Stap 6:** Tests: unit + integratie + security isolation
8. **Stap 7:** Apart Next.js project starten

### 6.2 Architectuur-compatibiliteit checklijst

Voor elke nieuw geschreven regel ADR-029 code:

- [ ] Router importeert NIET direct `get_db`, ORM-modellen, of core services (import-linter Contract 1)
- [ ] Router is ≤ 200 regels (ADR-033 §2)
- [ ] Gateway-methode beschrijft één domein use case (ADR-033 §3b)
- [ ] `tenant_id` is `int` (nooit UUID of string) (ADR-032 C-3 fix)
- [ ] Geen `datetime.now()` — gebruik `func.now()` of timezone-aware UTC (CLAUDE.md)
- [ ] Geen emoji of non-ASCII in code/comments/logs (CLAUDE.md)
- [ ] `# orphan:exempt` comment alleen als echt nodig

---

*Audit uitgevoerd op 2026-06-13. Codebase-refactoring: ADR-033 (SP-API-008 t/m SP-API-011) en ADR-032 zijn beide Accepted en actief in productie.*
