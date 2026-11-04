# Backend Feature Specification

## Metadata

- Feature ID: BE-CFG-005
- Feature naam: ENABLE_GENERATED_AGENTS Feature Flag
- Status: Completed
- Auteur: Agent (SP-H09, 2026-05-30)
- Reviewer: Subagent (Laag A review + onafhankelijke documentatie-review)
- Datum: 2026-05-30
- Gerelateerde user story / ticket: SP-H09 (MASTER-AUDIT-COMPLEET.md B-016)
- Gerelateerde router / module: `src/core/agents/subagent_loader.py`
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

79 generated agents in `src/core/agents/generated/` hebben lege `CAPABILITIES = []` waardoor
`get_capabilities()` een lege lijst retourneert. De AgentRouter (ADR-023) gebruikt tier-3
capability matching; een lege lijst geeft score 0 zodat agents nooit via tier-3 geselecteerd worden. Met `ENABLE_GENERATED_AGENTS=false`
(default) worden generated agents niet ontdekt door `SubagentLoader`, zodat de AgentRouter alleen
agents ziet met echte capabilities.

### In scope

- `ENABLE_GENERATED_AGENTS` omgevingsvariabele als feature flag in `SubagentLoader`
- `_is_generated_agents_enabled()` helper functie (runtime env-var read, testbaar via `patch.dict`)
- `_should_skip_file()` uitbreiding: `"generated" in file_path.parts` check
- Cache-key fix: flag-specifieke cache-key `agent_definitions:{enabled|disabled}`
- `datetime.now` -> `datetime.now(timezone.utc)` fix op `AgentDefinition.created_at`
- `.env.example` documentatie
- 18 unit/behavioral tests (TDD)

### Out of scope

- Implementatie van echte capabilities voor generated agents (vereist product-input per agent)
- Verwijdering van de generated agent bestanden
- Aanpassingen aan AgentRouter of capability-matching logica

---

## Build summary

- Nieuw gebouwd:
  - `_is_generated_agents_enabled()` module-level helper functie in `subagent_loader.py`
  - 18 unit tests in `tests/unit/test_sp_h09_generated_agents.py`
- Gewijzigd:
  - `src/core/agents/subagent_loader.py`: `_should_skip_file()` uitgebreid, cache-key aangepast,
    `AgentDefinition.created_at` datetime fix
  - `.env.example`: `ENABLE_GENERATED_AGENTS=false` sectie toegevoegd
- Verwijderd:
  - Niets (generated agent bestanden blijven voor toekomstige activatie)
- Beinvloede bestaande flows:
  - `SubagentLoader.discover_agents()`: overgeslagen generated/ bestanden bij flag=false
  - `SubagentLoader._should_skip_file()`: nieuwe check toegevoegd
  - Redis cache: cache-key nu flag-afhankelijk

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-CFG-005 | ENABLE_GENERATED_AGENTS feature flag | Config | `src/core/agents/subagent_loader.py` | Wijziging | BE-FLW-GEN-001 |

---

## API-flows

### Flow ID: BE-FLW-GEN-001

- Naam: Generated agents discovery bij SubagentLoader startup
- Trigger: `SubagentLoader.discover_agents()` aanroep (bij applicatie startup of expliciete scan)
- Voorwaarden: `ENABLE_GENERATED_AGENTS` env var (optioneel; default false)
- Request-pad: N/A (startup configuratie, geen HTTP endpoint)
- Service-stappen:
  1. `discover_agents()` bepaalt flag-specifieke cache-key: `agent_definitions:enabled` of `agent_definitions:disabled`
  2. Redis cache check op die key; bij hit: return gecachede definities (max 3600s)
  3. Bij cache miss: scan geconfigureerde scan directories via `rglob("*.py")`
  4. Per bestand: `_should_skip_file(file_path)` aangeroepen
  5. Als `"generated" in file_path.parts` EN `not _is_generated_agents_enabled()`: skip bestand
  6. Overige skip-regels: `_` prefix, `__init__.py`, backup extensies
  7. Niet-geskipte bestanden worden geanalyseerd voor agent class definitions
  8. Ontdekte definities worden opgeslagen in `self.agents` en gecached
- DB-operaties: Geen
- Successtatus:
  - `flag=false`: 0 generated agents geladen; enkel agents met echte capabilities beschikbaar
  - `flag=true`: alle 79 generated agents geladen (lege capabilities)
- Foutpaden:
  - Bestand analyse fout: gelogd als `ERROR`, bestand overgeslagen, loader gaat door
  - Redis onbereikbaar: `self.cache_manager` is None of exception; cache overgeslagen, scan altijd vers
- Eindtoestand:
  - `self.agents` dict gevuld met ontdekte agent definities
  - Redis cache bijgewerkt met flag-specifieke key

---

## Detaildocumentatie per artefact

---

## [BE-CFG-005] ENABLE_GENERATED_AGENTS Feature Flag

### 1. Type

Configuration / Feature Flag (module-level utility function + method uitbreiding)

### 2. Locatie

- Bestandspad: `src/core/agents/subagent_loader.py`
- Functies: `_is_generated_agents_enabled()`, `SubagentLoader._should_skip_file()`, `SubagentLoader.discover_agents()`

### 3. Gerelateerde flow

BE-FLW-GEN-001

### 4. Doel

Voorkomen dat 79 generated agents met lege capability catalogs geladen worden door `SubagentLoader`
in productie, zodat de AgentRouter (ADR-023) tier-3 capability matching correct werkt.

### 5. Functionele beschrijving

Bij applicatie startup bepaalt `ENABLE_GENERATED_AGENTS` of de `generated/` subdirectory van
`src/core/agents/` wordt gescand. Standaard is de flag `false`, wat betekent dat alle bestanden
in de `generated/` directory worden overgeslagen. De 79 generated agents zijn daardoor niet
zichtbaar voor de AgentRouter en beinvloeden routing niet. Bij `ENABLE_GENERATED_AGENTS=true`
(voor lokale ontwikkeling of testen) worden de agents wel geladen maar bieden ze geen capabilities.

### 6. Technische beschrijving

```python
def _is_generated_agents_enabled() -> bool:
    """
    Check if generated agents should be loaded.
    Generated agents have empty capability catalogs (B-016).
    Disabled by default. Set ENABLE_GENERATED_AGENTS=true for dev/test.
    """
    raw = os.getenv("ENABLE_GENERATED_AGENTS", "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}
```

Uitbreiding in `_should_skip_file()`:

```python
# NOTE: Generated agents have empty capability catalogs (B-016).
# Skip them unless ENABLE_GENERATED_AGENTS=true (default: false).
if "generated" in file_path.parts and not _is_generated_agents_enabled():
    return True
```

Cache-key fix in `discover_agents()`:

```python
flag_suffix = "enabled" if _is_generated_agents_enabled() else "disabled"
cache_key = f"agent_definitions:{flag_suffix}"
```

- `Path.parts` detectie: exacte segment matching (geen false positives voor `regenerated/` of
  `something_generated.py`)
- Env var op call-time (niet module-load-time): testbaar via `patch.dict(os.environ, ...)`
  zonder `importlib.reload()` (VERBODEN per CLAUDE.md)
- Cache-key is flag-afhankelijk: flag-wijziging heeft direct effect zonder 1-uur cache-warmte

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N/A (startup configuratie)
- Vereiste rol / scope: N/A
- Tenant-isolatie: N/A (SubagentLoader is niet tenant-specifiek)
- Feature flag: `ENABLE_GENERATED_AGENTS` (env var, default `false`)

### 8. Request-specificatie

N/A — startup configuratie, geen HTTP endpoint

### 9. Response-specificatie

N/A — startup configuratie

### 10. Validaties en constraints

- Env var moet een van `"1", "true", "yes", "on"` zijn (case-insensitive, whitespace-tolerant) voor `true`
- Elke andere waarde (inclusief `"false"`, `"0"`, lege string, niet gezet) = `false` (fail-closed)
- Pad-detectie via `"generated" in file_path.parts`: werkt op Windows (`\`) en POSIX (`/`)

### 11. Business rules

- Productie deployments: altijd `ENABLE_GENERATED_AGENTS=false` (default, geen actie vereist)
- Lokale ontwikkeling met generated agents: `ENABLE_GENERATED_AGENTS=true` in `.env.local`
- Generated agents hebben lege capabilities; AgentRouter selecteert ze via tier-4 (LLM) of tier-5
  (heuristic) — nooit via tier-3 (capability matching)

### 12. Afhankelijkheden

- `os` module (stdlib, al geimporteerd in `subagent_loader.py`)
- `pathlib.Path.parts` (stdlib)
- Redis cache manager (optioneel; `None` bij onbereikbare Redis)

### 13. Foutafhandeling

- Ongeldige env var waarde: behandeld als `false` (fail-closed, set-membership check)
- Geen exception raised door de feature flag zelf
- Cache miss bij flag-wijziging: normale cache-miss flow, scan opnieuw uitgevoerd

### 14. Transacties en dataïntegriteit

N/A — geen database operaties

### 15. Telemetry / logging / tracing

Bestaande logging in `discover_agents()` is van toepassing:

```python
logger.debug(f"Scan directory not found: {scan_path}")
logger.error(f"Error analyzing agent file {py_file}: {e}")
logger.info(f"Discovered {len(discovered_agents)} agents")
```

Geen nieuwe log statements toegevoegd door de feature flag zelf; skip is silent
(consistent met bestaand `_should_skip_file` gedrag).

### 16. Caching

- Gecached: Ja (Redis, via `self.cache_manager`)
- Cache-sleutel: `agent_definitions:enabled` of `agent_definitions:disabled`
- TTL: 3600 seconden (1 uur)
- Invalidatie: automatisch via flag-afhankelijke key; flag-wijziging geeft cache-miss op nieuwe key

### 17. Acceptatiecriteria

- [x] `ENABLE_GENERATED_AGENTS` niet gezet of `=false`: generated agents worden NIET geladen
- [x] `ENABLE_GENERATED_AGENTS=true`: generated agents WORDEN geladen
- [x] `ENABLE_GENERATED_AGENTS=1`, `yes`, `on`: worden als `true` geparsed
- [x] Niet-generated agents worden altijd geladen (ongeacht flag-state)
- [x] Bestaand skip-gedrag (`_` prefix, `__init__.py`) blijft onveranderd
- [x] Pad-varianten `generated/`, `core/agents/generated/`, `src/core/agents/generated/` allemaal geskipt
- [x] `.env.example` bevat `ENABLE_GENERATED_AGENTS=false` documentatie
- [x] Cache-key is flag-afhankelijk (geen stale cache na flag-wijziging)
- [x] 0 nieuwe regressies op niet-generated agents

### 18. Integratoruitleg

Generated agents zijn standaard uitgeschakeld in productie. Ze zijn placeholder-implementaties
met lege capabilities die de AgentRouter kunnen misleiden. Om generated agents te activeren
(uitsluitend voor lokale ontwikkeling), zet `ENABLE_GENERATED_AGENTS=true` in `.env.local`
en herstart de applicatie.

### 19. Trainingssamenvatting

| Veld | Inhoud |
| --- | --- |
| Actor | Platform operator of developer die SubagentLoader configureert |
| Voorwaarde | `ENABLE_GENERATED_AGENTS` env var aanwezig of afwezig in de deployment omgeving |
| Actie | Zet `ENABLE_GENERATED_AGENTS=false` (default, productie) of `=true` (dev/test) en herstart de app |
| Systeemverwerking | Bij startup scant `SubagentLoader.discover_agents()` agent directories; `_should_skip_file()` detecteert `"generated" in file_path.parts` en slaat het bestand over als `_is_generated_agents_enabled()` false retourneert; cache-key is flag-afhankelijk |
| Succesrespons | `flag=false`: 0 generated agents geladen; AgentRouter ziet alleen agents met echte capabilities. `flag=true`: alle 79 generated agents geladen (lege capabilities, tier-4/5 routing) |
| Foutrespons | Ongeldige env var waarde wordt als false behandeld (fail-closed). Cache onbereikbaar: scan altijd vers, geen effect op functionaliteit. |
| Uitzonderingen | `flag=true` maar generated agents hebben lege capabilities: AgentRouter selecteert ze via tier-4 (LLM) of tier-5 (heuristic), nooit via tier-3 (capability matching) |

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Generated agents zijn standaard uitgeschakeld (`ENABLE_GENERATED_AGENTS=false`). Ze bevatten
placeholder-code zonder echte capabilities. Activeer ze uitsluitend in een lokale
ontwikkelomgeving via `ENABLE_GENERATED_AGENTS=true` in `.env.local`.

In productie: geen actie vereist — de default is safe.

**Belangrijk bij runtime-wijziging:** Als de flag wordt gewijzigd in een draaiend systeem
(zonder herstart), heeft de wijziging pas effect na de cache-expiry (TTL: 3600 seconden).
Voor onmiddellijk effect: herstart de applicatie na de env var wijziging.

---

## Open aannames

- Generated agents hebben bewust lege capabilities; ze zijn placeholders voor toekomstige
  implementatie die product-input vereist per agent
- De 79 generated agents zijn gelijkwaardig qua structuur (allemaal identieke lege catalogs)

## Open vragen

- Wanneer worden de generated agents met echte capabilities uitgebreid? (buiten scope SP-H09)
- Moeten generated agents uiteindelijk verwijderd worden of gevuld?

## Risico's

- **Laag**: Developer vergeet `ENABLE_GENERATED_AGENTS=true` te zetten in lokale dev — agents
  niet zichtbaar, snel oplosbaar via env var
- **Laag**: Cache-warming: als Redis warm is van een andere flag-state, wordt de juiste flag-key
  gebruikt (cache-miss), geen false positives

---

## QA-checks

- [x] Feature functioneel getest (happy path) — 18 tests, TDD rood->groen
- [x] Default false getest — `test_default_is_false_when_flag_unset`
- [x] Truthy waarden getest — true, 1, yes, on (alle 4 varianten)
- [x] Falsy waarden getest — false, 0
- [x] Path-varianten getest — Unix, Windows, relatief, absoluut
- [x] Niet-generated files getest (blijven altijd geladen)
- [x] Bestaand skip-gedrag getest (underscore prefix, init.py)
- [x] Behavioral test: operator deployt zonder flag (alle generated geskipt)
- [x] Behavioral test: developer met flag=true (generated geladen)
- [x] .env.example documentatie-contract getest (pytest.fail bij ontbrekend bestand)
- [x] datetime.now(timezone.utc) fix getest — `test_agent_definition_created_at_is_timezone_aware`
- [x] Geen regressies — 569 unit tests groen na implementatie
- [x] Auth/permissies: N/A
- [x] Tenant-isolatie: N/A (SubagentLoader is niet tenant-specifiek)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle components geinventariseerd (BE-CFG-005)
- [x] Alle relevante foutstatussen beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar en getest
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig (Actor/Voorwaarde/Actie/Systeemverwerking/Succesrespons/Foutrespons/Uitzonderingen)
- [x] Open aannames benoemd
- [x] QA-checks uitgevoerd
- [x] Review door reviewer-prompt: APPROVED WITH MINOR GAPS
