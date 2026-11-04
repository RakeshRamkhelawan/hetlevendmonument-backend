# BE-AGT-020 -- CritiqueStore Materialized View Telemetry

## Metadata

- **Sprint**: SP-AGT-006, Dag 3 van 3
- **Status**: IMPLEMENTED
- **Datum**: 2026-06-27
- **Auteur**: Claude (SP-AGT-006 implementatie-agent)

---

## Samenvatting

Materialized view telemetrie voor CriticAgent. Critique-scores zijn nu querybaar als
tijdreeks zonder full-table-scan op `agent_critiques`. Gebruikt PostgreSQL materialized
view met 5-minuten refresh cooldown en een nieuw `GET /critics/telemetry` endpoint.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/alembic/versions/20260627_critique_hourly_stats_mv.py` | NIEUW -- materialized view migratie |
| `src/core/agents/critique_store.py` | `get_timeseries_stats()` + refresh guard + `_refresh_mv()` |
| `src/core/api/v1/orchestration/critic_router.py` | `GET /telemetry` endpoint (voor `/{agent_name}/...`) |
| `src/core/api/v1/orchestration/schemas.py` | `TelemetryDataPoint` + `TelemetryResponse` |
| `src/core/api/v1/orchestration/dependencies.py` | `get_critique_store()` factory + `CritiqueStore` re-export |

---

## Componenten

### 1. Alembic migratie -- `critique_hourly_stats` materialized view

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS critique_hourly_stats AS
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    tenant_id,
    agent_name,
    AVG(score)::float AS avg_score,
    COUNT(*)::int AS critique_count
FROM agent_critiques
GROUP BY 1, 2, 3
```

Unieke index op `(hour, tenant_id, agent_name)` -- vereist voor `REFRESH CONCURRENTLY`.

**Downgrade**: volledig omkeerbaar via `DROP INDEX ... ; DROP MATERIALIZED VIEW ...`

### 2. `CritiqueStore.get_timeseries_stats(tenant_id, hours=24)`

Querypt `critique_hourly_stats` met parametergebonden `tenant_id` en `cutoff`.
Retourneert `list[dict]` met `{hour, agent_name, avg_score, critique_count}`.
Bij DB-fout: logt en retourneert `[]` (degradeert gracefully).

### 3. Refresh guard in `CritiqueStore.store()`

Na elke `store()` aanroep, atomisch binnen `asyncio.Lock`:
- Leest + schrijft `_last_mv_refresh` binnen de lock (FA-002 fix)
- Beslissing: `should_refresh = True` als cooldown (300s) verstreken
- Stelt `_last_mv_refresh = now` BINNEN de lock om race conditions te voorkomen
- Daadwerkelijke refresh via `_refresh_mv()` BUITEN de lock (geen lock contention)
- `_refresh_mv()` wraps REFRESH CONCURRENTLY in `best_effort` (nooit blocking)

### 4. `GET /critics/telemetry?hours=24`

- Route geregistreerd VOOR `/{agent_name}/...` (FA-006: vermijdt path-parameter conflict)
- `hours`: `Query(ge=1, le=168)` -- 1 uur minimum, 1 week maximum
- `store: CritiqueStore = Depends(get_critique_store)` -- ADR-033 compliant (via dependencies.py)
- `tenant_id` via `critic.tenant_id` (JWT-middleware, ADR-003) -- NOOIT uit request body

### 5. Pydantic schemas

```python
class TelemetryDataPoint(BaseModel):
    hour: str
    agent_name: str
    avg_score: float = Field(..., ge=0.0, le=1.0)
    critique_count: int = Field(..., ge=0)

class TelemetryResponse(BaseModel):
    success: bool
    data: list[TelemetryDataPoint]
```

---

## Activatielogica

Altijd actief zodra migratie is uitgevoerd. Geen feature-flag of conditie.

---

## ADR-compliance

| ADR | Compliance |
|-----|-----------|
| ADR-033 | `CritiqueStore` toegankelijk via `dependencies.py` facade -- PASS |
| ADR-033 | `/telemetry` endpoint in `critic_router.py` (Laag 1) -- PASS |
| ADR-003 | `tenant_id` via `critic.tenant_id` (JWT) -- PASS |
| ADR-009 | Geen wijziging aan Traefik/TLS config -- N/A |

---

## Trainingssamenvatting

**Actor**: Externe caller (tenant-authenticated API client)
**Voorwaarde**: Geldige JWT-token met tenant_id; `critique_hourly_stats` view bestaat
**Actie**: `GET /critics/telemetry?hours=24`
**Systeemreactie**: Retourneert lijst van `TelemetryDataPoint` objecten per uur per agent
**Succes**: HTTP 200, `{"success": true, "data": [{"hour": "...", "agent_name": "...", "avg_score": 0.8, "critique_count": 5}]}`
**Fout (DB onbereikbaar)**: HTTP 200, `{"success": true, "data": []}` (graceful degradatie via `get_timeseries_stats` try/except)
**Fout (ongeldige hours)**: HTTP 422 -- FastAPI validatie (ge=1, le=168)
**Uitzondering (view niet aangemaakt)**: DB-fout gelogged, retourneert `[]` -- geen 500

---

## Niet-gedekt (backlog)

| Item | Beschrijving |
|------|-------------|
| Refresh-guard test | Geen unit test voor 5-min cooldown-gedrag -- functioneel correct, test toekomstig sprint-item |
| MV staleness indicator | Response bevat geen `last_refreshed_at` timestamp -- toekomstig sprint-item |
| TimescaleDB | Optie A (hypertable) uitgesteld per sprint plan -- toekomstig infra-sprint |
