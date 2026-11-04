# BE-RTR-028 -- Feature Flags Domain Migration naar v1/feature_flags/

**Sprint:** SP-API-006 Dag 3
**Datum:** 2026-06-05
**Commit:** b4afc787
**Status:** DONE

---

## Overzicht

`feature_flags_endpoints.py` (477 regels, flat file) is gemigreerd naar de drie-laags
ADR-033 structuur onder `src/core/api/v1/feature_flags/`. De migratie volgt het
Strangler Fig patroon: de flat file is vervangen door een shim re-export, zodat
bestaande import-paden compatibel blijven.

---

## Bestanden

| Bestand | Regels | Rol |
|---------|--------|-----|
| `src/core/api/v1/feature_flags/__init__.py` | 9 | Laag 2 domain_router (prefix="/api") |
| `src/core/api/v1/feature_flags/router.py` | 16 | Composite router (GEEN prefix) |
| `src/core/api/v1/feature_flags/features_router.py` | 82 | GET /features |
| `src/core/api/v1/feature_flags/tenant_router.py` | 165 | GET /tenant/features, GET /tenant/tier, GET /tenant/features/{feature}/check |
| `src/core/api/v1/feature_flags/admin_router.py` | 105 | POST /admin/features/{feature}/toggle |
| `src/core/api/v1/feature_flags/dependencies.py` | 29 | Shared lazy-import helpers |
| `src/core/api/feature_flags_endpoints.py` | 2 | Shim re-export (orphan:exempt) |
| `src/core/api/registries/analytics.py` | 67 | Bijgewerkte registry import |

---

## Routes (5 stuks, URL-freeze ADR-031)

| Methode | Pad | Sub-router |
|---------|-----|------------|
| GET | /api/features | features_router.py |
| GET | /api/tenant/features | tenant_router.py |
| GET | /api/tenant/tier | tenant_router.py |
| POST | /api/admin/features/{feature}/toggle | admin_router.py |
| GET | /api/tenant/features/{feature}/check | tenant_router.py |

---

## Pre-existing issues gevonden en gefixed

| Issue | Beschrijving | Actie |
|-------|-------------|-------|
| FREE tier in upgrade path | `tier_order.index(Tier.FREE)` gooide `ValueError` (FREE niet in upgrade lijst) | Vervangen door `try/except ValueError` met `current_index = -1` fallback |

---

## Kwaliteitschecks

- Geen `from __future__ import annotations`
- Geen f-strings in logger calls (alle `logger.info("... %s", waarde)`)
- `exc_info=True` niet van toepassing (geen try/except op errors die naar logs gaan)
- Geen `datetime.utcnow()` of `datetime.now()`
- tenant_id altijd uit `get_tenant_id()` (lazy JWT context)
- Geen hardcoded secrets of URLs

---

## Trainingssamenvatting

### Flow 1: Tenant vraagt eigen features op (GET /api/tenant/features)

| Stap | Detail |
|------|--------|
| **Actor** | Geinlogde tenant-gebruiker via browser of API client |
| **Voorwaarde** | Geldig JWT token; TenantMiddleware heeft tenant context gezet |
| **Actie** | GET /api/tenant/features |
| **Systeemverwerking** | `get_tenant_id()` leest tenant uit JWT context; ORM query op `Tenant` table; `get_tier_features(tier)` retourneert feature-lijst |
| **Succesrespons** | HTTP 200 `{"tenant_id": "42", "tier": "pro", "enabled_features": [...], "total_features": 8}` |
| **Foutrespons** | HTTP 400 als geen tenant context; HTTP 404 als tenant niet bestaat |
| **Uitzonderingen** | TenantMiddleware niet geregistreerd -> RuntimeError vanuit `get_tenant_id()` |

### Flow 2: Admin togglet feature voor andere tenant (POST /api/admin/features/{feature}/toggle)

| Stap | Detail |
|------|--------|
| **Actor** | Platform admin gebruiker |
| **Voorwaarde** | JWT met admin-rol; `ff_manager` aanwezig op `app.state` |
| **Actie** | POST /api/admin/features/memory_mcp/toggle?target_tenant_id=42 body: `{"enabled": true}` |
| **Systeemverwerking** | `require_admin(admin_user)` verifieert rol; `Feature(feature)` valideert feature naam; `TenantFilterBypass` inschakelen; PostgreSQL RLS context zetten via `set_config`; `FeatureFlag` upsert; Redis cache invalidatie |
| **Succesrespons** | HTTP 200 `{"success": true, "feature": "memory_mcp", "tenant_id": "42", "enabled": true}` |
| **Foutrespons** | HTTP 400 ongeldige feature naam; HTTP 403 geen admin-rol; HTTP 503 ff_manager niet beschikbaar |
| **Uitzonderingen** | Redis niet beschikbaar -> cache invalidatie wordt overgeslagen (niet fataal) |

### Flow 3: Frontend check voor UI-rendering (GET /api/tenant/features/{feature}/check)

| Stap | Detail |
|------|--------|
| **Actor** | Frontend applicatie die UI-elementen wil tonen/verbergen |
| **Voorwaarde** | Geldig JWT; `ff_manager` op `app.state` |
| **Actie** | GET /api/tenant/features/memory_mcp/check |
| **Systeemverwerking** | Valideer feature naam; `ff_manager.is_enabled(tenant_id_str, feature_enum)` checkt Redis cache + DB; ORM query voor current tier |
| **Succesrespons** | HTTP 200 `{"feature": "memory_mcp", "enabled": false, "minimum_tier": "pro", "current_tier": "starter", "upgrade_required": true, "upgrade_url": "/upgrade?feature=memory_mcp"}` |
| **Foutrespons** | HTTP 400 ongeldige feature; HTTP 503 ff_manager niet beschikbaar |
| **Uitzonderingen** | Tenant niet in DB -> `current_tier` defaults naar STARTER (graceful degradation) |
