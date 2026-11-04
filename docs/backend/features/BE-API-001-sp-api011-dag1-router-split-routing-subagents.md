# BE-API-001: SP-API-011 Dag 1 -- Router split routing + subagents (ADR-033)

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-API-001 |
| Sprint | SP-API-011 Dag 1 |
| Status | APPROVED |
| Datum | 2026-06-19 |
| Auteur | Claude (Sonnet 4.6) |

---

## Samenvatting

ADR-033 legt een harde grens van 200 regels per `router.py`. Dag 1 splitst twee van de vier oversized routers:

| Bestand | Voor | Na |
|---------|------|-----|
| `src/core/api/v1/routing/router.py` | 202 regels | 11 regels (composiet) |
| `src/core/api/v1/subagents/router.py` | 438 regels | 19 regels (composiet) |

---

## Gewijzigde bestanden

### Nieuw aangemaakt

| Bestand | Inhoud |
|---------|--------|
| `src/core/api/v1/routing/router_ops.py` | POST /test + POST /feedback + RouteRequest/RouteResponse schemas |
| `src/core/api/v1/routing/router_monitor.py` | GET /stats + GET /health |
| `src/core/api/v1/subagents/router_discovery.py` | GET /discover + /list + /metrics + /health + `_build_agent_list()` |
| `src/core/api/v1/subagents/router_management.py` | POST /load + /instantiate + /load-all + DELETE /unload/{name} |
| `src/core/api/v1/subagents/router_execution.py` | POST /action + GET /status/{name} + /types/{type} |

### Gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/routing/router.py` | Composiet: 202r -> 11r. include_router(ops, monitor). `# orphan:exempt` hersteld. |
| `src/core/api/v1/subagents/router.py` | Composiet: 438r -> 19r. include_router(discovery, management, execution). Re-exports voor legacy shim + test patches. |
| `tests/unit/test_subagent_endpoints.py` | 2 patch-targets bijgewerkt naar sub-module na split: `router.AgentStatus` -> `router_discovery.AgentStatus` (test_discover) + `router_management.AgentStatus` (test_instantiate_not_loaded). |

---

## ADR-033 Laag 1 patroon

- Composiet `router.py`: alleen `APIRouter(prefix=..., tags=[...])` + `include_router()` aanroepen
- Sub-routers: eigen `APIRouter(tags=[...])` zonder prefix (prefix geerfend van composiet)
- Re-exports in composiet voor:
  - Legacy shim `src/core/api/subagent_endpoints.py`: `discover_agents`, `list_agents`, `load_agents`, `instantiate_agent`, `get_agent_status`
  - Test patches: `AgentStatus`, `get_subagent_loader`, `get_current_user`, `require_scopes`

---

## Testresultaten

```
325 passed, 14 xfailed, 1 xpassed
```

- `tests/unit/test_subagent_endpoints.py`: 12/12 PASS
- `tests/unit/api/v1/test_no_dict_str_e_leak.py`: 3/3 PASS
- `tests/architecture/test_api_layer.py::test_no_orphan_routers`: PASS
- `tests/architecture/test_dsm_grade_a_plus.py::test_router_size_limit_adr033`: XFAIL (verwacht -- auth + governance_admin nog te splitsen in Dag 2+3)

---

## Pyright

```
0 errors, 55 warnings
```

Baseline (commit b1398e4c) intact.

---

## Openstaande oversized routers (Dag 2+3)

| Bestand | Regels | Dag |
|---------|--------|-----|
| `src/core/api/auth/router.py` | 1106 | Dag 3 |
| `src/core/api/v1/governance_admin/router.py` | 528 | Dag 2 |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-API-011 Dag 1: routing/router.py 202r->11r + subagents/router.py 438r->19r. 5 sub-routers aangemaakt. Re-exports voor legacy shim. 2 patch-targets bijgewerkt. 325 tests PASS. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-API-011 Dag 1: routing/router.py 202r->11r + subagents/router.py 438r->19r. 5 sub-routers aangemaakt. Re-exports voor legacy shim. 2 patch-targets bijgewerkt. 325 tests PASS..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
