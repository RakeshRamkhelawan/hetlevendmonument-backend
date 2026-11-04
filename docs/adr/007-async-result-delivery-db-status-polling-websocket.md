# ADR-007: Async Result Delivery - Database State Machine

## Status
Accepted

## Context
Zodra een asynchrone taak is gestart (ADR-006), moet de frontend op de hoogte blijven van de voortgang en het eindresultaat. We hebben een patroon nodig dat werkt voor zowel incidentele polling als real-time updates.

## Decision
We gebruiken de database als de **Source of Truth** voor taak-status, beheerd via een eenvoudige state-machine.

### 1. Task State Machine
Elke asynchrone taak heeft een record in de `task_executions` tabel met de volgende statussen:
| Status | Betekenis | UI Actie |
| :--- | :--- | :--- |
| `PENDING` | Taak staat in Redis queue | Toon spinner |
| `RUNNING` | Worker is gestart | Toon voortgangsbalk |
| `COMPLETED`| Resultaat is beschikbaar | Toon resultaat |
| `FAILED` | Fatale fout na 5 retries | Toon error / retry button |
| `RETRYING` | Wachten op backoff | "Retrying in X sec" |

### 2. Delvery Mechanismes
- **Baseline (Polling)**: De frontend pollt `GET /api/v1/tasks/{id}` elke 2-5 seconden. Dit is de fallback als WebSockets falen.
- **Enhanced (WebSockets)**: Bij statuswijzigingen stuurt de worker een signaal (via Redis Pub/Sub, zie ADR-008) dat een WebSocket event triggert.

### 3. Result Payload Structure
Resultaten worden opgeslagen in een JSONB kolom om flexibiliteit te bieden voor verschillende AI-outputs:
```python
# Voorbeeld schema
class TaskExecution(Base):
    id = Column(UUID, primary_key=True)
    status = Column(Enum(TaskStatus))
    result = Column(JSONB) # Bevat LLM output of error details
    tenant_id = Column(UUID, nullable=False) # Verplicht (ADR-005)
```

## Consequences
- **Positive**:
    - Robuust: Zelfs als de browser ververst, blijft de status van de taak behouden.
    - Audit Trail: Elke workflow-stap is gedocumenteerd in de DB.
- **Negative**:
    - Schrijfdruk op de database bij zeer veel kortstondige taken (te mitigeren via batch-updates voor logs).
- **Notes**:
    - Onvoltooide taken (`PENDING`/`RUNNING`) ouder dan 1 uur worden door een cleanup-cronjob gemarkeerd als `STALE/FAILED`.

## Implementatie stale-task cleanup (2026-05-22)

De cleanup-actor is geïmplementeerd als `cleanup_stale_tasks` Dramatiq actor in `src/workers/actors.py`:

**Stale criteria (1-uur timeout):**

- `status = PENDING` EN `created_at < NOW() - 1h` EN `started_at IS NULL`
- `status = RUNNING` EN `started_at < NOW() - 1h`

**Uitvoering:** APScheduler (`CronTrigger(minute=30)`) — uurlijks op :30.

**Tenant-isolatie:** `TenantFilterBypass` context manager vereist in worker-processen (geen request-middleware → ORM hook zou anders `WHERE 1=0` injecteren).

**error_json bij cleanup:**

```json
{"type": "StaleTaskError", "message": "Stale task cleanup: exceeded 1-hour timeout"}
```

**Database index:** `idx_c7_execution_task_status_created ON c7_execution_tasks (status, created_at)` via migratie `20260522b_stale_task_index`.
