# Batch 03 — Gate 2b: Downstream Caller Check

## Methode
Voor elke gewijzigde functie-parameter / return type zijn de call sites in `src/` gecontroleerd.

## Resultaten per bestand

### 1. `src/core/events/handlers/notification_handler.py`

| Functie | Gewijzigd type | Caller(s) | Caller type | Regressie? |
|---------|---------------|-----------|-------------|------------|
| `NotificationEventHandler.__init__` | geen wijziging | `app_lifespan.py:347` | `RedisPubSubManager` | **Geen risico** |
| `register_handlers` | geen wijziging | `app_lifespan.py:347` | n.v.t. | **Geen risico** |
| `_queue_notification` / `_process_notification` / senders | intern | n.v.t. | **Geen risico** |
| `get_queue_stats` | `QueueStats` TypedDict | geen callers in src/ | n.v.t. | **Geen risico** |

### 2. `src/core/database/vacuum_manager.py`

| Functie | Gewijzigd type | Caller(s) | Regressie? |
|---------|---------------|-----------|------------|
| `VacuumManager.__init__` | geen wijziging | n.v.t. | **Geen risico** |
| `get_table_stats` | return `list[TableStats]` | intern | **Geen risico** |
| `vacuum_table` | return `VacuumResult` TypedDict | intern (`vacuum_all_tables`) | **Geen risico** |
| `vacuum_all_tables` | return `list[VacuumResult]` | `run_scheduled_vacuum` | **Geen risico** |
| `get_autovacuum_settings` | return typed dict | geen externe callers | **Geen risico** |
| `get_bloat_report` | return `list[BloatRow]` | geen externe callers | **Geen risico** |

### 3. `src/core/api/v1/agentic/agents.py`

| Functie | Gewijzigd type | Caller(s) | Regressie? |
|---------|---------------|-----------|------------|
| FastAPI endpoints | Pydantic models / typed dicts | HTTP callers, geen directe Python callers | **Geen risico** |
| `ooda_profile` veld | `OodaProfile` Pydantic | request body; FastAPI coert | **Geen risico** |
| `errors` | `list[str]` | lokaal | **Geen risico** |

### 4. `src/core/memory/services/cleanup_service.py`

| Functie | Gewijzigd type | Caller(s) | Caller type | Regressie? |
|---------|---------------|-----------|-------------|------------|
| `filter_by_age_and_importance` | `Callable[[T], datetime/float]` | `facade.py:546/556/566` | `MemoryEntry -> datetime/float` | **Geen risico** — T is TypeVar |
| `cleanup_old_memories` | intern types | geen directe callers | n.v.t. | **Geen risico** |
| `get_memory_stats` | return typed dict | `facade.py` heeft eigen `get_memory_stats`; router.py heeft endpoint | **Geen risico** |

### 5. `src/core/jobs/retention_cleanup_job.py`

| Functie | Gewijzigd type | Caller(s) | Regressie? |
|---------|---------------|-----------|------------|
| `cleanup_by_jurisdiction` | return `CleanupStats` TypedDict | intern (`run_retention_cleanup`) | **Geen risico** |
| `run_retention_cleanup` | return `RetentionJobResult` TypedDict | `workers/actors.py` wrapper | **Geen risico** — wrapper gebruikt `.get()` |
| `get_retention_summary` | return `RetentionSummary` TypedDict | geen directe callers | **Geen risico** |

## Conclusie
Geen high-risk regressies geïdentificeerd. Alle wijzigingen zijn intern of backwards-compatible.
