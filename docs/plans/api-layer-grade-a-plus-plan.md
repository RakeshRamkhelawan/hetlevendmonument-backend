# API Layer — Grade A+ Implementatieplan
**Status:** DEFINITIEF — klaar voor uitvoering  
**Strategie:** Strangler Fig + directe P0-fixes + architecturele fitness functies  
**Opgesteld:** 2026-06-02  
**Bronnen:** API-LAYER-COUPLING-ANALYSIS-2026-06-02.md · Neo Architect review ·  
  zhanymkanov/fastapi-best-practices · arctikant/fastapi-modular-monolith-starter-kit ·  
  import-linter docs · ArchUnitPython · PyTestArch · handsonarchitects.com fitness functions  

---

## Waarom dit plan verschilt van het vorige

Het vorige plan loste de symptomen op. Dit plan lost de **oorzaken** op én maakt ze **permanent onmogelijk** via geautomatiseerde architectuurcontroles die bij elke commit draaien.

Nieuw t.o.v. vorig plan:

| Toevoeging | Wat het doet |
|---|---|
| `import-linter` contracts | Verbiedt verboden imports op laagniveau — CI-failure bij schending |
| `ArchUnitPython` fitness tests | Detecteert orphan routers, cyclische imports, te grote bestanden automatisch |
| Gateway-patroon per module | Elimineert cross-router imports structureel — niet door discipline maar door ontwerp |
| Drie-laags router compositie | Vervangt de centrale God-registry door hiërarchische samenstelling |
| Expliciete `__init__.py` public API | Elk module definieert exact wat het exporteert — geen accidentele lekken |
| Pre-commit hooks | Vangt schendingen op vóór ze de repo bereiken |

---

## Toolstack (production-proven)

```bash
pip install import-linter          # architectuurcontracts als CI-gate — primaire tool
```

`pytest-testarch` is verwijderd — nergens gebruikt in dit plan.  
`archunitpython` is verwijderd — de enige zinvolle test (`test_no_cycles`) maskte fouten via `try/except` en voegde weinig toe bovenop `import-linter`. `import-linter` dekt alle import-discipline. Cyclische imports worden opgevangen door smoke tests.

Geen nieuwe runtime-dependencies — dit is een development/CI-tool.

---

## Kernprincipe — lees dit vóór je ook maar één regel code schrijft

**De API Layer is uitsluitend verantwoordelijk voor HTTP-vertaling:**

- Accepteert een HTTP-request en valideert de vorm (Pydantic schema)
- Delegeert direct aan een application service of gateway
- Retourneert de respons als gestructureerde HTTP-response

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
    db: AsyncSession = Depends(get_db),        # ← directe DB
    current_user: UserResponse = Depends(get_current_user),
) -> MissionResponse:
    mission = MissionORM(title=request.title)  # ← ORM in route
    db.add(mission)
    await db.commit()                          # ← transactiebeheer in route
    return mission
```

Een router die dit principe schendt — door rechtstreeks te praten met repositories, ORM-modellen, core services of infra-componenten — is een Laag 1 violation, ook als alle andere regels kloppen.

---

## Deel 1 — Directe fixes (deze week, ~2.5 dagen)

### Stap 0A: 11 eager imports lazy maken (20 min, P0)

**⚠️ Kritieke vereiste vóór uitvoering:** `register_routers(app)` moet **synchroon** worden aangeroepen direct na `app = FastAPI(...)`, buiten de lifespan. FastAPI bouwt de router-regex-boom, DI-cache en OpenAPI schema op vóór de ASGI-app verkeer accepteert. Routes toevoegen ín de lifespan leidt tot incomplete Swagger-docs, middleware die niet correct wordt applied op late routes, en potentiële 404-errors bij vroege requests.

```python
# main.py of app_factory.py — CORRECT: synchroon, vóór lifespan
app = FastAPI(lifespan=lifespan)
register_routers(app)   # ← direct na app-instantiatie, NIET in lifespan

# FOUT — routes na ASGI-start registreren:
# async def lifespan(app):
#     register_routers(app)  ← te laat, middleware-volgorde is al vastgezet
#     yield
```

Test direct na Stap 0A: `uvicorn src.main:app --host 0.0.0.0 --port 8000` en verifieer dat `/docs` alle routes toont en dat TenantMiddleware actief is op alle endpoints.

```python
# src/core/api/setup/router_registry.py — verplaats regels 13-29 naar functie-body

# VOOR (module-level, fout):
from src.core.api.admin_endpoints import router as admin_router
from src.core.api.chat_endpoints import router as chat_router
# ... 9 meer

# NA (binnen register_routers(), correct):
def register_routers(app: FastAPI) -> None:
    from src.core.api.admin_endpoints import router as admin_router
    from src.core.api.chat_endpoints import router as chat_router
    # ... zelfde imports, alleen indented
    app.include_router(admin_router, ...)
```

Verwachte tijdwinst pytest-collectie: **15–25 seconden**.

### Stap 0B: TESTING guard in `api/main.py` (10 min, P0)

```python
# src/core/api/main.py — bovenaan na bestaande imports
import os
_TESTING = os.environ.get("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ

if not _TESTING:
    from src.core.api.setup.router_registry import (
        metrics_middleware_available,
        register_routers,
        security_available,
    )
```

### Stap 0C: Cross-router imports verbreken (30 min, P1)

Zeven paren waarbij routers andere routers importeren. **Belangrijk:** gooi ze niet allemaal in `dependencies.py` — dat wordt een nieuw God-bestand. Splits op scope:

```text
src/core/api/
├── dependencies.py               # alleen app-wide: require_admin_role, get_current_tenant_id
└── v1/
    └── cva/
        └── dependencies.py       # domein-specifiek: handle_cva_value_error
    └── compliance/
        └── dependencies.py       # compliance-specifiek
```

```python
# Voeg toe aan src/core/api/dependencies.py (alleen app-wide):
from fastapi import Depends, HTTPException, Security
from src.core.auth.dependencies import get_current_user

def require_admin_role(current_user=Security(get_current_user)):
    if "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user

# get_current_tenant_id (verplaats vanuit search_endpoints.py — app-wide)
```

```python
# src/core/api/v1/cva/dependencies.py (domein-specifiek):
def handle_cva_value_error(exc: ValueError) -> HTTPException:
    # handle_cva_value_error hoort NIET in globale dependencies
    return HTTPException(status_code=400, detail=str(exc))
```

Update alle importerende bestanden:
```python
# VOOR:
from src.core.api.admin_endpoints import require_admin_role
# NA (app-wide):
from src.core.api.dependencies import require_admin_role

# VOOR:
from src.core.api.cva_utils import handle_cva_value_error
# NA (domein-specifiek):
from src.core.api.v1.cva.dependencies import handle_cva_value_error
```

### Stap 0D: Hardcoded return-counts fixen (45 min, P1)

```python
# VOOR — maskeert registratiefouten:
def _register_agentic_features(app: FastAPI) -> int:
    # ... 22 imports en include_router calls
    return 22  # hardcoded

# NA — werkelijk getal, zichtbaar in logs:
def _register_agentic_features(app: FastAPI) -> int:
    count = 0
    from src.core.api.agentic_flow_endpoints import router as agentic_router
    app.include_router(agentic_router, prefix="/api/v1")
    count += 1
    # ... per include_router: count += 1
    return count
```

### Verificatie na Deel 1

```bash
pytest tests/unit/api/ -x -q --timeout=30
pytest tests/integration/ -x -q --timeout=60
python -c "from src.core.api.dependencies import require_admin_role; print('OK')"
```

---

## Deel 2 — Router Registry splitsen (dag 2–3)

### Doelstructuur: drie-laags compositie

Gebaseerd op het **arctikant modular monolith** patroon — production-proven voor precies dit probleem:

```
src/core/api/
├── router_registry.py          # Laag 3: app-level orchestrator (~80 regels)
├── registries/                 # Laag 2: domein-registries
│   ├── __init__.py
│   ├── auth_admin.py           # 6 routers
│   ├── copilot.py              # 3 routers → src/core/copilot/api/ (ADR-027)
│   ├── agents.py               # 10 routers
│   ├── workflows.py            # 18 routers
│   ├── knowledge.py            # 8 routers
│   ├── compliance.py           # 4 routers (governance, gatekeeper, GDPR, AI Act)
│   ├── realtime.py             # 6 routers (notifications, WebSocket)
│   ├── tenants.py              # 11 routers
│   ├── analytics.py            # 9 routers
│   └── integrations.py        # 15 routers (billing, webhooks, activepieces)
└── v1/                         # Laag 1: individuele route-bestanden
    ├── <domein>/
    │   ├── __init__.py         # Exporteert composite router + public API
    │   ├── router.py           # Routes — GEEN directe DB of domeinimports
    │   ├── schemas.py          # Pydantic request/response
    │   └── dependencies.py    # FastAPI Depends voor dit domein
```

### Nieuw `router_registry.py` (~80 regels)

```python
# src/core/api/router_registry.py
from fastapi import FastAPI
from loguru import logger

from src.core.api.registries import (
    auth_admin, copilot, agents, workflows,
    knowledge, compliance, realtime, tenants,
    analytics, integrations,
)

def register_all_routers(app: FastAPI) -> int:
    total = 0
    total += auth_admin.register(app)
    total += copilot.register(app)      # verwijst naar src/core/copilot/api/ — ADR-027 intact
    total += agents.register(app)
    total += workflows.register(app)
    total += knowledge.register(app)
    total += compliance.register(app)
    total += realtime.register(app)
    total += tenants.register(app)
    total += analytics.register(app)
    total += integrations.register(app)
    logger.info("api.routers_registered total={}", total)
    return total
```

### Voorbeeld domeinregistry (maximaal 80 regels)

```python
# src/core/api/registries/compliance.py
from fastapi import FastAPI


def register(app: FastAPI) -> int:
    count = 0
    from src.core.api.v1.compliance import compliance_router  # lazy
    app.include_router(compliance_router)
    count += 1
    return count
```

### Expliciete `__init__.py` public API per domein

```python
# src/core/api/v1/compliance/__init__.py
# Gebaseerd op arctikant modular monolith patroon
# NOTE: intern bestand heet gdpr_router.py — NIET compliance_router.py
# (compliance_router.py zou circulair zijn: compliance/__init__.py → compliance/compliance_router.py)
from fastapi import APIRouter

from src.core.api.v1.governance.router import router as governance_router
from src.core.api.v1.gatekeeper.router import router as gatekeeper_router
from src.core.api.v1.compliance.gdpr_router import router as gdpr_router      # ← gdpr_router.py
from src.core.api.v1.ai_act.incident_router import router as incident_router

# Composite router — 130 include_router calls worden ~11
compliance_router = APIRouter(prefix="/api/v1", tags=["Compliance"])
compliance_router.include_router(governance_router)
compliance_router.include_router(gatekeeper_router)
compliance_router.include_router(gdpr_router)
compliance_router.include_router(incident_router)

# Public API — alleen dit is importeerbaar van buiten het domein
__all__ = ["compliance_router"]
```

### Volgorde (3 dagen, per dag rollback-vrij)

**Dag 1 — laagste risico:**
- `registries/auth_admin.py` — `_register_auth_admin()` + `_register_admin_management()`
- `registries/compliance.py` — governance, gatekeeper, GDPR, AI Act
- Regression: `pytest tests/unit/api/ tests/integration/ -x -q`

**Dag 2 — medium:**
- `registries/analytics.py` + `registries/realtime.py` + `registries/tenants.py`

**Dag 3 — hoogste complexiteit:**
- `registries/agents.py` — 10 routers uit de God-function
- `registries/workflows.py` — 18 routers
- `registries/integrations.py` + `registries/copilot.py`

---

## Deel 3 — Architecturele fitness functies (dag 4–5)

Dit is het fundament dat toekomstige drift **permanent onmogelijk maakt**.

### 3A: import-linter contracts

```bash
# Installeer
pip install import-linter
# Voeg toe aan requirements-dev.txt: import-linter>=2.0
```

```ini
# .importlinter — projectroot
[importlinter]
root_package = src
include_external_packages = True

# Contract 1: API layer mag niet direct domeinmodules importeren
[importlinter:contract:api-no-domain]
name = API routers mogen niet direct domeinlogica importeren
type = forbidden
source_modules =
    src.core.api.v1.*.router
forbidden_modules =
    src.core.database
    src.core.governance
    src.core.learning
    src.core.agents
    src.core.workflow
    src.core.llm
ignore_imports =
    src.core.api.v1.*.dependencies -> src.core.database

# Contract 2: Routers mogen geen andere routers importeren
[importlinter:contract:no-cross-router]
name = Routers mogen niet andere routers importeren
type = forbidden
source_modules =
    src.core.api.v1.*.router
forbidden_modules =
    src.core.api.v1.*.router
ignore_imports =
    # geen uitzonderingen — dit is absoluut

# Contract 3: Gelaagde architectuur
# NOTE: alle domeinmodules moeten hier staan — anders vallen imports via
# niet-gedekte paden (bijv. src.core.auth) door de mand.
[importlinter:contract:layers]
name = API laag staat boven domeinlaag staat boven infrastructuurlaag
type = layers
layers =
    src.core.api
    src.core.copilot | src.core.als | src.core.workflow | src.core.agents | src.core.governance
    src.core.auth | src.core.database | src.core.caching | src.core.resilience

# Contract 4: Gateways mogen niet andere domein-gateways importeren (ADR-033 §3b)
# Cross-domain calls lopen via domeinservices, niet via API-laag gateways onderling.
[importlinter:contract:no-cross-gateway]
name = Gateways mogen niet andere domein-gateways importeren
type = forbidden
source_modules =
    src.core.api.v1.*.gateway
forbidden_modules =
    src.core.api.v1.*.gateway

# Contract 5: Governance mag niet afhangen van copilot (unidirectioneel)
# NOTE: disabled — copilot importeert governance (Council) by design (ADR-027).
# [importlinter:contract:governance-independence]
# name = Governance en copilot zijn onafhankelijk
# type = independence
# modules =
#     src.core.governance
#     src.core.copilot
```

Integreer in CI:
```bash
# scripts/ci-local-fast.sh — voeg toe:
echo "Checking architectural contracts..."
lint-imports
```

```yaml
# .github/workflows/ci.yml — voeg toe als apart job:
- name: Architecture contracts
  run: lint-imports
```

### 3B: Pytest fitness tests

`archunitpython` en `pytest-testarch` zijn verwijderd — `import-linter` dekt alle import-disciplineregels accuraat op AST-niveau. String-parsing tests (`test_no_direct_db_in_router_files`, `test_no_cross_router_imports`) zijn verwijderd omdat ze:

- Fragiel zijn bij multiline imports, aliassen en `from src.core import database`
- Exact dezelfde regels dubbel implementeren als `import-linter` contracts `api-no-domain` en `no-cross-router`

Behouden zijn de vier tests die `import-linter` **niet** dekt:

```python
# tests/architecture/test_api_layer.py
"""
Architectural fitness functions — structuurregels die import-linter niet dekt.
Bij elke commit gecontroleerd. Falen = bouw stopt.
"""
import ast
import pkgutil
import importlib
from pathlib import Path
import pytest


def _collect_router_defining_modules(root: Path) -> list[Path]:
    """
    Gebruik AST om bestanden te vinden die een APIRouter-instantie
    toewijzen aan een module-level naam. Betrouwbaarder dan string-search:
    vangt ook `router = APIRouter(prefix=...)` en aliassen.
    """
    results = []
    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # Zoek: <name> = APIRouter(...) op module-niveau (col_offset == 0)
            if (
                isinstance(node, ast.Assign)
                and node.col_offset == 0
                and isinstance(node.value, ast.Call)
            ):
                func = node.value.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute)
                    else ""
                )
                if name == "APIRouter":
                    results.append(py_file)
                    break
    return results


def test_no_orphan_routers():
    """
    Elk bestand met een module-level APIRouter-instantie moet
    geïmporteerd worden door de registry (direct of via registries/).
    """
    src = Path("src/core/api")
    # Verzamel alle import-statements in de registry-bestanden
    registry_imports: set[str] = set()
    for reg_file in [src / "router_registry.py"] + list((src / "registries").glob("*.py") if (src / "registries").exists() else []):
        if not reg_file.exists():
            continue
        try:
            tree = ast.parse(reg_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                registry_imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    registry_imports.add(alias.name)

    router_files = _collect_router_defining_modules(src)
    orphans = []
    for py_file in router_files:
        # Vertaal bestandspad naar module-pad
        rel = py_file.relative_to(Path("."))
        module = str(rel).replace("\\", "/").replace("/", ".").replace(".py", "")
        # Controleer of de module of een parent wordt geïmporteerd
        imported = any(
            module == imp or module.startswith(imp + ".") or imp.startswith(module)
            for imp in registry_imports
        )
        # Uitzondering: copilot/api en scheduling/api zijn correct geïsoleerde bounded contexts
        is_exempt = (
            "copilot/api" in str(py_file)
            or "scheduling/api" in str(py_file)
            or "# orphan:exempt" in py_file.read_text(encoding="utf-8", errors="ignore")
        )
        if not imported and not is_exempt:
            orphans.append(str(py_file))

    assert not orphans, (
        "Orphan router-bestanden gevonden (niet geregistreerd in registry):\n"
        + "\n".join(f"  - {f}" for f in orphans)
        + "\nVoeg toe aan src/core/api/registries/<domein>.py of verwijder het bestand."
        + "\nUitzonderingen: voeg `# orphan:exempt` toe aan het bestand."
    )


def test_no_router_files_over_200_lines():
    """
    router.py bestanden mogen niet groter zijn dan 200 regels.
    Groter = business logica in de route handler (verkeerd).
    """
    violations = []
    for py_file in Path("src/core/api/v1").rglob("router.py"):
        lines = len(py_file.read_text(encoding="utf-8").splitlines())
        if lines > 200:
            violations.append(f"{py_file} ({lines} regels)")
    assert not violations, (
        "Router bestanden te groot (max 200 regels):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_registry_files_under_80_lines():
    """
    Domeinregistry bestanden mogen niet groter zijn dan 80 regels.
    Groter = te veel verantwoordelijkheid per registry.
    """
    reg_dir = Path("src/core/api/registries")
    if not reg_dir.exists():
        pytest.skip("registries/ nog niet aangemaakt — na Deel 2 actief")
    violations = []
    for reg_file in reg_dir.glob("*.py"):
        if reg_file.name.startswith("_"):
            continue
        lines = len(reg_file.read_text(encoding="utf-8").splitlines())
        if lines > 80:
            violations.append(f"{reg_file} ({lines} regels)")
    assert not violations, (
        "Registry bestanden te groot (max 80 regels):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_no_eager_imports_in_setup_registry():
    """
    setup/router_registry.py mag geen module-level imports van
    endpoint-bestanden bevatten (eager import anti-patroon).
    Na Stap 0A moet deze test groen zijn.
    """
    setup_registry = Path("src/core/api/setup/router_registry.py")
    if not setup_registry.exists():
        return  # bestand verwijderd — test slaagt automatisch

    tree = ast.parse(setup_registry.read_text(encoding="utf-8"))

    # Verzamel TYPE_CHECKING guard-lijnen — die zijn geen runtime imports
    type_checking_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or
                (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_tc:
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        type_checking_lines.add(child.lineno)

    eager_imports = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.lineno in type_checking_lines:
            continue
        if getattr(node, "col_offset", 1) != 0:
            continue  # inspringing > 0 = binnen functie (lazy) — correct
        if isinstance(node, ast.ImportFrom) and node.module:
            if "endpoints" in node.module or node.module.endswith(".router"):
                eager_imports.append(f"  Lijn {node.lineno}: from {node.module} import ...")

    assert not eager_imports, (
        "Eager imports gevonden in setup/router_registry.py:\n"
        + "\n".join(eager_imports)
        + "\nVerplaats naar functie-body (lazy import patroon) — zie Stap 0A."
    )
```

### 3C: Pre-commit hook

```yaml
# .pre-commit-config.yaml — voeg toe aan bestaande hooks
repos:
  - repo: local
    hooks:
      - id: architecture-contracts
        name: Architecture contracts (import-linter)
        entry: lint-imports
        language: system
        pass_filenames: false
        always_run: true

      - id: architecture-fitness
        name: Architecture fitness tests (orphan + size)
        entry: pytest tests/architecture/test_api_layer.py -x -q
        language: system
        pass_filenames: false
        types: [python]
```

Geen `archunitpython` meer in de pre-commit chain — de vier fitness tests draaien via standaard pytest.

---

## Deel 4 — Strangler Fig migratie (per sprint)

### Principe (Netflix Dispatch / zhanymkanov patroon)

Elke domain-module volgt exact dit patroon — geen uitzonderingen:

```
src/core/api/v1/<domein>/
├── __init__.py         # Exporteert composite router + public API surface
├── router.py           # ALLEEN routes — max 200 regels, geen DB-imports
├── schemas.py          # ALLEEN Pydantic request/response models
├── dependencies.py    # ALLEEN FastAPI Depends()-functies voor dit domein
└── gateway.py          # Cross-module interface (zie Gateway-patroon)
```

### Gateway-patroon — elimineert cross-module imports structureel

**Scopebeperking: gateway.py mag geen mini-god-object worden.**

Een gateway-methode stelt één domein use case beschikbaar. Als het niet beschreven kan worden als "doe X voor domein Y", hoort het niet in `gateway.py`.

```python
# CORRECT — expliciete use cases
class AgentGateway:
    async def get_agent_summary(self, agent_id: str, tenant_id: int) -> AgentSummary: ...
    async def list_active_agents(self, tenant_id: int) -> list[AgentSummary]: ...

# FOUT — opportunistische shortcuts
class AgentGateway:
    def get_config(self): ...        # config access: hoort niet hier
    def format_response(self): ...   # utility helper: hoort in schemas.py
    def get_redis(self): ...         # infra shortcut: hoort in dependencies.py
```

Cross-domain communicatie loopt via de domeinservices zelf, niet via API-laag gateways onderling. Het `no-cross-gateway` import-linter contract (zie Deel 3A) dwingt dit af.

```python
# src/core/api/v1/agents/gateway.py
# Gebaseerd op arctikant modular monolith patroon
# Elk domein heeft één gateway — enige manier om van buiten te communiceren

from src.core.api.v1.agents.service import AgentService
from src.core.api.v1.agents.schemas import AgentSummary


class AgentGateway:
    """
    Publieke interface van het agents-domein.
    Andere modules importeren ALLEEN dit, nooit interne services.
    """
    def __init__(self, service: AgentService):
        self._svc = service

    async def get_agent_summary(self, agent_id: str, tenant_id: int) -> AgentSummary:
        return await self._svc.get_summary(agent_id, tenant_id)

    async def list_active_agents(self, tenant_id: int) -> list[AgentSummary]:
        return await self._svc.list_active(tenant_id)
```

```python
# src/core/api/v1/agents/__init__.py
from fastapi import APIRouter
from .router import router as agents_router

# Composite router
domain_router = APIRouter()
domain_router.include_router(agents_router)

# Public API — enige exports
from .gateway import AgentGateway
from .schemas import AgentSummary

__all__ = ["domain_router", "AgentGateway", "AgentSummary"]
```

### Repository-patroon voor CRUD (geen volledige service)

```python
# src/core/api/v1/missions/dependencies.py
from src.core.database.database import get_db
from src.core.repositories.mission_repository import MissionRepository

async def get_mission_repo(
    tenant_id: int = Depends(require_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> MissionRepository:
    return MissionRepository(db=db, tenant_id=tenant_id)
```

```python
# src/core/api/v1/missions/router.py — clean, geen DB-imports
@router.get("/missions")
async def list_missions(
    limit: int = Query(50, le=1000),
    offset: int = Query(0),
    repo: MissionRepository = Depends(get_mission_repo),
):
    return {"success": True, "data": await repo.list(limit=limit, offset=offset)}
```

### Migratieprocedure per domein (Strangler Fig)

Voer ALLEEN uit als je tóch al in dit domein werkt:

```
0. Controleer: bestaat er al een service/repository klasse voor dit domein?
   - Ja (bijv. MissionRepository) → gateway delegeert ernaar (ideaal)
   - Nee → maak een thin service die bestaande DB-calls omhult
   - Nooit → een nieuwe service schrijven die binnenin router.py logica dupliceert
1. Maak v1/<domein>/router.py, schemas.py, dependencies.py, gateway.py
2. Kopieer routes van *_endpoints.py naar router.py
3. Voeg toe aan v1/<domein>/__init__.py (composite router + public API)
4. Maak oud bestand re-export: from src.core.api.v1.X.router import router
5. Update registries/<domein>.py om nieuw pad te importeren
6. Voer behavioural equivalence test uit (zie hieronder)
7. Pas lint-imports contracts toe — alles groen?
8. Verwijder oud bestand na 5 groene CI-runs
```

### Behavioural equivalence test (verplicht per migratie)

```python
# tests/architecture/test_<domein>_equivalence.py
"""Bewijst dat gedrag identiek is vóór en na migratie."""

@pytest.mark.parametrize("method,path,expected", [
    ("GET",    "/api/v1/missions",        200),
    ("POST",   "/api/v1/missions",        201),
    ("GET",    "/api/v1/missions/999999", 404),
    ("DELETE", "/api/v1/missions/999999", 404),
])
async def test_mission_routes_preserved(method, path, expected, client, auth_headers):
    resp = await client.request(method, path, headers=auth_headers, json={"title": "t"})
    assert resp.status_code == expected, f"{method} {path} → {resp.status_code} (expected {expected})"
```

### Governance-routes — AI Act protocol

Routes onder ADR-031 (40 routes) behouden exact dezelfde URL, methode en response-schema.

Per migratie:
1. Structureel verplaatsen naar `v1/governance/router.py`
2. URL, HTTP-methode, response-schema **identiek** bewaren
3. Update ADR-031 evidence-matrix met nieuw bestandspad
4. Spec aanmaken in `docs/backend/features/` met "migrated from X"

---

## Deel 5 — Hard cutover (week 8)

```bash
# Identificeer resterende flat bestanden
find src/core/api -maxdepth 1 -name "*_endpoints.py" | grep -v "__"

# Per bestand: genereer v1/domain/ structuur
# Verifieer tests + lint-imports
# Verwijder oud bestand

# Na cutover: verwijder legacy-exemptie
# Nu geldt de import-gate voor ALLE bestanden
```

---

## Voorkomen van toekomstige drift — permanente maatregelen

### CI-pipeline (na alle fasen)

```yaml
# .github/workflows/ci.yml — architecture job
architecture-gate:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Import contracts
      run: lint-imports
    - name: Architecture fitness tests
      run: pytest tests/architecture/ -v --tb=short
    - name: Router discipline check
      run: bash scripts/ci-architecture-check.sh
```

```bash
# scripts/ci-architecture-check.sh
#!/bin/bash
set -e

echo "=== API Architecture Gate ==="

# 1. Geen orphan routers
# NOTE: while-loop in subshell via pipe verliest variabele — gebruik process substitution
echo "Checking orphan routers..."
ORPHANS=""
while IFS= read -r f; do
  stem=$(basename "$f" .py)
  if ! grep -q "$stem" src/core/api/router_registry.py 2>/dev/null; then
    ORPHANS="${ORPHANS}${f}\n"
  fi
done < <(find src/core/api -name "*.py" -maxdepth 1 | xargs grep -l "APIRouter()" 2>/dev/null)
[ -z "$ORPHANS" ] || { printf "FAIL: Orphan routers:\n%b" "$ORPHANS"; exit 1; }

# 2. Geen eager imports in setup registry
echo "Checking eager imports..."
python - <<'EOF'
import ast, sys
from pathlib import Path
f = Path("src/core/api/setup/router_registry.py")
if not f.exists():
    sys.exit(0)
tree = ast.parse(f.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and getattr(node, "col_offset", 1) == 0:
        if node.module and ("endpoints" in node.module or node.module.endswith(".router")):
            print(f"FAIL: Eager import at line {node.lineno}: from {node.module}")
            sys.exit(1)
EOF

# 3. Router bestanden < 200 regels
echo "Checking router file sizes..."
find src/core/api/v1 -name "router.py" | while read f; do
  lines=$(wc -l < "$f")
  [ "$lines" -le 200 ] || { echo "FAIL: $f has $lines lines (max 200)"; exit 1; }
done

echo "=== All architecture checks passed ==="
```

### ADR-033 — API Layer Discipline

Schrijf `docs/adr/ADR-033-api-layer-service-boundary.md` met:

- **Regel 1:** Elk domein heeft exact de structuur: `router.py / schemas.py / dependencies.py / gateway.py / __init__.py`
- **Regel 2:** `router.py` mag nooit direct importeren: `src.core.database`, `src.core.governance`, `src.core.learning`, `src.core.agents`, `src.core.workflow`, `src.core.llm`
- **Regel 3:** Routers mogen geen andere routers importeren — alleen `dependencies.py` of `gateway.py`
- **Regel 4:** Elke nieuwe router wordt geregistreerd in `registries/<domein>.py` — nooit in `router_registry.py` direct
- **Regel 5:** `registries/<domein>.py` maximaal 80 regels
- **Bewijs:** `lint-imports` + `pytest tests/architecture/` draaien bij elke commit

---

## Succesindicatoren

| Metriek | Nu | Na Deel 1+2 | Fully done |
|---|---|---|---|
| Eager module-level imports | 11 | 0 | 0 |
| `router_registry.py` regels | 1.027 | ~80 | ~80 |
| Orphan bestanden | 35 | 0 | 0 |
| Cross-router imports | 7 | 0 | 0 |
| `app.include_router()` calls | 130 | 130 | ~11 |
| Flat `*_endpoints.py` bestanden | ~60 | ~60 | 0 |
| `import-linter` contracts actief | nee | ja | ja |
| Pytest fitness tests (4 stuks) | 0 | 4 | 4 |
| Orphan auto-detectie in CI (AST) | nee | ja | ja |
| Pre-commit architecture hook | nee | ja | ja |
| Outgoing imports API layer | 852 | ~700 | < 200 |
| Pytest-collectietijd | ~139s | ~110s | < 80s |
| App startup tijd (cold, Docker) | ~X s | < X - 10% | < X - 20% |
| Nieuwe orphan MOGELIJK? | ja | **nee** | **nee** |
| Cross-router import MOGELIJK? | ja | **nee** | **nee** |

De laatste twee rijen zijn het echte doel: **structureel onmogelijk maken**, niet alleen repareren.

---

## Directe acties (vandaag)

- [ ] `pip install import-linter` → `requirements-dev.txt`
- [ ] **Verifieer eerst:** `register_routers(app)` staat synchroon na `app = FastAPI(...)`, buiten lifespan
- [ ] Stap 0A: eager imports lazy maken (20 min) — daarna: `uvicorn src.main:app` + check `/docs`
- [ ] Stap 0B: TESTING guard in `api/main.py` (10 min)
- [ ] Stap 0C: cross-router imports splitsen (app-wide → `dependencies.py`, domein-specifiek → `v1/<domein>/dependencies.py`) (30 min)
- [ ] Stap 0D: hardcoded return-counts fixen (45 min)
- [ ] Maak `tests/architecture/test_api_layer.py` aan (copy-paste uit dit plan)
- [ ] Maak `.importlinter` aan (copy-paste uit dit plan)
- [ ] Voeg `lint-imports` + fitness tests toe aan `scripts/ci-local-fast.sh`
- [ ] **Update CLAUDE.md §11** — herschrijf "altijd via de centrale registry (router_registry.py)" naar het nieuwe 3-laags patroon: individuele route → `v1/<domein>/__init__.py` composite → `registries/<domein>.py` → `router_registry.py` orchestrator
- [ ] Schrijf ADR-033
- [ ] Begin dag 1 van registry-split (auth_admin + compliance)

---

## Gerelateerde documenten

- `docs/reports/API-LAYER-COUPLING-ANALYSIS-2026-06-02.md` — grondige codebase-scan
- `docs/plans/api-layer-refactor-plan.md` — vorig plan (vervangen door dit document)
- `docs/adr/023-agent-orchestration-system.md` — agent routing architectuur
- CLAUDE.md §11 — "Routers via router_registry.py"
- AUDIT-COLL-01/02 valkuil — vergelijkbare eager-import fix
