# BE-SEC-028: CORS Fail-Fast Validatie (SEC-001, ADR-035 D4)

**Sprint:** AUDIT-SINGLE-TENANT-DB01 S6
**Datum:** 2026-07-01
**Status:** DONE

## Audit-bevinding

**SEC-001 (HIGH):** `security_middleware.py:269-271` had CORS wildcard als default.
De custom `CORSMiddleware`-class in dat bestand is dead code (niet gebruikt in `middleware_config.py`).
De echte CORS-config zit in `security_headers.py:get_cors_config()`.

**Staging bug (CORS spec):** De staging-branch van `get_cors_config()` combineerde
`allow_headers: ["*"]` met `allow_credentials: True`. Dit is een ongeldige CORS-combinatie
per de Fetch-specificatie. Browsers sturen preflight-requests terug met een fout.

## Implementatie

### Fix 1: staging `allow_headers` (security_headers.py:339)

Vervangen van `"allow_headers": ["*"]` door expliciete headers (gelijk aan productie):

```python
"allow_headers": [
    "Authorization",
    "Content-Type",
    "X-Request-ID",
    "X-Tenant-ID",
    "Accept",
    "Accept-Language",
],
```

### Fix 2: `validate_cors_config()` helper (security_headers.py)

Nieuwe functie naast bestaande `validate_cors_origins()`:

```python
def validate_cors_config(config: dict[str, Any], environment: str) -> None:
    """Valideer CORS-configuratie op ongeldige combinaties (SEC-001, ADR-035 D4)."""
    # Raise als allow_headers=['*'] + allow_credentials=True (ongeldige combinatie)
    # Raise als allow_origins=['*'] in productie
```

### Niet gewijzigd

- De custom `CORSMiddleware`-class in `security_middleware.py` is NOT aangepast.
  Er bestaat een bestaande test (`TestCORSMiddlewareDefaults.test_cors_app_with_defaults`)
  die het wildcard-gedrag vastlegt. Aanpassen vereist red-first commit; buiten scope S6.
- `CORS_ALLOWED_ORIGINS` env var is NIET geintroduceerd -- bestaande productie-path
  gebruikt `ALLOWED_ORIGINS` in `production_config.py`.

## Tests

`tests/unit/middleware/test_cors_fail_fast.py`:
1. `test_staging_cors_does_not_combine_wildcard_headers_with_credentials`
2. `test_validate_cors_config_raises_on_wildcard_headers_with_credentials`
3. `test_validate_cors_config_accepts_explicit_headers_with_credentials`
4. `test_validate_cors_config_raises_on_wildcard_origins_in_production`

`tests/architecture/test_detect_db_imports_zero.py`:
1. `test_detect_db_imports_returns_zero_offenders`
2. `test_detect_db_imports_script_exists`

## ADR-conformiteit

| ADR | Regel | Status |
|-----|-------|--------|
| ADR-035 D4 | CORS wildcard verboden | COMPLIANT: staging fix + validate_cors_config() |
| ADR-033 | router.py geen directe DB-imports | COMPLIANT: 69/69 schoon |

## Trainingssamenvatting

- Actor: FastAPI startup (`setup_middleware` in `src/core/api/setup/middleware_config.py`) of een operator/test die `validate_cors_config` aanroept.
- Voorwaarde: `ENVIRONMENT` is gezet (`development`, `staging` of `production`); `get_cors_config(ENVIRONMENT)` retourneert een dictionary.
- Actie (request): Roep `validate_cors_config(cors_config, ENVIRONMENT)` aan voordat de CORS middleware wordt geregistreerd.
- Systeemverwerking: De helper controleert of `allow_headers` wildcard (`*`) gecombineerd wordt met `allow_credentials=True` in staging/productie, en of `allow_origins` wildcard bevat in productie.
- Succesrespons: Geen exceptie; vervolgens wordt `CORSMiddleware` toegevoegd met `allow_origins`, `allow_credentials`, `allow_methods`, `allow_headers`, `expose_headers` en `max_age`.
- Foutrespons: `ValueError` met de tekst `allow_headers=['*'] gecombineerd met allow_credentials=True is een ongeldige CORS-configuratie (Fetch spec)` of `Wildcard CORS origins zijn niet toegestaan in productie`.
- Uitzonderingen: In development blijft `allow_headers: ["*"]` toegestaan; de staging-configuratie gebruikt nu expliciete headers (`Authorization`, `Content-Type`, `X-Request-ID`, `X-Tenant-ID`, `Accept`, `Accept-Language`).
