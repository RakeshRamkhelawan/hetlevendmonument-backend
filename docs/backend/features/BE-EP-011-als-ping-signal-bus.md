# BE-EP-011 — ALS Ping via SignalBus

**ID:** BE-EP-011
**Sprint:** SP-E06
**Datum:** 2026-05-29
**Bestand:** `src/core/api/v1/als/router.py` — `ping_agent` endpoint
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Het `POST /als/agents/{agent_id}/ping` endpoint retourneerde voorheen altijd een hardcoded succesrespons zonder een signaal te verzenden (P1-11). Fix: het endpoint bouwt nu een `Signal`-object met `SignalTier.COGNITIVE`, verzendt dit via `get_orchestrator(tenant_id).signal_bus.emit(signal)`, en retourneert een gestructureerde respons conform CLAUDE.md §12. Foutafhandeling is consistent met de andere endpoints in hetzelfde router-bestand (timeout 504, bus-fout 503).

---

## Endpoint

| Methode | Pad | Authenticatie |
|---------|-----|---------------|
| POST | `/api/v1/als/agents/{agent_id}/ping` | JWT via `get_current_tenant_id` |

---

## Request / Response

**Request:** geen body; `agent_id` als path-parameter.

**Succesrespons (200):**
```json
{
  "success": true,
  "data": {
    "agent_id": "agent-001",
    "ping": "sent"
  }
}
```

**Foutrespons (504):** SignalBus-emit timed out (>30s).

**Foutrespons (503):** SignalBus onbereikbaar (Redis down of andere exception).

---

## Architectuurbeslissingen

1. **Orchestrator-gebaseerde SignalBus:** `get_orchestrator(tenant_id)` hergebruikt de bestaande per-tenant orchestrator en diens al-geconfigureerde `SignalBus`. Geen nieuwe Redis-verbinding of bus-instantie aangemaakt.
2. **SignalTier.COGNITIVE:** Ping is een normale query (niet urgent reflex). Cooldown-mechanisme in SignalBus geldt (max 1 signal/seconde per bron per tier bij standaard configuratie).
3. **asyncio.wait_for met ALS_ORCHESTRATOR_TIMEOUT_SECONDS (30s):** Consistent met `delegate_task`, `get_system_health` en `broadcast_message` in hetzelfde bestand.
4. **tenant_id uit JWT:** Via `Depends(get_current_tenant_id)` — nooit uit request body (CLAUDE.md §6).

---

## Trainingssamenvatting

### Flow: Agent pingen via ALS SignalBus

| Veld | Inhoud |
|------|--------|
| **Actor** | Operator of systeem dat de responsiviteit van een specifieke agent wil controleren |
| **Voorwaarde** | Agent `agent_id` bestaat in de ALS van tenant; SignalBus (Redis) bereikbaar |
| **Actie** | `POST /api/v1/als/agents/{agent_id}/ping` |
| **Systeemverwerking** | `Signal(tenant_id, source="als_api", target=[agent_id], tier=COGNITIVE, payload={action:"ping"})` aangemaakt; `orchestrator.signal_bus.emit(signal)` aangeroepen met 30s timeout |
| **Succesrespons** | HTTP 200 `{"success": true, "data": {"agent_id": "...", "ping": "sent"}}` |
| **Foutrespons** | Timeout (>30s) → HTTP 504. Bus-fout → HTTP 503. Geldig JWT ontbreekt → HTTP 401/403 via middleware. |
| **Uitzonderingen** | Ping-signaal kan silent worden dropped door SignalBus als cooldown actief is (default 1s per tenant/tier/source); endpoint retourneert dan alsnog 200 (by design — cooldown is een flux-control maatregel, geen error) |

---

## Tests

- `tests/unit/test_sp_e06_small_fixes.py::TestALSPing` (6 tests)
  - `test_todo_comment_removed`
  - `test_signal_tier_used_in_router`
  - `test_emit_called_in_ping_function`
  - `test_ping_response_has_success_field`
  - `test_ping_timestamp_uses_timezone_utc`
  - `test_als_ping_emits_signal_behavioral` (behavioral)
