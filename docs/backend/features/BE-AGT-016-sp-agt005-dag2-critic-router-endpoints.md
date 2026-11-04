# BE-AGT-016 -- SP-AGT-005 Dag 2: CriticAgent GET Endpoints + Router Refactor

**Sprint:** SP-AGT-005 Dag 2
**Datum:** 2026-06-19
**Status:** APPROVED
**Auteur:** Claude Sonnet 4.6

---

## Doel

Dag 2 van SP-AGT-005 voegt drie GET-endpoints toe aan de orchestration critic router:
`GET /critics/health`, `GET /critics/{agent_name}/report` en
`GET /critics/{agent_name}/common-issues`. Tegelijkertijd lost het een pre-existing bug op:
de dubbele `_critic_cache` en lokale `get_critic_agent` factory in `critic_router.py`
die `clear_tenant_cache()` in `dependencies.py` omzeilden.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/orchestration/critic_router.py` | Dubbele cache verwijderd; 3 GET-endpoints toegevoegd; `tenant_id = critic.tenant_id` |
| `src/core/api/v1/orchestration/dependencies.py` | `consent_read_limit` re-export toegevoegd; `__all__` bijgewerkt |
| `src/core/agents/critic_agent.py` | `get_common_issues()` methode toegevoegd; 2 log-calls gefixd; `Optional` verwijderd |
| `src/core/agents/critique_store.py` | Return type `get_common_issues` vernauwd: `list[tuple[Any,...]]` -> `list[tuple[str,int]]` |
| `tests/unit/agents/test_critic_router_endpoints.py` | 5 nieuwe unit tests (RED->GREEN) |

---

## Technische details

### Endpoint 1: `GET /critics/health`

```python
@critic_router.get("/health")
@consent_read_limit
async def get_critic_health(
    request: Request,
    critic: CriticAgent = Depends(get_critic_agent),
) -> dict[str, Any]:
    result = await critic.get_system_health()
    return {"success": True, "data": result}
```

- `@consent_read_limit` onder `@router.get()` (correct patroon -- zie `consent_router.py`)
- `request: Request` als eerste parameter zodat de rate limiter de `Request` kan vinden
- Delegeert naar `CriticAgent.get_system_health()` (bestaande methode)

### Endpoint 2: `GET /critics/{agent_name}/report`

- Delegeert naar `CriticAgent.get_agent_report(agent_name)` (bestaande methode)
- `agent_name: str = Path(..., max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$")` voor input-validatie

### Endpoint 3: `GET /critics/{agent_name}/common-issues`

- Delegeert naar nieuw `CriticAgent.get_common_issues(agent_name)`:
  ```python
  async def get_common_issues(self, agent_name: str, limit: int = 10) -> list[dict[str, Any]]:
      raw = await self._store.get_common_issues(self._tenant_id, agent_name, limit=limit)
      return [{"issue": issue, "count": count} for issue, count in raw]
  ```

### Bug fix: dubbele `_critic_cache`

`critic_router.py` had zijn eigen `_critic_cache` dict en `get_critic_agent` factory. Deze
omzeilden `clear_tenant_cache()` in `dependencies.py` -- een gesuspendeerde tenant kon
nooit worden ge-evict uit de router-lokale cache. Fix: lokale cache en factory verwijderd;
`get_critic_agent` geimporteerd uit `dependencies.py`.

### Decorator volgorde rate-limit

Correct patroon (geverifieerd in `consent_router.py`):
```
@router.get(...)     # boven
@consent_read_limit  # onder
async def endpoint(request: Request, ...):
```

`admin_digital_twin.py` heeft de volgorde OMGEKEERD en mist `request: Request` -- dat is
een pre-existing bug (rate limit wordt daar nooit gehandhaafd). Dag 2 volgt het correcte
patroon.

---

## Tests

Bestand: `tests/unit/agents/test_critic_router_endpoints.py`

| Test | Scenario |
|------|---------|
| `test_health_endpoint_returns_200_with_health_data` | Happy path: health 200 + data |
| `test_report_endpoint_returns_200_with_agent_report` | Happy path: report 200 + agent_name |
| `test_common_issues_endpoint_returns_list_of_dicts` | Happy path: issues list met issue+count |
| `test_health_endpoint_returns_401_without_tenant` | Unhappy: geen tenant -> 401 |
| `test_report_endpoint_returns_401_without_tenant` | Unhappy: geen tenant -> 401 |

Alle 5 tests: GROEN na implementatie.

---

## ADR compliance

| ADR | Naleving |
|-----|---------|
| ADR-033 | `consent_read_limit` via `dependencies.py` re-export -- geen directe governance import in router.py |
| ADR-034 | Geen nieuwe agent_runtime grensschendingen |
| Pattern 4 | GET-endpoints: `consent_read_limit` (60/min) |
| Pattern 7 | `{"success": True, "data": ...}` voor alle 3 GET-endpoints |
| Pattern 1 | `tenant_id` via `safe_get_tenant_id` (JWT-claim) via `get_critic_agent` |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-AGT-005 Dag 2: CriticAgent GET endpoints (health + report + common-issues) + router refactor (dubbele cache fix, consent_read_limit, Path validatie) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-AGT-005 Dag 2: CriticAgent GET endpoints (health + report + common-issues) + router refactor (dubbele cache fix, consent_read_limit, Path validatie).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
