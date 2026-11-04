# Review BE-RTR-007 — Router Registry Dag 2 Cleanup

| Veld | Waarde |
| --- | --- |
| Reviewer | Claude Sonnet 4.6 (Laag A automatisch) |
| Datum | 2026-06-03 |
| Status | **APPROVED WITH MINOR GAPS** |

## Samenvatting

Extractie van `_register_optional_routers` en `_register_scheduling` naar afzonderlijke Laag 2 registry bestanden. `router_registry.py` is nu een pure thin orchestrator. Alle files <= 80 regels, alle tests groen.

## Bevindingen

### PASS — Architectuur

- Alle 4 nieuwe bestanden volgen het Laag 2 registry patroon (ADR-033)
- Lazy imports binnen `register()` function body
- `scheduling.py` is correcte facade-compositie
- `router_registry.py` bevat geen business logica meer

### PASS — Geen f-strings in logger calls

- `optional.py` gebruikt `logger.warning("... %s", e)` — correct
- `scheduling_rest.py` gebruikt `logger.warning("... %s", ...)` — correct
- `scheduling_ws.py` gebruikt `logger.warning("... %s", e)` — correct

### PASS — Return types

- Alle `register()` functies retourneren `int`
- `register_all_routers` gewijzigd van `None` naar `int`
- Call-sites in `src/main.py` negeren return value — geen breaking change

### PASS — Regellimiet

- `optional.py`: 76 regels
- `scheduling.py`: 11 regels
- `scheduling_ws.py`: 20 regels
- `scheduling_rest.py`: 35 regels (importlib-tabel)
- `router_registry.py`: ~60 regels

### MINOR GAP — importlib in scheduling_rest.py

`scheduling_rest.py` gebruikt `importlib.import_module()` in plaats van directe lazy imports. Dit is een pragmatische keuze om 8 routes binnen 80 regels te houden, maar de foutmelding bij ImportError bevat de module-path in plaats van een beschrijvende naam. Acceptabel voor MVP.

### PASS — Cross-router imports

Taak 4 grep toonde geen verboden cross-router imports. Alle gevonden imports zijn intra-domein (`__init__.py` → eigen `router.py`), conform ADR-033.

### PASS — Hardcoded counts

Geen `return N` met integer-literal gevonden. Alle registries gebruiken `count += 1`.

## Conclusie

**APPROVED WITH MINOR GAPS** — de minor gap (importlib foutmeldingen minder beschrijvend) heeft geen functionele impact. Productiesafe.
