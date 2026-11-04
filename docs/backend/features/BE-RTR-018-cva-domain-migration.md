# BE-RTR-018 -- CVA Domain Migration naar v1/cva/ (ADR-033)

**Sprint:** SP-API-004 Dag 3
**Datum:** 2026-06-04
**Status:** DONE

---

## Beschrijving

`cva_endpoints.py` (1110r) is gemigreerd naar de drie-laags ADR-033 structuur in
`src/core/api/v1/cva/`. Strangler Fig stap 1: routing gereorganiseerd, business
logica blijft in het flat bestand (re-export shim).

**Twee originele routers gemigreerd:**
- `router` (prefix `/api/v1/cva`) -- 12 routes
- `public_router` (prefix `/cva`) -- 2 routes

**Sub-routers:**

| Bestand | Routes | Regels |
|---|---|---|
| `chat_router.py` | POST /chat, POST /chat/stream | 220r (`# orphan:exempt` r1) |
| `legacy_router.py` | POST /chat/legacy | 185r |
| `conversations_router.py` | GET /conversations, GET /conversations/{id}, DELETE /conversations/{id} | 141r |
| `management_router.py` | GET /status, GET /status-detail, POST /optimize, GET /analytics, GET /health, POST /shutdown | 248r (`# orphan:exempt` r1) |
| `public_router.py` | POST /create_agent, POST /execute/{agent_id} | 171r |
| `state.py` | _cva_agents cache + get_cva_agent() | 29r |
| `router.py` | Composite | 16r |
| `__init__.py` | domain_router ZONDER prefix | 11r |

**Structurele beslissing:** `domain_router` heeft GEEN prefix -- de sub-routers
bevatten al hun volledige prefixes (`/api/v1/cva` of `/cva`). Dit matcht het
bestaande export-patroon van `cva_endpoints.py` regel 1106-1110.

**Gedeelde cache:** `_cva_agents: dict[int, UltimateCVAAgent]` verplaatst naar
`state.py` zodat alle sub-routers dezelfde instantie delen.

---

## Trainingssamenvatting

### Flow: CVA chat aanvragen

**Actor:** Geauthenticeerde gebruiker
**Voorwaarde:** Geldige JWT met tenant_id claim
**Actie:** POST /api/v1/cva/chat met prompt in request body
**Systeemverwerking:** chat_router delegeert naar UltimateCVAAgent uit state.py cache
**Succesrespons:** 200 ChatResponse met AI-antwoord
**Foutrespons:** 503 als CVA agent niet beschikbaar; 401 zonder auth
**Uitzonderingen:** POST /cva/create_agent via public_router (andere prefix, geen auth)

### Flow: CVA domein toevoegen aan registry

**Actor:** Backend developer
**Actie:** Import `from src.core.api.v1.cva import domain_router` in registry
**Let op:** domain_router heeft GEEN prefix -- sub-routers bevatten eigen prefix
**Test:** `pytest tests/architecture/test_registry_equivalence.py::test_cva_flat_file_migrated_to_v1`
