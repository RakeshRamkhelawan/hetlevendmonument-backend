# BE-EP-013 -- Agent Heartbeat Endpoint

**ID:** BE-EP-013
**Sprint:** SP-E08
**Datum:** 2026-05-30
**Bestand:** `src/core/api/v1/als/router.py` -- `get_agent_heartbeat`
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Nieuw `GET /api/v1/als/agents/{agent_id}/heartbeat` endpoint dat de echte status van
een geregistreerde agent ophaalt uit de `OrganismRegistry` tabel (DB-backed, geen
state-verlies bij worker-restart). Vervangen van de nep-data die
`HeartbeatMonitor.tsx` eerder zelf genereerde.

---

## Endpoint

| Methode | Pad | Authenticatie |
|---------|-----|---------------|
| GET | `/api/v1/als/agents/{agent_id}/heartbeat` | JWT via `get_current_tenant_id` |

**Succesrespons (200):**
```json
{
  "success": true,
  "data": {
    "agent_id": "email-agent-1",
    "status": "online",
    "last_seen": "2026-05-30T00:05:00+00:00",
    "response_time_ms": null,
    "error_rate": null
  }
}
```

**Onbekend agent (200, niet 404):**
```json
{"success": true, "data": {"agent_id": "...", "status": "unknown", ...nulls}}
```

---

## Architectuurbeslissingen

1. **DB-backed via OrganismRegistry:** Geen aparte in-memory monitoring service.
   OrganismRegistry tabel is al tenant-scoped en bevat `status` + `last_heartbeat`.
2. **status='unknown' bij onbekend agent:** 200 met unknown-status, geen 404.
   Monitoring dashboard verwacht altijd een response, ook voor niet-gevonden agents.
3. **response_time_ms/error_rate = null (MVP):** Historische metrics vereisen een
   aparte time-series opslag. Dit wordt bewust uitgesteld als post-MVP verbetering.

---

## Trainingssamenvatting

### Flow: Operator vraagt agent heartbeat op

| Veld | Inhoud |
|------|--------|
| **Actor** | Platform operator / HeartbeatMonitor dashboard |
| **Voorwaarde** | Agent is geregistreerd via OrganismRegistry OF onbekend |
| **Actie** | `GET /api/v1/als/agents/{agent_id}/heartbeat` |
| **Systeemverwerking** | `select(OrganismRegistry).where(agent_id=..., tenant_id=...)` |
| **Succesrespons** | HTTP 200 + status uit DB (healthy/degraded/unknown) |
| **Foutrespons** | HTTP 401/403 bij ontbrekende auth |
| **Uitzonderingen** | Agent onbekend: status='unknown', response_time_ms=null (MVP beperking) |

---

## Tests

- `tests/unit/test_sp_e08_heartbeat.py::TestHeartbeatEndpointExists` (5 tests)
