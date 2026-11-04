# Backend Feature Specification

## Metadata

| Veld | Waarde |
|---|---|
| Feature ID | BE-EP-037 |
| Naam | Foundation Portal map/geo-endpoint (ADR-029 gap P0-4) |
| Status | Approved (Gate 2 herreview APPROVED + Gate 3 groen, 2026-09-09) |
| Auteur | Kimi agent (sessie 2026-09-09) |
| Reviewer | Onafhankelijke review-agent (Gate 2) |
| Datum | 2026-09-09 |
| User story / ticket | ADR-029 P0-4 (`docs/adr/029-gap-analysis-productieklaar-rapport.md` regel 332-419; audit-correctie `docs/reports/ADR-029_AUDIT_VERIFIED_2026-08-30.md:235-242`) |
| Router / module | `src/core/api/v1/foundation/map.py` |
| Frontend endpoints | N.v.t. — dient het herstelde prototype (`prototype/levend-monument-portal`, MapLibre) |
| Database tabellen | `foundation_contents` — bestaande kolommen `lat`, `lng`; **GEEN migratie nodig** |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Publieke kaartweergave: `GET /{tenantSlug}/foundation/map/bbox` retourneert een GeoJSON FeatureCollection met goedgekeurde, publieke content binnen een bounding box. Publiek toegankelijk (geen login) — dit is het etalage-endpoint van het portaal.

### In scope

- `src/core/api/v1/foundation/map.py` — endpoint
- Registratie in `router.py`
- Rate limiter `portal_public_read_limit` (60/min/IP) — bestaat al in de facade
- Integratietests + DB-loze unit-tests voor bbox-validatie
- Anti-scrape-maatregelen volgens audit: maximale bbox-span + resultaat-cap

### Out of scope

- PostGIS/ruimtelijke indexen (lat/lng-bereikquery volstaat voor MVP; documentatie bij schaalproblemen)
- Clustering van punten (frontend/MapLibre-doener)
- Antimeridiaan-bbox (sw > ne over de 180-meridiaan) — expliciet afgekeurd met 400
- Content PUT/DELETE (P1-2, aparte feature)
- Content met `privacy == COMMUNITY` (vereist login-flow voor leden; apart besluit)

---

## Ontwerpbeslissingen (door de architect, met reden)

| # | Beslissing | Reden |
|---|---|---|
| O1 | **Publiek endpoint, geen auth** — alleen `status == APPROVED` EN `privacy == PUBLIC` | De kaart is de publieke etalage; community-content volgt pas met een leden-flow. Dubbele filter (status + privacy) is fail-safe. |
| O2 | **MAX_SPAN_DEG = 2.0 graden** op beide assen; overschrijding → 400 | Audit-correctie (`ADR-029_AUDIT_VERIFIED_2026-08-30.md:241-242`): zonder span-cap kan een client de hele planeet opvragen en alle publieke content in een call dumpen. 2 graden (~220 km) is ruim voor een stads-/regiokaart. |
| O3 | **Resultaat-cap = 500** (`LIMIT 501`, eerste 500 geretourneerd, `has_more` in response; aangepast 2026-09-09 na Gate-2 review LOW) | Voorkomt megaresponses en houdt de NFR (< 150 ms p95) haalbaar. `total` = aantal features in de response; `has_more: true/false` (berekend via de 501e rij) vertelt de frontend of er meer matches waren, zodat "precies 500" en "meer dan 500" te onderscheiden zijn. |
| O4 | **GeoJSON FeatureCollection** als response (`{"type": "FeatureCollection", "features": [...], "total": n}`) | MapLibre GL JS (het prototype) consumeert GeoJSON native; ADR-029-schets schrijft dit voor. |
| O5 | **Coordinates als `[lng, lat]`** in die volgorde | GeoJSON-standaard (RFC 7946) is longitude-eerst; de schets doet dit al correct. |
| O6 | **Rate limiter `portal_public_read_limit`** (60/min/IP) als decorator | Bestaand patroon (`settings.py` gebruikt deze al); read = min. 6x schrijf-limiet (patroon #4). |
| O7 | **Bbox-validatie server-side**: sw < ne per as, lat in [-90, 90], lng in [-180, 180] | Query-param-validatie via FastAPI `Query(ge=, le=)` + expliciete span-checks. |
| O8 | **Properties per feature**: `id`, `title_nl`, `type`, `creator_name`, `category`; **`creator_name` is `null` als `is_anonymous=True`** (anonimiteitsregel toegevoegd 2026-09-09 na Gate-2 review HIGH-1) | Exact de schets uit de gap-analyse; genoeg voor kaartpopups, geen overblootse data (file_url/body niet meesturen). De anonimiteitsvoorkeur van de uploader wordt gerespecteerd op dit publieke, bulk-scrapbare endpoint. NB: content list/detail honoreren `is_anonymous` (nog) niet — dat is een apart opvolg-item, buiten deze feature. |
| O9 | **Geen audit-log per request** | Publieke read; audit is voor schrijfacties (patroon #3 geldt voor mutations). |

---

## Build summary

### Nieuw gebouwd

- `src/core/api/v1/foundation/map.py` — endpoint + bbox-validatiehelpers
- `tests/integration/api/v1/foundation/test_map.py` — integratietests
- `tests/unit/test_be_ep_037_map_bbox_offline.py` — DB-loze validatietests

### Gewijzigd

- `src/core/api/v1/foundation/router.py` — `include_router(map.router)`
- `src/core/shared/public_registry.py` — `/foundation/map` toegevoegd aan publieke foundation-paden (noodzakelijke enabler voor O1: zonder deze entry blokkeert `TenantMiddleware` anonieme calls met 401; toegevoegd 2026-09-09, was een open LOW uit de Gate-2-review dat deze auth-relevante wijziging in de inventory ontbrak)
- `docs/backend/features/ID-REGISTRY.md` — BE-EP-037

### Verwijderd

- Niets.

### Beinvloede bestaande flows

- Geen. Puur additief endpoint.

---

## API-flow

### GET `/{tenantSlug}/foundation/map/bbox`

Query-params: `sw_lat`, `sw_lng`, `ne_lat`, `ne_lng` (alle verplicht, float, met ge/le-validatie).

1. Rate limiter: `portal_public_read_limit` (60/min/IP) — 429 bij overschrijding.
2. Bbox-validatie: `sw_lat < ne_lat` en `sw_lng < ne_lng`, anders 400. Span-check: `ne_lat - sw_lat > 2.0` of `ne_lng - sw_lng > 2.0` → 400 ("bbox too large, max 2 degrees").
3. `public_tenant_scope(tenantSlug, session)` — 404 bij onbekende/inactieve slug.
4. Query: `tenant_id == tenant.id` (expliciet, dubbele isolatie), `status == APPROVED`, `privacy == PUBLIC`, `lat/lng IS NOT NULL`, binnen bbox. `ORDER BY created_at DESC`, `LIMIT 501` (de 501e rij bepaalt `has_more`; aangepast 2026-09-09).
5. Response: FeatureCollection met per feature `geometry.coordinates = [lng, lat]` en de properties uit O8 (`creator_name = null` bij `is_anonymous=True`). `total` = aantal geretourneerde features; `has_more` = of er meer matches waren dan de cap.

### Testplan

**Unit (offline):** span-cap (2.0 exact toegestaan / erboven 400), sw >= ne geweigerd per as, grenswaarden lat/lng, helper-functies. Geen DB nodig — validatie als pure functies testbaar maken.

**Integratie (Postgres/Redis):** happy path met content binnen/buiten bbox; COMMUNITY-content komt NIET mee; PENDING/REJECTED komt niet mee; andere tenant komt niet mee; content zonder lat/lng komt niet mee; cap gedrag (501e item valt eraf); span-cap 400; ongeldige bbox 400; onbekende tenant 404; GeoJSON-structuur (type, coordinates-volgorde, properties-volledigheid).

---

## Open aannames

- **2 graden span-cap** is ruim voor een monumentenportaal dat per stad/regio werkt; als een toekomstige tenant landelijk wil tonen, wordt dit een configurabele waarde per tenant — eigen feature.
- **Geen ruimtelijke index**: bij < 100k contentrijen per tenant is een bereikscan op geindexeerde lat/lng voldoende; meetbaar maken zodra echte data draait.

## Definition of Done

- [x] Endpoint + registratie gebouwd (`src/core/api/v1/foundation/map.py` + `router.py` + `public_registry.py`)
- [x] Bbox-validatie met span-cap (2.0 graden) en resultaat-cap (500, met `has_more` via `LIMIT 501`)
- [x] Unit-tests groen (offline): 17/17 (`tests/unit/test_be_ep_037_map_bbox_offline.py`, 0.68s)
- [x] Integratietests groen tegen echte Postgres/Redis: 12/12 (`tests/integration/api/v1/foundation/test_map.py`, 69.4s, Postgres 5435 + Redis 6379)
- [x] Ruff schoon (5 geraakte bestanden: All checks passed); mypy: no issues in 3 source files (strict, project-config); pyright: 0 errors / 0 warnings (met project-venv interpreter)
- [x] Onafhankelijke review (Gate 2) met APPROVED (herreview 2026-09-09, na fix HIGH-1 is_anonymous-lek + LOW total-semantiek)
- [x] ID-REGISTRY.md bijgewerkt (BE-EP-037, regel 607)
- [x] Review-document `docs/backend/review/review-BE-EP-037.md` aanwezig

---

## Trainingssamenvatting

- **Actor:** Publieke bezoeker van het erfgoedportaal of interactieve kaartcomponent in de frontend.
- **Voorwaarde:** Geldige tenant slug en een geldige geografische bounding box binnen de toegestane span-limiet (maximaal 2.0 graden span).
- **Actie:** GET /{tenantSlug}/foundation/map/bbox?sw_lat=...&sw_lng=...&ne_lat=...&ne_lng=...
- **Systeemverwerking:** Valideert de bounding box coordinaten en de span-cap, stelt de public tenant context in, voert een query uit op goedgekeurde en publieke items (status = APPROVED, privacy = PUBLIC) met coordinaten binnen de bbox, pagineert/kapt af op maximaal 500 records met een LIMIT 501 voor has_more bepaling, maskeert de maker indien anoniem (is_anonymous = True), en assembleert de GeoJSON FeatureCollection.
- **Succesrespons:** HTTP 200 OK met GeoJSON FeatureCollection bevattende features met geometrie en publieke metadata (total, has_more).
- **Foutrespons:** HTTP 400 bij ongeldige bbox (sw >= ne) of te grote span (> 2.0 graden); HTTP 404 bij onbekende of inactieve tenant slug; HTTP 429 bij te veel verzoeken per minuut.
