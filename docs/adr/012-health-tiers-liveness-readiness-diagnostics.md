# ADR-012: Health Tiers - Liveness, Readiness & Diagnostics

## Status
Accepted

## Context
In een microservices architectuur met AI-dependencies is een simpele "up/down" check onvoldoende. Een service kan "up" zijn (proces draait), maar niet in staat zijn om AI-requests te verwerken door een timeout naar de LLM provider of een volle database pool. We hebben gedifferentieerde health-informatie nodig voor orchestrators (Docker/K8s) en on-call engineers.

## Decision
We implementeren drie specifieke Health Tiers met verschillende scopes en timeouts.

### 1. Health Tiers Tabel
| Endpoint | Type | Scope | Target | Timeout |
| :--- | :--- | :--- | :--- | :--- |
| `/health` | **Liveness** | Is het Python proces alive? | Orchestrator (Restart policy) | < 50ms |
| `/health/ready` | **Readiness** | Zijn kritieke deps (DB, Redis) bereikbaar? | Load Balancer (Routing) | < 500ms |
| `/health/db` | **Diagnostics** | Diepe check van migratie-status en pool-stats. | Engineers (Debugging) | < 2s |

### 2. Readiness Logic & Graceful Degradation (SLO)
De `/health/ready` check volgt een strikte logica:
- **Kritieke Fout**: Als PostgreSQL of Redis onbereikbaar is -> `503 Service Unavailable`. De service wordt uit de load balancer gehaald.
- **Gedegradeerd**: Als een LLM provider (bijv. Anthropic) traag is maar de rest werkt -> `200 OK` met een `warning` payload. De service blijft in de load balancer, maar de agent-functies kunnen trager zijn.

### 3. Implementatie Voorbeeld
```python
# src/api/v1/endpoints/health_endpoints.py
@router.get("/ready")
async def readiness_check():
    db_ok = await check_db_latency() # Max 200ms
    redis_ok = await check_redis()   # Max 100ms

    if not (db_ok and redis_ok):
        raise HTTPException(status_code=503, detail="Critical dependency missing")

    return {"status": "ready", "checks": {"db": "ok", "redis": "ok"}}
```

## Consequences
- **Positive**:
    - Voorkomt "cascading failures": Verkeer wordt alleen naar gezonde instanties gestuurd.
    - Snelheid: Liveness checks zijn extreem lichtgewicht.
- **Negative**:
    - Readiness checks voegen extra belasting toe op de database pool.
- **Notes**:
    - Timeouts op probes zijn cruciaal (ADR-011). Een hangende health check is net zo erg als een failure.

## Implementatie (2026-05-26)

3-tier health checks actief in `src/core/api/health_endpoints.py`:

- `/health` — liveness, Python process alive check
- `/health/ready` — readiness, PostgreSQL + Redis bereikbaarheid
- `/health/db` — diagnostics, Alembic migratiestatus + pool statistieken

Auto-rollback in `cd-production.yml` gebruikt `/health` als smoke test trigger.
RTO ~8 min, RPO ~1 min — zie `docs/build-stack-security/sprint-3-day-5-dr-test-report.md`.

## SOC 2 Mapping

Dit ADR levert aantoonbaar bewijs voor de volgende SOC 2 Security Criteria:

| Criterium | Subcriteria | Hoe dit ADR voldoet |
| --------- | ---------- | ------------------- |
| CC7.1 | Detection and monitoring of anomalies | 3-tier health checks detecteren afwijkingen op procesniveau (liveness), dependency-niveau (readiness) en configuratieniveau (diagnostics); elke tier heeft een aparte timeout en scope |
| CC7.2 | Monitoring tools implemented | `/health` (< 50ms liveness), `/health/ready` (< 500ms readiness met DB + Redis check), `/health/db` (< 2s diagnostics met migratiestatus en pool-statistieken) zijn geimplementeerd en actief bevraagd door de load balancer |
| CC7.3 | System incidents identified and communicated | `503 Service Unavailable` bij kritieke dependency-fout leidt tot automatische verwijdering uit de load balancer; `200 OK` met `warning` payload bij gedegradeerde staat informeert on-call engineers zonder verkeer te onderbreken |
| CC7.5 | Disaster recovery | Health checks zijn de trigger voor auto-rollback in `cd-production.yml`; smoke test na deployment valideert herstel; RTO ~8 min, RPO ~1 min (zie ADR-030) |

### Open gaps richting volledige SOC 2 Type I readiness

- Geen geautomatiseerde DR-test op schema — jaarlijks handmatig uitvoeren en het resulterende rapport opslaan als SOC 2 bewijs is nog niet ingepland als terugkerend proces
- Geen formeel incident response plan als ondertekend beleidsdocument — de procedure bestaat in runbooks maar is niet vastgelegd als een door management goedgekeurd en gedateerd document
