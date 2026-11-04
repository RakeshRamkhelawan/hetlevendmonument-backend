# BE-RTR-033 -- Subagents Domain Migration naar v1/subagents/ (SP-API-007 Dag 3)

**Sprint:** SP-API-007 Dag 3
**Datum:** 2026-06-05
**Status:** DONE

---

## Beschrijving

`subagent_endpoints.py` (579r, 11 routes) gemigreerd naar `src/core/api/v1/subagents/` via ADR-033 drie-laags compositie. Strangler Fig stap 1.

**domain_router:** GEEN prefix -- sub-router bevat `/api/v1/subagents`.

**11 routes:** discover, list, metrics, health, load, unload/{name}, status/{name}, reload/{name}, instantiate, action/{name}, load-all

**Bugfix:** `agent.stop` via `getattr` (Pyright-safe, `hasattr` guard gebleven voor runtime).

---

## Trainingssamenvatting

### Flow: subagent unloaden

**Actor:** Admin gebruiker
**Actie:** DELETE /api/v1/subagents/unload/{agent_name}
**Systeemverwerking:** unload_agent → `getattr(agent, "stop", None)` voor graceful shutdown → status UNLOADED
**Succesrespons:** 200 met unload bevestiging
**Foutrespons:** 404 als agent niet bestaat
