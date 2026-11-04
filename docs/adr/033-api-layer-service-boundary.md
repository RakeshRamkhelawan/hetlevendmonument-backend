# ADR-033: API Layer Service Boundary & Router Registry Architecture

## Status

Accepted — 2026-06-02

### Status History

- 2026-06-02: Proposed (na bottom-up codebase audit: 221 bestanden, 852 outgoing imports, 11 eager imports, 35 orphan routers, 7 cross-router import-paren)
- 2026-06-02: Accepted (na Neo Architect review + Gemini codebase-analyse + web research fastapi-best-practices, arctikant modular monolith)
- 2026-06-03: Uitgebreid (na externe ADR-review: thin delivery layer principe, gateway-scopebeperking, gateway cross-domain contract, meetbare succescriteria en DSM-risicokoppeling toegevoegd)
- 2026-06-06: Week 8 Hard Cutover CLOSED (SP-API-008). 5/7 succescriteria gehaald. 2 open criteria gedocumenteerd in §"Week 9 scope". Zie Changelog voor volledige sprint-geschiedenis.
- 2026-06-09–11: SP-API-009 (Week 9) CLOSED. 9/9 succescriteria PASS. Forbidden imports: 188. pytest-collectietijd: 79s. Import-linter: 4 contracts KEPT. ADR-033 volledig bereikt.
- 2026-06-12: SP-API-010 CLOSED. Contract 1 uitgebreid: `auth.router` + `services/ml/als/semantic_router` als forbidden_modules. 14 violations in 7 `router.py` bestanden gefixed via facade-patroon. 20 architecture tests GROEN (13 negatief + 7 positief bewijs).
- 2026-06-12–13: SP-API-011 voorbereiding. 5 proxy stubs aangemaakt (RFC 8594 Deprecation + Sunset headers). 8 `xfail(strict=True)` architecture tests als CI-stoplicht. 24 flat files resterend (5 expliciet SP-API-011, 18 TODO SP-VOLGENDE, 1 actief geïmporteerd).

---

## DSM-risicokoppeling

Deze ADR is het formele antwoord op de DSM-hotspot die de API-laag identificeert als centrale orkestratiehub. De bottom-up DSM-analyse (2026-06-02) toonde dat de API Layer zwaar gekoppeld is aan:

| DSM-koppeling | Imports | Risico |
|---|---|---|
| Auth & JWT | 285 | Elke router kent de auth-internals direct |
| Foundation Portal | 110 | Endpoints bevatten domeinlogica |
| Database & ORM | 88 | 358 directe `get_db` Depends in endpoints |
| Shared Utilities | 74 | Catch-all dump-zone voor gedeelde code |
| ASGI Middleware | 59 | Cross-laag koppeling |
| Governance & Hash Chain | 44 | Compliance-logica in de delivery-laag |
| Generated & Base Agents | 43 | Agentorkestratie in route-handlers |

**Dit is het profiel van een te centrale orkestratiehub.** Zonder structurele ingreep groeit dit patroon terug naar een dense mesh, ook als de mappenstructuur verbetert. De vier kernrisico's uit de DSM die deze ADR adresseert:

1. **Centralisatie** — één God-registry als single point of failure en merge-conflict magneet
2. **Cross-context coupling** — routers importeren rechtstreeks domein- en inframodules
3. **Orphan routes** — stille 404's doordat routers bestaan maar niet geregistreerd zijn
4. **Niet-afdwingbare grenzen** — discipline via documentatie groeit vanzelf terug naar chaos

---

## Context

De API-laag van SanskritiSetu heeft een structureel koppelprobleem dat is blootgelegd via een bottom-up codebase-scan (2026-06-02):

| Metriek | Waarde | Ernst |
|---|---|---|
| Python-bestanden in `src/core/api/` | 221 | — |
| Outgoing imports (API → domeinlagen) | 852 | KRITIEK hotspot |
| `router_registry.py` regels | 1.027 | God-bestand |
| `setup/router_registry.py` eager imports | 11 | P0: startup-overhead |
| Orphan router-bestanden (niet geregistreerd) | 35 | P0/P1: stille 404's |
| Cross-router import-paren | 7 | P1: fragiele koppeling |
| `app.include_router()` aanroepen in één bestand | 130 | merge-conflict magneet |

**Twee concurrerende registries** zijn actief in productie:
- `src/core/api/router_registry.py` (1.027 regels, lazy imports, correct)
- `src/core/api/setup/router_registry.py` (677 regels, **11 eager imports**, legacy)

De startup-keten `app_lifespan.py → src.main → wire_container → api/main.py → setup/router_registry.py` triggert 11 eager endpoint-loads + ~78 transitieve imports bij elke applicatiestart én bij elke pytest-collectie die `src.main` importeert.

**Root causes:**
1. Geen domeingrenzen — compliance, agents, billing en monitoring importeren elkaar via één centraal bestand
2. Flat namespace — ~60 `*_endpoints.py` bestanden in `src/core/api/` zonder domein-groepering
3. Geen afdwingbare importregels — discipline alleen via documentatie, niet via tooling
4. Geen orphan-detectie — nieuwe endpoints kunnen per ongeluk ongeregistreerd blijven (stille 404)
5. Router registreert itself in routes van andere routers (cross-router imports)

---

## Decision

### 0. Kernprincipe: API Layer is een thin delivery layer

**Dit is het overkoepelende principe waar alle andere beslissingen uit volgen.**

De API Layer is uitsluitend verantwoordelijk voor HTTP-vertaling:

- **Accepteert** een HTTP-request en valideert de vorm (Pydantic schema)
- **Delegeert** direct aan een application service of gateway
- **Retourneert** de respons als gestructureerde HTTP-response

**De API Layer orkestreert geen domeinlogica en koppelt niet direct aan infrastructuur.**

```python
# CORRECT — thin delivery
@router.post("/missions")
async def create_mission(
    request: CreateMissionRequest,
    svc: MissionService = Depends(get_mission_service),
    current_user: UserResponse = Depends(get_current_user),
) -> MissionResponse:
    return await svc.create(request, tenant_id=current_user.tenant_id)

# FOUT — domeinlogica in route-handler
@router.post("/missions")
async def create_mission(
    request: CreateMissionRequest,
    db: AsyncSession = Depends(get_db),           # ← directe DB
    current_user: UserResponse = Depends(get_current_user),
) -> MissionResponse:
    mission = MissionORM(title=request.title, ...)  # ← ORM in route
    db.add(mission)
    await db.commit()                               # ← transactiebeheer in route
    return mission
```

**Alle use-case orchestration loopt via een application service of gateway per domein.** Een router die dit principe schendt — door rechtstreeks te praten met repositories, ORM-modellen, core services of infrastructuurcomponenten — is een Laag 1 violation.

---

### 1. Drie-laags router compositie

Gebaseerd op het arctikant modular monolith patroon en Netflix Dispatch-architectuur. Vervangt de centrale God-registry door een hiërarchische samenstelling:

```
Laag 3: router_registry.py          (~80 regels — thin orchestrator)
Laag 2: registries/<domein>.py       (max 80 regels per domein, lazy imports)
Laag 1: v1/<domein>/__init__.py      (composite APIRouter per domein)
         v1/<domein>/router.py        (individuele routes)
```

**Nieuwe `register_all_routers()`:**

```python
# src/core/api/router_registry.py — na refactoring (~80 regels)
from src.core.api.registries import (
    auth_admin, copilot, agents, workflows,
    knowledge, compliance, realtime, tenants,
    analytics, integrations,
)

def register_all_routers(app: FastAPI) -> int:
    total = 0
    total += auth_admin.register(app)
    total += copilot.register(app)       # → src/core/copilot/api/ (ADR-027 intact)
    total += agents.register(app)
    # ... etc.
    logger.info("api.routers_registered total={}", total)
    return total
```

**Kritiek: registratie is synchroon, vóór lifespan**

```python
# main.py — CORRECT
app = FastAPI(lifespan=lifespan)
register_all_routers(app)   # ← direct na app-instantiatie, NIET in lifespan

# FOUT — routes in lifespan registreren is te laat:
# FastAPI bouwt router-regex-boom, DI-cache en OpenAPI schema vóór ASGI-start.
# Routes toevoegen in lifespan leidt tot incomplete Swagger-docs,
# middleware die niet correct applied wordt, en potentiële 404-errors.
```

### 2. Domeinmodule structuur

Elk domein heeft precies deze bestanden — geen uitzonderingen:

```
src/core/api/v1/<domein>/
├── __init__.py         # Exporteert composite router + expliciete public API (__all__)
├── router.py           # ALLEEN routes — max 200 regels, geen directe DB/domein-imports
├── schemas.py          # ALLEEN Pydantic request/response models
├── dependencies.py     # ALLEEN FastAPI Depends()-functies voor dit domein
└── gateway.py          # Cross-module interface (enige manier om van buiten te communiceren)
```

**Expliciete `__init__.py` public API (arctikant patroon):**

```python
# src/core/api/v1/compliance/__init__.py
from fastapi import APIRouter
from .gdpr_router import router as gdpr_router           # ← gdpr_router.py, NIET compliance_router.py
from .governance.router import router as governance_router
from ..gatekeeper.router import router as gatekeeper_router
from ..ai_act.incident_router import router as incident_router

compliance_router = APIRouter(prefix="/api/v1", tags=["Compliance"])
compliance_router.include_router(governance_router)
compliance_router.include_router(gatekeeper_router)
compliance_router.include_router(gdpr_router)
compliance_router.include_router(incident_router)

__all__ = ["compliance_router"]   # alleen dit is extern importeerbaar
```

**Bestandsnaming:** Interne bestanden mogen nooit dezelfde naam hebben als het pakket zelf om circulaire imports te vermijden (bijv. `compliance/compliance_router.py` → naamconflict). Gebruik beschrijvende namen: `gdpr_router.py`, `governance_router.py`.

### 3. Importdiscipline — afdwingbaar via tooling

Importregels zijn **niet** uitsluitend gedocumenteerd maar **geautomatiseerd gehandhaafd** via `import-linter` bij elke commit:

```ini
# .importlinter — projectroot
[importlinter]
root_package = src
include_external_packages = True

# Contract 1 — actief (SP-API-009/010)
[importlinter:contract:api-no-domain]
name = API routers mogen niet direct domeinlogica importeren
type = forbidden
source_modules =
    src.core.api.v1.*.router
    src.core.api.auth.router                      # SP-API-010: auth buiten v1/
    src.core.api.v1.orchestration.workflow_router  # SP-AGT-002
    src.core.api.v1.orchestration.critic_router
    src.core.api.v1.orchestration.health_router
    src.core.api.v1.orchestration.stats_router
forbidden_modules =
    src.core.database
    src.core.governance
    src.core.learning
    src.core.agents
    src.core.workflow
    src.core.llm
    src.core.services        # SP-API-010
    src.core.ml              # SP-API-010
    src.core.als             # SP-API-010
    src.core.semantic_router # SP-API-010
allow_indirect_imports = true
# Elke *.dependencies -> forbidden_module edge is gedocumenteerd in ignore_imports.
# Zie .importlinter voor de volledige lijst (60+ entries).

# Contract 4 — actief (ADR-033 §3b)
[importlinter:contract:no-cross-gateway]
name = Gateways mogen niet andere domein-gateways importeren
type = forbidden
source_modules = src.core.api.v1.*.gateway
forbidden_modules = src.core.api.v1.*.gateway

# Contracts 2, 3, 5 — uitgecommentarieerd tot Strangler Fig SP-API-011+ de grenzen
# voldoende heeft schoongemaakt (zie §6 Week 10+ scope).
# Contract 6+7 (agent_runtime boundary) staan in ADR-034.
```

### 3b. Gateway-scopebeperking

`gateway.py` mag geen nieuwe mini-god-object worden. Het biedt **uitsluitend** expliciete domain use cases of anti-corruption calls:

```python
# CORRECT — expliciete use case
class AgentGateway:
    async def get_agent_summary(self, agent_id: str, tenant_id: int) -> AgentSummary: ...
    async def list_active_agents(self, tenant_id: int) -> list[AgentSummary]: ...

# FOUT — opportunistische shortcuts
class AgentGateway:
    def get_config(self): ...        # ← config access: hoort niet hier
    def format_response(self): ...   # ← utility helper: hoort in schemas.py
    def get_redis(self): ...         # ← infra shortcut: hoort in dependencies.py
```

**Regel:** Een gateway-methode stelt één domein use case beschikbaar. Als het niet beschreven kan worden als "doe X voor domein Y", hoort het niet in `gateway.py`.

**Gateway-import-contract** — toegevoegd aan `.importlinter`:

```ini
[importlinter:contract:no-cross-gateway]
name = Gateways mogen niet andere domein-gateways importeren
type = forbidden
source_modules = src.core.api.v1.*.gateway
forbidden_modules = src.core.api.v1.*.gateway
```

Dit voorkomt dat gateways onderling een nieuwe web van cross-domain coupling vormen. Cross-domain communicatie loopt via de domeinservices zelf, niet via API-laag gateways.

### 4. Gedeelde dependencies — geen catch-all

`src/core/api/dependencies.py` bevat **uitsluitend app-wide** dependency-functies:
- `require_admin_role` (verplaatst vanuit `admin_endpoints.py`)
- `get_current_tenant_id` (verplaatst vanuit `search_endpoints.py`)

Domein-specifieke helpers horen in `v1/<domein>/dependencies.py`, nooit in de globale `dependencies.py`.

### 5. Orphan-detectie als pytest fitness test

Elk bestand met een module-level `APIRouter`-instantie moet geregistreerd zijn. Detectie via AST-inspectie (betrouwbaarder dan string-search — vangt ook `APIRouter(prefix=...)` en aliassen):

```python
# tests/architecture/test_api_layer.py
def test_no_orphan_routers():
    """AST-based: elk bestand met APIRouter() moet in de registry staan."""
    # Zie docs/plans/api-layer-grade-a-plus-plan.md voor volledige implementatie
```

Uitzonderingen via `# orphan:exempt` comment in het bestand. Bounded contexts `src/core/copilot/api/` en `src/core/scheduling/api/` zijn permanent vrijgesteld.

### 6. Strangler Fig migratiestrategie

Migreer een domein **uitsluitend** wanneer het tóch al wordt aangeraakt voor een feature of bugfix.  
Hard cutover op week 8 na start: resterende flat bestanden worden bulk gemigreerd via codegen-script.

**Per migratie verplicht:**
1. Behavioural equivalence test (HTTP-methoden + responses identiek voor en na)
2. `lint-imports` passes groen
3. 5 groene CI-runs voordat oud bestand verwijderd wordt

**AI Act governance-routes (ADR-031):** Behouden exact dezelfde URL, HTTP-methode en response-schema tijdens migratie. ADR-031 evidence-matrix wordt bijgewerkt met nieuwe bestandspaden.

#### Week 8 afsluiting — actuele stand (2026-06-06)

Week 8 hard cutover is CLOSED via sprint SP-API-008. Bereikt eindstand:

| Sprint | Scope | BE-RTR | Tests |
|--------|-------|--------|-------|
| SP-API-001 | Router registry split + dead code removal | BE-CFG-001–013 | 94 |
| SP-API-002 | Oversized router splits (≤200r) | BE-RTR-001–010 | 127 |
| SP-API-003 | workflow, agents, analytics, monitoring, audit, knowledge, memory | BE-RTR-011–015 | 135 |
| SP-API-004 | security, missions, cva, health, tenant_management, autonomous | BE-RTR-016–020 | 141 |
| SP-API-005 | gdpr, admin, user_management, activepieces, tool_broker, rbac, management | BE-RTR-021–025 | 149 |
| SP-API-006 | copilot_intent, cva consolidatie, feature_flags, sentiment, production, synthesis | BE-RTR-026–030 | 155 |
| SP-API-007 | experimentation, ai_features, subagents, models, prediction | BE-RTR-031–035 | 160 |
| SP-API-008 | Hard cutover: 31 shims, collection errors, import-linter, retrospective | BE-CFG-015–019 | 160 |

**Actieve bestanden na hard cutover:**
- `src/core/api/setup/router_registry.py` (644r) — nog actief: registreert 20+ routers die niet via `registries/` lopen. Gemarkeerd `# orphan:exempt + TODO(SP-VOLGENDE)`. Vereist verdere migratie in week 9.
- `src/core/api/*.py` flat files met `# orphan:exempt + TODO(SP-VOLGENDE)` — routers zijn gelabeld maar nog niet volledig naar v1/ gemigreerd.

#### Week 9 scope — **CLOSED** (SP-API-009, 2026-06-09–11)

Alle 3 resterende criteria zijn PASS. Zie Changelog en succescriteria tabel voor bewijs.

| Criterium | Doel | Eindstand | Status |
| --- | --- | --- | --- |
| DSM forbidden imports < 200 | < 200 | 188 (v1=149, flat=39) | PASS |
| import-linter Contract 1 groen | 0 broken | 4 kept, 0 broken, 0 warnings | PASS |
| pytest-collectietijd < 90s | < 90s | 79s lokaal | PASS |

Additioneel week 9:

- FA-004: startup smoke-test actief (`register_all_routers=124`) — PASS
- FA-002: 35 `HTTPException(5xx)` informatielekken gefixed (OWASP A5) — PASS

#### Week 10 scope — Contract 1 uitbreiding (SP-API-010, 2026-06-12) — **CLOSED**

DSM-audit 2026-06-12 toonde 14 verboden directe imports in 7 `router.py` bestanden buiten
de bestaande Contract 1 scope (`auth.router` viel buiten `v1.*.router`; `services`, `ml`,
`als`, `semantic_router` stonden niet in `forbidden_modules`).

Actie: Contract 1 scope uitgebreid, 7 `dependencies.py` facades aangemaakt of uitgebreid.
Bewijs: 20 architecture tests GROEN (13 negatief + 7 positief). 4 contracts KEPT. Commit `310131a4`.

#### Week 11 scope — Resterende flat files (SP-API-011, open)

**24 actieve flat files** wachten op volledige migratie naar `v1/`. Verdeling:

| Categorie | Aantal | Aanpak |
| --- | ---: | --- |
| Proxy stubs (SP-API-010 Dag 2, RFC 8594) | 5 | Volledig migreren naar v1/ in SP-API-011 |
| Structurele blockers (circulaire dep / geen v1/ service) | 3 | Aparte sprint; v1/ service aanmaken eerst |
| TODO SP-VOLGENDE — nog niet aangeraakt | 18 | Op volgorde van aanraking migreren |
| Actief geïmporteerd door middleware/agents | 1 | Migreer symbolen naar eigen module |

8 `xfail(strict=True)` architecture tests staan rood als CI-stoplicht totdat SP-API-011 ze fixt.
Zie `tests/architecture/test_flat_file_batch_a_gaps.py` en `test_flat_file_migration_gaps.py`.

---

## Meetbare succescriteria

De migratie is geslaagd als alle onderstaande metrics zijn bereikt.

### Meetmethode (KRITIEK — lees dit vóór je meet)

`scripts/generate_c4_dsm.py` rapporteert "175 unieke paren" — dit zijn GROUP-to-GROUP paren
tussen 23 groepen. **Dit is NIET de ADR-033 metriek.** De ADR-033 baseline van 852 was het
aantal *verboden imports* vanuit de API-laag naar domeinmodules.

**Correcte meting voor ADR-033:**

```python
import ast
from pathlib import Path

FORBIDDEN = [
    "src.core.database", "src.core.governance", "src.core.learning",
    "src.core.agents", "src.core.workflow", "src.core.llm",
]

def count(fp):
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8-sig", errors="ignore"))
        return sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any((getattr(node, "module", "") or "").startswith(f) for f in FORBIDDEN)
        )
    except: return 0

v1 = sum(count(f) for f in Path("src/core/api/v1").rglob("*.py"))
flat = sum(count(f) for f in Path("src/core/api").glob("*_endpoints.py"))
print(f"Forbidden imports: v1={v1}, flat={flat}, totaal={v1+flat}")
```

### Succescriteria tabel

| Metriek | Baseline (2026-06-02) | Doel | Actueel (2026-06-11) | Status |
|---|---|---|---|---|
| Forbidden imports API Layer | 852 | < 200 | 188 (v1=149, flat=39) | **PASS** — DSM-audit 2026-06-11 |
| Cross-router import-paren | 7 | 0 | 0 | **PASS** — `test_no_cross_router_imports` |
| Orphan router-bestanden | 35 | 0 | 0 | **PASS** — `test_no_orphan_routers` |
| `router_registry.py` regels | 1.027 | ≤ 80 | 65 | **PASS** — `wc -l` |
| Module-level eager imports | 11 | 0 | 0 | **PASS** — `test_no_eager_imports_in_setup_registry` |
| import-linter Contract 1 | n.v.t. | PASS | 4 contracts KEPT | **PASS** — lint-imports 2026-06-11 |
| Circulaire deps auth ↔ core_api | aanwezig | 0 | 0 | **PASS** — SP-API-009 Dag 2 |
| Circulaire deps agent_runtime ↔ core_api | 11 | 0 | 0 | **PASS** — `test_adr033_focus_builder_circular_dep` (SP-API-009 Dag 3) |
| `pytest-collectietijd` | ~231s | < 90s | 79s (lokaal gemeten 2026-06-11) | **PASS** — onder doelgrens |

**Eindstand week 8:** 5/9 criteria PASS.
**Stand week 9 Dag 2:** 6/9 PASS (circulaire deps auth opgelost). 49 forbidden imports resterend.
**Stand week 9 Dag 3-5 (SP-API-009 CLOSED):** 7/9 PASS (agent_runtime circ dep opgelost). Additioneel: FA-002 (35 OWASP A5 lekken gefixed) en FA-004 (startup smoke-test) PASS.
**Stand DSM-audit 2026-06-11:** 9/9 PASS. ADR-033 volledig bereikt.
**Stand SP-API-010 (2026-06-12):** Contract 1 scope uitgebreid. 14 nieuwe violations gefixed. 20 architecture tests GROEN. Import-linter: 4 contracts KEPT, 0 warnings.

**Herhalende meting:** run het bovenstaande meetscript na elke sprint en werk de "Actueel"-kolom bij.

---

## Consequences

### Positief

- **Nieuwe orphan is onmogelijk** — AST-check detecteert het bij de eerste commit
- **Cross-router imports zijn onmogelijk** — `import-linter` blokkeert de PR
- **`router_registry.py`**: 1.027 regels → ~80 regels na split
- **Startup-overhead**: 11 eager imports → 0 (testcollectie: ~15–25s tijdwinst)
- **Nieuwe endpoint toevoegen**: edit in 1 domeinbestand i.p.v. het centrale God-bestand
- **Externe reviewers** zien een herkenbare, gedocumenteerde structuur (verkoopbaarheid)
- **Pytest-collectietijd**: ~139s → <90s (gecombineerd met eerdere AUDIT-COLL-01/02 fixes)

### Negatief / Trade-offs

- Initiële migratie kost ~14 werkdagen (Strangler Fig verspreid over ~8 weken)
- `import-linter` vereist onderhoud bij toevoeging van nieuwe domeinen (contract bijwerken)
- Legacy `*_endpoints.py` bestanden zijn tijdelijk vrijgesteld (`# legacy: pre-migration`) — dit is bewust totdat de Strangler Fig migratie ze bereikt
- Composite `APIRouter` in `__init__.py` per domein introduceert één extra indirectieniveau

### Niet van toepassing

- **`src/core/copilot/api/`** — correct geïsoleerd per ADR-027. Geen wijziging.
- **`src/core/scheduling/api/`** — correct geïsoleerd, unidirectionele afhankelijkheid. Geen wijziging.
- **Auto-discovery via importlib** — expliciet afgewezen. Fragiel, moeilijk te debuggen, schendt het predictability-principe van CLAUDE.md §11.

---

## Implementatieplan

Volledig plan: `docs/plans/api-layer-grade-a-plus-plan.md`

Directe acties (week 1):
1. `pip install import-linter` → `requirements-dev.txt`
2. Verifieer `register_all_routers(app)` staat synchroon vóór lifespan
3. Stap 0A: 11 eager imports lazy maken in `setup/router_registry.py`
4. Stap 0B: TESTING guard in `api/main.py`
5. Stap 0C: cross-router imports verplaatsen naar `dependencies.py` / domein-specifieke `dependencies.py`
6. Stap 0D: hardcoded return-counts fixen
7. `tests/architecture/test_api_layer.py` aanmaken
8. `.importlinter` aanmaken
9. Dag 1 registry-split: `registries/auth_admin.py` + `registries/compliance.py`

---

## Gerelateerde ADRs

- **ADR-010** — FastAPI runtime: router-registratie moet synchroon zijn vóór lifespan (zie §3 hieronder)
- **ADR-027** — Copilot/Council: `src/core/copilot/api/` blijft als bounded context onaangeraakt
- **ADR-031** — AI Act governance: 40 routes behouden URL/schema tijdens migratie; evidence-matrix wordt bijgewerkt
- **CLAUDE.md §11** — Bijgewerkt: "altijd via centrale registry" vervangen door 3-laags registratie-patroon

---

## Changelog

| Datum | Sprint | Wijziging |
|---|---|---|
| 2026-06-02 | — | ADR voorgesteld + geaccepteerd na bottom-up codebase-audit (852 outgoing imports, 35 orphan routers) |
| 2026-06-03 | — | Uitgebreid: thin delivery layer principe, gateway-scopebeperking, meetbare succescriteria, DSM-risicokoppeling |
| 2026-06-02–04 | SP-API-001 | router_registry.py gesplitst (1027r → 65r); registries/ aangemaakt; fitness gates actief; 11 eager imports → 0 |
| 2026-06-03 | SP-API-002 | 11 oversized router.py bestanden gesplitst (≤200r); orphan:exempt patroon gevestigd |
| 2026-06-04 | SP-API-003 | workflow, agents, analytics, monitoring, audit, knowledge, memory → v1/; BE-RTR-011–015 |
| 2026-06-04 | SP-API-004 | security, missions, cva, health, tenant_management, autonomous → v1/; BE-RTR-016–020 |
| 2026-06-05 | SP-API-005 | gdpr, admin, user_management, activepieces, tool_broker, rbac, management → v1/; BE-RTR-021–025 |
| 2026-06-05 | SP-API-006 | copilot_intent, cva consolidatie, feature_flags, sentiment, production, synthesis → v1/; BE-RTR-026–030 |
| 2026-06-06 | SP-API-007 | experimentation, ai_features, subagents, models, prediction → v1/; BE-RTR-031–035; 160 tests |
| 2026-06-06 | SP-API-008 | Hard cutover: 31 dode flat files → shims; 3 collection ERRORs opgelost; import-linter geactiveerd; retrospective |
| 2026-06-06 | SP-API-009 Dag 1 | 50 registraties gecategoriseerd (A=11 dubbel, B=12 shim, C=22 uniek); 10 dubbele uitgecommentarieerd; goal_router BLOCKER gefixed |
| 2026-06-06 | SP-API-009 Dag 2 | 4 circulaire dep root causes opgelost: auth→core_api=0, agent_runtime→core_api 11→1; workflow/schemas.py + public_registry.py aangemaakt |
| 2026-06-06 | — | ADR bijgewerkt: meetmethode gecorrigeerd (175 paren ≠ 249 forbidden imports), succescriteria tabel bijgewerkt, SP-API-009 progress, Changelog uitgebreid |
| 2026-06-11 | SP-API-009 Dag 3 | focus_builder circ dep verwijderd (agent_runtime->core_api=0); architecture test + CI uitgebreid met tests/architecture/ |
| 2026-06-11 | SP-API-009 Dag 4 | FA-004: startup smoke-test (register_all_routers=124, app aanwezig) |
| 2026-06-11 | SP-API-009 Dag 5 | FA-002: 35 HTTPException(5xx) informatielekken gefixed in 10 bestanden (OWASP A5); architecture test PASS |
| 2026-06-11 | DSM-audit | 9/9 criteria PASS. Forbidden imports: 249→188 (v1=149, flat=39). import-linter: 4 contracts KEPT. pytest-collectietijd: 79s. ADR-033 volledig bereikt. |
| 2026-06-12 | SP-API-010 | Contract 1 uitgebreid: `auth.router` + `services/ml/als/semantic_router` als forbidden_modules. 14 violations in 7 `router.py` bestanden gefixed via facade-patroon. 7 `dependencies.py` aangemaakt/uitgebreid. 20 architecture tests GROEN. 4 contracts KEPT, 0 warnings. Commits: `310131a4`, `7f5b2378`, `6f4df20b`, `e4717af1`. |
| 2026-06-12 | SP-API-011 prep | 5 proxy stubs (RFC 8594 `Deprecation`/`Sunset` headers). 8 `xfail(strict=True)` architecture tests als CI-stoplicht. 24 actieve flat files resterend (zie §"Week 11 scope"). |
