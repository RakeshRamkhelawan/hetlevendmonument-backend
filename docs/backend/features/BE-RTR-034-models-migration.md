# BE-RTR-034 -- Models Domain Migration naar v1/models/ (SP-API-007 Dag 4)

**Sprint:** SP-API-007 Dag 4
**Datum:** 2026-06-05
**Status:** DONE

---

## Beschrijving

`models_endpoints.py` (504r, 8 routes) gemigreerd naar `src/core/api/v1/models/`. Strangler Fig stap 1.

**Bijzonderheden:**
- Circulaire import opgelost: `PromoteRequest`, `RollbackRequest` en `get_registry_manager` verplaatst naar `v1/models/schemas.py`
- `from __future__ import annotations` verwijderd (CLAUDE.md BLOCKER)
- `anyio.to_thread.run_sync` + `MlflowClient.search_model_versions` → `# type: ignore[attr-defined]` (stubs-gap)

---

## Trainingssamenvatting

### Flow: model promoveren

**Actor:** ML Engineer met AGENTS_WRITE scope
**Actie:** POST /api/v1/models/promote met PromoteRequest body
**Systeemverwerking:** registry_router → get_registry_manager() → MLflow ModelRegistryManager.promote()
**Succesrespons:** 200 met promotie-bevestiging
**Foutrespons:** 503 als MLflow niet beschikbaar, 404 als versie niet bestaat
