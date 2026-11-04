# BE-SVC-053 — BP-002 GET /agents/ Paginering

**Sprint:** SP-SEC-002 Dag 1
**Datum:** 2026-07-01
**Status:** APPROVED

## Samenvatting

`GET /agents/` ondersteunt nu `limit` en `offset` query-parameters conform backend-patterns pattern 5. Fix toegepast op 3 call-sites: `list_agents()`, `list_agents_root()` (agent_endpoints.py) en `list_agents()` (agent_crud_router.py).

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/agent_endpoints.py` | `limit`/`offset` params + slicing op gefilterde agenten |
| `src/core/api/v1/agents/agent_crud_router.py` | `limit`/`offset` params + doorgifte aan delegatieaanroep |
| `tests/unit/api/test_agents_pagination.py` | Nieuw — 4 tests (3 signature + 1 gedrag) |

## API-contract

```
GET /agents/?limit=50&offset=0
GET /agents/?category=Technical&limit=20&offset=40

Response:
{
  "agents": [...],
  "total_count": 248    // pre-slice teller (post-filter)
}
```

## Implementatiedetail

```python
total_count = len(filtered_agents)
paged_agents = filtered_agents[offset : offset + limit]
return AgentListResponse(agents=paged_agents, total_count=total_count)
```

## ADR-compliance

- Pattern 5: `le=1000`, `ge=0`, defaults 50/0.
- ADR-033: `list_agents_root` als doorstuurendpoint zonder eigen logica.

## Testbewijs

```
tests/unit/api/test_agents_pagination.py — 4 passed
```

## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:read` scope.
- Voorwaarde: Geldige JWT; optionele query params `category`, `capability`, `source`, `limit` (default 50, max 1000) en `offset` (min 0).
- Actie (request): Verstuur `GET /api/v1/agents/?limit=50&offset=0`.
- Systeemverwerking: `list_agents` laadt enterprise-catalogus agents uit YAML, merged optioneel ActivePieces integraties, past filters toe, berekent `total_count = len(filtered_agents)` en slice `paged_agents = filtered_agents[offset:offset+limit]`.
- Succesrespons: HTTP 200 met `AgentListResponse` body `{"agents": [...], "total_count": <int>}`.
- Foutrespons: HTTP 503 `Agent registry service is unavailable` bij AttributeError; HTTP 500 `Internal error retrieving agents` bij onverwachte fout.
- Uitzonderingen: ActivePieces timeout levert graceful degradation (alleen native agents); `list_agents_root` en `agent_crud_router.list_agents` delegeren naar dezelfde implementatie.
