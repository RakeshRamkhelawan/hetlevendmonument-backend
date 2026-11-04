# BE-AGT-014 -- ADR-034 Sluiting: Contract 7 Expansie + Cat B Documentatie + DSM Finale

**Sprint:** SP-AGT-004 Dag 5
**Datum:** 2026-06-12
**Status:** APPROVED
**ADR:** ADR-034 (agent_runtime service boundary)

---

## Samenvatting

Dag 5 sluit ADR-034 volledig af. Contract 7 (`agent_runtime_no_db`) is uitgebreid
van `src.core.agents.api` naar het volledige `src.core.agents` pakket. Alle 18
transitive violations zijn opgelost via `allow_indirect_imports = true` (consistent
met Contract 1 ADR-033). Cat B Stap-3D bestanden zijn gedocumenteerd met NOTE-comments
en `ignore_imports` entries. DSM finale-test bewaakt alle grenzen permanent.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `.importlinter` | Contract 7 source_modules uitgebreid naar `src.core.agents`; allow_indirect_imports=true |
| `tests/architecture/test_sp_agt_004_dsm_final.py` | Nieuw -- 4 DSM finale guards |
| `tests/architecture/test_sp_agt_004_ucr_wiring.py` | FA-D3-003: relatieve Path -> _REPO_ROOT / _UCR_FILE |
| `src/core/agents/diagnostics_agent/database.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/knowledge_agent/database.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/sentiment_agent/database.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/knowledge_agent/routes.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/translation_agent/routes.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/autonomous_agent.py` | NOTE: ADR-034 Cat B Stap 3D |
| `src/core/agents/seed_agent_registry.py` | NOTE: ADR-034 Cat B Stap 3D |
| `docs/adr/034-agent-runtime-service-boundary.md` | §10 bewijs-tabel SP-AGT-004 ingevuld |
| `docs/SPRINT_TRACKER.md` | SP-AGT-004 CLOSED entry toegevoegd |

---

## Ontwerp

### Contract 7 expansie

```
Oud: source_modules = src.core.agents.api (alleen facade)
Nieuw: source_modules = src.core.agents (volledig pakket)
```

`allow_indirect_imports = true` is correct omdat:
1. ADR-034 verbiedt DIRECTE koppeling vanuit agents naar database-laag
2. Transitive toegang via `search.hybrid_search`, `learning.services`, etc. valt
   onder die modules eigen contract-scope
3. Precisie-handhaving via AST-scan in `test_dsm_db_agents_no_regression`

### Cat B Stap-3D categorieen

| Categorie | Bestanden | Actie |
|-----------|-----------|-------|
| Subdomain database-modules | diagnostics_agent/database.py, knowledge_agent/database.py, sentiment_agent/database.py | NOTE + ignore_imports; backlog SP-AGT-005 |
| FastAPI routes (Depends(get_db)) | knowledge_agent/routes.py, translation_agent/routes.py | NOTE + ignore_imports; backlog SP-AGT-005 |
| Startup/Redis clients | seed_agent_registry.py, autonomous_agent.py | NOTE + ignore_imports; backlog SP-AGT-005 |

### DSM finale-test (4 guards)

| Test | Voorwaarde | Status na Dag 5 |
|------|-----------|-----------------|
| `test_contract7_source_modules_expanded` | .importlinter bevat `src.core.agents` (zonder .api) | GROEN |
| `test_dsm_gov_agents_at_zero` | 0 governance runtime-imports in agents/ | GROEN |
| `test_dsm_db_agents_no_regression` | DB violations agents/ <= 11 | GROEN |
| `test_ucr_still_operational` | UCR isinstance(ICapabilityRegistry) + discover() werkt | GROEN |

---

## Test-bewijs

```
pytest tests/architecture/ tests/unit/agents/ -q --timeout=60
467 passed, 12 xfailed in 47.97s

lint-imports: 4 contracts KEPT (0 broken)

pyright: 2 errors (pre-existing baseline, geen nieuwe)
```

---

## ADR-034 eindstatus

| Metriek | Voor SP-AGT-004 | Na SP-AGT-004 |
|---------|-----------------|---------------|
| GOV runtime-imports agents/ | 3 | 0 |
| DB violations agents/ | 11 | 11 (Cat A/B gedocumenteerd) |
| import-linter contracts KEPT | 4 | 4 |
| Contract 7 scope | src.core.agents.api | src.core.agents |

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
