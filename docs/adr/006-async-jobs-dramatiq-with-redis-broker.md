# ADR-006: Async Jobs - Dramatiq met Redis Broker

## Status
Accepted | Geimplementeerd op 2026-04-10

## Implementatie

**Uitgevoerd door:** Rakesh Ramkhelawan
**Datum:** 2026-04-10
**PR/branch:** main

### Wat is gewijzigd

| Bestand | Wijziging |
| :--- | :--- |
| `docker-compose.yml` | `rabbitmq` service, `rabbitmq_data` volume en alle `depends_on` refs verwijderd |
| `docker-compose.dev.yml` | `rabbitmq` uit `backend.depends_on` verwijderd |
| `docker-compose.prod.yml` | `rabbitmq` uit `backend.depends_on` verwijderd |
| `docker-compose.test.yml` | `rabbitmq-test` service, volume en deps verwijderd |
| `docker-compose.secrets.yml` | `rabbitmq_password` secret verwijderd |
| `src/core/events/publisher.py` | Volledig herschreven: `aio_pika` vervangen door `RedisPubSubManager` |
| `src/core/events/consumer.py` | Volledig herschreven: `aio_pika` vervangen door Redis-gebaseerde consumer |
| `src/core/events/handlers.py` | Docstrings bijgewerkt, emoji's vervangen door ASCII |
| `src/core/app_lifespan.py` | `RABBITMQ_URL` verwijderd, `_init_event_system` vereenvoudigd, cleanup-volgorde gecorrigeerd |
| `src/core/config/config_validator.py` | `RABBITMQ_USER/PASSWORD` vervangen door `REDIS_URL/REDIS_PASSWORD` |
| `src/core/api/health_endpoints.py` | RabbitMQ health check vervangen door Redis event consumer check |
| `requirements-base.txt` | `aio-pika>=9.4.0` verwijderd |
| `start_sanskritisetu.py` | `rabbitmq` uit service-lijsten, poortcheck en helptext verwijderd |

### Bijkomende fixes tijdens implementatie

- `DomainEvent.timestamp` mutable default bug opgelost (`Field(default_factory=...)`)
- Cleanup-volgorde gecorrigeerd: consumer/publisher sluiten voor Redis
- Non-ASCII/emoji logger-calls vervangen door ASCII conform CLAUDE.md regel 10
- `register_legacy_handlers` dode code-pad verwijderd uit lifespan
- `test_health_endpoints.py`: stale `rabbitmq` check-assertion en `ConnectionKey` bug opgelost

## Context
AI-operaties (zoals RAG, vector-indexering en agent-besluitvorming) zijn tijdsintensief en kunnen niet synchroon in de request-response cyclus van FastAPI worden afgehandeld. We hebben een betrouwbaar asynchroon task-queue systeem nodig.

### Eisen
1. **Betrouwbaarheid**: Taken mogen niet verloren gaan bij een crash.
2. **Observability**: We moeten weten waarom een taak faalt.
3. **Multi-tenancy**: Taken moeten tenant-aware zijn (ADR-004 doorvoeren in workers).

### Alternatieven
| Tool | Voordeel | Nadeel | Besluit |
| :--- | :--- | :--- | :--- |
| **Celery** | Industriestandaard | Complex; zware configuratie; "bloated" | **Afgewezen** |
| **FastAPI BackgroundTasks** | Simpel | Geen persistence; draait in web-proces | **Afgewezen** |
| **Dramatiq** | Simpel; robuust; focus op betrouwbaarheid | Kleindere community dan Celery | **Geselecteerd** |

## Decision
We gebruiken **Dramatiq** met **Redis** als message broker voor alle asynchrone processen.

### 1. Worker Configuratie & Middlewares
Workers worden geconfigureerd met specifieke middlewares voor stabiliteit:
```python
# src/workers/workflow_worker.py
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries, AsyncIO

redis_broker = RedisBroker(url=REDIS_URL)
redis_broker.add_middleware(Retries(max_retries=5))
redis_broker.add_middleware(AsyncIO()) # Voor async/await support
dramatiq.set_broker(redis_broker)
```

### 2. Retry & Backoff Policy (SLO)
Om te voorkomen dat workers overspoeld worden door falende AI-calls (bijv. LLM timeouts), hanteren we een exponentiële backoff:
| Parameter | Waarde | Doel |
| :--- | :--- | :--- |
| **Max Retries** | 5 | Voorkomt "poison pills" |
| **Backoff Factor** | 2 | Exponentiële vertraging (1s, 2s, 4s, ...) |
| **Time Limit** | 300s | Harde kill na 5 minuten voor AI-tasks |

### 3. Tenant Context Injection
Dramatiq actors moeten de `tenant_id` meekrijgen en de context handmatig herstellen:
```python
@dramatiq.actor
async def execute_task(task_id: str, tenant_id: str):
    set_tenant_context(tenant_id)
    # De automatische SQLAlchemy filters (ADR-004) werken nu ook in de worker!
```

## Consequences
- **Positive**:
    - Ontkoppeling van zware AI-workloads van de webserver.
    - Automatische herpogingen bij transient errors (API timeouts).
- **Negative**:
    - Extra infra-component (Redis) om te monitoren.
    - Race-conditions bij state-updates moeten worden voorkomen via locking of state-machines (ADR-007).
- **Degrade Mode**:
    - Bij Redis outage: Queue taken in-memory in het webproces (tijdelijk) met een waarschuwing in de UI dat resultaten vertraagd kunnen zijn.
    - Bij Worker overload: Prioritiseer "Chat" taken boven "Batch Indexing".
