# Final Approver Brief -- SP-API-011-backlog Dag 1

Sprint:     SP-API-011-backlog
Dag:        1 van 3
Datum:      2026-06-22
Branch:     develop
Commit:     da2d4869
Reviewtype: onafhankelijke beoordeling (6 lagen)

---

## Scope van deze dag

4 ADR-033 violations in het `agents/` domein verwijderd. Fix-patroon voor dag 2 en 3 gevestigd.

**Gewijzigde bestanden:**

| Bestand | Wijziging |
| ------- | --------- |
| `src/core/api/v1/agents/agent_crud_router.py` | TYPE_CHECKING AgentRegistry -> own-domain; AgentRegistryRepository via Depends-factory |
| `src/core/api/v1/agents/agent_execution_router.py` | TYPE_CHECKING AgentRegistry -> own-domain |
| `src/core/api/v1/agents/agent_management_router.py` | TYPE_CHECKING AgentRegistry -> own-domain |
| `src/core/api/v1/agents/dependencies.py` | AgentRegistry re-export + AgentRegistryRepository Depends-factory |

---

## Bewijs per deliverable

### Violation count: 32 (was 36, -4)

```
python scripts/dsm_api_violation_finder.py
Files with violations: 12
Total violation imports: 32
```

agents/ domein volledig schoon -- geen regels meer in agent_crud_router / agent_execution_router / agent_management_router.

### Unit tests agents/: 2/2 PASS

```
tests/unit/api/v1/agents/test_agent_router_lazy_import.py
  test_agents_domain_router_imports_without_agent_registry PASSED
  test_agent_endpoints_imports_without_agent_registry PASSED
2 passed in 1.67s
```

Geen regressies.

### Pyright: 0 errors

```
python -m pyright
0 errors, 11 warnings, 0 informations
```

Baseline ongewijzigd (warnings zijn pre-existing missing stubs voor aiosmtplib / tensorflow_hub).

### Ruff: 0 fouten

```
ruff check src/core/api/v1/agents/...
All checks passed!
```

### Architecture tests: 2 FAIL (verwacht)

```
FAILED test_api_layer_violations_regression_ceiling  -- 32 violations > 0 ceiling
FAILED test_all_v1_violations_resolved               -- 32 resterend
1 passed (test_api_layer_violations_trending_down)
```

Tests blijven ROOD totdat dag 3 (focus_builder/) voltooid is en count 0 bereikt.

---

## Laag 1 -- Code (CLAUDE.md patronen)

| Check | Status |
| ----- | ------ |
| Geen tenant_id uit request body | PASS -- geen logica gewijzigd |
| Geen datetime.now() | PASS |
| Geen emoji of non-ASCII | PASS |
| Geen hardcoded secrets | PASS |
| ADR-033 router boundary | PASS -- alle forbidden imports verwijderd uit agents/ |
| Geen nieuwe abstracties | PASS -- Depends-factory patroon al aanwezig in dependencies.py |

**Fix-patroon dat gevolgd is (OPTIE A per sprint brief):**
- `AgentRegistry` TYPE_CHECKING: eigen domein `src.core.api.v1.agents.dependencies` (toegestaan)
- `AgentRegistryRepository`: runtime top-level import -> `Depends(get_agent_registry_repository_dependency)` (proper FastAPI DI, testbaar, geen lazy import in handler body)
- `dependencies.py`: re-export `AgentRegistry as AgentRegistry` (noqa: F401) + nieuwe `get_agent_registry_repository_dependency` factory

---

## Laag 2 -- Security (OWASP + ADR)

| Check | Status |
| ----- | ------ |
| Tenant isolatie | PASS -- `AgentRegistryRepository.get_registered_agent_by_agent_id(agent_id, tenant_id)` ongewijzigd |
| Injection | PASS -- geen user input naar nieuwe code |
| Auth | PASS -- geen auth code gewijzigd |
| any-types | PASS -- expliciete types, geen `Any` toegevoegd |

---

## Laag 3 -- Tests

| Check | Status |
| ----- | ------ |
| Baseline VOOR fix | PASS -- 2 passed (agents/ unit), 2 FAIL (arch) gedocumenteerd |
| Regressie NA fix | PASS -- 2/2 unit tests nog steeds groen |
| Architecture tests rood als gate | PASS -- 2 FAIL verwacht en aanwezig |

---

## Laag 4 -- Architectuur

| Check | Status |
| ----- | ------ |
| ADR-033 Laag 1 | PASS -- agents/ compliant |
| Import linter scope | PASS -- TYPE_CHECKING imports alleen via own-domain |
| FastAPI DI patroon | PASS -- `Depends(factory)` i.p.v. lazy import in handler body |
| Geen nieuwe violations | PASS |

---

## Laag 5 -- PR-checklist

| Check | Status |
| ----- | ------ |
| Geen merge naar main | PASS -- alleen develop |
| Geen git-tag | PASS |
| Geen --no-verify | PASS |
| Commit bericht correct | PASS |
| pyright 0e baseline | PASS |

---

## Laag 6 -- Pre-existing

| Categorie | Wat | Status |
| --------- | --- | ------ |
| 32 violations in cva/ en focus_builder/ | Dag 2 en 3 | Ongewijzigd |
| 9 overige RED architecture tests | Backlog gates | Ongewijzigd |
| 11 pyright warnings missing stubs | aiosmtplib / tensorflow_hub | Ongewijzigd |

---

## Eindoordeel

**GO**

4 violations in `agents/` opgelost. Violation count: 36 -> 32. pyright 0e. ruff 0e.
Unit tests 2/2 PASS. Fix-patroon (OPTIE A) gevestigd voor dag 2 en 3.

---

## Volgende stap: dag 2 (cva/ domein, ~15 violations)

SP-API-011-backlog dag 1 klaar. Commit: da2d4869
Brief: docs/agent-briefs/generated/2026-06-22-final-approver-SP-API-011-backlog-dag1.md

agents/ domein: 4 violations verwijderd. Resterend: 32 (cva/ + focus_builder/).
Volgende actie: zeg "review dag 1" -- Claude leest de brief en geeft GO/NO-GO.
Bij GO: dag 2 brief (cva/ domein) wordt direct gegenereerd.

---

*Brief-type: final-approver | Sprint: SP-API-011-backlog | Dag 1 van 3 | Commit: da2d4869*


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-API-011-backlog Dag 1: agents/ domein 13 ADR-033 violations -> 0. dependencies.py uitgebreid (AgentRegistry, get_db, get_settings factories). 4 router files omgezet naar own-domain imports. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-API-011-backlog Dag 1: agents/ domein 13 ADR-033 violations -> 0. dependencies.py uitgebreid (AgentRegistry, get_db, get_settings factories). 4 router files omgezet naar own-domain imports..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
