# Production Readiness Checklist
**Last Updated**: 2026-01-13
**Contract**: No production deployment without Phase 1 = 100% ✅
**Based on**: FastAPI, Docker, Prometheus, OpenTelemetry best practices

---

## RELEASE GATING RULES

| Phase | Min % Complete | Deployment Target | Blocker? |
|-------|---------------|-------------------|----------|
| Phase 1: CRITICAL | **100%** | ANY production | ✅ HARD BLOCK |
| Phase 2: HIGH PRIORITY | **80%** | Paying tenants | ⚠️ SOFT BLOCK |
| Phase 3: MEDIUM PRIORITY | **60%** | Enterprise tier | 📊 RECOMMENDED |
| Phase 4: K8S MIGRATION | **0%** | Future/optional | 🔮 ROADMAP |

---

## PHASE 0: AUTORISATIE -- HARDE BLOKKER VOOR DE EERSTE KLANT (toegevoegd 2026-09-01)

**Status**: OPEN -- 5 punten op P0, 5 op P1, 2 op P2
**Blocker**: JA. Geen enkele externe klant op ENIGE omgeving zolang de P0-cluster open staat.
**Bron van waarheid**: het openpuntenregister in
`docs/adr/036-agentic-organizational-hierarchy-governance-reuse.md`, sectie 10.

### Waarom deze sectie bestaat

Op 2026-09-01 is bij het verifieren van een extern ontwerpdocument een privilege-escalatiepad
gevonden dat vier schakels lang is en waarmee een willekeurig authenticated account volledige
platformtoegang krijgt, inclusief cross-tenant lezen. Twee onafhankelijke reviews zonder context
hebben elke schakel bevestigd. Er is bewust NIET direct gefixt: er is nog geen enkele klant, en de
reparatie van een van de punten (OP-186) kan zonder voorafgaande meting echte beheerders
buitensluiten.

Deze sectie DUPLICEERT de bevindingen niet. Dat is een expliciete keuze: het register en de
codecommentaren zijn in dit project eerder uit elkaar gelopen doordat dezelfde bevinding op twee
plekken stond en er maar een werd bijgewerkt. Hieronder staan alleen de nummers en de poortregel.

**Herbevestigd 2026-09-07: dit is geen momentopname maar een duurzame randvoorwaarde van het
hele bouwtraject.** Er zijn GEEN bestaande klanten, en er komen GEEN nieuwe klanten zolang de
applicatie nog in de bouwfase zit -- eerst moet er een werkende applicatie zijn, pas daarna een
klant. Dit cluster (OP-182 t/m OP-193) blijft dus voor de VOLLE DUUR van de bouw ongemoeid, niet
tot een volgende, kortlopende herbeoordeling. Elke sessie die dit cluster tegenkomt (in het
ADR-036-register, in een backlog-sprint, in een audit) mag dit als vaststaand aannemen en hoeft
niet opnieuw te vragen of de situatie is veranderd. Wanneer de applicatie wel klaar is voor een
eerste klant, is dat een expliciet, apart moment dat Rakesh zelf aankondigt -- niet iets dat een
sessie zelf afleidt uit voortgang, tijdsverloop, of het gevoel dat de code er klaar voor is.

### De poortregel

| Punt | Wat het is, in een regel | Prio |
| --- | --- | --- |
| OP-182 | Een refresh-token wordt geaccepteerd als access-token, en draagt hardgecodeerd tenant 1 | P0 |
| OP-183 | Twee cross-tenant schrijfpaden zonder tenantcheck op de aanroeper | P0 |
| OP-184 | Een rolnaam uit een request-body bereikt het rol-aanmaakprimitief, op twee paden | P0 |
| OP-185 | Het rol-aanmaakprimitief maakt een onbekende rolnaam AAN en kent hem toe | P0 |
| OP-186 | De scope `ADMIN_ALL` in een JWT passeert elke scope-controle zonder databasecheck, over 306 endpoints | P0 |
| OP-187 | Permissieloze `admin`-rollen: `ensure_default_roles` slaat een bestaande naam over inclusief zijn wildcard-permissierij | P1 |
| OP-188 | Geen token-intrekking op het verzoekpad; uitloggen maakt een access-token niet ongeldig | P1 |
| OP-189 | `is_superuser` is een parallelle privilege-as die geen enkele rol- of niveaudefinitie kent | P1 |
| OP-190 | `roles` en `user_roles` vallen buiten Row Level Security; `user_roles` heeft geen `tenant_id` | P1 |
| OP-191 | Grammatica-mismatch scopes/permissies (meervoud tegen enkelvoud) | P1 |
| OP-192 | Ongeveer twintig rolbesluitpunten buiten de bestaande guard, waaronder HITL-goedkeurders en GDPR-wissing | P2 |
| OP-193 | Frontend-rolvocabulaire, waaronder een `AdminRoute` die een scope eist die niemand uitgeeft | P2 |

**Alle vijf de P0-punten moeten GESLOTEN staan in het register voordat een externe klant op enige
omgeving wordt aangesloten.** Het register dwingt zelf af dat een sluiting machineleesbaar bewijs
draagt (`tests/architecture/test_adr036_register_is_parseable.py`), dus "gesloten" is hier niet
iemands oordeel maar een toetsbare toestand.

### Twee dwingende volgorde-eisen bij de reparatie

1. **OP-186 mag niet dicht voordat OP-187 gemeten is.** Vandaag maskeert de `ADMIN_ALL`-
   snelkoppeling dat sommige `admin`-rollen nul permissierijen hebben. Hem weghalen geeft die
   tenants een 403 op alle 306 scope-beschermde endpoints, voor de ECHTE beheerder. De meting is
   een read-only query per tenant en levert tegelijk de detectielijst voor misbruik.
2. **OP-191 vergroot diezelfde groep.** De databasefallback matcht `agents:read` niet tegen een
   geseede `agent:*`-rij, dus ook legitieme `editor`-rollen vallen buiten. Meenemen in dezelfde
   meting.

### Wat NIET tot deze poort hoort

De structurele herinrichting van de autorisatielaag (een permissieregister met geordende niveaus,
`Role.slug`/`Role.level`, consolidatie van de acht admin-definities) is geen blokker. Die is
wenselijk maar niet nodig om veilig te kunnen deployen; de twaalf punten hierboven zijn dat wel.
Die scheiding is bewust: het door elkaar halen van "veilig" en "netjes" leidde eerder tot een
schatting van weken waar dagen nodig waren.

---

## PHASE 1: CRITICAL FIXES (DEPLOYMENT BLOCKERS)

**Status**: 🔴 0/5 Complete
**Target Release**: v1.0.0
**Blocker**: YES - Cannot deploy to ANY production environment

### 1.1 Docker Multi-Stage Build with Security Hardening
- [ ] Verify multi-stage Dockerfile (`base` → `dependencies` → `production`)
- [ ] Ensure production stage uses minimal base image (python:3.13-slim-bookworm)
- [ ] Add non-root user (`appuser` with UID 10001)
- [ ] Set `USER appuser` in final stage
- [ ] Enable read-only root filesystem (`read_only: true` in compose)
- [ ] Configure tmpfs for writable directories (`/tmp`, `/app/.cache`)
- [ ] **Test Command**: `docker build --target production -t sanskritisetu_backend_prod:latest .`
- [ ] **Success Criteria**: Image builds, runs as non-root, no security warnings

### 1.2 Docker Compose Production Stack with Health Checks
- [ ] Create `docker-compose.prod.yml` with external network reference
- [ ] Configure multi-level health checks (liveness + readiness)
  - Liveness: `/health` (basic container alive check)
  - Readiness: `/health/ready` (ready to serve traffic)
  - Startup: `start_period: 60s` for slow DB connections
- [ ] Add depends_on with `service_healthy` conditions
- [ ] Set restart policy to `unless-stopped`
- [ ] Configure resource limits (CPU, memory)
- [ ] Validate environment variables on startup
- [ ] **Test Command**: `docker-compose -f docker-compose.prod.yml up -d && docker-compose -f docker-compose.prod.yml ps`
- [ ] **Success Criteria**: All services `Up (healthy)` within 90s

### 1.3 Database Connection with pg_isready
- [ ] Replace fragile `db_url.replace('asyncpg', 'psycopg2')` in `entrypoint-prod.sh`
- [ ] Use `pg_isready -h postgres -p 5432 -U postgres` for health checks
- [ ] Set connection timeout (30 attempts × 2s = 60s max wait)
- [ ] Add structured logging for connection attempts
- [ ] **Test Command**: `docker exec sanskritisetu_backend_prod pg_isready -h postgres -p 5432`
- [ ] **Success Criteria**: `accepting connections` within 30s, no parsing errors

### 1.4 Docker Secrets for Sensitive Data
- [ ] Create `secrets/` directory (gitignored)
- [ ] Generate JWT secret: `python -c 'import secrets; print(secrets.token_urlsafe(32))' > secrets/jwt_secret.txt`
- [ ] Generate app secret: `python -c 'import secrets; print(secrets.token_urlsafe(32))' > secrets/app_secret.txt`
- [ ] Update `docker-compose.prod.yml` to mount secrets at `/run/secrets/`
- [ ] Modify `src/core/security.py` to read from `JWT_SECRET_KEY_FILE`
- [ ] Add validation: fail fast if secrets missing in production
- [ ] **Test Command**: Restart container, verify `JWT_SECRET_KEY` loaded from file
- [ ] **Success Criteria**: JWT tokens persist across restarts, no secrets in env vars

### 1.5 FastAPI Health Endpoints (Multi-Level)
- [ ] Implement `/health` (liveness - basic OK response)
- [ ] Implement `/health/ready` (readiness - check DB connection)
- [ ] Implement `/health/db` (detailed - pool stats, tenant count)
- [ ] Add correlation ID to all responses (`X-Request-ID` header)
- [ ] Return appropriate HTTP status codes (200 OK, 503 Service Unavailable)
- [ ] **Test Command**:
  ```powershell
  curl http://localhost:8001/health
  curl http://localhost:8001/health/ready
  curl http://localhost:8001/health/db
  ```
- [ ] **Success Criteria**: All endpoints return 200, `/health/db` shows pool stats

**Phase 1 Sign-Off**: _____________ (Tech Lead) Date: _______

---

## PHASE 2: HIGH PRIORITY (STABLE PRODUCTION)

**Status**: 🔴 0/8 Complete
**Target Release**: v1.1.0
**Blocker**: YES for paying customers

### 2.1 Multi-Worker Configuration
- [ ] Add gunicorn to `requirements-prod.txt`
- [ ] Update `entrypoint-prod.sh` with CPU-based worker calculation
- [ ] Configure worker recycling (`--max-requests 1000`)
- [ ] Set graceful timeout (30s)
- [ ] **Test Command**: `docker exec sanskritisetu_backend_prod ps aux | grep gunicorn`
- [ ] **Success Criteria**: Multiple worker processes visible

### 2.2 Database Connection Pooling
- [ ] Update `src/core/database/database.py` with QueuePool
- [ ] Set pool_size=20, max_overflow=10
- [ ] Enable pool_pre_ping
- [ ] Add pool_recycle=3600
- [ ] **Test Command**: `curl http://localhost:8001/health/db`
- [ ] **Success Criteria**: Pool stats visible in response

### 2.3 Structured Logging
- [ ] Add python-json-logger to requirements
- [ ] Create `src/core/observability/logging.py`
- [ ] Configure JSON formatter with tenant_id, trace_id
- [ ] Update docker-compose logging driver
- [ ] **Test Command**: `docker logs sanskritisetu_backend_prod --tail 10 | jq .`
- [ ] **Success Criteria**: Valid JSON logs with tenant_id field

### 2.4 Enhanced Health Endpoints
- [ ] Implement `/health/ready` (readiness probe)
- [ ] Implement `/health/db` (database connectivity)
- [ ] Add pool statistics to `/health/db`
- [ ] Update docker-compose healthcheck
- [ ] **Test Command**: `curl http://localhost:8001/health/ready`
- [ ] **Success Criteria**: Returns 200 only when DB connected

### 2.5 Correlation ID Middleware
- [ ] Add correlation_id to every request
- [ ] Inject into logging context
- [ ] Return in response headers (X-Request-ID)
- [ ] Propagate to database queries
- [ ] **Test Command**: `curl -i http://localhost:8001/health`
- [ ] **Success Criteria**: Response has `X-Request-ID` header

### 2.6 Tenant Context in All Logs
- [ ] Add tenant_id to LogRecord
- [ ] Include in JSON formatter
- [ ] Test multi-tenant log filtering
- [ ] Document log query patterns
- [ ] **Test Command**: `docker logs sanskritisetu_backend_prod | jq 'select(.tenant_id == "1")'`
- [ ] **Success Criteria**: Can filter logs by tenant

### 2.7 Graceful Shutdown Handler
- [ ] Implement SIGTERM handler
- [ ] Drain active connections
- [ ] Close database pool
- [ ] Log shutdown events
- [ ] **Test Command**: `docker stop -t 30 sanskritisetu_backend_prod`
- [ ] **Success Criteria**: Clean shutdown within 30s

### 2.8 Automated Smoke Tests
- [ ] Create `scripts/smoke_test.sh`
- [ ] Test all critical endpoints
- [ ] Verify health checks
- [ ] Check database connectivity
- [ ] **Test Command**: `./scripts/smoke_test.sh prod`
- [ ] **Success Criteria**: Exit code 0, all checks pass

**Phase 2 Sign-Off**: _____________ (SRE Lead) Date: _______

---

## PHASE 2: HIGH PRIORITY (STABLE PRODUCTION)

**Status**: 🔴 0/10 Complete
**Target Release**: v1.1.0
**Blocker**: YES for paying customers

### 2.1 Gunicorn Multi-Worker with UvicornWorker
- [ ] Add `gunicorn` to `requirements-prod.txt`
- [ ] Update `entrypoint-prod.sh` with CPU-based worker calculation
  ```bash
  WORKERS=$(python3 -c 'import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)')
  gunicorn src.main:app --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker
  ```
- [ ] Configure worker recycling (`--max-requests 1000 --max-requests-jitter 100`)
- [ ] Set graceful timeout (30s) for clean shutdown
- [ ] Add worker-tmp-dir (`/dev/shm`) for faster restarts
- [ ] **Test Command**: `docker exec sanskritisetu_backend_prod ps aux | grep gunicorn`
- [ ] **Success Criteria**: Multiple worker processes visible (e.g., 5 workers on 2-core CPU)

### 2.2 Database Connection Pooling (QueuePool)
- [ ] Update `src/core/database/database.py` with explicit pool configuration
  ```python
  from sqlalchemy.pool import QueuePool

  engine = create_async_engine(
      DATABASE_URL,
      poolclass=QueuePool,
      pool_size=20,
      max_overflow=10,
      pool_pre_ping=True,
      pool_recycle=3600
  )
  ```
- [ ] Set environment variables: `DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=10`
- [ ] Add pool statistics to `/health/db` endpoint
- [ ] Monitor pool exhaustion via Prometheus metrics
- [ ] **Test Command**: `curl http://localhost:8001/health/db | jq '.pool'`
- [ ] **Success Criteria**: Pool stats visible (size, checked_in, overflow)

### 2.3 Structured JSON Logging with Tenant Context
- [ ] Add `python-json-logger` to requirements
- [ ] Create `src/core/observability/logging.py` with JsonFormatter
- [ ] Configure logging to include: `timestamp`, `level`, `message`, `tenant_id`, `trace_id`, `correlation_id`
- [ ] Update all `logger.info()` calls to inject tenant context
- [ ] Configure Docker Compose logging driver: `json-file` with max-size/max-file
- [ ] **Test Command**: `docker logs sanskritisetu_backend_prod --tail 10 | jq .`
- [ ] **Success Criteria**: Valid JSON logs with `tenant_id` field

### 2.4 Prometheus Metrics with FastAPI Instrumentator
- [ ] Add `prometheus-fastapi-instrumentator==7.0.0` to requirements
- [ ] Instrument FastAPI app in `src/main.py`:
  ```python
  from prometheus_client import make_asgi_app, Counter, Histogram
  from prometheus_client.multiprocess import MultiProcessCollector, CollectorRegistry

  # Multi-process support (for Gunicorn)
  registry = CollectorRegistry()
  MultiProcessCollector(registry)

  # Custom metrics
  http_requests = Counter('http_requests_total', 'HTTP requests',
                          ['method', 'endpoint', 'status', 'tenant'])
  http_duration = Histogram('http_request_duration_seconds',
                            'HTTP request duration',
                            ['method', 'endpoint'])

  # Mount metrics app
  metrics_app = make_asgi_app(registry=registry)
  app.mount("/metrics", metrics_app)
  ```
- [ ] Add tenant ID as metric label for per-tenant monitoring
- [ ] Configure Prometheus scraping (see `observability/prometheus.yml`)
- [ ] **Test Command**: `curl http://localhost:8001/metrics | grep http_requests_total`
- [ ] **Success Criteria**: Prometheus format metrics with tenant labels

### 2.5 OpenTelemetry Distributed Tracing
- [ ] Add OpenTelemetry packages to requirements:
  ```
  opentelemetry-api==1.28.0
  opentelemetry-sdk==1.28.0
  opentelemetry-instrumentation-fastapi==0.49b0
  opentelemetry-exporter-otlp-proto-grpc==1.28.0
  ```
- [ ] Create `src/core/observability/tracing.py`:
  ```python
  from opentelemetry import trace
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor
  from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
  from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

  def setup_tracing(app):
      resource = Resource.create({"service.name": "sanskritisetu-backend"})
      provider = TracerProvider(resource=resource)
      provider.add_span_processor(
          BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))
      )
      trace.set_tracer_provider(provider)
      FastAPIInstrumentor.instrument_app(app)
  ```
- [ ] Call `setup_tracing(app)` in `src/main.py`
- [ ] Add `tenant.id` as span attribute in middleware
- [ ] Configure Jaeger exporter (OTLP gRPC on port 4317)
- [ ] **Test Command**: Browse `http://localhost:16686` (Jaeger UI)
- [ ] **Success Criteria**: Full request traces visible with DB query spans

### 2.6 Correlation ID Middleware
- [ ] Create `src/core/middleware/correlation_id.py`:
  ```python
  import uuid
  from starlette.middleware.base import BaseHTTPMiddleware

  class CorrelationIDMiddleware(BaseHTTPMiddleware):
      async def dispatch(self, request, call_next):
          correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
          request.state.correlation_id = correlation_id

          response = await call_next(request)
          response.headers["X-Request-ID"] = correlation_id
          return response
  ```
- [ ] Add middleware to app: `app.add_middleware(CorrelationIDMiddleware)`
- [ ] Inject correlation ID into logging context
- [ ] Propagate to OpenTelemetry spans as attribute
- [ ] **Test Command**: `curl -i http://localhost:8001/health | grep X-Request-ID`
- [ ] **Success Criteria**: Response has `X-Request-ID` header

### 2.7 Gunicorn Post-Fork Hook for Tracer Reinitialization
- [ ] Create `gunicorn_config.py`:
  ```python
  from opentelemetry import trace
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor
  from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

  def post_fork(server, worker):
      server.log.info(f"Worker spawned (pid: {worker.pid})")

      # Reinitialize tracer in forked process
      provider = TracerProvider()
      provider.add_span_processor(
          BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))
      )
      trace.set_tracer_provider(provider)
  ```
- [ ] Update `entrypoint-prod.sh`: `gunicorn -c gunicorn_config.py src.main:app`
- [ ] Verify traces from all worker processes
- [ ] **Test Command**: Check Jaeger UI for traces from multiple worker PIDs
- [ ] **Success Criteria**: Traces visible from all Gunicorn workers

### 2.8 Graceful Shutdown with Signal Handling
- [ ] Add SIGTERM handler in `src/main.py`:
  ```python
  import signal

  async def shutdown_handler(signum, frame):
      logger.info("Received shutdown signal, draining connections...")
      # Close database pool
      await db_engine.dispose()
      # Flush pending traces
      trace.get_tracer_provider().shutdown()
      logger.info("Graceful shutdown complete")

  signal.signal(signal.SIGTERM, shutdown_handler)
  signal.signal(signal.SIGINT, shutdown_handler)
  ```
- [ ] Configure Gunicorn: `--graceful-timeout 30`
- [ ] Test shutdown: `docker stop -t 30 sanskritisetu_backend_prod`
- [ ] **Test Command**: Send SIGTERM and check logs
- [ ] **Success Criteria**: Clean shutdown within 30s, no connection leaks

### 2.9 Automated Smoke Tests Script
- [ ] Create `scripts/smoke_test.ps1` with health check validation
- [ ] Test all critical endpoints (/health, /health/ready, /health/db, /metrics)
- [ ] Verify correlation ID header presence
- [ ] Check response times (p95 < 1000ms)
- [ ] Validate JSON log format
- [ ] **Test Command**: `.\scripts\smoke_test.ps1 -BaseUrl http://localhost:8001`
- [ ] **Success Criteria**: Exit code 0, alle checks pass (11 sinds ADR-036 OP-124: /docs, /redoc en /openapi.json moeten DICHT zijn, en /health/db moet 4xx geven -- dat is de diagnostics-tier)

### 2.10 Process Collector for System Metrics
- [ ] Add process metrics to Prometheus:
  ```python
  from prometheus_client import ProcessCollector, PlatformCollector

  ProcessCollector(namespace='sanskritisetu', registry=registry)
  PlatformCollector(registry=registry)
  ```
- [ ] Expose CPU usage, memory, file descriptors, GC stats
- [ ] Configure Grafana dashboard for system metrics
- [ ] Set up alerts for resource exhaustion (>80% memory, >90% CPU)
- [ ] **Test Command**: `curl http://localhost:8001/metrics | grep process_`
- [ ] **Success Criteria**: Process metrics visible (cpu, memory, fds)

**Phase 2 Sign-Off**: _____________ (SRE Lead) Date: _______

---

## PHASE 3: SCALABILITY & PRODUCTION HARDENING

**Status**: 🔴 0/6 Complete
**Target Release**: v1.2.0
**Blocker**: NO (recommended for enterprise scale)
**Context7 Sources**: FastAPI, Prometheus, Grafana docs

### 3.1 Rate Limiting with SlowAPI
**Context7 Pattern**: FastAPI best practices - per-tenant, per-endpoint throttling

- [ ] Add to requirements: `slowapi==0.1.9` and `limits==3.13.0`
- [ ] Create `src/core/middleware/rate_limit.py`:
  ```python
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.util import get_remote_address
  from slowapi.errors import RateLimitExceeded

  # Use tenant_id from request state for per-tenant limiting
  def get_tenant_key(request: Request):
      return f"tenant:{getattr(request.state, 'tenant_id', 'anonymous')}"

  limiter = Limiter(
      key_func=get_tenant_key,
      storage_uri=os.getenv("REDIS_URL", "redis://localhost:6379"),
      default_limits=["100/minute", "1000/hour"]
  )

  # In main.py
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

  # On endpoint
  @router.get("/expensive-operation")
  @limiter.limit("10/minute")
  async def expensive_op():
      ...
  ```
- [ ] Configure Redis backend for distributed rate limiting
- [ ] Add per-endpoint decorators: `@limiter.limit("10/minute")` for expensive operations
- [ ] Configure per-tenant quotas in database (different limits per subscription tier)
- [ ] **Test Command**: `for ($i=1; $i -le 200; $i++) { Invoke-WebRequest http://localhost:8001/api/v1/workflows }`
- [ ] **Success Criteria**: HTTP 429 with `Retry-After` header, tenant-specific limits enforced

### 3.2 Grafana Dashboards for Metrics
**Context7 Pattern**: Prometheus + Grafana provisioning for automated dashboard deployment

- [ ] Create `observability/grafana/dashboards/overview.json`:
  ```json
  {
    "dashboard": {
      "title": "SanskritiSetu Production Overview",
      "panels": [
        {
          "title": "Request Rate by Tenant",
          "targets": [{
            "expr": "rate(http_requests_total{tenant!=\"\"}[5m])"
          }]
        },
        {
          "title": "P95 Latency",
          "targets": [{
            "expr": "histogram_quantile(0.95, http_request_duration_seconds_bucket)"
          }]
        },
        {
          "title": "Database Pool Utilization",
          "targets": [{
            "expr": "db_pool_size - db_pool_checked_in"
          }]
        }
      ]
    }
  }
  ```
- [ ] Create `observability/grafana/provisioning/dashboards/dashboard.yml`:
  ```yaml
  apiVersion: 1
  providers:
    - name: 'SanskritiSetu'
      folder: 'Production'
      type: file
      options:
        path: /etc/grafana/dashboards
  ```
- [ ] Add Grafana service to docker-compose.prod.yml
- [ ] Import dashboard via provisioning (auto-load on startup)
- [ ] **Test Command**: Browse http://localhost:3000/dashboards
- [ ] **Success Criteria**: Overview dashboard auto-loaded with 6 panels

### 3.3 Distributed Tracing Dashboard
**Context7 Pattern**: Jaeger + OpenTelemetry service graph visualization

- [ ] Verify OpenTelemetry instrumentation from Phase 2.5
- [ ] Create `observability/jaeger/jaeger-query.yml` for custom UI config
- [ ] Configure service dependencies graph
- [ ] Set up trace retention (7 days for production)
- [ ] Add custom span attributes: `tenant_id`, `user_id`, `workflow_id`
- [ ] **Test Command**: Browse http://localhost:16686, search by tenant_id
- [ ] **Success Criteria**: Full request traces with DB queries, tenant context visible

### 3.4 Per-Tenant Resource Quotas
**Context7 Pattern**: FastAPI dependency injection for quota enforcement

- [ ] Add quota columns to `tenants` table:
  ```sql
  ALTER TABLE tenants ADD COLUMN max_agents INTEGER DEFAULT 10;
  ALTER TABLE tenants ADD COLUMN max_workflows_per_day INTEGER DEFAULT 100;
  ALTER TABLE tenants ADD COLUMN max_storage_mb INTEGER DEFAULT 1000;
  ```
- [ ] Create `src/core/middleware/quota_check.py`:
  ```python
  async def check_tenant_quota(
      resource: str,
      db: AsyncSession = Depends(get_db)
  ):
      tenant_id = get_current_tenant_id()
      tenant = await db.get(Tenant, tenant_id)

      current_usage = await get_usage(tenant_id, resource)
      quota = getattr(tenant, f"max_{resource}")

      if current_usage >= quota:
          raise HTTPException(
              status_code=429,
              detail=f"Quota exceeded for {resource}: {current_usage}/{quota}"
          )

  # On endpoint
  @router.post("/agents")
  async def create_agent(
      _: None = Depends(check_tenant_quota("agents"))
  ):
      ...
  ```
- [ ] Add Prometheus metrics for quota usage per tenant
- [ ] Configure alerts for tenants approaching limits (>90%)
- [ ] **Test Command**: Create agents until quota exceeded
- [ ] **Success Criteria**: HTTP 429 with quota details in response

### 3.5 Prometheus Alert Rules
**Context7 Pattern**: Prometheus alert manager with runbook links

- [ ] Create `observability/prometheus/alerts.yml`:
  ```yaml
  groups:
    - name: production_critical
      interval: 30s
      rules:
        - alert: HighErrorRate
          expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "High 5xx error rate"
            description: "{{ $value }}% of requests failing"
            runbook_url: "https://wiki.sanskritisetu.org/runbooks/high-error-rate"

        - alert: DatabasePoolExhaustion
          expr: (db_pool_size - db_pool_checked_in) / db_pool_size > 0.9
          for: 1m
          labels:
            severity: warning
          annotations:
            summary: "Database pool >90% utilized"

        - alert: TenantQuotaExceeded
          expr: tenant_quota_usage_ratio > 0.95
          for: 5m
          labels:
            severity: info
          annotations:
            summary: "Tenant {{ $labels.tenant_id }} near quota limit"
  ```
- [ ] Configure Alertmanager with Slack/email receivers
- [ ] Test alerts with `amtool alert add` (manual trigger)
- [ ] Document runbooks in wiki for each alert
- [ ] **Test Command**: `curl -X POST http://localhost:9093/api/v1/alerts`
- [ ] **Success Criteria**: Alert notification received in Slack within 2 minutes

### 3.6 Performance Baselines & SLOs
**Context7 Pattern**: Prometheus recording rules for SLI tracking

- [ ] Define SLOs (Service Level Objectives):
  ```yaml
  # observability/prometheus/recording_rules.yml
  groups:
    - name: slo_rules
      interval: 30s
      rules:
        - record: slo:http_request_duration_seconds:p95
          expr: histogram_quantile(0.95, http_request_duration_seconds_bucket)

        - record: slo:availability_ratio
          expr: sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

        - record: slo:error_budget_remaining
          expr: 1 - ((1 - slo:availability_ratio) / (1 - 0.999))  # 99.9% target
  ```
- [ ] Set performance targets:
  - P95 latency < 500ms for read operations
  - P95 latency < 2000ms for write operations
  - 99.9% availability (43 minutes downtime/month allowed)
- [ ] Create Grafana dashboard for SLO tracking with burn rate
- [ ] Configure alert if error budget depleted >50% in 1 hour
- [ ] **Test Command**: `curl http://localhost:9090/api/v1/query?query=slo:availability_ratio`
- [ ] **Success Criteria**: SLI metrics recorded every 30s, burn rate visible in Grafana

**Phase 3 Sign-Off**: _____________ (Platform Architect) Date: _______

---

## PHASE 4: KUBERNETES MIGRATION (FUTURE)

**Status**: 🔮 ROADMAP
**Target Release**: v2.0.0
**Blocker**: NO (future scalability when >100k requests/day)
**Context7 Sources**: Docker, Kubernetes best practices

### 4.1 Kubernetes Deployment Manifests
**Context7 Pattern**: K8s multi-container pods with health checks

- [ ] Create `k8s/backend-deployment.yml`:
  ```yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: sanskritisetu-backend
    labels:
      app: sanskritisetu
      component: backend
  spec:
    replicas: 3
    selector:
      matchLabels:
        app: sanskritisetu
        component: backend
    template:
      metadata:
        labels:
          app: sanskritisetu
          component: backend
      spec:
        securityContext:
          runAsUser: 10001
          runAsNonRoot: true
          fsGroup: 10001

        containers:
        - name: backend
          image: sanskritisetu/backend:latest

          # Security
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]

          # Probes (three-tier health checks)
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10

          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5

          # Resources
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi

          # Volumes for read-only filesystem
          volumeMounts:
          - name: tmp
            mountPath: /tmp
          - name: cache
            mountPath: /app/.cache

        volumes:
        - name: tmp
          emptyDir: {}
        - name: cache
          emptyDir: {}
  ```
- [ ] Create `k8s/backend-service.yml` (ClusterIP + LoadBalancer)
- [ ] Create `k8s/configmap.yml` for environment config
- [ ] Create `k8s/secrets.yml` from sealed secrets (NOT plain text!)
- [ ] **Test Command**: `kubectl apply -k k8s/`
- [ ] **Success Criteria**: 3 pods running, probes passing

### 4.2 Horizontal Pod Autoscaler (HPA)
**Context7 Pattern**: K8s HPA with custom Prometheus metrics

- [ ] Create `k8s/hpa.yml`:
  ```yaml
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: sanskritisetu-backend-hpa
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: sanskritisetu-backend
    minReplicas: 3
    maxReplicas: 20
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70

    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80

    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "100"

    behavior:
      scaleDown:
        stabilizationWindowSeconds: 300
        policies:
        - type: Percent
          value: 50
          periodSeconds: 60
      scaleUp:
        stabilizationWindowSeconds: 60
        policies:
        - type: Percent
          value: 100
          periodSeconds: 30
  ```
- [ ] Install Prometheus Adapter for custom metrics
- [ ] Configure metrics server for resource metrics
- [ ] Test scaling: `kubectl run -it --rm load-generator --image=busybox`
- [ ] **Test Command**: `kubectl get hpa -w` (watch scaling)
- [ ] **Success Criteria**: Auto-scales from 3→20 pods under load, scales down gracefully

### 4.3 Blue-Green Deployment Strategy
**Context7 Pattern**: K8s zero-downtime deployment with traffic shifting

- [ ] Create `k8s/backend-blue.yml` and `k8s/backend-green.yml` (separate deployments)
- [ ] Use label selectors for traffic routing:
  ```yaml
  # Service routes to active deployment
  apiVersion: v1
  kind: Service
  metadata:
    name: sanskritisetu-backend
  spec:
    selector:
      app: sanskritisetu
      component: backend
      version: blue  # Switch to 'green' for cutover
  ```
- [ ] Create `scripts/deploy_blue_green.sh`:
  ```bash
  #!/bin/bash
  CURRENT=$(kubectl get svc sanskritisetu-backend -o jsonpath='{.spec.selector.version}')
  NEW=$([[ $CURRENT == "blue" ]] && echo "green" || echo "blue")

  echo "Deploying to $NEW environment..."
  kubectl apply -f k8s/backend-$NEW.yml
  kubectl wait --for=condition=available deployment/sanskritisetu-backend-$NEW

  echo "Running smoke tests..."
  ./scripts/smoke_test.sh http://backend-$NEW-service:8000

  echo "Switching traffic to $NEW..."
  kubectl patch svc sanskritisetu-backend -p "{\"spec\":{\"selector\":{\"version\":\"$NEW\"}}}"

  echo "Keeping $CURRENT as rollback target for 10 minutes..."
  sleep 600
  kubectl delete deployment sanskritisetu-backend-$CURRENT
  ```
- [ ] Document rollback procedure: switch service selector back to previous version
- [ ] **Test Command**: `./scripts/deploy_blue_green.sh`
- [ ] **Success Criteria**: Zero downtime deployment, <1s traffic shift

### 4.4 Service Mesh Integration (Istio/Linkerd)
**Context7 Pattern**: mTLS, circuit breaking, retry policies

- [ ] Install Istio service mesh: `istioctl install --set profile=production`
- [ ] Enable sidecar injection: `kubectl label namespace default istio-injection=enabled`
- [ ] Create `k8s/virtualservice.yml` for traffic management:
  ```yaml
  apiVersion: networking.istio.io/v1beta1
  kind: VirtualService
  metadata:
    name: sanskritisetu-backend
  spec:
    hosts:
    - sanskritisetu-backend
    http:
    - match:
      - headers:
          tenant-id:
            exact: "premium-tenant"
      route:
      - destination:
          host: sanskritisetu-backend
          subset: high-priority
        weight: 100
      timeout: 30s
      retries:
        attempts: 3
        perTryTimeout: 10s

    - route:  # Default route
      - destination:
          host: sanskritisetu-backend
          subset: standard
        weight: 100
  ```
- [ ] Create `k8s/destinationrule.yml` for circuit breaking:
  ```yaml
  apiVersion: networking.istio.io/v1beta1
  kind: DestinationRule
  metadata:
    name: sanskritisetu-backend
  spec:
    host: sanskritisetu-backend
    trafficPolicy:
      connectionPool:
        tcp:
          maxConnections: 100
        http:
          http1MaxPendingRequests: 50
          http2MaxRequests: 100
      outlierDetection:
        consecutiveErrors: 5
        interval: 30s
        baseEjectionTime: 60s
        maxEjectionPercent: 50
    subsets:
    - name: high-priority
      labels:
        tier: premium
    - name: standard
      labels:
        tier: standard
  ```
- [ ] Enable mTLS for all inter-service communication
- [ ] Configure distributed tracing via Istio telemetry
- [ ] **Test Command**: `istioctl analyze` (validate configs)
- [ ] **Success Criteria**: mTLS enforced, circuit breaker triggers at 5 errors/30s

**Phase 4 Sign-Off**: _____________ (Cloud Architect) Date: _______
- [ ] Test traffic switching
- [ ] Zero-downtime verified
- [ ] **Test Command**: Deploy new version
- [ ] **Success Criteria**: No dropped requests

### 4.4 Service Mesh (Optional)
- [ ] Evaluate Istio/Linkerd
- [ ] Implement if beneficial
- [ ] Configure mTLS
- [ ] Set up traffic policies
- [ ] **Deliverable**: Service mesh decision doc

---

## TESTING MATRIX

### Environments

| Environment | Purpose | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|-------------|---------|---------|---------|---------|---------|
| Local Dev | Development | ✅ | ⚠️ | ❌ | ❌ |
| Staging | Integration | ✅ | ✅ | ✅ | ❌ |
| Production | Live traffic | ✅ | ✅ | ✅ | ✅ |

### Test Types

- [ ] **Unit Tests**: 80%+ coverage (existing)
- [ ] **Integration Tests**: All endpoints with DB
- [ ] **Smoke Tests**: Critical path validation
- [ ] **Load Tests**: 1000 req/s sustained
- [ ] **Chaos Tests**: Network failures, DB restarts
- [ ] **Security Tests**: OWASP Top 10 scans

---

## DEPLOYMENT CHECKLIST (Pre-Release)

**Run this before EVERY production deployment:**

```powershell
# 1. Verify Phase 1 is 100% complete
Get-Content docs/prod-readiness.md | Select-String "Phase 1" -Context 20

# 2. Run full test suite
python -m pytest tests/ --cov=src --cov-fail-under=80

# 3. Build production image
docker build --target production --tag sanskritisetu_backend_prod:v1.0.0 .

# 4. Tag with release version
docker tag sanskritisetu_backend_prod:v1.0.0 sanskritisetu_backend_prod:latest

# 5. Deploy to staging first
docker-compose -f docker-compose.prod.yml up -d

# 6. Run smoke tests
./scripts/smoke_test.sh staging

# 7. Monitor for 30 minutes
# - Check logs for errors
# - Verify metrics baseline
# - Test all critical endpoints

# 8. If staging OK, deploy to production
./scripts/deploy_prod.sh v1.0.0

# 9. Post-deployment validation
./scripts/smoke_test.sh prod

# 10. Monitor for 2 hours
# - Watch error rates
# - Check response times
# - Verify tenant isolation
```

---

## ROLLBACK PROCEDURE

**If any Phase 1 test fails after deployment:**

```powershell
# 1. Stop new deployment
docker-compose -f docker-compose.prod.yml down

# 2. Restore previous version
docker-compose -f docker-compose.prod.yml up -d sanskritisetu_backend_prod:v0.9.0

# 3. Verify rollback success
./scripts/smoke_test.sh prod

# 4. Document incident
# - What failed
# - Why it wasn't caught in staging
# - Preventive measures

# 5. Fix forward
# - Create hotfix branch
# - Fix issue
# - Re-run Phase 1 checklist
```

---

## VERSION HISTORY

| Version | Date | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Notes |
|---------|------|---------|---------|---------|---------|-------|
| v0.9.0 | 2026-01-13 | 0% | 0% | 0% | 0% | Initial dev image |
| v1.0.0 | TBD | - | - | - | - | First prod-ready release |

---

## RELEASE APPROVAL SIGNATURES

**Phase 1 Complete** (Required for ANY production):
- [ ] Tech Lead: _________________ Date: _______
- [ ] Security: _________________ Date: _______

**Phase 2 Complete** (Required for paying customers):
- [ ] SRE Lead: _________________ Date: _______
- [ ] Product: _________________ Date: _______

**Phase 3 Complete** (Recommended for enterprise):
- [ ] Platform Architect: _________________ Date: _______
- [ ] CTO: _________________ Date: _______

---

**Document Owner**: Platform Team
**Review Frequency**: Before each major release
**Next Review**: Before v1.0.0 deployment
