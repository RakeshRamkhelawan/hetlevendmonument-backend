# BE-RTR-007 — Router Registry Dag 2 Cleanup (ADR-033)

## Metadata

| Veld | Waarde |
| --- | --- |
| ID | BE-RTR-007 |
| Sprint | SP-API-002 Dag 2 |
| Datum | 2026-06-03 |
| Status | APPROVED WITH MINOR GAPS |
| ADR | ADR-033 |

## Samenvatting

Extractie van de twee resterende inline helpers uit `router_registry.py` naar afzonderlijke Laag 2 registry bestanden. Na deze sprint is `router_registry.py` een pure thin Laag 3 orchestrator van ~60 regels met `int` return type. De module bevat geen business logica meer.

## Gewijzigde bestanden

| Bestand | Actie | Regels |
| --- | --- | --- |
| `src/core/api/registries/optional.py` | Nieuw | 76 |
| `src/core/api/registries/scheduling_rest.py` | Nieuw | 35 |
| `src/core/api/registries/scheduling_ws.py` | Nieuw | 20 |
| `src/core/api/registries/scheduling.py` | Nieuw (facade) | 11 |
| `src/core/api/router_registry.py` | Herschreven | ~60 |

## Architectuurpatroon

```text
Laag 3: router_registry.py (~60r)  — thin orchestrator, delegeert alles
Laag 2: registries/optional.py     — 8 optionele routers met try/except
Laag 2: registries/scheduling.py   — facade: REST + WS
Laag 2: registries/scheduling_rest.py — 8 REST scheduling routes (importlib)
Laag 2: registries/scheduling_ws.py   — 1 WebSocket scheduling route
```

`scheduling_rest.py` gebruikt `importlib.import_module()` met een `_ROUTES` lookup-table om de 8 routes binnen 35 regels te registreren, terwijl het lazy-import-principe behouden blijft.

## Return type wijziging

`register_all_routers(app: FastAPI) -> None` is gewijzigd naar `-> int`. Alle call-sites in `src/main.py` negeren de return waarde — geen breaking change.

## Trainingssamenvatting

### Flow: Optional router registratie met graceful degradation

| Aspect | Beschrijving |
| --- | --- |
| Actor | FastAPI applicatie startup |
| Voorwaarde | `create_app()` roept `register_all_routers(app)` aan na `app = FastAPI(...)` |
| Actie | `optional.register(app)` probeert 8 routers te importeren en te registreren |
| Systeemverwerking | Per router: try-import, `app.include_router()`, `count += 1`. Bij ImportError: `logger.warning(...)`, skip |
| Succesrespons | Router beschikbaar op zijn prefix; count verhoogd |
| Foutrespons | ImportError gelogged als WARNING; applicatie start toch op |
| Uitzonderingen | Digital Twin router logt ook een INFO-bericht bij succes |

### Flow: Scheduling router registratie

| Aspect | Beschrijving |
| --- | --- |
| Actor | FastAPI applicatie startup |
| Voorwaarde | `scheduling.register(app)` wordt aangeroepen door `router_registry.py` |
| Actie | Delegeert naar `scheduling_rest.register(app)` + `scheduling_ws.register(app)` |
| Systeemverwerking | REST: `importlib.import_module()` per entry in `_ROUTES`; WS: directe try/except import |
| Succesrespons | Alle beschikbare scheduling endpoints geregistreerd; totaal count teruggegeven |
| Foutrespons | Ontbrekende modules gelogged als WARNING; overige routes worden gewoon geregistreerd |
| Uitzonderingen | `scheduling_rest.py` gebruikt importlib (geen from-import) om binnen 80 regels te blijven |

## Verificatie

- `pytest tests/architecture/test_api_layer.py::test_registry_files_under_80_lines` — PASS
- `pytest tests/unit/api/ -x -q --timeout=30` — 100/100 PASS
- `ruff check src/core/api/` — 0 errors
- Alle nieuwe registries <= 80 regels
