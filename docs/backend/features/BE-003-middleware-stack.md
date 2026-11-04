# Backend Feature Specification

## Metadata

- **Feature ID:** BE-003
- **Feature naam:** Middleware Stack
- **Status:** ACTIEF
- **Auteur:** Rakesh Ramkhelawan
- **Datum:** 2026-05-25
- **ADR:** ADR-003 (tenant via JWT claim), ADR-009 (Traefik/TLS), ADR-005 (tenant_id NOT NULL + RLS), ADR-014 (OpenTelemetry + Prometheus), ADR-015 (ToolBroker allowlist)
- **Gerelateerde module:** `src/core/middleware/`, `src/core/api/setup/middleware_config.py`, `src/core/observability/metrics.py`, `src/core/security/security_middleware.py`

---

## Doel en scope

De middleware stack vormt de volledige requestverwerkingspijplijn van de SanskritiSetu FastAPI-applicatie. Elke inkomende HTTP- of WebSocket-request doorloopt de stack voordat hij een route-handler bereikt. Elke uitgaande response passeert de stack in omgekeerde volgorde.

**Primaire verantwoordelijkheden:**

1. **Probe-bypass** — health- en statusendpoints worden kortgesloten voordat enige andere middleware draait.
2. **CORS-afhandeling** — zowel reguliere HTTP- als WebSocket-handshakes krijgen correcte Cross-Origin headers.
3. **Observability** — Prometheus-metrics en per-endpoint latentieprofiling worden op iedere request bijgehouden.
4. **Tenant-isolatie** — tenant_id wordt uit het JWT-claim gehaald en opgeslagen in een ContextVar zodat alle ORM-queries automatisch gefilterd worden (ADR-003).
5. **Quotahandhaving** — resource- en gebruikslimieten worden getoetst per tenant vóór elke schrijfactie.
6. **Compressie** — responses groter dan 1000 bytes worden automatisch gecomprimeerd met GZip.
7. **TLS-afdwinging** — in productie worden HTTP-requests automatisch omgeleid naar HTTPS.
8. **Security headers** — OWASP-conforme response-headers worden op alle responses gezet.
9. **Threat detection en IP-filtering** — verdachte requests worden tegengehouden voordat ze de applicatielogica bereiken.

**Buiten scope:**

- Applicatieniveau-authenticatie (JWT-verificatie buiten tenant-extractie): valt onder `src/core/auth/`.
- Auditlogging: `audit_middleware.py` bestaat maar is niet geregistreerd in `setup_middleware()` en valt daarmee buiten deze spec.
- TLS-terminatie zelf: wordt afgehandeld door Traefik (ADR-009); de applicatie ziet alleen plaintext intern.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Uitvoervolgorde |
|----|------|------|-------------|-----------------|-----------------|
| BE-MID-001 | ProbeBypassMiddleware | BE-MID | `src/core/api/setup/middleware_config.py` | Bestaand | 1 (buitenste) |
| BE-MID-002 | CORSMiddleware | BE-MID | FastAPI built-in (`fastapi.middleware.cors`) | Bestaand | 2 |
| BE-MID-003 | WebSocketCORSMiddleware | BE-MID | `src/core/middleware/websocket_cors.py` | Bestaand | 3 |
| BE-MID-004 | ToolBrokerMetricsMiddleware | BE-MID | `src/core/middleware/metrics_middleware.py` | Bestaand | 4 (optioneel) |
| BE-MID-005 | PrometheusMiddleware | BE-MID | `src/core/observability/metrics.py` | Bestaand | 5 |
| BE-MID-006 | PerformanceProfilingMiddleware | BE-MID | `src/core/middleware/performance_profiler.py` | Bestaand | 6 |
| BE-MID-007 | TenantMiddleware | BE-MID | `src/core/middleware/tenant_middleware.py` | Bestaand | 7 |
| BE-MID-008 | TenantQuotaMiddleware | BE-MID | `src/core/middleware/quota_middleware.py` | Bestaand | 8 |
| BE-MID-009 | GZipMiddleware | BE-MID | FastAPI built-in (`fastapi.middleware.gzip`) | Bestaand | 9 |
| BE-MID-010 | HTTPSRedirectMiddleware | BE-MID | FastAPI built-in (`fastapi.middleware.httpsredirect`) | Bestaand | 10 (alleen productie) |
| BE-MID-011 | SecurityHeadersMiddleware | BE-MID | `src/core/middleware/security_headers.py` | Bestaand | 11 |
| BE-MID-012 | SecurityMiddleware | BE-MID | `src/core/security/security_middleware.py` | Bestaand | 12 (binnenste) |

**Ondersteunende modules (geen middleware, maar direct gebruikt door middleware):**

| Module | Pad | Gebruikt door |
|--------|-----|---------------|
| TenantContext | `src/core/middleware/tenant_context.py` | TenantMiddleware, TenantQuotaMiddleware, PrometheusMiddleware |
| SecurityManager | `src/core/security/security_manager.py` | SecurityMiddleware |
| PublicEndpointRegistry | `src/core/api/public_endpoints.py` | TenantMiddleware, SecurityMiddleware |
| jwt_handler | `src/core/auth/jwt_handler.py` | TenantMiddleware |
| UsageService | `src/core/services/usage_service.py` | TenantQuotaMiddleware |
| AuditService | `src/core/services/audit_service.py` | TenantMiddleware, TenantQuotaMiddleware |

---

## API-flows

### BE-FLW-005: Request Processing Flow (volledige middleware stack)

Onderstaand diagram toont de uitvoervolgorde (LIFO ten opzichte van `add_middleware`-registratie).

```
Inkomende request
       |
       v
[BE-MID-001] ProbeBypassMiddleware
   - path == "/health"  --> 200 JSON direct, stack stopt hier
   - path == "/status"  --> 200 JSON direct, stack stopt hier
   - anders: doorgaan
       |
       v
[BE-MID-002] CORSMiddleware
   - Preflight OPTIONS --> 204 met CORS-headers, stack stopt hier
   - Ongeldige origin  --> 400 (geen CORS-header in response)
   - Geldig            --> Access-Control-Allow-Origin toegevoegd aan response
       |
       v
[BE-MID-003] WebSocketCORSMiddleware
   - scope["type"] != "websocket" --> doorgaan zonder aanpassing
   - WebSocket, origin toegestaan  --> Access-Control-Allow-Origin injecteren in afwijzingsresponse
   - WebSocket, origin verboden    --> send() gewrapped maar geen header toegevoegd
       |
       v
[BE-MID-004] ToolBrokerMetricsMiddleware  (alleen als metrics_middleware_available=True)
   - path in skip_paths (/health, /metrics, /docs, /redoc, /openapi.json) --> doorgaan
   - anders: Prometheus-counters en histogram bijwerken
       |
       v
[BE-MID-005] PrometheusMiddleware
   - Telt requests, latentie, fouten per tenant en endpoint
       |
       v
[BE-MID-006] PerformanceProfilingMiddleware
   - path in exclude_paths (/health, /live, /ready, /metrics, /openapi.json, /docs, /redoc) --> doorgaan
   - anders: latentie meten (time.perf_counter), opslaan in singleton PerformanceProfiler
       |
       v
[BE-MID-007] TenantMiddleware
   - scope["type"] != "http"              --> doorgaan
   - method == "OPTIONS"                  --> doorgaan (CORS preflight)
   - PublicEndpointRegistry.is_public()   --> doorgaan zonder tenant-context
   - EXCLUDED_PREFIXES match              --> doorgaan zonder tenant-context
   - geen token (header + cookie)         --> 401 {"error": "Missing or invalid authentication"}
   - token aanwezig, jwt_handler.verify_token() == None --> 401 {"error": "Invalid or expired token"}
   - tenant_id ontbreekt in payload       --> 401 {"error": "Token missing tenant context"} + SecurityEvent.TENANT_CONTEXT_FAILED
   - tenant_id geen geldig integer        --> 401 {"error": "Invalid tenant context"}
   - OK: set_tenant_id(tenant_id) in ContextVar, scope["state"] uitgebreid met tenant_id/user_id/email/roles/scopes
   - response: X-Request-ID header toegevoegd
   - finally: clear_tenant_context()
       |
       v
[BE-MID-008] TenantQuotaMiddleware
   - scope["type"] != "http"  --> doorgaan
   - method != "POST"         --> doorgaan (alleen POST-requests gecontroleerd)
   - path niet in QUOTA_ENDPOINTS --> doorgaan
   - tenant_id is None            --> doorgaan (publiek endpoint)
   - count-gebaseerde quota overschreden (users/agents) --> 403 {"detail": "Resource limit reached (N). Please upgrade your plan."}
   - gebruiksgebaseerde quota overschreden (tokens/runs) --> 402 {"detail": "Monthly limit (N) reached for X in Y tier. Please upgrade."} + SecurityEvent.QUOTA_EXCEEDED
       |
       v
[BE-MID-009] GZipMiddleware
   - response body < 1000 bytes --> doorgaan zonder compressie
   - response body >= 1000 bytes --> comprimeren met GZip, Content-Encoding: gzip
       |
       v
[BE-MID-010] HTTPSRedirectMiddleware  (alleen als FORCE_HTTPS=true)
   - request via HTTP --> 301 redirect naar https://
   - request via HTTPS --> doorgaan
       |
       v
[BE-MID-011] SecurityHeadersMiddleware
   - Voegt beveiligingsheaders toe aan http.response.start (pure ASGI send_wrapper)
   - Sensitive paths: extra Cache-Control: no-store headers
   - Cacheable paths (/docs, /redoc, /openapi.json, /static): minder strikt cache-beleid
   - WebSocket (scope != "http"): doorgaan zonder aanpassing
       |
       v
[BE-MID-012] SecurityMiddleware  (binnenste)
   - scope["type"] niet in ("http", "websocket") --> doorgaan (lifespan events)
   - scope["type"] == "websocket" --> doorgaan (WS-auth via eigen route-handler)
   - method == "OPTIONS" --> doorgaan (CORS preflight)
   - enable_security=False --> doorgaan (alle checks overgeslagen)
   - ENVIRONMENT in ("development", "dev", "local", "test") --> IP allowlist wordt NIET gecontroleerd
   - IP in blocked_ips --> 429 {"error": "IP blocked"}
   - IP niet in allowlist (alleen productie) --> 403 {"error": "Access denied"}
   - rate limit overschreden --> 429 {"error": "Rate limit exceeded", "retry_after": 60}
   - ThreatLevel.CRITICAL gedetecteerd --> 403 {"error": "Security violation"}
   - SecurityLevel != PUBLIC, geen auth --> 401 {"error": "Authentication required"}
   - OK: doorgaan naar route-handler
       |
       v
[Route Handler]
       |
       v
Response terug omhoog door dezelfde lagen (response-fase)
```

---

## Detaildocumentatie per middleware

---

### BE-MID-001: ProbeBypassMiddleware

**Bestandspad:** `src/core/api/setup/middleware_config.py` (klasse gedefinieerd bovenaan het bestand)

**Doel:**
Onderschept `/health` en `/status` requests voordat enige andere middleware of route-handler draait. Voorkomt onnodige database-connecties, JWT-verificaties en metrics-overhead voor probe-verkeer van Kubernetes/Traefik.

**Configuratievariabelen:** Geen. Hardcoded paden `/health` en `/status`.

**Wat het toevoegt aan request:** Niets — short-circuit.

**Wat het controleert:** `scope["type"] == "http"` en `scope["path"]` exact gelijk aan `/health` of `/status`.

**Reactie bij match:**

| Pad | HTTP-status | Body |
|-----|-------------|------|
| `/health` | 200 | `{"status": "healthy", "service": "sanskriti-setu-api", "timestamp": "<ISO-8601>"}` |
| `/status` | 200 | `{"status": "operational", "database_initialized": <bool>, "timestamp": "<ISO-8601>"}` |

`/status` leest `database_initialized` uit `app_state` (lazy import van `src.core.api.setup.app_state`).

**Uitzonderingen:** Alleen `/health` en `/status` worden onderschept. Alle andere paden worden doorgegeven.

**Implementatiepatroon:** Pure ASGI (`__call__` met Scope/Receive/Send). Geen `BaseHTTPMiddleware`. Dit is bewust om stream-issues en event-loop-problemen te vermijden.

**Relatie tot andere middleware:** Wordt als laatste geregistreerd (`add_middleware`) en is daarmee de buitenste laag — first to run, last to register.

**Beveiligingsimplicaties:**
- `/health` en `/status` vereisen geen authenticatie en zijn bewust openbaar.
- `/status` lekt geen gevoelige configuratiedetails: alleen `database_initialized` (bool).
- Aanvallen via probe-paden (flooding) worden niet beperkt door deze middleware; rate limiting op IP-niveau zit in BE-MID-012 maar `/health` bereikt die nooit. Overweeg aparte rate limiting op infrastructuurniveau (Traefik) voor probe-endpoints.

---

### BE-MID-002: CORSMiddleware

**Bestandspad:** `fastapi.middleware.cors` (FastAPI built-in), geconfigureerd via `get_cors_config()` in `src/core/middleware/security_headers.py`

**Doel:**
Verwerkt Cross-Origin Resource Sharing voor alle HTTP-requests. Voegt `Access-Control-Allow-*` headers toe aan responses en beantwoordt OPTIONS-preflight-requests.

**Configuratievariabelen:**

| Variabele | Type | Standaard | Omschrijving |
|-----------|------|-----------|--------------|
| `ENVIRONMENT` | `str` | `"development"` | Bepaalt welke originslijst gebruikt wordt |
| `ALLOWED_ORIGINS` | `str` (komma-gescheiden) | `""` | Extra toegestane origins in productie (worden samengevoegd met standaardlijst) |

**Configuratie per omgeving:**

| Omgeving | Toegestane origins | allow_methods | allow_headers | max_age |
|----------|--------------------|---------------|---------------|---------|
| `development` | `localhost:3000`, `localhost:8000`, `localhost:5173`, `localhost:5174`, `127.0.0.1:*` varianten | `*` | `*` | 3600s |
| `staging` | `https://staging.sanskritisetu.nl`, `https://www.staging.sanskritisetu.nl`, `http://localhost:3000`, `http://localhost:8080` | `GET,POST,PUT,DELETE,PATCH,OPTIONS` | `*` | 300s |
| `production` | `https://www.sanskritisetu.org`, `https://sanskritisetu.org`, `https://api.sanskritisetu.org`, `https://www.sanskritisetu.nl`, `https://sanskritisetu.nl`, `https://api.sanskritisetu.nl` + `ALLOWED_ORIGINS` env var | `GET,POST,PUT,DELETE,PATCH,OPTIONS` | `Authorization, Content-Type, X-Request-ID, X-Tenant-ID, Accept, Accept-Language` | 600s |

**expose_headers (productie):** `X-Request-ID`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

`allow_credentials=True` in alle omgevingen.

**Wat het controleert:** Origin-header van inkomende request. Wildcard `*` in combinatie met `allow_credentials=True` is ongeldig en wordt geblokkeerd door `validate_cors_origins()` bij productie.

**Bij mislukking:** Geen CORS-header in response. Browser weigert de response. HTTP-status wordt bepaald door de onderliggende handler; CORS-fout is client-side.

**Uitzonderingen:** OPTIONS-preflight wordt door deze middleware zelf beantwoord (204); de onderliggende stack wordt dan niet bereikt.

**Beveiligingsimplicaties:**
- Productie gebruikt uitsluitend HTTPS-origins. `validate_cors_origins()` gooit `ValueError` als een HTTP-origin (niet-localhost) wordt doorgegeven.
- `allow_credentials=True` vereist expliciete origins — geen wildcard. Dit is afgedwongen in code.
- `X-Tenant-ID` staat in `allow_headers` (productie) voor backwards-compat, maar de applicatie leest tenant_id nooit uit deze header (ADR-003: altijd via JWT).

---

### BE-MID-003: WebSocketCORSMiddleware

**Bestandspad:** `src/core/middleware/websocket_cors.py`

**Doel:**
Starlette's ingebouwde `CORSMiddleware` voegt geen CORS-headers toe aan WebSocket-afwijzingsresponses (bijv. HTTP 400/403 bij mislukte upgrade). Hierdoor zien browsers een misleidende "CORS error" terwijl het werkelijke probleem authenticatie of routing is. Deze middleware lost dat op door `Access-Control-Allow-Origin` te injecteren in niet-101-responses op WebSocket-scopes.

**Configuratievariabelen:** Geen eigen env vars. Ontvangt `allowed_origins` als parameter vanuit `setup_middleware()` (zelfde lijst als CORSMiddleware).

**Wat het toevoegt aan request:** Niets.

**Wat het toevoegt aan response (bij WebSocket-afwijzing):**
- `Access-Control-Allow-Origin: <origin>` (alleen als origin in allowlist)
- `Access-Control-Allow-Credentials: true`

**Wat het controleert:** `scope["type"] == "websocket"` en `Origin`-header in `scope["headers"]`.

**Bij mislukking:** Geen actie — de afwijzing wordt doorgegeven zonder CORS-header als origin niet in de allowlist staat.

**Uitzonderingen:** Alle niet-WebSocket-requests (`scope["type"] != "websocket"`) worden ongewijzigd doorgegeven.

**Relatie tot andere middleware:** Wordt geregistreerd vóór `CORSMiddleware` (dus uitgevoerd na CORSMiddleware in LIFO). Beide middlewares zijn nodig: CORSMiddleware voor HTTP, WebSocketCORSMiddleware voor WS-afwijzingen.

**Beveiligingsimplicaties:**
- WebSocket-authenticatie zelf valt buiten deze middleware. De WS-route-handler gebruikt cookie-auth of query-param fallback (zie CLAUDE.md §13.1).
- Deze middleware voegt alleen CORS-headers toe aan responses op reeds-bestaande afwijzingen; het verandert geen statuscodes en blokkeert niets.

---

### BE-MID-004: ToolBrokerMetricsMiddleware (optioneel)

**Bestandspad:** `src/core/middleware/metrics_middleware.py`

**Doel:**
Verzamelt gedetailleerde Prometheus-metrics specifiek voor de Tool Broker service: aanvraaglatentie, request-counts per status, actieve requests en HTTP-fouten. Aanvullend op de generieke `PrometheusMiddleware` (BE-MID-005).

**Activatieconditie:** Wordt alleen geregistreerd als `setup_middleware()` aangeroepen wordt met `metrics_middleware_available=True`. Bij `ImportError` wordt de registratie stil overgeslagen.

**Configuratievariabelen:** Geen env vars. `skip_paths` hardcoded als `["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]`.

**Prometheus-metrics die worden bijgehouden:**

| Metriek | Type | Labels |
|---------|------|--------|
| `tool_broker_request_latency_seconds` | Histogram | `endpoint`, `method` |
| `tool_broker_requests_total` | Counter | `endpoint`, `method`, `status_code` |
| `tool_broker_active_requests` | Gauge | `endpoint`, `method` |
| `tool_broker_http_errors_total` | Counter | `endpoint`, `method`, `status_code` |
| `tool_broker_tool_executions_total` | Counter | `tool_name`, `status` |
| `tool_broker_tool_execution_latency_seconds` | Histogram | `tool_name` |
| `tool_broker_service_health` | Gauge | `service_name` |
| `tool_broker_client_connections` | Gauge | `client_name` |

**Path-normalisatie:** Numerieke IDs, UUIDs en lange hash-segmenten in paden worden vervangen door `{id}` om metric-explosie te voorkomen.

**Implementatiepatroon:** `BaseHTTPMiddleware` (via `starlette.middleware.base`). WebSocket-scopes worden doorgegeven.

**Uitzonderingen:** Paths in `skip_paths` worden overgeslagen; `scope["type"] != "http"` wordt doorgegeven.

**Beveiligingsimplicaties:** Metrics bevatten geen gevoelige payload-inhoud — alleen endpoint-paden, methodes en statuscodes.

---

### BE-MID-005: PrometheusMiddleware

**Bestandspad:** `src/core/observability/metrics.py`

**Doel:**
Platform-brede Prometheus-metrics voor alle requests: aanvraagcounts, latentie en fouten met tenant-context (via `get_tenant_id()` uit ContextVar). Ondersteunt Gunicorn multi-worker via `MultiProcessCollector` wanneer `PROMETHEUS_MULTIPROC_DIR` is ingesteld.

**Configuratievariabelen:**

| Variabele | Type | Omschrijving |
|-----------|------|--------------|
| `PROMETHEUS_MULTIPROC_DIR` | `str` | Als ingesteld: multi-process modus met eigen `CollectorRegistry` en `MultiProcessCollector`. Anders: enkelvoudige registry (`REGISTRY`). |

**Relatie tot andere middleware:** Draait vóór `PerformanceProfilingMiddleware` (in uitvoervolgorde). Beide meten latentie onafhankelijk. `PrometheusMiddleware` gebruikt Prometheus-histogrammen; `PerformanceProfilingMiddleware` houdt in-memory percentieldata bij.

**Uitzonderingen:** Geen expliciete skip-paden (implementatiedetail dat niet zichtbaar is in `setup_middleware`; eventuele filtering zit intern).

**Beveiligingsimplicaties:** `/metrics`-endpoint moet beschermd worden via Traefik of netwerkpolicies. Metrics bevatten tenant_id als label (indien beschikbaar via ContextVar) — let op privacy bij extern blootstellen van metrics.

---

### BE-MID-006: PerformanceProfilingMiddleware

**Bestandspad:** `src/core/middleware/performance_profiler.py`

**Doel:**
Meet request-latentie per endpoint met hoge precisie (`time.perf_counter`). Slaat samples op in een in-memory singleton `PerformanceProfiler` en logt trage requests op drie niveaus.

**Configuratievariabelen:** Geen env vars. Drempelwaarden zijn constants in de module:

| Constant | Waarde | Gedrag |
|----------|--------|--------|
| `SLOW_REQUEST_THRESHOLD_MS` | 200 ms | `logger.info("[SLOW] ...")` |
| `VERY_SLOW_REQUEST_THRESHOLD_MS` | 500 ms | `logger.warning("[VERY SLOW] ...")` |
| `CRITICAL_REQUEST_THRESHOLD_MS` | 1000 ms | `logger.warning("[CRITICAL SLOW] ...")` |
| `MAX_LATENCY_SAMPLES` | 10.000 | Maximaal aantal samples per endpoint in geheugen |
| `CLEANUP_INTERVAL_SECONDS` | 300 s | Opruiminterval voor endpoints zonder activiteit (>24u) |

**Path-normalisatie:** UUIDs en numerieke segmenten worden vervangen door `/{id}` zodat metrics per route-template worden bijgehouden, niet per resource-instantie.

**Wat het toevoegt aan request:** Niets.

**Wat het toevoegt aan response:** Niets (metrics worden intern opgeslagen, niet in response-headers).

**Uitzonderingen:** `exclude_paths` (hardcoded standaard): `/health`, `/live`, `/ready`, `/metrics`, `/openapi.json`, `/docs`, `/redoc`. WebSocket-scopes (`scope["type"] != "http"`) worden doorgegeven.

**Implementatiepatroon:** `BaseHTTPMiddleware`. Let op: dit betekent dat het in de binnenste ASGI-keten draait als onderdeel van de Starlette middleware-stack.

**Relatie tot andere middleware:** `PerformanceProfiler.get_instance()` is een process-level singleton. Data is beschikbaar via `GET /api/v1/diagnostics/performance` (of gelijkwaardig).

**Beveiligingsimplicaties:** In-memory opslag groeit met het aantal unieke genormaliseerde endpoints. Bij extreem veel unieke padpatronen (bijv. parameter-injectie in paden) kan geheugengebruik toenemen. `MAX_LATENCY_SAMPLES=10.000` per endpoint begrenst de samplebuffer.

---

### BE-MID-007: TenantMiddleware

**Bestandspad:** `src/core/middleware/tenant_middleware.py`

**Doel:**
Kerncomponent voor multi-tenancy (ADR-003). Extraheert `tenant_id` uit het JWT-claim, valideert het en slaat het op in een `ContextVar`. Alle SQLAlchemy ORM-queries gebruiken automatisch deze waarde via de `do_orm_execute`-hook (ADR-004), zodat data-isolatie per tenant gegarandeerd is zonder handmatige filterlogica in route-handlers.

**Configuratievariabelen:** Geen directe env vars. Gedrag wordt gestuurd door:
- `PublicEndpointRegistry` (dynamisch register van publieke endpoints)
- Hardcoded `EXCLUDED_PREFIXES`: `/health`, `/ready`, `/metrics`, `/api/v1/auth`, `/docs`, `/openapi.json`

**Token-extractie prioriteit:**
1. `Authorization: Bearer <token>` header
2. `access_token` cookie (fallback voor browser-sessies)

Query-parameter `?token=` wordt NIET ondersteund voor HTTP-requests (ADR-013.1).

**Wat het toevoegt aan `scope["state"]`:**

| Veld | Type | Bron |
|------|------|------|
| `request_id` | `str` (UUID) | `X-Request-ID` header of nieuw UUID |
| `tenant_id` | `int` | JWT claim `tenant_id` |
| `user_id` | `str` | JWT claim `sub` |
| `email` | `str` | JWT claim `email` |
| `roles` | `list[str]` | JWT claim `roles` |
| `scopes` | `list[str]` | JWT claim `scopes` (OAuth2-stijl, bijv. `"agents:read"`) |

**Foutcodes:**

| Situatie | HTTP-status | Body |
|----------|-------------|------|
| Geen token (header + cookie beide afwezig) | 401 | `{"error": "Missing or invalid authentication"}` |
| Token aanwezig maar ongeldig/verlopen | 401 | `{"error": "Invalid or expired token"}` |
| JWT mist `tenant_id` claim | 401 | `{"error": "Token missing tenant context"}` + SecurityEvent.TENANT_CONTEXT_FAILED |
| `tenant_id` niet omzetbaar naar integer | 401 | `{"error": "Invalid tenant context"}` |
| Onverwachte uitzondering | 401 | `{"error": "Authentication failed"}` |

**Wat wordt overgeslagen (geen tenant-context vereist):**
- `scope["type"] != "http"` (WebSocket, lifespan)
- `method == "OPTIONS"` (CORS preflight)
- Paden geregistreerd in `PublicEndpointRegistry`
- Paden die beginnen met `EXCLUDED_PREFIXES`

**Response-fase:** `send_wrapper` voegt `X-Request-ID` header toe aan elke response. `X-Tenant-ID` wordt bewust NIET toegevoegd aan responses (information disclosure).

**Cleanup:** In `finally`-blok: `clear_tenant_context()`. Kritiek voor async-veiligheid — ContextVar-waarden mogen niet overlopen naar volgende requests in dezelfde worker.

**Beveiligingsimplicaties:**
- `set_tenant_id()` in `tenant_context.py` valideert het integer-formaat en controleert op SQL-injectiepatronen (P5.1.3).
- `tenant_id=0` of negatief wordt geweigerd.
- `tenant_id > 2147483647` (int32-overflow) wordt geweigerd.
- JWT zonder `tenant_id` claim produceert een SecurityEvent-auditlog (`TENANT_CONTEXT_FAILED`) met IP-adres, pad en gebruikersnaam.
- `require_tenant_id()` in route-handlers gooit een `RuntimeError` als de ContextVar toch leeg is — fail-secure.

---

### BE-MID-008: TenantQuotaMiddleware

**Bestandspad:** `src/core/middleware/quota_middleware.py`

**Doel:**
Handhaaft resource- en gebruikslimieten per tenant voordat een schrijfactie de applicatielogica bereikt. Afhankelijk van de `tenant_id` die door TenantMiddleware (BE-MID-007) in de ContextVar is gezet.

**Activatieconditie:** Wordt alleen geactiveerd voor POST-requests op paden die beginnen met een van de geconfigureerde `QUOTA_ENDPOINTS`.

**QUOTA_ENDPOINTS:**

| Pad-prefix | Metric-type | Controletype |
|------------|-------------|--------------|
| `/api/users`, `/api/v1/users` | `user` | Count-based |
| `/api/auth/register`, `/api/v1/auth/register` | `user` | Count-based |
| `/api/agents`, `/api/v1/agents` | `agent` | Count-based |
| `/api/v1/workflows` | `workflow_run` | Gebruiksgebaseerd (alleen `/run`, `/execute`, `/generate`) |
| `/api/v1/ai` | `ai_token` | Gebruiksgebaseerd |
| `/api/v1/synthesis` | `synthesis_run` | Gebruiksgebaseerd |

**Tier-limieten:**

| Tier | users | agents | workflow_run | ai_token | synthesis_run |
|------|-------|--------|--------------|----------|---------------|
| `free` | 2 | 3 | 50 | 10.000 | 5 |
| `pro` | 10 | 20 | 1.000 | 500.000 | 100 |
| `enterprise` | 999 | 999 | 999.999 | 99.999.999 | 999.999 |

Limieten worden gelezen uit `Tenant.max_users` / `Tenant.max_agents` (indien ingesteld) of vallen terug op bovenstaande tier-defaults.

**Foutcodes:**

| Situatie | HTTP-status | Body |
|----------|-------------|------|
| Count-quota overschreden (users/agents) | 403 | `{"detail": "Resource limit reached (N). Please upgrade your plan."}` |
| Gebruiksquota overschreden (tokens/runs) | 402 | `{"detail": "Monthly limit (N) reached for X in Y tier. Please upgrade."}` |

Bij beide fouten wordt `SecurityEvent.QUOTA_EXCEEDED` gelogd via `AuditService`.

**Uitzonderingen:**
- `scope["type"] != "http"`: doorgaan
- `method != "POST"`: doorgaan
- `tenant_id is None` (publiek endpoint): doorgaan
- Pad buiten `QUOTA_ENDPOINTS`: doorgaan
- Gebruiksgebaseerde checks: alleen als pad `/run`, `/execute` of `/generate` bevat

**Relatie tot andere middleware:** Vereist dat TenantMiddleware (BE-MID-007) al heeft gedraaid en `tenant_id` in de ContextVar heeft gezet. Volgorde in uitvoering is TenantMiddleware → TenantQuotaMiddleware.

**Beveiligingsimplicaties:**
- Tier-limieten zijn hardcoded in de middleware. Een wijziging vereist een code-deploy. Overweeg in een volgende sprint: dynamische limieten uit de Tenant-configuratietabel.
- `Tenant.subscription_tier` kan `None` zijn; in dat geval wordt `"free"` als fallback gebruikt (regel `tier = getattr(tenant, "subscription_tier", "free")`).
- DB-sessie wordt geopend via `db_manager.get_session()` — dit verbruikt een verbinding per quota-check. Bij hoge aanvraagfrequentie op quota-endpoints: bewaken via connectionpool-metrics.

---

### BE-MID-009: GZipMiddleware

**Bestandspad:** FastAPI built-in (`fastapi.middleware.gzip.GZipMiddleware`)

**Doel:**
Comprimeert HTTP-responses groter dan 1000 bytes met GZip. Vermindert bandbreedtegebruik voor grote API-responses (bijv. agent-listings, auditlogs, DSAR-exports).

**Configuratievariabelen:**

| Parameter | Waarde | Omschrijving |
|-----------|--------|--------------|
| `minimum_size` | 1000 bytes | Responses kleiner dan dit worden niet gecomprimeerd |

**Wat het toevoegt aan response:**
- `Content-Encoding: gzip` (bij compressie)
- Verkorte `Content-Length`

**Uitzonderingen:** Responses kleiner dan 1000 bytes worden ongewijzigd doorgegeven. Clients zonder `Accept-Encoding: gzip` ontvangen ongecomprimeerde responses.

**Beveiligingsimplicaties:** GZip-compressie in combinatie met TLS en geheime data kan in theorie leiden tot CRIME/BREACH-aanvallen. In de SanskritiSetu-context: cookies zijn `httpOnly` (geen JS-toegang) en CSRF-tokens worden via response-headers verzonden, niet in de body. Risico is laag maar documenteer dit als bekend.

---

### BE-MID-010: HTTPSRedirectMiddleware

**Bestandspad:** FastAPI built-in (`fastapi.middleware.httpsredirect.HTTPSRedirectMiddleware`)

**Doel:**
Dwingt HTTPS af door alle HTTP-requests te redirecten naar het HTTPS-equivalent. Actief alleen in productie.

**Activatieconditie:** Alleen geregistreerd als `FORCE_HTTPS=true`.

**Configuratievariabelen:**

| Variabele | Type | Standaard | Omschrijving |
|-----------|------|-----------|--------------|
| `FORCE_HTTPS` | `str` | `"false"` | Zet op `"true"` om HTTPS-redirect te activeren |

**Foutcode bij HTTP-request:** 301 Moved Permanently naar `https://`-equivalent.

**Relatie tot infrastructuur:** In productie termineert Traefik TLS (ADR-009). `HTTPSRedirectMiddleware` is een aanvullende laag voor het geval requests de applicatie rechtstreeks bereiken buiten Traefik om.

**Beveiligingsimplicaties:** Eerste HTTP-request wordt tijdelijk onbeveiligd verstuurd voordat de redirect plaatsvindt. Voor volledige bescherming: combineer met HSTS-header (zie BE-MID-011) zodat browsers toekomstige requests direct via HTTPS sturen.

---

### BE-MID-011: SecurityHeadersMiddleware

**Bestandspad:** `src/core/middleware/security_headers.py`

**Doel:**
Voegt OWASP-conforme security-headers toe aan alle HTTP-responses. Doelstelling: A+-score op securityheaders.com en Mozilla Observatory.

**Configuratievariabelen:**

| Variabele | Type | Effect |
|-----------|------|--------|
| `ENVIRONMENT` | `str` | `"production"` activeert strenge CSP en `Expect-CT`; anders permissieve CSP voor development |
| `HTTPS_ENABLED` | `str` | `"true"` + `ENVIRONMENT=production` activeert `Strict-Transport-Security` via `SecurityHeadersConfig` |

**Headers die altijd worden toegevoegd:**

| Header | Waarde |
|--------|--------|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` |
| `Content-Security-Policy` | Zie tabel hieronder |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Alle browser-features uitgeschakeld (zie broncode) |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Cross-Origin-Opener-Policy` | `same-origin-allow-popups` |
| `Cross-Origin-Embedder-Policy` | `credentialless` |

**CSP per omgeving:**

| Omgeving | `script-src` | `connect-src` | `upgrade-insecure-requests` |
|----------|-------------|---------------|----------------------------|
| `production` | `'self'` | `'self'` | Ja |
| Development | `'self' 'unsafe-inline' 'unsafe-eval'` | `'self' ws://localhost:* ...` | Nee |

**Cache-Control per padtype:**

| Padtype | Cache-Control |
|---------|---------------|
| Gevoelig (`/api/auth/*`, `/api/admin/*`, `/api/v1/auth/*`, `/api/v1/admin/*`, `/api/security/*`) | `no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0` + `Pragma: no-cache` + `Expires: 0` |
| Cacheable (`/docs`, `/redoc`, `/openapi.json`, `/static`) | Geen `Cache-Control` header toegevoegd |
| Overig | `no-store, max-age=0` |

**Extra productie-header:** `Expect-CT: max-age=86400, enforce` (alleen als `ENVIRONMENT=production`).

**Implementatiepatroon:** Pure ASGI (`send_wrapper` op `http.response.start`). WebSocket-scopes (`scope["type"] != "http"`) worden ongewijzigd doorgegeven.

**Bestaande headers worden vervangen:** De send_wrapper filtert bestaande headers met dezelfde naam eruit voordat de security-headers worden toegevoegd, zodat er geen duplicaten ontstaan.

**Uitzonderingen:** Geen path-based uitzonderingen voor de headers zelf; alleen de Cache-Control-instelling varieert per padtype.

**Beveiligingsimplicaties:**
- `X-Frame-Options: DENY` en `Content-Security-Policy: frame-ancestors 'none'` beschermen tegen clickjacking.
- `HSTS` met `preload` is onomkeerbaar voor browsers die de site al kennen; verwijder `preload` alleen als je bewust terug wilt naar HTTP.
- `Expect-CT` is deprecated in moderne browsers (Chrome 107+) maar schaadt niet.

---

### BE-MID-012: SecurityMiddleware (binnenste)

**Bestandspad:** `src/core/security/security_middleware.py`

**Doel:**
Binnenste beveiligingslaag. Controleert IP-allowlist, blokkeert geblokkeerde IPs, handhaaft rate limiting op IP-niveau, detecteert bedreigingen en valideert authenticatie. Actief voor HTTP-requests; WebSocket-requests worden doorgegeven (WS-auth zit in route-handlers).

**Configuratievariabelen:**

| Variabele | Type | Standaard | Omschrijving |
|-----------|------|-----------|--------------|
| `ENABLE_SECURITY_MIDDLEWARE` | `str` | `"true"` | `"false"`, `"0"`, `"off"`, `"no"` schakelt alle checks uit |
| `ENVIRONMENT` | `str` | `"development"` | `"development"`, `"dev"`, `"local"`, `"test"` schakelen IP-allowlist uit |

**Controlevolgorde (bij `enable_security=True`):**

1. **IP allowlist** (alleen productie — niet bij `ENVIRONMENT` in development/test): IP niet in allowlist → 403
2. **Blocked IPs**: IP in `security_manager.blocked_ips` → 429
3. **Rate limiting**: limiet overschreden voor combinatie IP + endpoint + SecurityLevel → 429 met `"retry_after": 60`
4. **Threat detection**: `detect_suspicious_activity()` retourneert `ThreatLevel.CRITICAL` → 403
5. **Authenticatiecontrole** (alleen als `SecurityLevel != PUBLIC`): geen of ongeldig token → 401

**SecurityLevel-toewijzing:**

| Patroon | Level |
|---------|-------|
| `PublicEndpointRegistry.is_public(endpoint)` | `PUBLIC` |
| `/orchestrator` in pad | `PUBLIC` (tijdelijk, development) |
| `/admin`, `/system`, `/config` in pad | `ADMIN` |
| `/autonomous` in pad | `ADMIN` |
| `/phase2`, `/collaboration` in pad | `AUTHORIZED` |
| Overig | `AUTHENTICATED` |

**Foutcodes:**

| Situatie | HTTP-status | Body |
|----------|-------------|------|
| IP niet in allowlist (productie) | 403 | `{"error": "Access denied", "message": "Your IP address is not allowed"}` |
| IP geblokkeerd | 429 | `{"error": "IP blocked", "message": "Your IP has been blocked due to suspicious activity"}` |
| Rate limit overschreden | 429 | `{"error": "Rate limit exceeded", "message": "Too many requests...", "retry_after": 60}` |
| Critical threat | 403 | `{"error": "Security violation", "message": "Request blocked due to security policy"}` |
| Geen authenticatie (niet-publiek endpoint) | 401 | `{"error": "Authentication required", "message": "..."}` |
| Onverwachte fout in middleware | 500 | `{"error": "Internal server error"}` |

**Uitzonderingen:**
- `scope["type"] not in ("http", "websocket")`: doorgaan (lifespan events)
- `scope["type"] == "websocket"`: doorgaan (eigen auth in WS-route)
- `method == "OPTIONS"`: doorgaan (CORS preflight)
- `enable_security=False`: alle checks overgeslagen

**IP-extractie:** `X-Forwarded-For` header (eerste IP bij meerdere), dan `X-Real-IP`, dan `request.client.host`.

**Development-token:** In development/test-omgevingen wordt `"dev-token-safe-development"` als geldig token geaccepteerd voor `SecurityLevel.AUTHENTICATED`. Admin-endpoints (`SecurityLevel.ADMIN`) vereisen altijd een echt JWT, ook in development.

**Foutafhandeling:** Bij onverwachte exceptions: traceback wegschrijven naar `{tempdir}/security_middleware_traceback.log`, `logger.error()` met `exc_info=True`, en een 500 sturen als de response nog niet gestart is (fail-open voor beschikbaarheid).

**Beveiligingsimplicaties:**
- De middleware is fail-open bij onverwachte fouten (geeft 500 terug in plaats van te hangen), wat beschikbaarheid boven absolute veiligheid stelt. Acceptabel voor een API-laag; de werkelijke tenant-isolatie wordt gegarandeerd door TenantMiddleware en ORM-hooks.
- IP-allowlist is alleen actief in productie. Test- en CI-omgevingen draaien altijd zonder IP-filtering.
- `ENABLE_SECURITY_MIDDLEWARE=false` is bedoeld voor geïsoleerde integratietests. Stel nooit in op `false` in productie.
- SecurityMiddleware voegt ook security-headers toe via `security_manager.get_security_headers()`. Dit overlapt met SecurityHeadersMiddleware (BE-MID-011). SecurityHeadersMiddleware is de bepalende laag; duplicaten worden overschreven.

---

## Integratiehandleiding

### CORS instellen voor een nieuwe omgeving

1. Voeg de origin toe aan `get_cors_config()` in `src/core/middleware/security_headers.py` onder het juiste `env`-blok.
2. Origins in productie moeten beginnen met `https://`. `validate_cors_origins()` gooit een `ValueError` bij HTTP-origins.
3. Alternatief: voeg de origin toe via de `ALLOWED_ORIGINS` env var (komma-gescheiden), uitsluitend voor productie.
4. Na wijziging: herstart de applicatie (CORS-config wordt geladen bij startup in `setup_middleware()`).

### SecurityMiddleware uitschakelen voor integratietests

Zet in de testomgeving:

```bash
ENABLE_SECURITY_MIDDLEWARE=false
ENVIRONMENT=test
```

`ENVIRONMENT=test` schakelt bovendien de IP-allowlist uit. `ENABLE_SECURITY_MIDDLEWARE=false` schakelt alle vijf checks uit (allowlist, block-list, rate limiting, threat detection, authenticatiecontrole).

Gebruik in pytest-fixtures:

```python
import os
os.environ["ENABLE_SECURITY_MIDDLEWARE"] = "false"
os.environ["ENVIRONMENT"] = "test"
```

### Nieuw publiek endpoint registreren

Gebruik `PublicEndpointRegistry` zodat zowel TenantMiddleware als SecurityMiddleware het endpoint overslaan:

```python
# src/core/api/public_endpoints.py
PublicEndpointRegistry.register("/api/v1/mijn-publiek-endpoint")
```

**Let op:** Elk pad in `PUBLIC_PREFIXES` / `PublicEndpointRegistry` omzeilt TenantMiddleware volledig. Voeg geen admin- of gevoelige endpoints toe (zie CLAUDE.md valkuilen: "PUBLIC_PREFIXES omzeilt TenantMiddleware volledig").

### TenantQuotaMiddleware aanpassen voor nieuwe resources

Voeg een entry toe aan `QUOTA_ENDPOINTS` in `quota_middleware.py`:

```python
QUOTA_ENDPOINTS = {
    ...
    "/api/v1/mijn-resource": "mijn_metric_type",
}
```

Voeg de bijbehorende limiet toe aan `TIER_LIMITS`:

```python
TIER_LIMITS = {
    "free": {..., "mijn_metric_type": 10},
    "pro": {..., "mijn_metric_type": 100},
    "enterprise": {..., "mijn_metric_type": 999999},
}
```

### Volgorde van `add_middleware` aanpassen

**Waarschuwing:** De uitvoervolgorde is het omgekeerde van de registratievolgorde (LIFO). De volgende invarianten mogen nooit worden gebroken:

1. `ProbeBypassMiddleware` moet als laatste geregistreerd worden (buitenste laag).
2. `TenantMiddleware` moet altijd vóór `TenantQuotaMiddleware` geregistreerd worden (zodat de ContextVar beschikbaar is voor quota-checks).
3. `CORSMiddleware` en `WebSocketCORSMiddleware` moeten vóór alle authenticatie-middlewares geregistreerd worden (zodat preflight niet geblokkeerd wordt).
4. `SecurityMiddleware` moet als eerste geregistreerd worden (binnenste laag — last to run in request-fase).

---

## Open aannames / vragen / risico's

| ID | Type | Omschrijving | Prioriteit |
|----|------|--------------|------------|
| OA-001 | Aanname | Tier-limieten in `TenantQuotaMiddleware` zijn hardcoded. Er is geen mechanisme om limieten per tenant dynamisch aan te passen zonder code-deploy. | Hoog |
| OA-002 | Risico | `ProbeBypassMiddleware` heeft geen rate limiting. Een flooding-aanval op `/health` bereikt geen andere middleware maar verbruikt wel server-resources. Mitigatie via Traefik rate limiting aanbevolen. | Middel |
| OA-003 | Risico | `PerformanceProfilingMiddleware` is `BaseHTTPMiddleware`. Dit kan bij streaming responses of grote request-bodies stream-buffering veroorzaken. Overweeg migratie naar pure ASGI. | Middel |
| OA-004 | Aanname | `audit_middleware.py` bestaat maar is niet geregistreerd in `setup_middleware()`. De reden is onbekend. Controleer of dit bewust is of een omissie. | Middel |
| OA-005 | Risico | `SecurityMiddleware._determine_security_level()` markeert `/orchestrator`-endpoints als `PUBLIC` (commentaar: "Allow CVA -> Orchestrator without auth for development"). Dit is een tijdelijke maatregel. Verwijder dit vóór go-live. | Hoog |
| OA-006 | Vraag | `ToolBrokerMetricsMiddleware` wordt alleen geregistreerd als `metrics_middleware_available=True`. Wat is de conditie in `main.py` die deze parameter bepaalt? Documenteer dit in `main.py`. | Laag |
| OA-007 | Risico | GZip + TLS + geheime cookies: theoretisch BREACH-aanval mogelijk. Praktisch risico laag gegeven httpOnly-cookies en token-in-header-architectuur. Accepteerd risico, documenteer expliciet. | Laag |
| OA-008 | Aanname | `WebSocketCORSMiddleware` voegt `Access-Control-Allow-Credentials: true` toe aan alle WebSocket-afwijzingen van toegestane origins, ongeacht of de specifieke WS-route credentials vereist. Dit is conservatief maar correct. | Laag |

---

## QA-checks

De volgende checks moeten aantoonbaar slagen voordat wijzigingen aan de middleware stack worden gemerged:

### Functionele checks

- [ ] `GET /health` retourneert 200 zonder authenticatie, zonder database-verbinding, zonder tenant-context
- [ ] `GET /status` retourneert 200 met correcte `database_initialized`-boolean
- [ ] `GET /api/v1/agents` zonder token retourneert 401 met `{"error": "Missing or invalid authentication"}`
- [ ] `GET /api/v1/agents` met geldig JWT maar zonder `tenant_id` claim retourneert 401 met `{"error": "Token missing tenant context"}`
- [ ] `POST /api/v1/users` met geldig JWT op een `free`-tenant met 2 gebruikers retourneert 403 met quota-melding
- [ ] OPTIONS-preflight request op elk CORS-endpoint retourneert 204 met correcte `Access-Control-Allow-*` headers
- [ ] Response op `/api/v1/auth/login` bevat `Cache-Control: no-store`
- [ ] Response op elk endpoint bevat `X-Frame-Options: DENY`
- [ ] Response op elk endpoint bevat `Content-Security-Policy`
- [ ] Response op elk endpoint bevat `X-Request-ID`
- [ ] Response body > 1000 bytes wordt geretourneerd met `Content-Encoding: gzip`

### Beveiligingschecks

- [ ] Tenant A kan data van Tenant B niet opvragen via een geldig JWT van Tenant A
- [ ] JWT zonder `tenant_id` claim produceert een auditlog-entry met `SecurityEvent.TENANT_CONTEXT_FAILED`
- [ ] `ENABLE_SECURITY_MIDDLEWARE=false` in productie-configuratie leidt tot falende CI (configuratievalidator)
- [ ] `/orchestrator`-endpoints zijn beveiligd in productie (`ENVIRONMENT=production` + `ENABLE_SECURITY_MIDDLEWARE=true`)

### Prestatiechecks

- [ ] P95-latentie van `GET /health` < 5 ms (geen middleware-overhead)
- [ ] P95-latentie van `GET /api/v1/agents` (gecachede query) < 200 ms

---

## Definition of Done

- [ ] Alle 12 middlewares zijn gedocumenteerd in deze spec met doel, configuratie, foutcodes en uitzonderingen
- [ ] Uitvoervolgorde is correct beschreven en geverifieerd tegen `setup_middleware()` broncode
- [ ] OA-005 (`/orchestrator` als PUBLIC) is geregistreerd als ticket voor go-live
- [ ] OA-001 (hardcoded tier-limieten) is geregistreerd als backlog-item
- [ ] QA-checks zijn opgenomen in de testmatrix
- [ ] Spec is gereviewd door een tweede lezer (zie `docs/frontend/review/` voor het reviewpatroon)
- [ ] Spec is geregistreerd in `docs/backend/features/ID-REGISTRY.md` onder BE-003

---

## Trainingssamenvatting

### Flow: Authenticated request doorloopt de middleware stack

- **Actor:** Frontend-gebruiker (of API-client) met geldig JWT in `Authorization: Bearer` header of `access_token` cookie.
- **Voorwaarde:** Backend draait met `setup_middleware()` correct geregistreerd; JWT bevat verplichte claims `sub`, `tenant_id`, `roles`; SecurityMiddleware staat aan (`ENABLE_SECURITY_MIDDLEWARE=true`).
- **Actie:** Client doet bijvoorbeeld `POST /api/v1/agents` met JSON body en `Authorization: Bearer <jwt>`.
- **Systeemreactie:** Request doorloopt de stack van buiten naar binnen (zie BE-FLW-005): ProbeBypass (geen match, doorgaan), CORS (HTTPS-origin OK), WebSocketCORS (HTTP-scope, doorgaan), ToolBrokerMetrics + Prometheus + PerformanceProfiling (counters/timers), TenantMiddleware (token extract -> `jwt_handler.verify_token()` -> `set_tenant_id(tenant_id)` in ContextVar), TenantQuotaMiddleware (POST + path matcht `/api/agents` -> count-quota check tegen Tenant.subscription_tier), GZip (response-fase), HTTPSRedirect (HTTPS al actief, skip), SecurityHeaders (CSP/HSTS/X-Frame-Options injection), SecurityMiddleware (IP + rate-limit + threat detection + auth verify). Daarna bereikt request de route-handler die ORM-queries doet -- `do_orm_execute` hook (ADR-004) injecteert automatisch `WHERE tenant_id = <ContextVar>`.
- **Succesrespons:** HTTP 201 met `X-Request-ID` header, security-headers ingevuld, response gecomprimeerd als > 1000 bytes. `finally`-blok in TenantMiddleware roept `clear_tenant_context()` aan zodat de ContextVar niet lekt naar de volgende request in dezelfde worker.
- **Foutrespons:**
  - Geen token: 401 `{"error": "Missing or invalid authentication"}` (TenantMiddleware).
  - Token zonder `tenant_id` claim: 401 `{"error": "Token missing tenant context"}` + SecurityEvent.TENANT_CONTEXT_FAILED auditlog.
  - Tier-quota overschreden (free tier, 3e agent): 403 `{"detail": "Resource limit reached (2). Please upgrade your plan."}` (TenantQuotaMiddleware).
  - Rate limit per IP overschreden: 429 met `retry_after: 60` (SecurityMiddleware).
  - IP buiten allowlist (alleen productie): 403 `{"error": "Access denied"}`.
- **Uitzonderingen:** OPTIONS preflight wordt door CORSMiddleware afgevangen (204) zonder dat TenantMiddleware draait. Paden in `PublicEndpointRegistry` of `EXCLUDED_PREFIXES` (`/health`, `/ready`, `/metrics`, `/api/v1/auth`, `/docs`, `/openapi.json`) slaan TenantMiddleware over. `/orchestrator` is tijdelijk `SecurityLevel.PUBLIC` (OA-005, verwijderen vóór go-live). `ENABLE_SECURITY_MIDDLEWARE=false` schakelt IP/rate/threat/auth-checks uit -- uitsluitend voor integratietests.

