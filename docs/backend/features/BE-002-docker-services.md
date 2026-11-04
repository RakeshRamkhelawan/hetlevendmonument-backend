# Backend Feature Specification

## Metadata

- Feature ID: BE-002
- Feature naam: Docker Services Stack & Infrastructure
- Status: ACTIEF
- Auteur: Rakesh Ramkhelawan
- Reviewer: —
- Datum: 2026-05-25
- Gerelateerde user story / ticket: ADR-009 (Traefik), ADR-006 (Redis/Dramatiq), ADR-010 (Gunicorn+Uvicorn)
- Gerelateerde router / module: docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml
- Gerelateerde frontend endpoints: alle
- Gerelateerde database tabellen: alle
- Versie: 1.0

---

## Doel en scope

### Doel

De Docker Services Stack definieert de volledige containerinfrastructuur van SanskritiSetu. De stack bestaat
uit 16 services verdeeld over vijf lagen: infrastructuur (postgres, redis, ollama), applicatie (backend,
frontend, sync-server, workflow-worker, focusbuilder), edge gateway (traefik), automatisering (activepieces),
workers (learning-worker) en observability (prometheus, grafana, jaeger, redis-exporter, postgres-exporter).

De stack wordt via Docker Compose samengesteld uit een basisbestand en omgevingsspecifieke overrides. De
productieomgeving draait op Azure Container Apps; lokale ontwikkeling en CI gebruiken dezelfde Compose-bestanden
met afwijkende overrides.

### In scope

- Volledige documentatie van alle 16 services: image, ports, volumes, environment variabelen, healthchecks,
  netwerkconfiguratie, Traefik-labels en opstartafhankelijkheden
- Alle Docker Compose varianten (base, dev, prod, ci, test, integration-test, e2e, quickstart, secrets, test-db)
- Traefik routingregels en TLS-configuratie (traefik/traefik.yml)
- Volume- en netwerkinventaris
- Startup dependency chain en failure scenarios per service
- Integratorhandleiding voor het starten en beheren van de stack

### Out of scope

- focusbuilder productie-implementatie (placeholder, ADR-gereserveerd, niet gedeployed op Azure)
- Azure Container Apps YAML-configuratie (aparte infra-laag)
- Kubernetes manifesten (k8s/ directory, post-MVP)
- Interne applicatielogica van de services zelf

---

## Build summary

De stack is operationeel en actief in gebruik. Alle services zijn geconfigureerd in docker-compose.yml
(basis). Omgevingsspecifieke overrides overschrijven alleen de afwijkende velden (image targets, ports,
env-waarden, restart policies). De Traefik-configuratie in traefik/traefik.yml is statisch en wordt
read-only gemount. TLS-certificaten worden via LetsEncrypt ACME opgeslagen in het traefik_certs volume.

Dramatiq-workers (workflow-worker, learning-worker) gebruiken Redis database 1 als broker en Redis
database 0 voor applicatiedata. De observability-stack (prometheus, grafana, jaeger) is volledig
geconfigureerd voor productie-monitoring met OpenTelemetry OTLP-ingest via jaeger op poort 4317.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|---|---|---|---|---|---|
| BE-CFG-001 | postgres service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-001 |
| BE-CFG-002 | redis service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-001 |
| BE-CFG-003 | ollama service | BE-CFG | docker-compose.yml | Bestaand | — |
| BE-CFG-004 | backend service | BE-CFG | docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml | Bestaand | BE-FLW-001, BE-FLW-002 |
| BE-CFG-005 | sync-server service | BE-CFG | docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml | Bestaand | BE-FLW-001 |
| BE-CFG-006 | frontend service | BE-CFG | docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml | Bestaand | BE-FLW-002 |
| BE-CFG-007 | workflow-worker service | BE-CFG | docker-compose.yml, docker-compose.prod.yml | Bestaand | BE-FLW-001 |
| BE-CFG-008 | focusbuilder service | BE-CFG | docker-compose.yml | Bestaand | — |
| BE-CFG-009 | traefik service | BE-CFG | docker-compose.yml, traefik/traefik.yml | Bestaand | BE-FLW-002 |
| BE-CFG-010 | activepieces service | BE-CFG | docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml | Bestaand | BE-FLW-002 |
| BE-CFG-011 | learning-worker service | BE-CFG | docker-compose.yml, docker-compose.prod.yml, docker-compose.dev.yml | Bestaand | BE-FLW-001 |
| BE-CFG-012 | prometheus service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-003 |
| BE-CFG-013 | grafana service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-003 |
| BE-CFG-014 | jaeger service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-003 |
| BE-CFG-015 | redis-exporter service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-003 |
| BE-CFG-016 | postgres-exporter service | BE-CFG | docker-compose.yml | Bestaand | BE-FLW-003 |
| BE-CFG-017 | Traefik statische config | BE-CFG | traefik/traefik.yml | Bestaand | BE-FLW-002 |
| BE-CFG-018 | docker-compose.dev.yml | BE-CFG | docker-compose.dev.yml | Bestaand | — |
| BE-CFG-019 | docker-compose.prod.yml | BE-CFG | docker-compose.prod.yml | Bestaand | — |
| BE-CFG-020 | docker-compose.ci.yml | BE-CFG | docker-compose.ci.yml | Bestaand | — |
| BE-CFG-021 | docker-compose.test.yml | BE-CFG | docker-compose.test.yml | Bestaand | — |
| BE-CFG-022 | docker-compose.integration-test.yml | BE-CFG | docker-compose.integration-test.yml | Bestaand | — |
| BE-CFG-023 | docker-compose.e2e.yml | BE-CFG | docker-compose.e2e.yml | Bestaand | — |
| BE-CFG-024 | docker-compose.quickstart.yml | BE-CFG | docker-compose.quickstart.yml | Bestaand | — |
| BE-CFG-025 | docker-compose.secrets.yml | BE-CFG | docker-compose.secrets.yml | Bestaand | — |
| BE-CFG-026 | docker-compose.test-db.yml | BE-CFG | docker-compose.test-db.yml | Bestaand | — |

---

## API-flows

### Flow ID: BE-FLW-001

- **Naam:** Service Startup Dependencies Chain
- **Trigger:** docker compose up
- **Beschrijving:** Services starten in volgorde op basis van depends_on + condition: service_healthy.
  postgres en redis starten als eerste en moeten healthy zijn voordat downstream services opstarten.
  backend wacht op postgres EN redis healthy. sync-server en de workers wachten op backend healthy.
  frontend wacht op backend healthy en sync-server started.

**Opstartsequentie (verplichte volgorde):**

```
Tier 1 (parallel): postgres, redis, traefik
         |
         | (postgres healthy + redis healthy)
         v
Tier 2: backend
         |
         | (backend healthy)
         v
Tier 3 (parallel): sync-server, workflow-worker, learning-worker, focusbuilder, activepieces
         |
         | (sync-server started)
         v
Tier 4: frontend
         |
         | (observability, onafhankelijk van tiers 1-4)
         v
Tier 5 (parallel): prometheus, grafana, jaeger, redis-exporter, postgres-exporter
```

**Healthcheck-tijdlijn (worst case):**

| Service | start_period | interval | retries | Max wachttijd |
|---|---|---|---|---|
| postgres | 10s | 10s | 5 | 60s |
| redis | 5s | 10s | 5 | 55s |
| backend | 180s | 30s | 5 | 330s |
| sync-server | 30s | 10s | 5 | 80s |
| learning-worker | 10s | 30s | 3 | 100s |
| traefik | 10s | 30s | 3 | 100s |

---

### Flow ID: BE-FLW-002

- **Naam:** Traefik TLS Routing Flow
- **Trigger:** Inkomend HTTP- of HTTPS-verzoek
- **Beschrijving:** Traefik fungeert als edge gateway en routeert inkomende verzoeken naar de juiste
  backend-service op basis van padregels. In productie wordt HTTP automatisch omgeleid naar HTTPS
  via een permanente redirect (301). TLS-terminatie vindt plaats op Traefik-niveau; interne
  container-to-container communicatie is niet versleuteld.

**Routeringstabel:**

| Pad | Doel | Poort | Middleware |
|---|---|---|---|
| /api/* | backend:8000 | 8000 | security-headers |
| /automation* | activepieces:80 | 80 | security-headers, ap-strip (StripPrefix /automation) |
| / (catch-all) | frontend:3000 | 3000 | security-headers |

**Security headers (alle routes):**

| Header | Waarde |
|---|---|
| X-Frame-Options | DENY (frameDeny=true) |
| X-Content-Type-Options | nosniff |
| Referrer-Policy | same-origin |
| Strict-Transport-Security | max-age=31536000; includeSubDomains |

**TLS:**
- Minimale versie: TLS 1.3 (options: tls13only in traefik.yml)
- Certificaten: LetsEncrypt ACME, httpChallenge via entrypoint web
- Opslag: volume traefik_certs -> /letsencrypt/acme.json

**Productie-specifiek (docker-compose.prod.yml):**
- HTTP naar HTTPS permanente redirect actief via CLI flag --entrypoints.web.http.redirections
- Dashboard beveiligd: --api.insecure=false

**Development-specifiek (docker-compose.dev.yml):**
- Geen TLS-redirect
- Traefik log level: DEBUG
- Dashboard toegankelijk zonder auth (insecure=true in traefik.yml)

---

### Flow ID: BE-FLW-003

- **Naam:** Observability Metrics Flow
- **Trigger:** Continu (scrape interval Prometheus)
- **Beschrijving:** Prometheus scrapt metrics van alle services. Grafana visualiseert de metrics via
  dashboards. Jaeger ontvangt distributed traces via OTLP gRPC. Exporters vertalen service-specifieke
  metrics naar Prometheus-formaat.

**Metrics-bronnen:**

| Bron | Exporter | Prometheus-poort | Wat wordt gemeten |
|---|---|---|---|
| Redis | redis-exporter:9121 | 9121 | verbindingen, geheugen, hit rate, commands/sec |
| PostgreSQL | postgres-exporter:9187 | 9187 | queries, locks, replica lag, tabelgrootte |
| Traefik | ingebouwd (poort 8080) | 8080 | requests/s, latency, TLS handshakes, router stats |
| Backend | /metrics endpoint | 8000 | API latency, agent calls, HITL queue, token gebruik |

**Trace-flow:**

```
Backend (OpenTelemetry SDK)
    --> OTLP gRPC --> jaeger:4317
    --> Jaeger UI (poort 16686)
```

---

## Detaildocumentatie per service

---

### Service 1: postgres

**Doel:** Primaire relationele database met pgvector-extensie voor vector embeddings. Bewaart alle
applicatiedata: tenants, gebruikers, agents, taken, audit logs, council-beslissingen, consent-records.

**Image:** ankane/pgvector:v0.5.1
- Basis: PostgreSQL 15 met pgvector-extensie voorgeinstalleerd
- Kritiek: standaard postgres:15 image mist pgvector; gebruik altijd dit image

**Container naam:** sanskritisetu_postgres

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 5435 | 5432 | 127.0.0.1 (niet publiek) |

**Volumes:**

| Volume | Mount in container | Inhoud |
|---|---|---|
| postgres_data | /var/lib/postgresql/data | Persistente databasedata |
| ./scripts/init-databases.sql | /docker-entrypoint-initdb.d/99-init-databases.sql (ro) | Initscript bij eerste start |

**Environment variabelen:**

| Variabele | Default | Verplicht |
|---|---|---|
| POSTGRES_USER | postgres | Ja |
| POSTGRES_PASSWORD | postgres | Ja (WIJZIG IN PRODUCTIE) |
| POSTGRES_DB | sanskritisetu | Ja |

**Healthcheck:**

```
test:         pg_isready -U postgres
interval:     10s
timeout:      5s
retries:      5
start_period: 10s
```

**Netwerk:** sanskritisetu_network (bridge)

**Afhankelijkheden:** geen

**Traefik-labels:** geen (interne service)

**Start conditie voor downstream:** condition: service_healthy

**Wat gaat er mis bij failure:**
- backend kan niet starten (depends_on condition: service_healthy)
- workflow-worker, learning-worker, activepieces kunnen niet starten
- Migrations worden niet uitgevoerd -> applicatie start zonder schema -> 500-fouten op alle API-calls
- Dataverlies als postgres_data volume ontbreekt of corrupt is

**Productie-override:** geen (base config is productiegeschikt)

**Development-override:** geen (base config gebruikt ook voor development)

**CI-override (docker-compose.ci.yml):**
- Aparte service: postgres-ci op poort 5433, image postgres:16 (zonder pgvector), voor CI-snelheid
- Let op: postgres:16 ondersteunt geen vector-queries. Integratietests vereisen het pgvector-image.

---

### Service 2: redis

**Doel:** Message broker voor Dramatiq-taken (database 1), applicatiecache en session state (database 0),
pub/sub voor WebSocket-pushes (ws:user:{id} kanaal), digest queues en rate-limiting counters.

**Image:** redis:7-alpine

**Container naam:** sanskritisetu_redis

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 6385 | 6379 | 127.0.0.1 (niet publiek) |

**Command:**
```
redis-server
  --requirepass ${REDIS_PASSWORD:-changeme_in_production}
  --appendonly yes
```

requirepass: authenticatie verplicht. Default changeme_in_production moet worden overschreven.
appendonly yes: AOF-persistentie. Alle writes worden gelogd voor durability na herstart.

**Volumes:**

| Volume | Mount in container | Inhoud |
|---|---|---|
| redis_data | /data | AOF-log en RDB-snapshot |

**Environment variabelen:** geen (wachtwoord wordt via command meegegeven)

**Healthcheck:**

```
test:         redis-cli ping
interval:     10s
timeout:      3s
retries:      5
start_period: 5s
```

**Netwerk:** sanskritisetu_network

**Afhankelijkheden:** geen

**Traefik-labels:** geen

**Start conditie voor downstream:** condition: service_healthy

**Redis database indeling:**

| Database | Gebruik |
|---|---|
| /0 | Applicatiecache, sessions, rate-limiting, pub/sub, digest queues |
| /1 | Dramatiq message broker (workflow-worker, learning-worker) |

**Verbindingsstrings (intern):**
- Applicatie: redis://:${REDIS_PASSWORD}@redis:6379/0
- Dramatiq: redis://:${REDIS_PASSWORD}@redis:6379/1
- redis-exporter: redis://redis:6379 + REDIS_PASSWORD env var

**Wat gaat er mis bij failure:**
- backend verliest cache; alle requests gaan rechtstreeks naar database (prestatiedegradatie)
- Dramatiq-workers verliezen broker-verbinding; taken worden niet meer verwerkt
- WebSocket pub/sub valt weg; realtime notificaties werken niet
- Rate-limiters vallen terug op in-memory limiter of falen open (afhankelijk van implementatie)

**Bekende valkuil:** De integratietest-conftest gebruikte hardcoded poort 6381. Dit is gecorrigeerd naar
os.environ.setdefault("REDIS_URL", "redis://localhost:6379"). Zie CLAUDE.md bekende valkuilen.

---

### Service 3: ollama

**Doel:** Lokale LLM-inferentie en embedding-generatie voor het semantic routing systeem. Draait het
nomic-embed-text model voor vector embeddings. Optionele service — in development gebruikt de backend
Ollama via host.docker.internal (lokale installatie op de host), niet via deze container.

**Image:** ollama/ollama:0.3.13

**Container naam:** sanskritisetu_ollama

**Profiles:** ["ollama"] — start NIET automatisch. Vereist --profile ollama bij docker compose up.

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 11434 | 11434 | 127.0.0.1 (niet publiek) |

**Volumes:**

| Volume | Mount in container | Inhoud |
|---|---|---|
| ollama_data | /root/.ollama | Gedownloade modellen |

**Environment variabelen:**

| Variabele | Waarde | Doel |
|---|---|---|
| OLLAMA_HOST | 0.0.0.0 | Luistert op alle interfaces binnen de container |

**Entrypoint (model preload):**
```sh
sh -c "ollama serve &
       sleep 10 &&
       ollama pull nomic-embed-text &&
       wait"
```
Model wordt automatisch gedownload bij eerste start. Download vereist internettoegang.

**Resource limieten:**

| Resource | Limiet | Reservering |
|---|---|---|
| Geheugen | 4G | 2G |

**Healthcheck:**

```
test:         curl -f http://localhost:11434/api/tags
interval:     30s
timeout:      10s
retries:      5
start_period: 60s
```

start_period van 60s is nodig omdat model-download bij eerste start meerdere minuten kan duren.

**Netwerk:** sanskritisetu_network

**Afhankelijkheden:** geen

**Backend-integratie:** OLLAMA_BASE_URL=http://host.docker.internal:11434 (dev) of
OLLAMA_BASE_URL=http://ollama:11434 (wanneer --profile ollama actief is)

**Wat gaat er mis bij failure:**
- Embedding-calls falen (met foutmelding, geen silent failure)
- Semantic routing valt terug op keyword-matching (Tier 3 in AgentRouterAgent)
- LLM-routing (Tier 4) valt terug op heuristic fallback (Tier 5)
- Applicatie blijft functioneel; alleen embedding-kwaliteit vermindert

---

### Service 4: backend

**Doel:** Centrale FastAPI-applicatie. Serveert de REST API (/api/v1/*) en WebSocket endpoints.
Voert Alembic-migraties uit bij start. Draait onder Gunicorn met Uvicorn-workers (ADR-010).

**Image:** sanskritisetu/backend:latest (productie) / gebouwd via Dockerfile target (dev/prod)

**Container naam:** sanskritisetu_backend

**Dockerfile targets:**

| Target | Override-bestand | Gebruik |
|---|---|---|
| development | docker-compose.dev.yml | Lokale ontwikkeling met hot-reload en debugpy |
| production-api | docker-compose.prod.yml | Productie: Gunicorn + Uvicorn workers |

**Poorten:**

| Host | Container | Bindadres | Gebruik |
|---|---|---|---|
| 5678 | 5678 | 127.0.0.1 | debugpy (alleen dev) |
| 8111 | 8000 | 127.0.0.1 | Directe toegang buiten Traefik (base) |
| 8110 | 8000 | 127.0.0.1 | Directe toegang buiten Traefik (prod-override) |

Poort 8111 is de base-configuratie; docker-compose.prod.yml overschrijft dit naar 8110.

**Volumes (alleen development):**

| Host-pad | Container-pad | Doel |
|---|---|---|
| ./src | /app/src | Hot-reload source code |
| ./scripts | /app/scripts | Scripts beschikbaar in container |

**Environment variabelen (base):**

| Variabele | Vereist | Beschrijving |
|---|---|---|
| DATABASE_URL | Ja | PostgreSQL asyncpg connection string |
| REDIS_URL | Ja | Redis voor applicatiecache (db 0) |
| DRAMATIQ_BROKER_URL | Ja | Redis voor Dramatiq broker (db 1) |
| ENVIRONMENT | Ja | development / production |
| LOG_LEVEL | Nee | Default: INFO |
| API_PORT | Nee | Default: 8000 |
| ALLOWED_ORIGINS | Ja | CORS whitelist |
| DEFAULT_ADMIN_PASSWORD | Ja | Initieel admin-account wachtwoord |

**Environment variabelen (development extra):**

| Variabele | Waarde | Beschrijving |
|---|---|---|
| DEBUG | true | Schakel debug-mode in |
| OLLAMA_BASE_URL | http://host.docker.internal:11434 | Host-Ollama via Docker bridge |
| LLM_PROVIDER | moonshot (default) | Actieve LLM-provider |
| LLM_MODEL | moonshot-v1-8k | Actief model |
| LLM_API_KEY | ${MOONSHOT_API_KEY} | API-sleutel |
| LLM_TIMEOUT | 45 | Timeout in seconden |
| DEEPSEEK_API_KEY | ${DEEPSEEK_API_KEY} | Fallback LLM |
| GOOGLE_API_KEY | ${GOOGLE_API_KEY} | Google Gemini provider |
| WATCHFILES_FORCE_POLLING | true | Windows-compatibele hot-reload |
| PYTHONDONTWRITEBYTECODE | 1 | Geen .pyc-bestanden in volume |

**Healthcheck:**

```
test:         curl -f http://localhost:8000/health
interval:     30s
timeout:      10s
retries:      5
start_period: 180s (base) / 120s (prod-override)
```

start_period van 180s in base geeft ruimte voor Alembic-migraties bij cold start.

**Afhankelijkheden:**
- postgres (condition: service_healthy)
- redis (condition: service_healthy)

**Traefik-labels:**

| Label | Waarde |
|---|---|
| traefik.enable | true |
| traefik.http.routers.backend.rule | PathPrefix("/api/") |
| traefik.http.routers.backend.entrypoints | web,websecure |
| traefik.http.routers.backend.tls | true |
| traefik.http.routers.backend.tls.certresolver | letsencrypt |
| traefik.http.services.backend-svc.loadbalancer.server.port | 8000 |
| traefik.http.routers.backend.middlewares | security-headers |

Security headers worden via de backend-service gedefinieerd en zijn daarmee beschikbaar voor alle routes.

**Restart policy:** always (productie), geen (development)

**Wat gaat er mis bij failure:**
- Alle API-calls retourneren 502 Bad Gateway via Traefik
- WebSocket-verbindingen worden verbroken
- sync-server, workflow-worker, learning-worker, frontend en focusbuilder kunnen niet (opnieuw) starten
- Traefik blijft luisteren maar stuurt verkeer naar een onbeschikbare upstream

---

### Service 5: sync-server

**Doel:** YJS Hocuspocus document-synchronisatieserver. Verzorgt real-time collaborative editing via
WebSocket. Frontend verbindt via ws://localhost:1234 (dev) of via Traefik (productie).

**Build:** ./services/sync-server (Dockerfile in sync-server directory)

**Container naam:** sanskritisetu_sync_server

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 1234 | 1234 | 127.0.0.1 |

**Environment variabelen:**

| Variabele | Default | Beschrijving |
|---|---|---|
| PORT | 1234 | Luisterpoort |
| BACKEND_URL | http://backend:8110 (base) / http://backend:8000 (prod) | Backend voor webhook-validatie |
| SYNC_WEBHOOK_SECRET | change-me-in-production | Webhook HMAC-secret |
| NODE_ENV | production (prod) | Node.js mode |

**Healthcheck:**

```
test:         nc -z 127.0.0.1 1234
interval:     10s
timeout:      5s
retries:      5
start_period: 30s (base) / 60s (prod)
```

In development (docker-compose.dev.yml) is healthcheck uitgeschakeld (disable: true).

**Afhankelijkheden:**
- backend (condition: service_healthy) in base en productie
- backend (geen conditie, alleen started) in development

**Traefik-labels:** geen in base. WebSocket-verbindingen gaan via directe poort-binding (1234).

**Restart policy:** always (productie)

**Wat gaat er mis bij failure:**
- Real-time collaborative editing valt weg
- Frontend-hook useFocusBuilderWS detecteert verbindingsbreuk en probeert te reconnecten (mountedRef-guard)
- Applicatie blijft functioneel voor niet-collaborative functies

---

### Service 6: frontend

**Doel:** React SPA geserveerd als statische bestanden. In productie gebouwd met Vite naar een
Nginx-container (target: production). In development draait de Vite dev-server met HMR.

**Image:** sanskritisetu/frontend:latest (productie) / gebouwd via Dockerfile target

**Container naam:** sanskritisetu_frontend

**Dockerfile targets:**

| Target | Override-bestand | Gebruik |
|---|---|---|
| development | docker-compose.dev.yml | Vite dev-server, HMR, poort 5173 |
| production | docker-compose.prod.yml | Vite build -> Nginx statisch, poort 80 |

**Poorten:**

| Omgeving | Host | Container | Bindadres |
|---|---|---|---|
| Development | 5173 | 5173 | 127.0.0.1 |
| Productie | geen directe binding | 80 (intern) | alleen via Traefik |

**Build-argumenten (productie):**

| Arg | Waarde |
|---|---|
| VITE_ENVIRONMENT | production |
| VITE_API_URL | https://api.sanskritisetu.org |
| VITE_AUTH_URL | https://api.sanskritisetu.org |

**Environment variabelen (development):**

| Variabele | Waarde |
|---|---|
| VITE_ENVIRONMENT | development |
| VITE_API_URL | /api/v1 |
| VITE_AUTH_URL | /api/v1 |
| VITE_SYNC_URL | ws://localhost:1234 |
| WATCHPACK_POLLING | true (Windows HMR) |
| CHOKIDAR_USEPOLLING | true |
| CHOKIDAR_INTERVAL | 300 |

**Volumes (development):**

| Host-pad | Container-pad |
|---|---|
| ./frontend/src | /app/src |
| ./frontend/public | /app/public |

**Afhankelijkheden:**
- backend (condition: service_healthy)
- sync-server (condition: service_started)

**Traefik-labels (productie):**

| Label | Waarde |
|---|---|
| traefik.enable | true |
| traefik.http.routers.frontend.rule | PathPrefix("/") -- catch-all, laagste prioriteit |
| traefik.http.routers.frontend.entrypoints | web,websecure |
| traefik.http.routers.frontend.tls | true |
| traefik.http.services.frontend-svc.loadbalancer.server.port | 3000 (base) / 80 (prod) |
| traefik.http.routers.frontend.middlewares | security-headers |

**Traefik routerprioriteit:** PathPrefix("/api/") matcht voor /api/*. PathPrefix("/automation") matcht
voor /automation*. PathPrefix("/") is de catch-all en wordt alleen geraakt als geen andere router matcht.

**Restart policy:** always (productie)

**Wat gaat er mis bij failure:**
- Gebruikers zien een 502 Bad Gateway via Traefik
- Backend API blijft bereikbaar voor directe API-clients (curl, apps)

---

### Service 7: workflow-worker

**Doel:** Dramatiq-worker voor de ProductionWorkflowEngine. Verwerkt asynchrone workflow-taken uit
de Redis-broker. Draait 2 processen met elk 4 threads (8 gelijktijdige taken).

**Dockerfile target:** production-worker

**Container naam:** sanskritisetu_workflow_worker

**Command:**
```
dramatiq src.workers.workflow_worker src.workers.actors --processes 2 --threads 4
```

**Environment variabelen:**

| Variabele | Waarde | Beschrijving |
|---|---|---|
| DATABASE_URL | ${DATABASE_URL} | PostgreSQL connection string |
| REDIS_URL | redis://:${REDIS_PASSWORD}@redis:6379/0 | Applicatiecache |
| DRAMATIQ_BROKER_URL | redis://:${REDIS_PASSWORD}@redis:6379/1 | Dramatiq broker |
| ENVIRONMENT | development (base) / production (prod) | Runtime mode |
| PYTHONUNBUFFERED | 1 | Direct stdout/stderr |

**Resource limieten (productie):**

| Resource | Limiet | Reservering |
|---|---|---|
| Geheugen | 1G | 512M |

**Afhankelijkheden:**
- postgres (condition: service_healthy)
- redis (condition: service_healthy)
- backend (condition: service_healthy)

**Healthcheck:** geen geconfigureerd in base. Gebruik pgrep -f dramatiq als healthcheck nodig is.

**Restart policy:** always (productie)

**Netwerk:** sanskritisetu_network

**Wat gaat er mis bij failure:**
- Asynchrone workflow-taken worden niet verwerkt; stapelen op in de Redis-broker (db 1)
- Taken blijven in de queue totdat de worker herstart
- Geen directe gebruikersimpact (async), maar SLA's voor workflow-afhandeling worden niet gehaald
- Backpressure ontstaat als de queue overloopt (Redis geheugendruk)

---

### Service 8: focusbuilder

**Doel:** Placeholder voor een toekomstige FocusBuilder-microservice. Houdt de container-slot actief
zodat downstream depends_on verwijzingen niet falen. Voert geen applicatielogica uit.

**Image:** alpine:3.20

**Container naam:** sanskritisetu_focusbuilder

**Command:** tail -f /dev/null (blokkeert eeuwig, doet niets)

**Poorten:** geen

**Volumes:** geen

**Afhankelijkheden:**
- postgres (condition: service_healthy)
- redis (condition: service_healthy)
- backend (condition: service_healthy)

**Traefik-labels:** geen

**Azure-deployment:** NIET gedeployed. Deze service heeft geen Container App in de CD-pipeline.

**Wanneer te vervangen:** Als de FocusBuilder-module beschikbaar is, vervang image + command door de
echte implementatie. Voeg een healthcheck toe. Registreer de Container App in de Azure CD-configuratie.

---

### Service 9: traefik

**Doel:** Edge gateway en reverse proxy (ADR-009). Verzorgt TLS-terminatie, HTTP->HTTPS-redirect
(productie), routering naar upstream services op basis van padregels, en security-headers-injectie.
Exposeert ook een Prometheus-metrics-endpoint op poort 8080.

**Image:** traefik:v3.1

**Container naam:** sanskritisetu_traefik

**Poorten:**

| Host | Container | Bindadres | Gebruik |
|---|---|---|---|
| 80 | 80 | 127.0.0.1 | HTTP (entrypoint: web) |
| 443 | 443 | 127.0.0.1 | HTTPS (entrypoint: websecure) |
| 8080 | 8080 | 127.0.0.1 | Dashboard + Prometheus metrics (entrypoint: traefik) |

**Volumes:**

| Host-pad of volume | Mount in container | Modus | Inhoud |
|---|---|---|---|
| /var/run/docker.sock | /var/run/docker.sock | ro | Docker API voor label-discovery |
| ./traefik/traefik.yml | /traefik.yml | ro | Statische configuratie |
| traefik_certs | /letsencrypt | rw | ACME-certificaten |

**Command (base):**
```
--configFile=/traefik.yml
--certificatesresolvers.letsencrypt.acme.email=${LETSENCRYPT_EMAIL:-admin@sanskritisetu.org}
```

**Command (productie extra flags via docker-compose.prod.yml):**
```
--api.insecure=false
--entrypoints.web.http.redirections.entryPoint.to=websecure
--entrypoints.web.http.redirections.entryPoint.scheme=https
--entrypoints.web.http.redirections.entryPoint.permanent=true
```

**Command (development extra flags via docker-compose.dev.yml):**
```
--log.level=DEBUG
```

**Statische configuratie samenvatting (traefik/traefik.yml):**

```
entryPoints:
  web:       :80
  websecure: :443  (tls.options: tls13only)
  traefik:   :8080

tls.options.tls13only:
  minVersion: VersionTLS13

certificatesResolvers.letsencrypt:
  acme:
    storage: /letsencrypt/acme.json
    httpChallenge.entryPoint: web

providers.docker:
  exposedByDefault: false
  network: sanskritisetu_network
  watch: true

api:
  dashboard: true
  insecure: true  (dev; overschreven in prod)

metrics.prometheus:
  entryPoint: traefik
  addRoutersLabels: true
  addServicesLabels: true
```

**Healthcheck:**

```
test:         traefik healthcheck
interval:     30s
timeout:      10s
retries:      3
start_period: 10s
```

Vereist ping: {} in traefik.yml (aanwezig).

**Afhankelijkheden:** geen (start onafhankelijk als Tier 1)

**Restart policy:** unless-stopped (base en productie)

**Veiligheidsnoot:** Docker socket wordt read-only gemount. Traefik gebruikt dit uitsluitend voor
label-discovery; het kan geen containers starten of stoppen. exposedByDefault: false zorgt ervoor
dat alleen services met traefik.enable=true label worden gerouteerd.

**Wat gaat er mis bij failure:**
- Alle publieke HTTP/HTTPS-toegang valt weg (503 op load balancer niveau)
- Direct-access via poort 8111 of 8110 (backend) en 5173 (frontend dev) blijft werken
- TLS-certificaatvernieuwing mislukt als Traefik langer dan 30 dagen offline is (LetsEncrypt ACME)

---

### Service 10: activepieces

**Doel:** No-code workflow-automatiseringsplatform. Bereikbaar via /automation pad via Traefik.
Gebruikt dezelfde postgres en redis instanties als de applicatie. Verwerkt automatiseringsflows
in MEMORY queue-mode (geen externe queue-service nodig).

**Image:** ghcr.io/activepieces/activepieces:0.81.4

**Container naam:** sanskritisetu_activepieces_internal

**Poorten:**
- Intern: expose: "80" (alleen beschikbaar binnen sanskritisetu_network)
- Development-override: 127.0.0.1:8090:80 (directe toegang voor debugging)
- Productie: geen directe host-binding; uitsluitend via Traefik

**Volumes:**

| Volume | Mount in container | Inhoud |
|---|---|---|
| activepieces_data | /root/.activepieces | ActivePieces configuratie en state |

**Environment variabelen:**

| Variabele | Beschrijving | Verplicht te wijzigen |
|---|---|---|
| AP_ENCRYPTION_KEY | Gegevensencryptiesleutel | Ja |
| AP_JWT_SECRET | JWT-signeringssleutel | Ja |
| AP_WORKER_TOKEN | Server-worker authenticatietoken (JWT) | Ja |
| AP_QUEUE_MODE | MEMORY | Nee |
| AP_POSTGRES_HOST | postgres | Nee |
| AP_POSTGRES_PORT | 5432 | Nee |
| AP_POSTGRES_DATABASE | ${POSTGRES_DB:-sanskritisetu} | Nee |
| AP_POSTGRES_USERNAME | ${POSTGRES_USER:-postgres} | Nee |
| AP_POSTGRES_PASSWORD | ${POSTGRES_PASSWORD:-postgres} | Ja (prod) |
| AP_REDIS_HOST | redis | Nee |
| AP_REDIS_PORT | 6379 | Nee |
| AP_REDIS_USE_SSL | false | Nee |
| AP_FRONTEND_URL | Base-URL voor de AP-interface | Ja (per omgeving) |
| AP_API_URL | Base-URL voor AP API-calls vanuit browser | Ja (per omgeving) |
| AP_EXECUTION_MODE | UNSANDBOXED | Nee |
| AP_TELEMETRY_ENABLED | false | Nee |
| AP_SANDBOX_RUN_TIME_SECONDS | 600 | Nee |
| AP_WEBHOOK_TIMEOUT_SECONDS | 30 | Nee |
| AP_TRIGGER_DEFAULT_POLL_INTERVAL | 5 (minuten) | Nee |
| AP_LOG_LEVEL | info (base) / debug (dev) | Nee |

**AP_FRONTEND_URL en AP_API_URL per omgeving:**

| Omgeving | AP_FRONTEND_URL | AP_API_URL |
|---|---|---|
| Development (direct) | http://localhost:8090 | http://localhost:8090/api |
| Base/staging | http://localhost/automation | http://localhost/automation/api |
| Productie | https://sanskritisetu.org/automation | https://sanskritisetu.org/automation/api |

**Traefik-labels:**

| Label | Waarde |
|---|---|
| traefik.enable | true |
| traefik.http.routers.activepieces.rule | PathPrefix("/automation") |
| traefik.http.routers.activepieces.entrypoints | web,websecure |
| traefik.http.routers.activepieces.tls | true |
| traefik.http.services.activepieces-svc.loadbalancer.server.port | 80 |
| traefik.http.middlewares.ap-strip.stripprefix.prefixes | /automation |
| traefik.http.routers.activepieces.middlewares | security-headers,ap-strip |

**StripPrefix-werking:** Traefik verwijdert het /automation prefix voordat het verzoek aan
de container wordt doorgegeven. /automation/api/v1/flows -> /api/v1/flows voor de container.

**Afhankelijkheden:**
- postgres (condition: service_healthy)
- redis (condition: service_healthy)

**Bekende valkuilen:**
- AP_WORKER_TOKEN moet een JWT zijn gesigneerd met AP_JWT_SECRET met payload
  {type: "WORKER", id: ..., iss: "activepieces"}. Een plain hex-string geeft "Authentication error".
- Intern draait de container op poort 80, niet 3000. Onjuiste port-mapping (8090:3000) geeft
  ERR_EMPTY_RESPONSE. Gebruik 8090:80.
- SPA-routing na subpad-migratie: interne redirects gaan naar root zonder prefix. In development
  gebruik directe poort-mapping (8090:80) voor debugging.

**Webhook-beveiliging:** Webhook-events mogen nooit tenant_id uit de payload vertrouwen.
Zie CLAUDE.md regel 6.1 voor het correcte patroon.

**Wat gaat er mis bij failure:**
- Automatiseringsflows worden niet uitgevoerd
- Webhook-events worden niet verwerkt
- Applicatie blijft volledig functioneel; alleen automatiseringsfunctionaliteit valt weg

---

### Service 11: learning-worker

**Doel:** Dramatiq-worker voor het LearningMixin systeem (ADR-022). Verwerkt asynchrone
feedback-verwerking en agent-leerprocessen. Draait 4 processen met elk 2 threads.

**Image:** Gebouwd via Dockerfile (base: applicatie-image, prod: production-worker target)

**Container naam:** sanskritisetu_learning_worker

**Command:**
```
dramatiq src.core.learning.worker --processes 4 --threads 2
```

**Environment variabelen:**

| Variabele | Waarde | Beschrijving |
|---|---|---|
| DATABASE_URL | ${DATABASE_URL} | PostgreSQL connection string |
| REDIS_URL | ${REDIS_URL} | Applicatiecache (db 0) |
| DRAMATIQ_BROKER_URL | ${DRAMATIQ_BROKER_URL:-redis://redis:6379/1} | Dramatiq broker (db 1) |
| ASYNC_FEEDBACK_PROCESSING | true | Schakel async-modus in |
| ENVIRONMENT | ${ENVIRONMENT:-production} | Runtime mode |
| LOG_LEVEL | ${LOG_LEVEL:-INFO} | Log-niveau |

**Development-override:** 2 processen, 1 thread (--processes 2 --threads 1), LOG_LEVEL DEBUG,
source-code volume gemount, healthcheck uitgeschakeld.

**Resource limieten:**

| Omgeving | Geheugen limiet | Reservering |
|---|---|---|
| Base (productie) | 1G | 512M |
| Productie-override | 2G | 1G |

**Healthcheck:**

```
test:         pgrep -f dramatiq
interval:     30s
timeout:      10s
retries:      3
start_period: 10s
```

**Afhankelijkheden:**
- postgres (condition: service_healthy)
- redis (condition: service_healthy)
- backend (condition: service_healthy)

**Restart policy:** always (productie)

**Netwerk:** sanskritisetu_network

**Wat gaat er mis bij failure:**
- Agent-leerprocessen worden niet uitgevoerd; feedback-data stapelt op in Redis-broker
- Geen directe gebruikersimpact (async verwerking)
- LearningMixin @auto_learn decorators blijven taken enqueuen; bij herstart worden taken opgepakt

---

### Service 12: prometheus

**Doel:** Tijdreeksdatabase voor metrics. Scrapt alle services op geconfigureerde intervals.
Evalueert alerting-regels en stuurt notificaties naar Alertmanager (indien geconfigureerd).

**Image:** prom/prometheus:v2.55.0

**Container naam:** sanskritisetu_prometheus

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 9090 | 9090 | 127.0.0.1 |

**Volumes:**

| Host-pad | Mount in container | Modus | Inhoud |
|---|---|---|---|
| ./prometheus/prometheus.yml | /etc/prometheus/prometheus.yml | ro | Scrape-configuratie |
| ./prometheus/alerts | /etc/prometheus/alerts | ro | Alert-regels |
| ./prometheus/learning-alerts.yml | /etc/prometheus/learning-alerts.yml | ro | Learning-specifieke alerts |
| prometheus_data | /prometheus | rw | Tijdreeksdata |

**Command:**
```
--config.file=/etc/prometheus/prometheus.yml
--storage.tsdb.path=/prometheus
--web.console.libraries=/usr/share/prometheus/console_libraries
--web.console.templates=/usr/share/prometheus/consoles
--web.enable-lifecycle
```

--web.enable-lifecycle staat hot-reload van configuratie toe via POST /-/reload.

**Afhankelijkheden:** geen (start onafhankelijk)

**Netwerk:** sanskritisetu_network

**Scrape-targets (geconfigureerd in prometheus.yml):**
- backend: :8000/metrics
- traefik: :8080/metrics
- redis-exporter: :9121/metrics
- postgres-exporter: :9187/metrics

**Wat gaat er mis bij failure:**
- Geen metrics-data; Grafana-dashboards tonen "No Data"
- Alerts worden niet geëvalueerd; geen notificaties bij incidenten
- Applicatie blijft volledig functioneel

---

### Service 13: grafana

**Doel:** Dashboardplatform voor visualisatie van Prometheus-metrics en Jaeger-traces.
Dashboards zijn geprovisioneerd vanuit monitoring/grafana/dashboards/.

**Image:** grafana/grafana:11.1.4

**Container naam:** sanskritisetu_grafana

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 4000 | 3000 | 127.0.0.1 |

**Volumes:**

| Host-pad of volume | Mount in container | Modus | Inhoud |
|---|---|---|---|
| grafana_data | /var/lib/grafana | rw | Dashboards, users, plugins |
| ./monitoring/grafana/provisioning | /etc/grafana/provisioning | ro | Datasource + dashboard provisioning |
| ./monitoring/grafana/dashboards | /var/lib/grafana/dashboards | ro | Dashboard JSON-bestanden |

**Environment variabelen:**

| Variabele | Default | Beschrijving |
|---|---|---|
| GF_SECURITY_ADMIN_USER | admin | Admin-gebruikersnaam |
| GF_SECURITY_ADMIN_PASSWORD | admin | Admin-wachtwoord (WIJZIG IN PRODUCTIE) |
| GF_USERS_ALLOW_SIGN_UP | false | Zelfregistratie uitgeschakeld |

**Afhankelijkheden:** prometheus

**Netwerk:** sanskritisetu_network

**Geconfigureerde dashboards:**
- copilot-proactive.json (Sprint 5: 4 panels voor proactive monitoring flows)
- Agent Council observability dashboard (Sprint 3)
- Overige applicatie-dashboards

**Wat gaat er mis bij failure:**
- Dashboard-toegang niet beschikbaar
- Prometheus en Jaeger blijven data verzamelen
- Geen gebruikersimpact

---

### Service 14: jaeger

**Doel:** Distributed tracing backend (ADR-014). Ontvangt OpenTelemetry traces van de backend
via OTLP gRPC. Biedt een UI voor trace-analyse en latency-debugging.

**Image:** jaegertracing/all-in-one:1.60.0

**Container naam:** sanskritisetu_jaeger

**Poorten:**

| Host | Container | Bindadres | Gebruik |
|---|---|---|---|
| 16686 | 16686 | 0.0.0.0 | Jaeger UI |
| 4317 | 4317 | 0.0.0.0 | OTLP gRPC ingest |

**Opgelet:** Jaeger bindt op alle interfaces (geen 127.0.0.1 prefix). In productie-omgevingen
achter een firewall is dit acceptabel; bij rechtstreeks publiek-bereikbare omgevingen
moet een bindadres worden toegevoegd.

**Environment variabelen:**

| Variabele | Waarde | Beschrijving |
|---|---|---|
| COLLECTOR_OTLP_ENABLED | true | Activeer OTLP gRPC collector op poort 4317 |

**Afhankelijkheden:** geen

**Netwerk:** sanskritisetu_network

**Backend-integratie:**
- Backend gebruikt OpenTelemetry SDK met OTLP gRPC exporter
- OTLP endpoint: http://jaeger:4317 (intern) of http://localhost:4317 (host)

**Wat gaat er mis bij failure:**
- Traces worden niet opgeslagen; tracing-data gaat verloren
- Backend logt een waarschuwing bij OTLP-verbindingsfout maar blijft functioneel
- Latency-debugging en trace-analyse niet beschikbaar

---

### Service 15: redis-exporter

**Doel:** Prometheus-exporter voor Redis-metrics. Vertaalt Redis INFO-output naar
Prometheus-formaat. Scraped door Prometheus op poort 9121.

**Image:** oliver006/redis_exporter:latest

**Container naam:** sanskritisetu_redis_exporter

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 9121 | 9121 | 127.0.0.1 |

**Environment variabelen:**

| Variabele | Waarde |
|---|---|
| REDIS_ADDR | redis://redis:6379 |
| REDIS_PASSWORD | ${REDIS_PASSWORD:-changeme_in_production} |

**Afhankelijkheden:** redis

**Netwerk:** sanskritisetu_network

**Beschikbare metrics (selectie):**
- redis_connected_clients — actieve verbindingen
- redis_memory_used_bytes — geheugengebruik
- redis_keyspace_hits_total / redis_keyspace_misses_total — cache hit rate
- redis_commands_processed_total — commands per seconde
- redis_db_keys — aantal keys per database

**Wat gaat er mis bij failure:**
- Redis-metrics ontbreken in Prometheus en Grafana
- Redis zelf blijft volledig functioneel

---

### Service 16: postgres-exporter

**Doel:** Prometheus-exporter voor PostgreSQL-metrics. Verbindt als database-client en
exporteert query-statistieken, lock-informatie en tabelgroottes.

**Image:** prometheuscommunity/postgres-exporter:latest

**Container naam:** sanskritisetu_postgres_exporter

**Poorten:**

| Host | Container | Bindadres |
|---|---|---|
| 9187 | 9187 | 127.0.0.1 |

**Environment variabelen:**

| Variabele | Waarde |
|---|---|
| DATA_SOURCE_NAME | postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}?sslmode=disable |

**Afhankelijkheden:** postgres

**Netwerk:** sanskritisetu_network

**Beschikbare metrics (selectie):**
- pg_stat_database_tup_fetched — gelezen rijen
- pg_locks_count — actieve locks per lock-type
- pg_stat_user_tables_n_live_tup — levende rijen per tabel
- pg_stat_activity_count — actieve verbindingen per state
- pg_database_size_bytes — databasegrootte

**Wat gaat er mis bij failure:**
- PostgreSQL-metrics ontbreken in Prometheus en Grafana
- PostgreSQL zelf blijft volledig functioneel

---

## Volumes-inventaris

| Volume naam | Docker naam | Gemount in | Inhoud | Persistentie |
|---|---|---|---|---|
| postgres_data | sanskritisetu_postgres_data | postgres:/var/lib/postgresql/data | Alle databasedata | Kritiek — nooit verwijderen |
| redis_data | sanskritisetu_redis_data | redis:/data | AOF-log + RDB-snapshot | Belangrijk — kan worden gereconstrueerd maar met dataverlies |
| ollama_data | sanskritisetu_ollama_data | ollama:/root/.ollama | Gedownloade LLM-modellen | Herdownloadbaar maar traag (meerdere GB's) |
| prometheus_data | sanskritisetu_prometheus_data | prometheus:/prometheus | Tijdreeksdata | Niet-kritiek — kan worden opgebouwd |
| grafana_data | sanskritisetu_grafana_data | grafana:/var/lib/grafana | Dashboards, gebruikers, plugins | Niet-kritiek (dashboards in git) |
| activepieces_data | sanskritisetu_activepieces_data | activepieces:/root/.activepieces | AP-configuratie | Belangrijk — verlies vereist herconfiguratie |
| traefik_certs | sanskritisetu_traefik_certs | traefik:/letsencrypt | TLS-certificaten | Hervernieuwbaar maar veroorzaakt downtime |

---

## Netwerk-inventaris

| Netwerk | Docker naam | Driver | Gebruik |
|---|---|---|---|
| sanskritisetu_network | sanskritisetu_network | bridge | Alle productie-services |

Alle services zijn verbonden met sanskritisetu_network. Dit is het enige netwerk in de base-configuratie.
CI-, test- en e2e-varianten gebruiken eigen geïsoleerde netwerken (integration-network, e2e-network).

---

## Docker Compose varianten

### docker-compose.yml (base)

Bevat alle services met hun standaardconfiguratie. Wordt altijd als eerste bestand opgegeven.
Zelfstandig bruikbaar maar mist productie-hardening (geen restart policies, geen HTTP->HTTPS redirect).

```bash
docker compose -p sanskritisetu -f docker-compose.yml up -d
```

### docker-compose.dev.yml (development)

Overschrijft: Traefik log-level DEBUG, backend met hot-reload en debugpy, frontend Vite dev-server
op poort 5173, activepieces direct bereikbaar op poort 8090, learning-worker gereduceerde concurrency,
sync-server zonder healthcheck, volume-mounts voor source-code hot-reload.

```bash
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### docker-compose.prod.yml (productie)

Overschrijft: Traefik HTTP->HTTPS redirect + api.insecure=false, backend production-api target +
restart:always, frontend production target (Nginx), activepieces productie-URLs, learning-worker
hogere geheugenlimieten, workflow-worker productie-image, sync-server production Node.js mode,
alle services met restart: always.

```bash
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### docker-compose.ci.yml (CI)

Alleen postgres-ci en redis-ci services. Gebruikt postgres:16 (zonder pgvector) voor snelheid.
Poorten: postgres-ci op 5433, redis-ci op 6380. Bedoeld voor unit- en snelle integratietests
in GitHub Actions.

Let op: postgres:16 mist pgvector. Integratietests die vector-queries uitvoeren vereisen
docker-compose.integration-test.yml (met ankane/pgvector).

### docker-compose.test.yml (E2E-tests)

Services: postgres-test (poort 55433), redis-test (poort 6380), test-runner.
Netwerk: e2e-network. test-runner bouwt via Dockerfile.test en draait pytest tests/e2e/.

### docker-compose.integration-test.yml (integratietests)

Services: postgres-integration (poort 5455, pgvector, geoptimaliseerde PostgreSQL-instellingen),
redis-integration (poort 6380), optionele test-runner.
Netwerk: integration-network.
Poort 5455 matcht de pytest-configuratie voor integratietests (make test-db-up).

### docker-compose.e2e.yml (E2E Playwright)

Bevat Playwright-infrastructuur voor browser-E2E-tests. Aparte documentatie aanbevolen.

### docker-compose.quickstart.yml (snel opstarten)

Minimalistische stack: api (SQLite + uvicorn), redis, worker (dramatiq). Geen postgres, geen Traefik,
geen observability. Bedoeld voor demo's en eerste verkenning.

### docker-compose.secrets.yml (file-based secrets)

Override voor Docker Swarm-omgevingen: vervangt externe secrets (external: false) door
file-based secrets vanuit ./secrets/. Bestanden: jwt_secret, db_password, redis_password,
google_api_key, smtp_password, ap_encryption_key, ap_jwt_secret.

### docker-compose.test-db.yml (testdatabase)

Alleen postgres-test service op poort 5455 met pgvector/pgvector:pg15. Gebruikt voor make test-db-up.

---

## Integratorhandleiding

### Vereisten

- Docker Engine 24+ en Docker Compose v2.20+
- Minimaal 8 GB RAM beschikbaar voor Docker
- Poorten 80, 443, 8080, 5435, 6385, 9090, 4000, 16686, 4317, 9121, 9187 vrij op de host

### Omgevingsvariabelen instellen

Kopieer .env.example naar .env en vul minimaal in:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<sterk-wachtwoord>
POSTGRES_DB=sanskritisetu
REDIS_PASSWORD=<sterk-wachtwoord>
DATABASE_URL=postgresql+asyncpg://postgres:<wachtwoord>@postgres:5432/sanskritisetu
REDIS_URL=redis://:<wachtwoord>@redis:6379/0
DRAMATIQ_BROKER_URL=redis://:<wachtwoord>@redis:6379/1
LETSENCRYPT_EMAIL=admin@sanskritisetu.org
AP_ENCRYPTION_KEY=<32-karakter-sleutel>
AP_JWT_SECRET=<32-karakter-sleutel>
AP_WORKER_TOKEN=<JWT-gesigneerd-met-AP_JWT_SECRET>
DEFAULT_ADMIN_PASSWORD=<admin-wachtwoord>
ALLOWED_ORIGINS=https://sanskritisetu.org
SYNC_WEBHOOK_SECRET=<secret>
```

### Stack starten

**Development (lokaal):**
```bash
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.dev.yml up -d
```

**Productie:**
```bash
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
```

**Met Ollama (optioneel, embedding in container):**
```bash
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.dev.yml --profile ollama up -d
```

**Integratietests (poort 5455):**
```bash
docker compose -f docker-compose.integration-test.yml up -d postgres-integration redis-integration
# of via Makefile:
make test-db-up
```

### Beschikbare poorten na opstarten

| Service | URL | Gebruik |
|---|---|---|
| Frontend (dev) | http://localhost:5173 | React app met HMR |
| Frontend (via Traefik) | http://localhost | React app |
| Backend API (direct, base) | http://localhost:8111 | Directe API-toegang |
| Backend API (direct, prod) | http://localhost:8110 | Directe API-toegang |
| Backend API (via Traefik) | http://localhost/api/v1/ | Via gateway |
| ActivePieces (dev direct) | http://localhost:8090 | AP-dashboard |
| ActivePieces (via Traefik) | http://localhost/automation | AP via gateway |
| Sync Server | ws://localhost:1234 | YJS WebSocket |
| PostgreSQL | localhost:5435 | psql of DBeaver |
| Redis | localhost:6385 | redis-cli of RedisInsight |
| Traefik Dashboard | http://localhost:8080 | Routing-overzicht |
| Prometheus | http://localhost:9090 | Metrics-query |
| Grafana | http://localhost:4000 | Dashboards (admin/admin) |
| Jaeger UI | http://localhost:16686 | Distributed traces |
| Redis Exporter | http://localhost:9121/metrics | Prometheus scrape |
| PostgreSQL Exporter | http://localhost:9187/metrics | Prometheus scrape |

### Status en logs controleren

```bash
# Status alle services
docker compose -p sanskritisetu ps

# Logs van specifieke service
docker compose -p sanskritisetu logs -f backend

# Healthcheck-status
docker inspect sanskritisetu_backend --format='{{.State.Health.Status}}'

# Alle containers met healthstatus
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

### Migraties uitvoeren

Alembic-migraties draaien automatisch bij backend-start. Handmatig uitvoeren:

```bash
docker compose -p sanskritisetu exec backend alembic -c src/alembic.ini upgrade head
```

### Stack stoppen

```bash
docker compose -p sanskritisetu down
# Met verwijdering van orphan containers (aanbevolen):
docker compose -p sanskritisetu down --remove-orphans
# Volumes verwijderen (WAARSCHUWING: dataverlies):
docker compose -p sanskritisetu down -v
```

### Project-naam altijd meegeven

Gebruik altijd -p sanskritisetu (of COMPOSE_PROJECT_NAME=sanskritisetu in .env).
Zonder expliciete project-naam kan Docker Compose conflicteren met bestaande containers als
de directory-naam verschilt. Zie CLAUDE.md bekende valkuilen.

---

## Open aannames / vragen / risico's

| Nr | Type | Beschrijving | Prioriteit |
|---|---|---|---|
| 1 | Risico | Jaeger bindt poorten 16686 en 4317 op 0.0.0.0 (geen 127.0.0.1-beperking). In productie achter NAT geen probleem, maar bij directe publieke blootstelling is aanvullende firewall-regel of bindadres vereist. | MEDIUM |
| 2 | Aanname | docker-compose.e2e.yml is aanwezig maar niet volledig gedocumenteerd in dit spec-bestand (Playwright-infrastructuur). Inhoud behoeft aparte documentatie. | LAAG |
| 3 | Risico | ActivePieces AP_EXECUTION_MODE=UNSANDBOXED betekent dat flows zonder sandboxing draaien. Acceptabel als flows door vertrouwde gebruikers worden gemaakt, maar verhoogt het aanvalsoppervlak bij compromised tenants. | MEDIUM |
| 4 | Aanname | Backend-service exposeert Prometheus-metrics op /metrics (poort 8000). Verificatie van dit endpoint valt buiten scope van dit spec-bestand; zie backend API-spec. | LAAG |
| 5 | Vraag | sync-server verbindt met BACKEND_URL=http://backend:8110 (base) vs http://backend:8000 (prod). Productie-override gebruikt 8000. Base-bestand gebruikt 8110. Dit suggereert een inconsistentie: base zou 8000 moeten gebruiken of de productie-override is bedoeld als correctie. Verificatie vereist. | MEDIUM |
| 6 | Risico | GF_SECURITY_ADMIN_PASSWORD=admin als default in docker-compose.yml. Als productie zonder override-bestand wordt gestart, is het Grafana-dashboard toegankelijk met standaard credentials. | HIGH -- altijd overschrijven via env var of prod-override |
| 7 | Aanname | focusbuilder heeft geen healthcheck. Downstream services die hiervan afhangen mogen alleen condition: service_started gebruiken, niet service_healthy. Huidige configuratie is correct. | LAAG |

---

## QA-checks

De volgende controles zijn verplicht na elke wijziging aan Compose-bestanden of Traefik-configuratie:

```bash
# 1. Valideer alle Compose-bestanden
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet

# 2. Bouw productie-images lokaal
docker build --target production-api .
docker build frontend/

# 3. Controleer dat alle Dockerfile-referenced bestanden in git zitten
git ls-files --error-unmatch scripts/init-databases.sql
git ls-files --error-unmatch traefik/traefik.yml
git ls-files --error-unmatch prometheus/prometheus.yml

# 4. Start stack en controleer healthchecks (development)
docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.dev.yml up -d
sleep 60
docker compose -p sanskritisetu ps | grep -v "healthy\|running"

# 5. Controleer Traefik-routing
curl -s http://localhost/api/v1/health | grep -q "ok"
curl -sI http://localhost/ | grep -q "200"

# 6. Controleer dat database bereikbaar is
docker compose -p sanskritisetu exec postgres pg_isready -U postgres

# 7. Controleer Redis-authenticatie
docker compose -p sanskritisetu exec redis redis-cli -a ${REDIS_PASSWORD} ping

# 8. Controleer dat Prometheus scrape-targets healthy zijn
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json, sys
data = json.load(sys.stdin)
unhealthy = [t for t in data['data']['activeTargets'] if t['health'] != 'up']
print(str(len(unhealthy)) + ' unhealthy targets' if unhealthy else 'All targets healthy')
"
```

---

## Definition of Done

Een wijziging aan de Docker-stack is pas KLAAR als aan alle onderstaande criteria is voldaan:

- [ ] docker compose -f docker-compose.yml config --quiet slaagt zonder fouten
- [ ] docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet slaagt
- [ ] docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet slaagt
- [ ] docker build --target production-api . slaagt lokaal
- [ ] docker build frontend/ slaagt lokaal
- [ ] bash scripts/pre-deploy-check.sh slaagt volledig (inclusief git-aanwezigheidscontrole)
- [ ] Alle gerefereerde bestanden in Dockerfile en Compose-bestanden staan in git (git ls-files --error-unmatch)
- [ ] Nieuwe environment-variabelen zijn gedocumenteerd in dit spec-bestand en in .env.example
- [ ] Gewijzigde healthchecks zijn getest met docker inspect --format='{{.State.Health.Status}}'
- [ ] Traefik-routering is getest: /api/*, /automation* en / retourneren verwacht resultaat
- [ ] Geen hardcoded wachtwoorden of secrets in Compose-bestanden (altijd ${VAR:-default} patroon)
- [ ] Nieuwe services gebruiken 127.0.0.1:-bindadres voor host-poorten (geen publieke binding)
- [ ] Nieuwe services zijn toegevoegd aan de Backend-inventaristabel in dit document
- [ ] ID-register (docs/backend/features/ID-REGISTRY.md) is bijgewerkt
- [ ] Startup-volgorde (BE-FLW-001) is bijgewerkt als depends_on is gewijzigd
- [ ] Routeringstabel (BE-FLW-002) is bijgewerkt als Traefik-labels zijn gewijzigd

---

## Trainingssamenvatting

### Flow: `docker compose up` opstartketen van de volledige stack

- **Actor:** Operator (developer of CI/CD pipeline)
- **Voorwaarde:** Docker daemon draait, `.env` of `.env.{ENVIRONMENT}` aanwezig met verplichte secrets (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `DEFAULT_ADMIN_PASSWORD`, etc.), juiste compose-bestanden beschikbaar, geen orphan containers van eerdere runs.
- **Actie:** Operator voert uit `docker compose -p sanskritisetu -f docker-compose.yml -f docker-compose.{dev|prod}.yml up -d --remove-orphans` (of equivalent voor CI/test/e2e).
- **Systeemreactie:** Docker start services in 5 tiers volgens `depends_on` + `condition: service_healthy` (zie BE-FLW-001): Tier 1 (postgres, redis, traefik) parallel; Tier 2 (backend) wacht op postgres+redis healthy; Tier 3 (sync-server, workflow-worker, learning-worker, focusbuilder, activepieces) parallel na backend healthy; Tier 4 (frontend) na sync-server started; Tier 5 (observability stack) onafhankelijk. Traefik discovert containers via Docker socket (read-only mount) en bouwt routes uit `traefik.enable=true` labels.
- **Succesrespons:** Alle 16 services zijn `Up (healthy)` in `docker ps`. Backend bereikbaar via `http://localhost/api/v1/health` (via Traefik) of direct op `127.0.0.1:8110/health`. Frontend bereikbaar via `http://localhost/`. Activepieces op `http://localhost/automation`. Observability: Grafana `127.0.0.1:4000`, Jaeger `127.0.0.1:16686`, Prometheus `127.0.0.1:9090`.
- **Foutrespons:** Service blijft `unhealthy`: `docker inspect <container> --format='{{json .State.Health}}'` toont FailingStreak + laatste curl-fout (zie CLAUDE.md "Docker Backend Startup Fix"). Migratie-fout in backend: container crash-loopt (Alembic version mismatch); fix via `alembic upgrade head --sql` dry-run. ACME-fout in traefik: certificaat-uitgifte mislukt; check `traefik_certs` volume.
- **Uitzonderingen:** Profielen: `ollama` service start uitsluitend met `--profile ollama`. CI-variant gebruikt `postgres-ci` op poort 5433 met `postgres:16` (geen pgvector -- integratietests die vector-queries doen vereisen `pgvector/pgvector:pg15`). Orphan containers van vorige compose-runs blokkeren start: altijd `--remove-orphans` gebruiken.
