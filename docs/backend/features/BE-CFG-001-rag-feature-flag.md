# Backend Feature Specification

## Metadata

- Feature ID: BE-CFG-001
- Feature naam: RAG Feature Flag (RAG_ENABLED + legacy fallback)
- Status: Completed
- Auteur: Agent (SP-B03 re-executed 2026-05-29)
- Reviewer: Subagent (Laag A)
- Datum: 2026-05-29
- Gerelateerde user story / ticket: SP-B03
- Gerelateerde router / module: `src/core/api/router_registry.py`
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 2.0

---

## Doel en scope

### Doel

Gate RAG (Retrieval-Augmented Generation) endpoints achter een feature flag (`RAG_ENABLED`) zodat stub-implementaties niet live exposed zijn in productie. `ENABLE_RAG_ROUTERS` blijft als legacy fallback ondersteund. RAG is post-MVP en vereist een vector store.

### In scope

- Feature flag `RAG_ENABLED` (canoniek) env var in `router_registry.py`
- Legacy fallback `ENABLE_RAG_ROUTERS` voor backward compatibility (met deprecation warning)
- Default `false` (fail-closed)
- `.env.example` documentatie
- 13 tests voor enabled/disabled states, precedence, deprecation log, behavioral
- Regressiecheck op niet-RAG endpoints

### Out of scope

- RAG endpoint implementatie (post-MVP)
- Vector store integratie
- Frontend wijzigingen

---

## Build summary

- Nieuw gebouwd:
  - `RAG_ENABLED` feature flag gate in `_register_admin_management()`
  - `_resolve_rag_router_enabled()` met canonical + legacy precedence + deprecation warning
  - 13 unit tests in `tests/unit/test_sp_b03_rag_feature_flag.py`
- Gewijzigd:
  - `src/core/api/router_registry.py`: RAG router registratie achter feature flag
  - `.env.example`: `RAG_ENABLED=false` toegevoegd
- Verwijderd:
  - Niets (RAG endpoints blijven in source voor toekomstige activatie)
- Beinvloede bestaande flows:
  - `register_all_routers()`: RAG router count is 0 (flag=false) of 1 (flag=true)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-CFG-001 | RAG_ENABLED feature flag | Config | `src/core/api/router_registry.py` | Wijziging | BE-FLW-RAG-001 |
| BE-UTL-002 | test_sp_b03_rag_feature_flag | Test | `tests/unit/test_sp_b03_rag_feature_flag.py` | Nieuw | - |

---

## API-flows

### Flow ID: BE-FLW-RAG-001

- Naam: RAG router registratie bij startup
- Trigger: Application startup (`register_all_routers()`)
- Voorwaarden: `RAG_ENABLED` of `ENABLE_RAG_ROUTERS` env var (optioneel)
- Request-pad: N/A (startup flow)
- Service-stappen:
  1. `register_all_routers()` roept `_register_admin_management()` aan
  2. `_resolve_rag_router_enabled()` leest `RAG_ENABLED` eerst
  3. Als `RAG_ENABLED` aanwezig: gebruik die waarde
  4. Als `RAG_ENABLED` afwezig: lees `ENABLE_RAG_ROUTERS`, log deprecation warning
  5. Als beide afwezig: return `False` (default, fail-closed)
  6. Boolean parsing via `_is_truthy_flag()` met waarden `{"1", "true", "yes", "on"}`
  7. Als true: RAG router wordt lazy-imported en geregistreerd
  8. Als false: RAG router wordt niet gemount; alle `/api/v1/rag/*` routes geven 404
- DB-operaties: Geen
- Successtatus: Router count 0 (disabled) of 1 (enabled)
- Foutpaden:
  - `ImportError/ModuleNotFoundError`: gelogd als warning, router overgeslagen
  - Andere Exception: gelogd als error, re-raised (bewust fail-loud)
- Eindtoestand: App heeft 0 of 1 RAG router afhankelijk van flag

---

## Detaildocumentatie per artefact

---

## [BE-CFG-001] RAG_ENABLED (met ENABLE_RAG_ROUTERS fallback)

### 1. Type

Configuration / Feature Flag

### 2. Locatie

- Bestandspad: `src/core/api/router_registry.py`
- Functies: `_is_truthy_flag()`, `_resolve_rag_router_enabled()`, `_register_admin_management()`

### 3. Gerelateerde flow

BE-FLW-RAG-001

### 4. Doel

Voorkomen dat RAG stub endpoints live exposed zijn in productie zonder expliciete opt-in.

### 5. Functionele beschrijving

Bij applicatie startup bepaalt de `RAG_ENABLED` omgevingsvariabele of de RAG router wordt geregistreerd. Als `RAG_ENABLED` niet gezet is, wordt `ENABLE_RAG_ROUTERS` gebruikt als fallback (met deprecation warning in de logs). Standaard is dit uitgeschakeld (`false`), wat betekent dat alle `/api/v1/rag/*` routes niet bereikbaar zijn (HTTP 404).

### 6. Technische beschrijving

```python
def _is_truthy_flag(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_rag_router_enabled() -> bool:
    canonical = os.getenv("RAG_ENABLED")
    if canonical is not None:
        return _is_truthy_flag(canonical)

    legacy = os.getenv("ENABLE_RAG_ROUTERS")
    if legacy is not None:
        logger.warning(
            "ENABLE_RAG_ROUTERS is deprecated; use RAG_ENABLED instead. "
            "Using legacy fallback for this process."
        )
        return _is_truthy_flag(legacy)

    return False


def _register_admin_management(app: FastAPI) -> int:
    count: int = 0
    enable_rag = _resolve_rag_router_enabled()
    if enable_rag:
        try:
            from src.core.api.rag_endpoints import router as rag_router
            app.include_router(rag_router, tags=["RAG"])
        except (ImportError, ModuleNotFoundError) as e:
            logger.warning("Skipping RAG router (missing dependency): %s", e)
        except Exception as e:
            logger.error("RAG router registration failed unexpectedly: %s", e)
            raise
        else:
            count += 1
    logger.debug("Admin Management routers registered: %s", count)
    return count
```

- Lazy import binnen if-block: voorkomt laden van RAG module bij flag=false
- Narrow except: `ImportError/ModuleNotFoundError` voor ontbrekende deps; overige exceptions worden re-raised
- Presence-based precedence: canonical `RAG_ENABLED` wint altijd van legacy fallback
- Deprecation warning bij legacy gebruik

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N/A (startup configuratie)
- Vereiste rol / scope: N/A
- Tenant-isolatie: N/A
- Feature flag: `RAG_ENABLED` (canoniek), met `ENABLE_RAG_ROUTERS` als fallback

### 8. Request-specificatie

N/A — startup configuratie

### 9. Response-specificatie

N/A — startup configuratie

### 10. Validaties en constraints

- Env var moet een van `"1", "true", "yes", "on"` zijn (case-insensitive, whitespace-tolerant)
- Default is `"false"` — fail-closed
- Lege string (`RAG_ENABLED=`) wordt als false behandeld

### 11. Business rules

- Productie deployments: altijd `RAG_ENABLED=false` (default, geen actie vereist)
- Ontwikkelomgevingen met vector store: `RAG_ENABLED=true`
- Legacy `ENABLE_RAG_ROUTERS` werkt maar genereert deprecation warning in logs

### 12. Afhankelijkheden

- `src.core.api.rag_endpoints` (lazy import, alleen bij flag=true)
- `os` (stdlib)

### 13. Foutafhandeling

- Ongeldige env var waarde: behandeld als false (fail-closed)
- ImportError bij RAG endpoints: gelogd als warning, startup gaat door
- Overige Exception bij registratie: gelogd als error, re-raised (fail-loud)

### 14. Transacties en dataïntegriteit

N/A — geen database operaties

### 15. Telemetry / logging / tracing

```python
logger.warning(
    "ENABLE_RAG_ROUTERS is deprecated; use RAG_ENABLED instead."
)
logger.warning("Skipping RAG router (missing dependency): %s", e)
logger.error("RAG router registration failed unexpectedly: %s", e)
logger.debug("Admin Management routers registered: %s", count)
```

### 16. Caching

- Gecached: Nee (gelezen bij startup, eenmalig per process)

### 17. Acceptatiecriteria

- [x] `RAG_ENABLED=false` (default) — RAG routes geven 404
- [x] `RAG_ENABLED=true` — RAG routes bereikbaar (backwards compat voor dev)
- [x] `ENABLE_RAG_ROUTERS=true` werkt als fallback (met deprecation warning)
- [x] `RAG_ENABLED` heeft precedence over `ENABLE_RAG_ROUTERS`
- [x] `.env.example` bevat `RAG_ENABLED=false` documentatie
- [x] Geen regressies op niet-RAG endpoints

### 18. Integratoruitleg

Om RAG endpoints te activeren, zet `RAG_ENABLED=true` in de omgeving en herstart de applicatie. Als je tijdelijke backward compatibility nodig hebt, kan `ENABLE_RAG_ROUTERS=true` gebruikt worden zolang `RAG_ENABLED` niet gezet is (deprecated).

### 19. Trainingssamenvatting

| Veld | Inhoud |
| --- | --- |
| Actor | Platform operator (Rakesh) die RAG activatie beheert via env variabele |
| Voorwaarde | `RAG_ENABLED` env variabele aanwezig in de deployment omgeving |
| Actie | Zet `RAG_ENABLED=false` (default) of `RAG_ENABLED=true` in de omgeving en herstart de app |
| Systeemverwerking | Bij startup leest `router_registry.py` eerst `RAG_ENABLED`; als die niet bestaat wordt `ENABLE_RAG_ROUTERS` fallback gebruikt (met deprecation warning); bij false wordt de RAG router niet gemount |
| Succesrespons | `RAG_ENABLED=false`: alle `/api/v1/rag/*` routes geven HTTP 404. `RAG_ENABLED=true`: routes bereikbaar |
| Foutrespons | Ongeldige env var waarde wordt als false behandeld (fail-closed). `ImportError` bij RAG module: warning gelogd, startup doorgezet. Overige exceptions: re-raised (fail-loud). |
| Uitzonderingen | `RAG_ENABLED=true` maar geen vector store geconfigureerd: endpoints retourneren HTTP 501 (bestaand stub-gedrag voor /rag/search en /rag/ask) |

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

RAG endpoints zijn standaard niet beschikbaar (HTTP 404). Neem contact op met de platform operator als je RAG functionaliteit nodig hebt. Migreer van `ENABLE_RAG_ROUTERS` naar `RAG_ENABLED` — de legacy flag wordt in een toekomstige release verwijderd.

---

## Open aannames

- RAG implementatie is post-MVP en wordt in een latere sprint toegevoegd
- Vector store (Qdrant/Weaviate) is vereist voor volledige RAG functionaliteit

## Open vragen

- Moet er een runtime toggle komen (API endpoint om RAG aan/uit te zetten zonder herstart)?

## Risico's

- **Laag**: Ontwikkelaars vergeten `RAG_ENABLED=true` te zetten in dev — duidelijke 404, snel te fixen

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — 13 tests
- [x] Alle foutstatus-codes getest — 404 bij disabled, bereikbaar bij enabled
- [x] Auth en permissies getest — N/A (startup config)
- [x] Tenant-isolatie getest — N/A
- [x] Validaties getest (ongeldige invoer) — ongeldige env var waarden behandeld als false
- [x] Edge cases getest — default false, case insensitive, numeric "1", legacy fallback
- [x] Dataïntegriteit en transacties getest — N/A
- [x] Behavioral test aanwezig — operator ziet 404 zonder flag
- [x] Logging en tracing gecontroleerd — deprecation warning, debug count, error re-raise

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
