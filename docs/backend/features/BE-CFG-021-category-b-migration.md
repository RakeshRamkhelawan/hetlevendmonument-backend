# BE-CFG-021 — SP-API-009 Dag 2: Circulaire Dep Fixes + Categorie B Analyse

**ID:** BE-CFG-021
**Sprint:** SP-API-009 Dag 2
**ADR:** ADR-033
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

SP-API-009 Dag 2: 4 root-cause circulaire dependencies gefixed (auth: 1→0, agent_runtime: 11→1), str(e) cache-endpoints opgeschoond, monitoring/sandbox prefix-discrepantie geanalyseerd, Categorie B migratie uitgesteld door analytics.py 80r-limiet.

---

## Resultaten

### Circulaire Deps (Taak 4)

**Voor:** auth=1, agent_runtime=11 = 12 totaal  
**Na:** auth=0, agent_runtime=1 = 1 totaal

| Root cause | Fix | Impact |
|------------|-----|--------|
| A: `get_db` via API-laag | `agents/knowledge_agent/routes.py` + `translation_agent/routes.py` → `database.database` | auth=0 bereikt |
| B: `global_pack_repo` singleton | Verwijderd (was al weg in SP-A02); methoden uitgeschakeld + TODO | 2 broken imports opgeruimd |
| C: Workflow schemas in endpoint | `workflow_refinement_endpoints.py` klassen → `src/core/workflow/schemas.py`; shim re-export; 3 bestanden bijgewerkt | agent_runtime -4 |
| D: `PublicEndpointRegistry` in API-laag | Verplaatst naar `src/core/middleware/public_registry.py`; shim in `public_endpoints.py`; `security_middleware.py` + `tenant_middleware.py` bijgewerkt | auth: 1→0 |

**Resterend (1):** `focus_builder_chat_agent.py:343` importeert `_get_internal_agents` van `v1/focus_builder/agents.py`. Gemarkeerd met TODO(SP-VOLGENDE) — verplaatsen vereist grotere refactoring van de focus_builder API module.

### Str(e) cache-endpoints (Taak 1)

3 lokaties in `system_endpoints.py` (admin-only cache endpoints) vervangen door `"Internal error"` + `logger.warning(..., exc_info=True)`.

### Monitoring/sandbox prefix-analyse (Taak 2)

- `monitoring_dashboard_endpoints` shim re-exporteert `v1/monitoring_v1/dashboard_router` (GEEN prefix). `registries/analytics.py` registreert `v1/monitoring_v1/domain_router` MET `/api/v1` prefix. Verschillende paden → GEEN duplicaat.
- `sandbox_endpoints` setup=no-prefix, registries=`/api/v1` → GEEN duplicaat.
- Beide bewaard met TODO-comment.

### Categorie B migratie (Taak 3) — uitgesteld

`registries/analytics.py` is al op 80r (ADR-033 max). De 12 categorie-B shims zijn nog niet naar registries/ verplaatst. Uitgesteld naar Dag 3 of SP-VOLGENDE met registry-splitsing.

### DSM meting

| Meting | Count |
|--------|-------|
| Baseline (start Dag 1) | 334 |
| Na Dag 2 fixes | 335 |

+1 door `workflow_refinement_endpoints.py` shim die nu `src.core.workflow.schemas` importeert (circulaire dep doorbroken maar shim-import telt mee). Structureel verbeterd.

---

## Nieuwe bestanden

| Bestand | Doel |
|---------|------|
| `src/core/middleware/public_registry.py` | `PublicEndpointRegistry` — middleware-eigendom |
| `src/core/workflow/schemas.py` | `WorkflowNode`, `WorkflowEdge`, `WorkflowDefinition`, `RefinementSuggestion` |

---

## Trainingssamenvatting

### Flow 1: Circulaire dep doorbreken via klasse-verplaatsing

**Actor:** Sprint-engineer  
**Voorwaarde:** Module in domeinlaag importeert een klasse/functie die gedefinieerd is in de API-laag  
**Actie:** Verplaats klasse naar de domeinlaag; voeg shim re-export toe in het API-bestand; update alle callers  
**Systeemverwerking:** AST-scan verifieert dat het aantal `src.core.api` imports in domeinlaag daalt; tests blijven groen  
**Succesrespons:** Circulaire dep teller daalt; klasse is bereikbaar via beide paden (backward compat via shim)  
**Foutrespons:** Als callers de shim gebruiken maar de klasse is niet correct re-geëxporteerd: `ImportError`. Logger altijd met `exc_info=True` per CLAUDE.md §11  
**Uitzonderingen:** Klassen die sterk API-specifiek zijn (FastAPI dependencies, request schemas) kunnen niet worden verplaatst zonder de API-laag te importeren

### Flow 2: Dode import detecteren en opruimen

**Actor:** Sprint-engineer  
**Voorwaarde:** Code importeert een module-singleton die al verwijderd is in een eerdere sprint  
**Actie:** Test de import (`python -c "from ... import X"`); als ImportError → verwijder import; voeg TODO-comment toe  
**Systeemverwerking:** Method body zonder werkende import wordt uitgeschakeld met `logger.warning`; bestaande functionaliteit blijft intact (graceful degradation)  
**Succesrespons:** ImportError verdwijnt; methode werkt degraded; circulaire dep count daalt  
**Foutrespons:** Als methode essentieel is voor core flows: geef expliciet `NotImplementedError` met duidelijke foutmelding  
**Uitzonderingen:** Singletons die bewust als module-level objects leven: verplaatsen naar repository-laag per ADR-005 principes

### Flow 3: Analytics registry 80r-limiet bewaken

**Actor:** Sprint-engineer  
**Voorwaarde:** Nieuw router moet toegevoegd worden aan `registries/analytics.py` maar bestand is al op de 80-regels-limiet  
**Actie:** Stop met toevoegen; maak een nieuwe `registries/analytics_extra.py` of splits de bestaande file  
**Systeemverwerking:** Fitness-test `test_registry_files_under_80_lines` detecteert overschrijding automatisch  
**Succesrespons:** Nieuwe router gaat naar aparte registry; beide files zijn ≤ 80r; fitness-test blijft groen  
**Foutrespons:** Als registry te groot wordt: `FAIL test_registry_files_under_80_lines` → STOP, splits eerst  
**Uitzonderingen:** Registry files in `registries/` die bewust > 80r zijn moeten een `# orphan:exempt` comment hebben
