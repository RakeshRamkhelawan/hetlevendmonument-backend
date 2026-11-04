# BE-SEC-001: FA-SEC-001 Agent Discovery Tenant Isolation Fix

**Sprint:** FA-SEC-001 (one-off security fix)
**Status:** COMPLETED
**Datum:** 2026-06-11
**Auteur:** Claude (Sonnet 4.6)

---

## Samenvatting

P0 security fix: alle 6 endpoints onder `/api/v1/agentic/discovery` waren opgenomen in
`PUBLIC_PREFIXES`, waardoor `TenantMiddleware` de JWT-extractie oversloeg. Dit resulteerde
in `get_tenant_id()` die `None` teruggaf, en `_get_all_agents(None, db)` die een
ongefiltreerde `SELECT * FROM registered_agents` uitvoerde -- alle agents van alle tenants
werden teruggegeven aan elke ongeauthenticeerde aanvrager.

---

## Root Cause

1. `/api/v1/agentic/discovery` in `PublicEndpointRegistry.PUBLIC_PREFIXES`
2. `TenantMiddleware` slaat JWT-extractie over voor publieke paden
3. `get_tenant_id()` returnt `None` als ContextVar niet gezet is
4. `_get_all_agents(None, db)` had een `if tenant_id is None:` branch met `select(RegisteredAgent)` zonder WHERE clause
5. ADR-004 `do_orm_execute` hook niet geimplementeerd -- geen compenserend control

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/middleware/public_registry.py` | `/api/v1/agentic/discovery` verwijderd uit `PUBLIC_PREFIXES` |
| `src/core/api/v1/agentic/agent_discovery.py` | Router-level auth dependency; `require_tenant_id()` i.p.v. `get_tenant_id()`; None-branch verwijderd; signaturen `int\|None` -> `int`; 3x 404 info-leaks gefixed |
| `tests/architecture/test_agent_discovery_auth.py` | Twee architecture tests (RED->GREEN bewijs) |
| `tests/integration/test_agent_discovery_endpoints.py` | `TestDiscoveryTenantIsolation` updated: 6 tests asserteren 401; info-leak assertions verwijderd |

---

## Implementatiedetails

### public_registry.py
Verwijderd uit `PUBLIC_PREFIXES`:
```python
"/api/v1/agentic/discovery",
```

### agent_discovery.py
Router heeft nu auth dependency:
```python
router = APIRouter(
    prefix="/discovery",
    tags=["Agent Discovery"],
    dependencies=[Depends(get_current_user)],
)
```

`_get_all_agents` signature gewijzigd van `int | None` naar `int`:
```python
async def _get_all_agents(tenant_id: int, session: AsyncSession) -> list[AgentDiscoveryItem]:
```

6 aanroepen `get_tenant_id()` vervangen door `require_tenant_id()` (fail-secure: gooit
`RuntimeError` als tenant context niet gezet is -- TenantMiddleware blokkeert voor het
zover komt).

3 info-leaks in 404 details verwijderd:
- `f"No agents found in department: {department}"` -> `"Department not found"`
- `f"No agents found with function: {function}"` -> `"Function not found"`
- `f"Agent not found: {agent_id}"` -> `"Agent not found"`

---

## Tests

### Architecture tests (RED->GREEN bewijs)
- `test_agent_discovery_not_in_public_prefixes` -- verifieert PUBLIC_PREFIXES entry afwezig
- `test_agent_discovery_no_unfiltered_tenant_none_branch` -- AST-check op afwezigheid None-branch

### Integration tests
- `TestDiscoveryTenantIsolation`: 6 tests asserteren nu 401 voor unauthenticated requests

### Unit tests
- `tests/unit/test_agent_discovery_find_by_functions.py`: 6/6 PASSED

---

## Verificatie

```bash
python -m pytest tests/architecture/test_agent_discovery_auth.py -v --timeout=30
# 2 passed

python -m pytest tests/unit/test_agent_discovery_find_by_functions.py -q --timeout=30
# 6 passed

python -m pytest tests/architecture/ tests/unit/api/ -q --tb=short --timeout=30
# 191 passed, 12 xfailed

python -m pyright
# 0 errors, 55 warnings
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
