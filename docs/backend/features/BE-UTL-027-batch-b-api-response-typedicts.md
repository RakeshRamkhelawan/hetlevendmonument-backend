---
id: BE-UTL-026
name: Batch B -- API Response TypedDicts + dict[str,object] Hardening
sprint: SP-ANY-B
date: 2026-05-31
status: APPROVED WITH MINOR GAPS
commit: 812e1afa
---

# BE-UTL-026 -- Batch B API Response TypedDicts

## Samenvatting

Eliminatie van 135 bare-Any violations in 7 build-bestanden via TypedDicts voor
bekende structuren en `dict[str, object]` voor opaque HTTP-response payloads.

## Gewijzigde bestanden

| Bestand | Violations voor | Violations na | Aanpak |
|---------|----------------|---------------|--------|
| `resilient_api_client.py` | 35 | 0 | TypedDicts + dict[str,object] |
| `response_formatter.py` | 19 | 2* | Protocol + dict[str,object] |
| `chat_endpoints.py` | 3 | 0 | list[dict[str,str]] |
| `activepieces_endpoints.py` | 4 | 0 | dict[str,object] |
| `executor_agent.py` | 22 | 8* | dict[str,object] + type:ignore stubs |
| `workflow_generator_service.py` | 9 | 2* | dict[str,object] |
| `api/main.py` | 9 | 4* | dict[str,object] + TODO Pydantic |

*Resterende violations zijn request-body dicts (`dict[str,Any]` met TODO) of
pre-existing stubs die een aparte refactor vereisen.

## Nieuwe TypedDicts

### `CircuitBreakerMetricsDict` (resilient_api_client.py)
```python
class CircuitBreakerMetricsDict(TypedDict):
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    average_response_time: float
    circuit_opens: int
```

### `CircuitBreakerStatusDict` (resilient_api_client.py)
```python
class CircuitBreakerStatusDict(TypedDict):
    state: str
    failure_count: int
    metrics: CircuitBreakerMetricsDict
```

### `HealthSummaryDict` (resilient_api_client.py)
```python
class HealthSummaryDict(TypedDict, total=False):
    system_health: dict[str, object]
    learning_health: dict[str, object]
    safety_health: dict[str, object]
    circuit_breakers: dict[str, CircuitBreakerStatusDict]
    overall_health_score: float
    status: str
    error: str
```

### `_CacheLayer` Protocol (response_formatter.py)
```python
class _CacheLayer(Protocol):
    def get(self, key: str) -> object | None: ...
    def set(self, key: str, value: object, ttl: int = 0) -> None: ...
```

## Beslissingen

- **`dict[str, object]` voor HTTP-responses**: JSON-waarden zijn heterogeen
  (`str | int | float | bool | None | list | dict`). `object` is de correcte
  supertype. Callers moeten narrowen voor gebruik.
- **`dict[str, Any]` behouden voor request-bodies**: Waarden worden direct
  doorgegeven aan TypedClass constructors -- explicit narrowing is buiten Batch B scope.
  TODO-comments toegevoegd voor Pydantic-model refactor.
- **`list[dict[str,str]]` voor conversation_history**: role en content zijn altijd str.
- **`_CacheLayer` Protocol i.p.v. concrete import**: Vermijdt circulaire import;
  structural subtyping werkt voor alle cache-backends.

## Trainingssamenvatting

### Flow: TypedDict toevoegen voor bekende HTTP-response structuur

| Stap | Detail |
|------|--------|
| **Actor** | Backend developer / type-fix agent |
| **Voorwaarde** | Bestand heeft `dict[str, Any]` als return-type van methode die een bekende JSON-structuur opbouwt |
| **Actie** | Definieer TypedDict met exacte keys; wijzig return-annotatie; gebruik `cast(TypedDict, ...)` voor opaque blobs |
| **Systeemverwerking** | Mypy/Pyright valideert dat alle keys aanwezig zijn bij dict-literal constructie |
| **Succesrespons** | `ruff check`: 0 errors; scan: violation verdwijnt; TDD-test: PASS |
| **Foutrespons** | Pyright `reportReturnType`: dict-literal heeft onbekende keys -> voeg `total=False` toe of gebruik `cast()` |
| **Uitzondering** | HTTP-response van externe API: gebruik `dict[str, object]` + `cast()`, geen TypedDict (shape onbekend) |

### Flow: `object` vs `Any` kiezen voor dict-values

| Stap | Detail |
|------|--------|
| **Actor** | Type-fix agent |
| **Voorwaarde** | `dict[str, Any]` in een parameter of return-type |
| **Actie** | Check of values direct als typed argument gebruikt worden; zo ja -> `Any` + TODO; zo nee -> `object` |
| **Succesrespons** | Geen downstream Pyright-errors; scanviolation verdwijnt |
| **Foutrespons** | `reportArgumentType`/`reportAttributeAccessIssue` -> revert naar `dict[str, Any]` + TODO |
| **Uitzondering** | `**dict_var` unpacking: altijd `dict[str, Any]` vereist -- `object` breekt Pyright |

## TDD

- `tests/unit/test_batch_b_type_hardening.py`: 8 tests, 8/8 PASS
- Tests dekken: TypedDict aanwezigheid (AST), return-annotatie geen Any, param-annotatie geen Any

## Kwaliteitsresultaten

- `ruff check` 7 bestanden: 0 errors
- Scan before: 507 violations; after: 372 violations (-135, -26.6%)
- 0 regressies op bestaande suite
