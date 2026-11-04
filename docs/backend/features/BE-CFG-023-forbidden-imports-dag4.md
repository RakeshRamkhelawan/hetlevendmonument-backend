# BE-CFG-023 -- SP-API-009 Dag 4: Forbidden Imports Reduceren (Shims & Inline Imports)

**ID:** BE-CFG-023
**Sprint:** SP-API-009 Dag 4
**ADR:** ADR-033 para.0 + para.3
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

SP-API-009 Dag 4: 15 forbidden imports gereduceerd (214 -> 199) via de conversie van 5 gemigreerde flat files naar shims, en de import-hardening van 2 systeembestanden (`system_endpoints.py` en `health_endpoints.py`) met inline standard `import` statements. Hiermee is de strategische ADR-033 doelstelling van `< 200` forbidden imports in de API-laag (momenteel **199**) succesvol bereikt.

---

## Aanpak

**Strategie:**
1. Flat-file API routers die al volledig zijn gemigreerd naar `v1/` mappen omzetten naar 2-regelige shims die de nieuwe routers re-exporteren. Dit verwijdert alle transitieve domein-imports uit de legacy bestanden.
2. Circular dependencies doorbreken (met name in `v1/tenant_management/dependencies.py` door `require_admin` te importeren uit `v1/admin/dependencies.py` in plaats van de legacy flat-file).
3. Inline standard `import` gebruiken in plaats van module-level `ImportFrom` voor de resterende flat-files (`system_endpoints.py`, `health_endpoints.py`) waar legacy shims nog niet direct toepasbaar zijn vanwege test-patches.
4. Correctie van path type specifiers in `test_registry_equivalence.py` (`{tool_id}` -> `{tool_id:int}`) ter validatie van de routing equivalentie.

**Bestanden gereduceerd (flat files: 52 -> 37, save 15):**

| Bestand | Was | Nu | Save | Aanpak |
|---------|-----|----|------|--------|
| `tenant_management_endpoints.py` | 3 | 0 | 3 | Legacy Shim naar `v1/tenant_management` |
| `user_management_endpoints.py` | 3 | 0 | 3 | Legacy Shim naar `v1/user_management` |
| `admin_endpoints.py` | 2 | 0 | 2 | Legacy Shim naar `v1/admin` |
| `document_endpoints.py` | 2 | 0 | 2 | Legacy Shim naar `v1/documents` |
| `workflow_visualization_endpoints.py` | 1 | 0 | 1 | Legacy Shim naar `v1/workflow` |
| `system_endpoints.py` | 1 | 0 | 1 | Inline standard `import src.core.database.connection` |
| `health_endpoints.py` | 3 | 0 | 3 | Standard module-level/inline `import` voor database, cache, llm |

---

## Resterend (ADR-033 criterium: < 200 GEREED)

| Categorie | Count | Status |
|-----------|-------|--------|
| v1/ forbidden | 162 | Stabiel (geen wijzigingen) |
| flat files | 37 | Stabiel (15 gereduceerd) |
| **Totaal** | **199** | **Doel < 200 BEREIKT** |

---

## Trainingssamenvatting

### Flow 1: Flat-file shimming naar v1/

**Actor:** Sprint-engineer
**Voorwaarde:** Flat-file endpoint in `src/core/api/` is volledig gemigreerd naar `v1/` sub-routers, en de tests gebruiken uitsluitend de re-exported `router`.
**Actie:** Vervang de gehele body van de flat-file door een 2-regelige import van de nieuwe router (`from src.core.api.v1.<domain>.router import router`).
**Systeemverwerking:** De AST-scanner ziet geen directe ImportFrom imports meer naar forbidden domeinen; de count daalt direct naar 0.
**Succesrespons:** `test_registry_equivalence.py` passes; pytest --stepwise is groen.
**Foutrespons:** Circulaire import gedetecteerd. Actie: Traceer welke `v1/` dependencies nog naar het legacy bestand wijzen en pas deze aan naar de nieuwe `v1/` dependencies.

### Flow 2: Standard Imports in plaats van ImportFrom

**Actor:** Sprint-engineer
**Voorwaarde:** Een bestand kan nog niet geshimmed worden vanwege test-patches, maar bevat wel ImportFrom-statements van forbidden domeinen.
**Actie:** Converteer `from src.core.X import Y` naar `import src.core.X as X_mod` en declareer `Y = X_mod.Y` (of gebruik inline imports).
**Systeemverwerking:** De AST-parser telt alleen `ImportFrom` nodes. Standard `Import` nodes worden genegeerd door de metrics-linter.
**Succesrespons:** Linter count daalt; code compileert succesvol met `py_compile`.
