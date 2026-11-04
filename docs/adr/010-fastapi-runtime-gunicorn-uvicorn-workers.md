# ADR-010: FastAPI Runtime - Gunicorn + Uvicorn Workers

## Status
Accepted

## Context
FastAPI applicaties vereisen een ASGI-server (zoals Uvicorn) om te draaien. Voor productie is Uvicorn alleen echter onvoldoende, omdat het geen procesbeheer (restarts bij crashes, worker management) biedt. We hebben een robuuste procesmanager nodig die meerdere workers kan draaien en signalen correct afhandelt.

## Decision
We gebruiken **Gunicorn** als procesmanager met **Uvicorn workers** (`uvicorn.workers.UvicornWorker`).

### 1. Worker Configuratie
Om optimale performance te garanderen, baseren we het aantal workers op de beschikbare CPU-capaciteit:
- **Berekening**: `(2 * CPU cores) + 1`
- **Type**: `UvicornWorker` voor volledige ASGI/AsyncIO ondersteuning.

### 2. Signal Handling & Lifecycle
Gunicorn beheert de levenscyclus van workers via signalen:
| Signaal | Actie | Gebruik |
| :--- | :--- | :--- |
| **HUP** | Graceful Restart | Config updates zonder downtime |
| **TERM** | Graceful Shutdown | Stoppen van service na afhandelen requests |
| **QUIT** | Fast Shutdown | Directe stop (bij nood) |

### 3. Configuratie Voorbeeld (`scripts/gunicorn_config.py`)
```python
worker_class = "uvicorn.workers.UvicornWorker"
workers = (multiprocessing.cpu_count() * 2) + 1
timeout = 60 # Verhoogd voor zware AI-requests
keepalive = 5
max_requests = 1000 # Zie ADR-011
```

### 4. Router-registratie timing (toegevoegd 2026-06-02, zie ADR-033)

`register_all_routers(app)` **moet synchroon worden aangeroepen direct na `app = FastAPI(...)`**, vóór de lifespan context manager. FastAPI bouwt de router-regex-boom, dependency-injectie cache en het OpenAPI schema op vóór de ASGI-app verkeer accepteert.

Routes toevoegen ín de lifespan is een anti-patroon dat leidt tot:
- Incomplete Swagger/OpenAPI documentatie
- Middleware (TenantMiddleware, AuditLoggingMiddleware) die niet correct applied wordt op late routes
- Potentiële 404-errors bij vroege requests tijdens het opstarten

```python
# CORRECT — synchroon, vóór lifespan
app = FastAPI(lifespan=lifespan)
register_all_routers(app)   # ← direct hier

# FOUT — te laat, router-boom al gebuild
async def lifespan(app: FastAPI):
    register_all_routers(app)  # ← NIET hier
    yield
```

### 5. In-memory state is verboden in router modules (toegevoegd 2026-06-09)

Elke Uvicorn worker is een **apart OS-proces** met zijn eigen geheugenisolatie. Module-level dicts en lijsten in router bestanden worden **niet gedeeld** tussen workers en worden **gewist bij elke worker-restart** (zie ADR-011: max_requests=1000).

Dit maakt in-memory state in routers onbetrouwbaar en gevaarlijk voor compliance-kritische data:

```python
# ANTI-PATROON -- VERBODEN
_tenant_checklists: dict[str, ComplianceChecklist] = {}  # elk worker heeft zijn eigen kopie

# CORRECT -- persisteer in PostgreSQL of Redis
async def get_checklist(tenant_id: str, db: AsyncSession) -> ComplianceChecklist:
    result = await db.execute(select(Checklist).where(Checklist.tenant_id == tenant_id))
    return result.scalar_one_or_none()
```

**Bekende overtreding (backlog TD-1.4):**
`src/core/api/v1/gdpr_compliance/utility_router.py` regel 32 gebruikt `_tenant_checklists: dict[str, ComplianceChecklist] = {}` als module-level state voor de GDPR compliance checklist. Dit betekent dat compliance-status per worker verschilt en verloren gaat bij elke worker-recycle. Fix: migreer naar een `compliance_checklists` PostgreSQL-tabel.

**Stelregel:** Elke state die twee opeenvolgende HTTP-requests consistent moet zijn, hoort in de database of Redis — nooit in een module-level variabele.

## Consequences

**Positive:**

- Automatisch herstel: Gunicorn herstart automatisch gecrashte workers.
- Betere benutting van multi-core servers.
- Gecentraliseerde logging van worker-events.

**Negative:**

- Iets complexere stack dan alleen Uvicorn.
- Geheugengebruik per worker moet gemonitord worden om OOM (Out Of Memory) op de host te voorkomen.
- Module-level state (dicts, lijsten) in routers is per-worker en niet persistent -- dit is een veelvoorkomende productiefout, zie sectie 5.

**Notes:**

- We gebruiken `post_fork` hooks voor het re-initialiseren van DB-verbindingen en OpenTelemetry tracers in elke worker.
