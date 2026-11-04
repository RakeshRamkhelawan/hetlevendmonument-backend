# BE-RTR-026 — Copilot Intent Parser Migration naar v1/copilot_intent/

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-RTR-026 |
| Sprint | SP-API-006 Dag 1 |
| Datum | 2026-06-05 |
| Status | APPROVED WITH MINOR GAPS |
| Type | BE-RTR (Router migratie) |
| Gerelateerde ADR | ADR-033 |

## Samenvatting

`src/core/api/copilot_endpoints.py` (426 regels, flat file) is gemigreerd naar een
ADR-033-conforme drie-laags structuur onder `src/core/api/v1/copilot_intent/`.

De enige route `POST /api/v1/intents/parse` is een DEPRECATED endpoint dat doorverwijst
naar `POST /api/v1/copilot/turn`. De migratie behoudt het endpoint volledig (URL-freeze)
en corrigeert pre-existing code-kwaliteitsfouten.

## Gewijzigde bestanden

| Bestand | Actie | Regels |
|---------|-------|--------|
| `src/core/api/v1/copilot_intent/__init__.py` | Nieuw — Laag 2 package | 12 |
| `src/core/api/v1/copilot_intent/router.py` | Nieuw — composite router | 12 |
| `src/core/api/v1/copilot_intent/parse_router.py` | Nieuw — Laag 1 sub-router | ~250 |
| `src/core/api/v1/copilot_intent/dependencies.py` | Nieuw — domein-dependencies | 8 |
| `src/core/api/copilot_endpoints.py` | Gewijzigd — re-export shim | 23 |
| `src/core/api/registries/core_api.py` | Gewijzigd — lazy import naar domain_router | 52 |
| `tests/architecture/test_registry_equivalence.py` | Gewijzigd — equivalentietest toegevoegd | +25 |

## Architectuur (ADR-033 drie-laags patroon)

```
Laag 3: src/core/api/registries/core_api.py
         └── lazy import: from src.core.api.v1.copilot_intent import domain_router

Laag 2: src/core/api/v1/copilot_intent/__init__.py
         └── domain_router = APIRouter(tags=["Copilot - Intent Parser"])

Laag 1: src/core/api/v1/copilot_intent/router.py (composite)
         └── src/core/api/v1/copilot_intent/parse_router.py
              └── POST /api/v1/intents/parse (DEPRECATED)
```

## Pre-existing issues gefixed

| Issue | Locatie | Fix |
|-------|---------|-----|
| f-string in logger: `f"Parsing intent: {query[:50]}..."` | copilot_endpoints.py:218 | `logger.info("Parsing intent: %s...", query[:50])` |
| `Optional` unused import (typing) | copilot_endpoints.py:11 | Verwijderd uit nieuwe parse_router.py |
| `raise ... from e` ontbrak in except | copilot_endpoints.py:423 | `raise HTTPException(...) from e` toegevoegd |
| logger.error miste type-naam in message | copilot_endpoints.py:417 | `"Intent parse error: %s: %s", type(e).__name__, e` |

## Routes (URL-freeze gehandhaafd, ADR-031)

| Method | Pad | Status |
|--------|-----|--------|
| POST | `/api/v1/intents/parse` | DEPRECATED — preserved |

## Trainingssamenvatting

### Flow 1 — Gebruiker stuurt een natural language intent

**Actor:** Authenticated API user  
**Voorwaarde:** Geldige JWT met `agents:read` scope  
**Actie:** `POST /api/v1/intents/parse` met body `{"query": "Create a donor-churn workflow"}`  
**Systeemverwerking:**
1. JWT gevalideerd door TenantMiddleware
2. `IntentParserService.parse()` classificeert query via regex-patronen
3. Agent type (workflow/memory/governance/specialist) bepaald op basis van keyword-matching
4. Confidence score berekend (0.5–1.0)
5. Deprecation headers gezet (`Sunset`, `Link: rel="successor-version"`)
6. Audit log via `log_deprecated_call()`

**Succesrespons:** HTTP 200 `{"success": true, "intent": {...}, "execution_time_ms": 15.3}`  
**Foutrespons:** HTTP 500 `{"detail": "Failed to parse intent"}` bij onverwachte parse-fout  
**Uitzonderingen:**
- Query < 5 tekens: HTTP 200 met `success: false` en `confidence: 0.0`
- Unauthenticated: HTTP 401 (TenantMiddleware)

### Flow 2 — Deprecation-bewuste consumer ontvangt headers

**Actor:** API consumer die `POST /api/v1/intents/parse` aanroept  
**Voorwaarde:** Geldige request  
**Actie:** Consumer leest response headers  
**Systeemverwerking:** `emit_deprecation_headers()` zet `Deprecation`, `Sunset`, `Link` headers  
**Succesrespons:** Response bevat `Link: </api/v1/copilot/turn>; rel="successor-version"` header  
**Foutrespons:** N.v.t. — headers worden altijd gezet bij succesvolle auth  
**Uitzonderingen:** Geen
