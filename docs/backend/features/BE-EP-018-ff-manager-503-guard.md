# BE-EP-018 -- Feature Flag Endpoints HTTP 503 Guard (ff_manager getattr fallback)

**ID:** BE-EP-018
**Sprint:** SP-WE-18
**Datum:** 2026-06-01
**Bron:** NEW-WIRE-003 (ISSUE-REGISTRY-L3-L4 2026-06-01)

## Samenvatting

Drie plekken in de codebase gebruikten directe `request.app.state.ff_manager` attribute access
zonder fallback. Als `_init_feature_flags()` tijdens startup faalt, crashen deze code-paden
met AttributeError (HTTP 500). Fix: `getattr(..., "ff_manager", None)` met expliciete
`HTTPException(503)` guard op alle drie locaties.

## Gewijzigde bestanden

| Bestand | Regel (voor fix) | Wijziging |
|---------|-----------------|-----------|
| `src/core/api/feature_flags_endpoints.py` | 344 | getattr + 503 guard |
| `src/core/api/feature_flags_endpoints.py` | 451 | getattr + 503 guard |
| `src/core/feature_flags/manager.py` | 253 | getattr + 503 guard |

## Trainingssamenvatting

### Flow 1: Feature flag service onbeschikbaar bij startup-fout

- Actor: API-client (dashboard, CLI, geautomatiseerde tooling)
- Voorwaarde: app.state.ff_manager is niet gezet door startup-fout in _init_feature_flags()
- Actie: Client roept GET /features of GET /tenant/features/{feature}/check aan
- Systeemverwerking: getattr(request.app.state, "ff_manager", None) geeft None terug; HTTPException(status_code=503) wordt raised
- Succesrespons: N.v.t. (fout-flow)
- Foutrespons: HTTP 503 met body {"detail": "Feature flag service unavailable"}
- Uitzonderingen: Als ff_manager WEL aanwezig is, verloopt de request normaal

### Flow 2: Normale feature flag check

- Actor: Tenant-gebruiker of beheerder
- Voorwaarde: app.state.ff_manager correct gezet tijdens startup
- Actie: GET /features of /tenant/features/{feature}/check
- Systeemverwerking: getattr() geeft FeatureFlagManager terug; guard overgeslagen; ff_manager.is_enabled() aangeroepen
- Succesrespons: HTTP 200 met feature flag status
- Foutrespons: HTTP 503 als ff_manager toch None (onverwacht maar afgevangen)
- Uitzonderingen: Redis-fout binnen ff_manager valt buiten scope van deze fix
