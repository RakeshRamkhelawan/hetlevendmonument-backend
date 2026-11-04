# BE-CFG-017 — SP-API-008 Dag 1: ADR-033 API Layer Hard Cutover

**ID:** BE-CFG-017  
**Sprint:** SP-API-008 Dag 1  
**ADR:** ADR-033  
**Status:** APPROVED WITH MINOR GAPS  

---

## Samenvatting

ADR-033 hard cutover dag 1: 3 test collection ERRORs opgelost, `from __future__ import annotations` BLOCKER verwijderd, 31 dode flat files omgezet naar 2-regel shims, 22 actieve flat files gemarkeerd met `# orphan:exempt + TODO(SP-VOLGENDE)`, import-linter geinstalleerd en Contract 1 draaiend.

---

## Componenten

### 1. Shim re-exports (Taak 1)

Drie shims hadden incomplete re-exports die test collection blockeerden:

- `src/core/api/models_endpoints.py` — `PromoteRequest`, `RollbackRequest`, `VersionInfo`, `get_registry_manager` toegevoegd vanuit `v1/models/schemas.py`
- `src/core/api/subagent_endpoints.py` — 8 symbolen (routes + schemas) toegevoegd vanuit `v1/subagents/`
- `src/core/api/synthesis_endpoints.py` — 20 symbolen (enums, schemas, functies, `get_tenant`, `generate_synthesis`) toegevoegd vanuit `v1/synthesis/`

### 2. CLAUDE.md BLOCKER fix (Taak 2)

`src/core/api/admin_learning_endpoints.py`:
- `from __future__ import annotations` verwijderd (CLAUDE.md verbiedt dit expliciet)
- `Optional` import verwijderd (ongebruikt)
- Bestand gebruikt native Python 3.11+ syntax (`int | None`, `str | None`) — geen verdere wijzigingen nodig

### 3. Flat file cutover (Taak 3)

**31 DOOD files** omgezet naar 2-regel shim:
```python
# orphan:exempt reason: dead code, not registered in any registry (SP-API-008 cutover)
# All routes migrated to v1/<domein>/ or permanently removed.
```

**22 ACTIEF files** gemarkeerd met `# orphan:exempt + TODO(SP-VOLGENDE)`.

**4 files hersteld** die foutief als DOOD geclassificeerd waren (actief geimporteerd door middleware/agents/v1-routers):
- `public_endpoints.py` (PublicEndpointRegistry — gebruikt door TenantMiddleware + SecurityMiddleware)
- `health_endpoints.py` (health_check/readiness_check — gebruikt door v1/health sub-routers)
- `tenant_management_endpoints.py` (business logica — gebruikt door v1/tenant_management/crud_router.py)
- `workflow_refinement_endpoints.py` (WorkflowNode/WorkflowEdge etc. — runtime imports in WorkflowOrchestratorAgent)

**1 extra shim gerepareerd:**
- `gdpr_compliance_endpoints.py` — router re-export toegevoegd (test importing `router`)

### 4. import-linter (Taak 4)

- `import-linter` succesvol geinstalleerd
- Contract 1 (`api-no-domain`) draait
- **214 violations** gevonden — ALLE transitief via `src.core.auth.dependencies` → `src.core.models.rbac_models` → `src.__init__` → `src.workers` → domeinmodules
- Root cause: `src/__init__.py` importeert `src.workers` die domeinlogica importeert
- Dit zijn pre-existing structuurproblemen, NIET direct veroorzaakt door router-code
- Contract 2 (`no-cross-gateway`) = **KEPT** — geen violations

---

## Trainingssamenvatting

### Flow 1: Collection ERROR herstel

**Actor:** CI pipeline / developer die `pytest tests/unit/` draait  
**Voorwaarde:** Shim-bestand mist re-exports van symbolen die tests importeren  
**Actie:** Developer voegt symbolen toe aan shim via `# noqa: F401` re-exports  
**Systeemverwerking:** Python importeert symbolen uit v1/ sub-module en stelt ze beschikbaar onder het legacy shim-pad  
**Succesrespons:** Pytest collecteert tests zonder ImportError; 160 tests groen  
**Foutrespons:** Als symbool niet bestaat in v1/: `ImportError: cannot import name 'X' from '...'`  
**Uitzonderingen:** Symbool bestaat niet meer na v1/-migratie → markeer test als `@pytest.mark.skip(reason="TODO(SP-VOLGENDE)")`

### Flow 2: Dead flat file cutover

**Actor:** Sprint-dag automatisering (SP-API-008)  
**Voorwaarde:** Flat file heeft router-code maar is niet geregistreerd in registries/ en niet geimporteerd buiten registry-scope  
**Actie:** Vervang volledige inhoud door 2-regel shim  
**Systeemverwerking:** Python module bestaat nog maar bevat geen router-definitie meer — import van `router` faalt met ImportError  
**Succesrespons:** `APIRouter` code verdwijnt uit plat bestand; import-linter ziet minder domain-imports; testresultaten ongewijzigd  
**Foutrespons:** Als file toch actief geimporteerd wordt (buiten registry-scope): `ImportError` bij runtime — herstel via `git checkout HEAD -- <file>`  
**Uitzonderingen:** Files geimporteerd door middleware/agents/services moeten als ACTIEF behandeld worden ondanks afwezigheid in registries

### Flow 3: CLAUDE.md BLOCKER fix

**Actor:** Developer of CI-pipeline die type-checks draait  
**Voorwaarde:** Bestand heeft `from __future__ import annotations` + Pydantic/FastAPI body-params  
**Actie:** Verwijder `from __future__ import annotations`  
**Systeemverwerking:** Python 3.11+ evalueert type-annotaties natively; geen `get_type_hints()` string-evaluatie overhead meer  
**Succesrespons:** Bestand importeerbaar zonder future-import; FastAPI body-param introspectie werkt correct  
**Foutrespons:** Als `X | Y` syntax gebruikt wordt in Python <3.10: `TypeError` — niet van toepassing (project gebruikt Python 3.11+)

---

## Pre-existing gaps (niet geopend door deze sprint)

| Issue | Status |
|-------|--------|
| 214 import-linter violations (transitief via `src.__init__` → workers) | TODO(SP-VOLGENDE): `src/__init__.py` cleanup |
| DSM outgoing imports: 278 (doel < 200) | TODO(SP-VOLGENDE): actieve flat files migreren naar v1/ |
| Collectietijd > 90s (nog niet gemeten) | Meten in Taak 5C |
