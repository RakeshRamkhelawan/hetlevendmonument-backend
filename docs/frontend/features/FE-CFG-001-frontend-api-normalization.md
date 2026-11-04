# FE-CFG-001: Frontend API Base URL Normalisatie

**Sprint:** Startup Pipeline Fix Dag 1  
**Datum:** 2026-06-05  
**Status:** APPROVED  

## Samenvatting

Alle frontend API client modules gebruiken nu consistent `normalizeApiBaseUrl()` om `VITE_API_URL` te verwerken, waardoor dev-mode requests via de Vite proxy gaan in plaats van direct naar `localhost:8110`.

## Context

- **Probleem (B-002):** `VITE_API_URL=http://localhost:8110` in `.env.development` lekte naar modules die geen dev-mode normalisatie toepasten (`publicClient.ts`, `config/api.ts`). Dit veroorzaakte CORS errors en timeouts.
- **Impact:** Frontend `/api/v1/auth/me` timeout >8s; inconsistent API pattern.

## Wijzigingen

### `frontend/src/lib/api/publicClient.ts`

- `let BASE_URL = (import.meta.env.VITE_API_URL as string) || '';`
- → `let BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL as string | undefined, import.meta.env.DEV);`

### `frontend/src/config/api.ts`

- `let API_HOST = (import.meta.env.VITE_API_URL as string);`
- → `let API_HOST = normalizeApiBaseUrl(import.meta.env.VITE_API_URL as string | undefined, import.meta.env.DEV);`

## Testdekking

- `tests/unit/frontend/test_api_base_url_normalization.py` (4 tests)
  - `publicClient.ts` importeert en gebruikt `normalizeApiBaseUrl`
  - `config/api.ts` importeert en gebruikt `normalizeApiBaseUrl`
  - `client.ts` behoudt bestaande normalisatie (regression guard)
  - Geen directe `VITE_API_URL` reads zonder normalisatie

## Rollback

```bash
git revert <commit-hash>
```

## Acceptatiecriteria

- [x] Frontend doet 0 directe calls naar `localhost:8110`
- [x] Alle API client modules gebruiken `normalizeApiBaseUrl()`
- [x] Type-check slaagt (`npm run type-check`)

## Trainingssamenvatting

- Actor: frontend developer / CI-systeem
- Voorwaarde: `VITE_API_URL` geconfigureerd in `.env.development`
- Actie: frontend API client wordt geinitaliseerd bij opstarten van de applicatie
- Systeemverwerking: `normalizeApiBaseUrl()` normaliseert de URL naar Vite proxy in dev-mode
- Succesrespons: API calls gaan via `/api/` proxy, geen CORS errors
- Foutrespons: directe `localhost:8110` calls resulteren in CORS error (dev-mode) of timeout
- Uitzonderingen: productie-builds gebruiken altijd de geconfigureerde `VITE_API_URL` direct
