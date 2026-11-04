# AGENTS.md -- Code Quality Review Pipeline

**Effective Date:** 2026-05-30
**Enforcement:** MANDATORY for every implementation task

---

## Overview

This document defines the **mandatory agent-driven code quality pipeline** that ensures every line of code written for SanskritiSetu is:
- Architecturally sound (28 ADRs -- zie CLAUDE.md tabel)
- Type-safe (mypy via `scripts/run_mypy_audit.py` + pyright)
- Well-formatted (ruff)
- Secure (OWASP top 10, tenant isolation, secrets scanning)
- Testable (happy + unhappy paths)
- Gedocumenteerd (feature spec + review per sprint-dag)

**NO CODE IS WRITTEN WITHOUT PASSING ALL THREE GATES.**

---

## The Three Gates (Non-Negotiable)

### Gate 1: EnterPlanMode

**When:** Before ANY implementation task is started
**What:** Claude enters plan mode to analyze and design the solution
**Who:** Claude (planning) + User (approval)

**Checklist:**
- [ ] Read relevant CLAUDE.md sections (patterns, tenant isolation, error handling)
- [ ] Read relevant ADRs -- zie "Architectuur Kernbeslissingen" tabel in CLAUDE.md
- [ ] Read `docs/AUDIT-TO-FIX-WORKFLOW.md` if task is a bug fix or audit finding
- [ ] Read existing similar code (patterns, conventions)
- [ ] Design approach with trade-offs
- [ ] Identify which agents will be needed (beyond code-reviewer + quality-reviewer)
- [ ] Call ExitPlanMode and request user approval

**Outcome:**
- User approves -> proceed to Gate 2
- User requests changes -> loop back to design
- User rejects -> don't start Gate 2

---

### Gate 2: Spawn Agents (Parallel)

**When:** After user approves the design from Gate 1
**What:** Spawn independent agents to review the planned implementation BEFORE code is written
**Agents spawned:** 2 parallel agents (both must approve)

#### Agent: code-reviewer

**Purpose:** Review architecture, patterns, ADR compliance, tenant isolation

**Checklist:**
- [ ] Code follows CLAUDE.md architecture rules
- [ ] All ADR decisions from CLAUDE.md "Architectuur Kernbeslissingen" tabel are respected (geen RabbitMQ, geen Nginx, JWT tenant_id, etc.)
- [ ] `tenant_id` altijd uit JWT/middleware (`require_tenant_id()`), NOOIT uit request body -- CLAUDE.md regel 6
- [ ] Tenant isolation correct geimplementeerd (geen cross-tenant leaks)
- [ ] Error handling gebruikt custom exceptions, niet generieke HTTPException
- [ ] Logging bevat tenant_id + user_id + exc_info=True bij fouten -- CLAUDE.md regel 11
- [ ] Repository methods filteren op tenant_id + isolatietest aanwezig -- CLAUDE.md regel 10
- [ ] Geen hardcoded URLs, secrets, of configuratiewaarden -- altijd os.getenv()
- [ ] Alembic migrations (indien aanwezig): keten intact (`alembic check`), werkende downgrade()
- [ ] Test isolatie gehandhaafd (geen gedeelde staat tussen tests)
- [ ] Audit logs in `best_effort` blok -- CLAUDE.md regel 1 (nooit 500 veroorzaken bij audit failure)
- [ ] GET-endpoints hebben 6x hogere rate-limit dan schrijf-endpoints -- CLAUDE.md regel 2
- [ ] List-endpoints hebben limit/offset paginering -- CLAUDE.md regel 7
- [ ] Webhook events vertrouwen NOOIT tenant_id uit payload -- CLAUDE.md ActivePieces regel
- [ ] Optional dependency imports gebruiken fallback stub class patroon (niet `= None`) -- CLAUDE.md valkuilen 2026-05-30

**Output format:**
```
## Code Reviewer

**Status:** APPROVED | CHANGES_REQUESTED | BLOCKED

**Findings:**
- [ ] Finding 1 (severity: P0 | P1 | P2)

**Timestamp:** 2026-05-30T14:30:00Z
```

---

#### Agent: quality-reviewer

**Purpose:** Review code style, types, secrets, OWASP top 10

**Checklist:**
- [ ] Geen `any` types in TypeScript (gebruik `unknown` + type guard) -- CLAUDE.md Frontend regel 15
- [ ] Geen losse `any` in Python (gebruik expliciete types; `Any` is last resort met TODO-comment)
- [ ] Alle functies hebben type hints (mypy strict)
- [ ] Geen hardcoded secrets, API keys, passwords, tokens
- [ ] Geen commented-out code
- [ ] ASCII-only in source code -- geen emoji, geen Unicode -- CLAUDE.md regel 10
- [ ] Ruff linting passeert (`ruff check src/`)
- [ ] mypy baseline niet verhoogd (`python scripts/run_mypy_audit.py --fail-on-increase`)
- [ ] Imports georganiseerd (stdlib -> third-party -> internal -> relative)
- [ ] Geen unused imports of variabelen
- [ ] Logging gebruikt `%s` formatting, GEEN f-strings -- CLAUDE.md coderegel
- [ ] `datetime.now(timezone.utc)` gebruikt, NOOIT `datetime.now()` of `datetime.utcnow()` -- CLAUDE.md regel 3
- [ ] SQLAlchemy async: `select()` + `await db.execute()`, GEEN `.query()` -- CLAUDE.md regel 4
- [ ] Optional dependency try/except: fallback stub class, NIET `Foo = None` -- valkuil 2026-05-30
- [ ] TYPE_CHECKING blocks bevatten GEEN try/except -- valkuil 2026-05-30
- [ ] Geen `# type: ignore` zonder specifieke error-code EN uitleg waarom

**OWASP Top 10 Checks:**
- [ ] Geen SQL injection (parameterized queries, geen f-strings in SQL)
- [ ] Geen XSS (input sanitization, escaping)
- [ ] Geen sensitive data exposure (geen plaintext passwords, tokens in logs)
- [ ] Geen insecure deserialization
- [ ] Geen broken authentication (JWT validation, token expiry)
- [ ] Geen insecure direct object references (tenant_id filters)
- [ ] Geen broken access control (RBAC checks)

**Output format:**
```
## Quality Reviewer

**Status:** APPROVED | CHANGES_REQUESTED | BLOCKED

**Findings:**
- [ ] Finding 1 (severity: P0 | P1 | P2)

**Linting Results:**
- Ruff: PASS / FAIL
- MyPy baseline: PASS / FAIL (run_mypy_audit.py --fail-on-increase)

**Timestamp:** 2026-05-30T14:30:00Z
```

---

#### Outcome: Gate 2

- Beide agents APPROVED -> proceed to Gate 3
- Een van beide CHANGES_REQUESTED -> loop terug naar Gate 1
- Een van beide BLOCKED -> loop terug naar Gate 1

**Do NOT attempt to merge or work around reviewer feedback.**

---

### Gate 3: Local CI Checks

**When:** After both agents approve
**What:** Verify that code quality checks pass locally

```bash
# Backend -- gebruik audit scripts, niet directe mypy aanroep
python scripts/run_mypy_audit.py --fail-on-increase   # mypy via project config
pyright src/
ruff check src/

# Feature docs (frontend EN backend sprint-dag -- script valideert beide)
python scripts/validate_feature_docs.py                # exit 0 vereist
# Controleert: FE-* spec+Trainingssamenvatting+user-guide, BE-* spec+Trainingssamenvatting+review(APPROVED)

# Frontend
npm run type-check       # TypeScript strict
npm run lint             # ESLint
npm run test:unit        # Windows: npm run test:unit, NOOIT npx vitest (OOM)
```

**Waarom `run_mypy_audit.py` en niet directe `python -m mypy src/`?**
Directe mypy-aanroepen via PowerShell-subprocess kunnen een gecorrumpeerde cache lezen
en 20+ valse fouten tonen. Het audit-script runt mypy in een eigen subprocess met
eigen cache-context en toont de werkelijke stand.

**Outcome:**
- Alle checks slagen -> code is veilig om te schrijven (spawn Edit/Write)
- Een check faalt -> loop terug naar Gate 1

---

## Regressieverbod bij Refactoring, Migratie en Strangler Fig

**NON-NEGOTIABLE -- geen uitzonderingen.**

Elke migratie, refactoring of Strangler Fig-stap die importpaden, module-locaties of
router-registraties wijzigt, vereist een **volledige regressiecheck** vóór commit.
Alleen `tests/architecture/ tests/unit/api/` is NIET voldoende -- Strangler Fig-stappen
breken importpaden in tests buiten die directories.

### Verplichte volgorde bij refactoring

**Stap 1 — Impact-analyse VOOR de eerste wijziging (verplicht)**

De volledige suite draaien na elke wijziging is onwerkbaar (45+ minuten). Gebruik de
impact-analyse om alleen de gerakte tests te vinden. Die run je na elke bestandswijziging.

Vóór je ook maar één bestand aanpast, zoek je alle tests die dat bestand importeren:

```bash
python - << 'PYEOF'
from pathlib import Path

CHANGED_FILES = [
    # "src/core/api/v1/workflow/workflow_execution_router.py",
    # Vul aan met alle bestanden die je vandaag aanraakt
]

affected = set()
for changed in CHANGED_FILES:
    stem = Path(changed).stem
    module = changed.replace("/", ".").replace("\\", ".").replace(".py", "")
    for test_file in Path("tests/unit").rglob("*.py"):
        try:
            src = test_file.read_text(encoding="utf-8-sig", errors="ignore")
            if stem in src or module in src:
                affected.add(str(test_file))
        except:
            pass
for t in sorted(affected): print(t)
PYEOF
```

Run de gevonden tests VOOR de eerste wijziging en noteer hun status.

**Stap 2 — Na elke individuele bestandswijziging: gerichte check (seconden)**

```bash
python -m pytest <testbestanden-uit-stap-1> -q --tb=short --timeout=60 2>&1 | tail -5
# Nieuw falen hier = zet het bestand terug, STOP
```

**Stap 3 — Voor commit: architectuur + gerichte tests (< 2 min)**

```bash
python -m pytest tests/architecture/ tests/unit/api/ -q --tb=short --timeout=30 2>&1 | tail -3
python -m pytest <testbestanden-uit-stap-1> -q --tb=short --timeout=60 2>&1 | tail -3
```

**Volledige suite (`tests/unit/`):** alleen via CI, niet lokaal na elke wijziging.

**Stopcriterium:** als gerichte tests of architectuurtests mislukken die vóór de dag
groen waren → STOP, commit niet, fix eerst.

### Wat als een test al vóór de refactoring faalt?

Documenteer dit als "pre-existing" in de final-approver brief. Introduceer nooit nieuwe
failures en sla pre-existing failures nooit ongedocumenteerd over. CI/CD mag niet rood
zijn door werk van vandaag.

### Waarom dit strikt is

Strangler Fig-shims die niet alle namen re-exporteren breken tests die de originele
locatie importeren. Dit is onzichtbaar voor `tests/architecture/` maar zichtbaar in
`tests/unit/` en `tests/security/`. Één gemiste re-export kan tientallen tests breken
die niets met de wijziging lijken te hebben. Eén keer vergeten kost weken herstelwerk.

---

## DSM Meting — Correcte Methode (kritiek)

`scripts/generate_c4_dsm.py` rapporteert "175 unieke paren" — dit zijn GROUP-to-GROUP paren
tussen 23 groepen. **Dit is NIET de ADR-033 metriek "outgoing imports < 200".**

De ADR-033 baseline van 852 en het doel < 200 meten *verboden imports* vanuit de API-laag:

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
print(f"ADR-033 forbidden imports: {v1+flat} (doel: <200)")
```

Gebruik **altijd** dit script bij DSM-rapportage, nooit de DSM-generator output alleen.

---

## Circulaire Afhankelijkheden Oplossen

Circulaire deps (`auth ↔ core_api`, `agent_runtime ↔ core_api`) worden opgelost door
de bron van de dep-chain te verplaatsen naar een neutraal pakket:

| Patroon | Root cause | Fix |
|---------|-----------|-----|
| `auth` importeert `src.core.api.*` | `PublicEndpointRegistry` in API-laag | Verplaats naar `src/core/middleware/public_registry.py` |
| `agent_runtime` importeert `src.core.api.v1.*` | Schemas in endpoint-bestand | Verplaats naar `src/core/<domein>/schemas.py` |
| `router` importeert `src.core.database` | Directe DB-import | Verplaats naar `v1/<domein>/dependencies.py` |

Elke fix: lees bestand → identificeer import → verplaats naar neutraal pakket →
re-export shim in origineel bestand voor backward compat → regressiecheck.

---

## After All Gates Pass: Write Code

**ONLY when gates 1, 2, and 3 are complete:**
1. Spawn Edit/Write tools
2. Schrijf de code
3. Schrijf tests (happy + unhappy paths + behavioral + integration)
4. Verifieer dat tests groen zijn

---

## Verplicht na elke sprint-dag: Feature Documentation

Elke sprint-dag die backend-endpoints, services, models, schemas, agents of utilities
oplevert is pas KLAAR als de feature-documentatie is gegenereerd en gereviewd.

**Backend:** Volg `docs/backend/FEATURE_DOC_WORKFLOW.md` (3 stappen)
- Stap 1: Spec genereren -> `docs/backend/features/<ID>-<naam>.md`
- Stap 2: Review uitvoeren -> `docs/backend/review/review-<ID>.md`
- Stap 3: `python scripts/validate_feature_docs.py` -> exit 0

**Frontend:** Volg `docs/copilot-phase-2-frontend-visual-redesign/FEATURE_DOC_WORKFLOW.md` (5 stappen)

**ID-REGISTRY altijd bijwerken** voor elk nieuw ID.

---

## Audit-to-Fix Workflow

Na een audit met bevindingen (security, compliance, code review, AI Act):

> **STOP. Lees eerst `docs/AUDIT-TO-FIX-WORKFLOW.md` volledig vóór je ook maar een bestand aanraakt.**

De werkwijze is verplicht: structureren -> triage -> groupering -> sprint -> test-first fix -> verificatie -> preventie.

---

## Review Escalation Rules

| Severity | Action | Voorbeeld |
|----------|--------|-----------|
| **P0 (Critical)** | BLOCKED -- must be fixed | SQL injection, secrets in code, tenant isolation leak |
| **P1 (High)** | CHANGES_REQUESTED -- must be fixed | Missing type hints, hardcoded URL, no test coverage |
| **P2 (Medium)** | CHANGES_REQUESTED -- can be WAIVEd by owner | Style inconsistency, minor refactoring |

**Approval rules:**
- P0 findings: ZERO exceptions
- P1 findings: MUST be fixed before approval
- P2 findings: Can be WAIVED with owner justification (document why)

---

## Special Reviewer Roles (Context-Dependent)

Afhankelijk van de taak kunnen extra agents worden gespawned NA code-reviewer + quality-reviewer:

### performance-reviewer

**When:** Code touches API endpoints, database queries, bundle size, caching
**Checks:**
- Query performance (geen N+1, juiste indexes)
- Caching strategies (Redis, in-memory)
- Bundle size impact (frontend)
- Memory leaks (cleanup in useEffect, listeners)
- Rate limiting: GET-endpoints krijgen minimaal 6x de schrijf-limiet

### security-reviewer

**When:** Code touches auth, encryption, tenant isolation, rate limiting, webhooks
**Checks:**
- Tenant isolation (geen cross-tenant leaks)
- JWT validation (algorithm, expiry, claims)
- Cookie security (httpOnly, Secure, SameSite) -- CLAUDE.md regel 13.1
- Webhook payload validation: NOOIT tenant_id uit payload vertrouwen
- SQL injection prevention
- OWASP compliance

### frontend-designer

**When:** Code creates or modifies UI components
**Checks:**
- UX consistency (Radix UI patterns)
- Accessibility (ARIA, keyboard navigation)
- Responsive design
- Performance (bundle size, render optimization)
- Design system adherence

---

## Example: Full Pipeline in Action

### Scenario: "Add consent endpoint"

```
User: "Add POST /api/v1/consent endpoint"

Gate 1: EnterPlanMode
  Claude reads CLAUDE.md (best_effort patroon, rate limits, etc.)
  Claude reads ADR-003 (JWT tenant_id), ADR-005 (RLS)
  Claude designs: "Create service class, middleware voor tenant isolation, rate limit 10/min"
  Claude: ExitPlanMode
  User: "Approved"

Gate 2: Spawn Agents (parallel)
  code-reviewer:
    "Correctly uses require_tenant_id(), no X-Tenant-ID header fallback,
     audit logs in best_effort block" -> APPROVED
  quality-reviewer:
    "All types present, no secrets, ruff/mypy audit pass,
     datetime.now(timezone.utc) used" -> APPROVED

Gate 3: Local CI
  python scripts/run_mypy_audit.py --fail-on-increase -> PASS
  python scripts/validate_feature_docs.py             -> PASS (na documentatie)
  ruff check src/                                     -> PASS

Write Code
  Edit/Write spawned
  Code written
  Tests added (happy + unhappy + behavioral)

Sprint-dag sluit:
  Feature spec aangemaakt (docs/backend/features/<ID>.md)
  Review aangemaakt (docs/backend/review/review-<ID>.md)
  validate_feature_docs.py exit 0
```

---

## Common Pitfalls (What Agents Look For)

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Tenant leakage | code-reviewer checkt alle queries op `.where(Model.tenant_id == ...)` | Filter toevoegen of RepositoryError gooien |
| Type errors | quality-reviewer draait mypy audit script | Expliciete type hints toevoegen |
| Secrets in code | quality-reviewer scant op: `secret=`, `key=`, `token=` | Verplaatsen naar .env + os.getenv() |
| Geen tests | code-reviewer checkt test coverage | Happy + unhappy paths schrijven |
| Rate limit op GET | code-reviewer checkt decorator | Gebruik consent_read_limit (60/min), niet consent_update_limit (10/min) |
| Circular imports | quality-reviewer draait import checks | Imports reorganiseren of naar apart module verplaatsen |
| Missing tenant_id in logs | code-reviewer leest logging calls | `extra={"tenant_id": tenant_id}` toevoegen |
| `Foo = None` sentinel anti-patroon | quality-reviewer checkt optional imports | Fallback stub class gebruiken + `# type: ignore[no-redef]` |
| `TYPE_CHECKING + try/except` | quality-reviewer checkt TYPE_CHECKING blocks | Directe imports (alle libs in `ignore_missing_imports`) |
| `datetime.now()` zonder timezone | quality-reviewer scant op `datetime.now()` | Vervangen door `datetime.now(timezone.utc)` |
| Audit log buiten `best_effort` | code-reviewer checkt audit log writes | Wrap in `async with best_effort("...", db_session=db):` |
| `mypy --no-strict-optional` als CLI-flag | quality-reviewer | Gebruik `scripts/run_mypy_audit.py`, niet directe mypy CLI met flags |
| Unit test met volledige app-stack (async_client) | code-reviewer checkt fixture type | Verplaatsen naar `tests/integration/`; unit tests gebruiken alleen AsyncMock |
| mypy cache-corruptie na bulk-edits | audit script geeft inconsistente resultaten | `Remove-Item -Recurse -Force .mypy_cache` + herdraai via run_mypy_audit.py |

---

## Auditing the Pipeline

To verify compliance, run:

```bash
# Backend -- altijd audit scripts gebruiken
python scripts/run_mypy_audit.py --fail-on-increase
pyright src/
ruff check src/
python -m pytest tests/unit/ -n 8 --timeout=60 -q --tb=short
python scripts/validate_feature_docs.py

# Frontend
npm run type-check
npm run lint
npm run test:unit
```

Alle checks moeten slagen voor een PR wordt aangemaakt.

### Test Suite Health Checks

Na elke volledige unit run, controleer de samenvatting op:

```
N failed    -- 0 verwacht; elk getal vereist directe fix
N error     -- 0 verwacht; setup/teardown fouten
N xpassed   -- 0 verwacht; stale @pytest.mark.xfail markers -- verwijder ze
N xfailed   -- gedocumenteerde verwachte failures; zie test voor reden
```

**XPASS aanpak:** grep het gemelde testpad op `@pytest.mark.xfail` en verwijder de decorator. Doe dit direct -- stale xfail markers maskeren regressions.

**Quarantine tellen (recursief):**

```bash
python -c "from pathlib import Path; d=Path('tests/unit/temp_disabled'); files=[p for p in d.rglob('test_*.py') if '__pycache__' not in str(p)]; print(f'{len(files)} bestanden in quarantine')"
```

Grens: `MAX_QUARANTINED_TEST_FILES` in `tests/unit/test_pytest_suite_configuration.py`. Subdirectories tellen mee.


---

## L3 Wiring Audit Bevindingen -- 2026-06-01

Bottom-up L3 component scan uitgevoerd. 95 componenten gecontroleerd.
**Resultaat: 52 WIRED | 14 PARTIAL | 22 ORPHAN | 1 STUB**

### Kritieke gaps in de Agent Layer

#### CG-005 [HIGH] AgentHealthMonitorAgent heeft geen write-bridge naar AgentRouterAgent

`AgentHealthMonitorAgent` is volledig read-only in-memory. Er bestaat geen call-path
die `health_status` terugschrijft naar `AgentManifest` of `RegisteredAgent`.
`AgentRouterAgent._manifests` heeft `health_status` altijd `UNKNOWN`.
De Redis cache-tier (tier 2 van de ADR-023 5-tier routing) is ook afwezig:
`RouteCache` is puur in-memory, geen Redis client geinjectioneerd.

**Gevolg:** Health-aware routing is blind in productie. De 68 health-aware routing tests
slagen omdat ze health-data mocken. Ongezonde agents worden niet uitgesloten.

**Fix:**
```python
# In AgentRouterAgent -- toe te voegen methode:
def update_agent_health(self, agent_id: str, status: HealthStatus) -> None:
    if agent_id in self._manifests:
        self._manifests[agent_id].health_status = status
        # Invalideer routing-cache voor deze agent
        self._route_cache.invalidate(agent_id)

# In AgentHealthMonitorAgent -- aanroepen na evaluatie:
router_agent.update_agent_health(agent_id, new_status)
```

**Bewijs:** `src/core/agents/agent_router_agent.py` (health_status=UNKNOWN default),
`src/core/agents/agent_health_monitor_agent.py` (geen write-back methode).
**Sprint:** SP-WE-10

#### CG-006 [HIGH] CriticAgent niet geinjectioneerd in MasterOrchestratorAgent

`self._critic` in `MasterOrchestratorAgent` is getypeerd als `object | None`
met commentaar `"CriticAgent not yet built"`. `CriticAgent` is gewired als standalone
endpoint-dependency voor `/api/v1/orchestrate/critique` maar nooit doorgegeven
aan `MasterOrchestratorAgent`. Orchestrated workflows missen de kwaliteitsgate.

**Fix:**
```python
# In dependencies.py of orchestration router:
critic_agent = get_critic_agent(tenant_id=tenant_id, db=db)
orchestrator = MasterOrchestratorAgent(
    tenant_id=tenant_id,
    critic=critic_agent,   # <-- dit ontbreekt
    router=agent_router,
)
```

**Bewijs:** `src/core/agents/master_orchestrator_agent.py` (`self._critic = None`).
**Sprint:** SP-WE-11

#### CG-005b [MEDIUM] SubagentLoader is geen echte singleton

CLAUDE.md beschrijft `SubagentLoader` als singleton maar er is geen module-level
`_instance` guard. Meerdere instantiatiepaden bestaan in `dependencies.py` en
`proposal_builder.py`. Bij elke request kan een nieuwe instantie worden aangemaakt,
wat leidt tot dubbel database-laadgedrag en inconsistente agent-catalogi.

**Fix:**
```python
# src/core/agents/subagent_loader.py
_loader: SubagentLoader | None = None

def get_subagent_loader() -> SubagentLoader:
    global _loader
    if _loader is None:
        _loader = SubagentLoader()
    return _loader
```

**Sprint:** SP-WE-12

### Orphan routers in de API Layer (22 bestanden)

De volgende endpoint-bestanden bestaan maar zijn NIET geregistreerd in `router_registry.py`.
De meeste zijn legacy-bestanden vervangen door `v1/`-varianten:

| Bestand | Status | Opmerking |
| --- | --- | --- |
| `collaboration_endpoints.py` | Legacy | Vervangen door `v1/collaboration/router.py` |
| `document_endpoints.py` | Legacy | Vervangen door `v1/documents/router.py` |
| `goal_endpoints.py` | Legacy | Vervangen door `v1/company/goal_router.py` |
| `tenant_management_endpoints.py` | Legacy | Vervangen door `v1/tenants/router.py` |
| `webhook_endpoints.py` | Legacy | Vervangen door specifieke webhook handlers |
| `websocket_endpoints.py` | Legacy | Vervangen door `v1/websocket/router.py` |
| `gdpr_compliance_endpoints.py` | **Medium** | GDPR endpoints mogelijk niet bereikbaar |
| `chat_endpoints.py` | Orphan | Niet geregistreerd, geen opvolger gevonden |
| `cva_admin.py` | Orphan | Niet geregistreerd |
| `ai_features_endpoints.py` | Orphan | Niet geregistreerd |
| `EnterpriseRouter` | Dead code | Registratie blokkeert door vroege `return 1` |

Legacy-bestanden kunnen worden verwijderd zodra is geverifieerd dat er geen clients
meer zijn die de oude paden aanroepen.

### Middleware Stack -- orphan middleware

De volgende middleware-klassen zijn gedefinieerd maar NIET in de ASGI-stack:

| Klasse | Bestand | Ernst | Opmerking |
| --- | --- | --- | --- |
| `AuditLoggingMiddleware` | `audit_middleware.py` | **HIGH** | Geen request-level audit trail -- SOC 2 CC7.2 niet gedekt |
| `AuditLoggerMiddleware` | (variant) | **MEDIUM** | Security pattern detection (SQLi/XSS) inactief |
| `RateLimitMiddleware` (Redis TokenBucket) | `rate_limit_middleware.py` | **MEDIUM** | Per-tenant tier-limieten inactief; alleen per-endpoint slowapi decorators werken |
| `HTTPSRedirectMiddleware` | `middleware_config.py` | **MEDIUM** | Alleen actief bij `FORCE_HTTPS=true`; moet altijd aan in productie |

### Nieuwe sprints vereist

| Sprint | Omschrijving | Prio |
| --- | --- | --- |
| SP-WE-10 | AgentHealthMonitorAgent write-bridge + Redis cache tier | P1 |
| SP-WE-11 | CriticAgent injectie in MasterOrchestratorAgent | P1 |
| SP-WE-12 | SubagentLoader singleton pattern | P2 |
| SP-WE-13 | JWT verificatie unificeren (3 paden -> 1) | P1 security |
| SP-WE-14 | AuditLoggingMiddleware toevoegen aan ASGI-stack | P1 compliance |
| SP-WE-15 | hitl_repo injecteren in CopilotService | P0 |
| SP-WE-16 | NotificationDispatcher instantiëren bij startup | P1 |
| SP-WE-17 | Canvas migratie: CanvasBase -> hoofd-Base + Alembic | P0 |

---

## Links

- **CLAUDE.md** -- Volledige regels: codepatronen, testing, ADRs, valkuilen, lessons learned
- **docs/AUDIT-TO-FIX-WORKFLOW.md** -- Verplichte werkwijze na audit-bevindingen
- **docs/backend/FEATURE_DOC_WORKFLOW.md** -- Verplichte backend feature documentatie
- **docs/copilot-phase-2-frontend-visual-redesign/FEATURE_DOC_WORKFLOW.md** -- Frontend feature docs
- **mypy-baseline.json** -- Huidige mypy error baseline (CI blokkeert bij toename)
- **scripts/run_mypy_audit.py** -- Mypy audit met baseline tracking
- **Memory: feedback_mandatory_agent_review_enforcement** -- Enforcement beslissing (2026-05-15)
- **ADRs** -- Architectuurbeslissingen (ADR-003 JWT, ADR-004 ORM filtering, ADR-026 LLM failover, etc.)
- **docs/adr/023-agent-orchestration-system.md** -- Agent orchestratie: CG-005/006 wiring gaps
- **docs/adr/003-tenant-boundary-jwt-source-of-truth.md** -- JWT: CG-007 drie verificatiepaden
- **docs/adr/019-audit-logging-compliance.md** -- Audit logging: CG-008 orphan middleware
- **docs/adr/027-copilot-agent-council.md** -- Council: CG-001 ComplianceOfficer, CG-003/004 HITL/NotificationDispatcher
