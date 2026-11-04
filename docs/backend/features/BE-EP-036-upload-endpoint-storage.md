# Backend Feature Specification

## Metadata

| Veld | Waarde |
|---|---|
| Feature ID | BE-EP-036 |
| Naam | Foundation Portal upload-endpoint + storage-service (ADR-029 gap P0-3) |
| Status | Approved (Gate 2 herreview APPROVED + Gate 3 groen, 2026-09-09) |
| Auteur | Kimi agent (sessie 2026-09-09) |
| Reviewer | Onafhankelijke review-agent (Gate 2) |
| Datum | 2026-09-09 |
| User story / ticket | ADR-029 P0-3 (`docs/adr/029-gap-analysis-productieklaar-rapport.md` regel 221-328; audit-correcties `docs/reports/ADR-029_AUDIT_VERIFIED_2026-08-30.md:199-233`) |
| Router / module | `src/core/api/v1/foundation/upload.py` + `src/core/services/foundation_storage.py` |
| Frontend endpoints | N.v.t. — publiek frontend ontbreekt nog (P0-7 / beslissing D1) |
| Database tabellen | `foundation_contents` — bestaande kolommen `file_url`, `file_mime`, `file_size_bytes`; **GEEN migratie nodig** |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Portal-gebruikers (ingelogd via magic-link JWT, scope `portal_uploader`) kunnen een bestand uploaden bij **bestaande** `FoundationContent`. De upload is veilig: tenant-isolatie, autorisatie (uploader of curator/admin), MIME-validatie op magic bytes, size-cap, rate limiting, audit-logging. Opslag gaat via een nieuwe `FoundationStorageService` met een `local` backend (dev/test, default) en een `azure` backend (Azure Blob + SAS URL).

### In scope

- `POST /{tenantSlug}/foundation/content/{content_id}/upload` (multipart/form-data)
- `FoundationStorageService` (`src/core/services/foundation_storage.py`) met backend-switch
- Facade-uitbreiding `src/core/api/v1/foundation/dependencies.py` (`portal_public_write_limit`, `get_foundation_storage`)
- Registratie in `src/core/api/v1/foundation/router.py`
- Response-schema `FoundationFileUploadResponse` in `schemas.py`
- Config-velden voor Azure Blob in `src/core/shared/config.py`
- Nieuwe dependencies: `puremagic` (MIME magic bytes, pure Python) en `azure-storage-blob`
- Unit-tests (offline) + integratietests (Postgres/Redis)
- **Meegepakt (expliciet gemarkeerd):** ontbrekende rate limiter op `create_content` (audit-bevinding N-4) — zelfde decorator die dit endpoint krijgt

### Out of scope

- Alembic-migraties (kolommen bestaan al; checksum blijft bewust uit het schema)
- Download/serveer-endpoint voor bestanden (hoort bij P0-7 frontend / P1)
- User-delegation SAS via managed identity (productie-hardening, P1 — zie "Open aannames")
- Virusscanning (ClamAV), hCaptcha
- Traefik `maxRequestBodySize` (bestaat niet in de echte config; applicatie-cap is de verdediging)
- Verhogen van de globale `max_body_size_middleware`-limiet (50 MB)

---

## Ontwerpbeslissingen (door de architect, met reden)

| # | Beslissing | Reden |
|---|---|---|
| O1 | **MIME-detectie via `puremagic`** (pure Python) i.p.v. `python-magic` | `python-magic` vereist `libmagic1` (apt) en is op Windows lokaal onbetrouwbaar; de audit waarschuwt hiervoor. `puremagic` heeft geen native dependency en werkt overal identiek. **Aangescherpt 2026-09-10:** gepind op `1.30`, niet 2.x — CI draait Python 3.11 en puremagic 2.x vereist >=3.12 (pip-audit-gate faalde hierop). 1.x gooit `PureError` bij niet-herkenbare input i.p.v. een lege lijst te retourneren; `detect_allowed_mime` vangt die af. |
| O2 | **Cap = `settings.max_upload_size_bytes` (50 MB)**, niet 100 MB uit de gap-analyse | De app-brede `max_body_size_middleware` (`src/core/middleware/max_body_size_middleware.py`) staat op 50 MB. Een 100 MB endpoint-cap zou daar doodlopen of vereisen dat de globale limiet omhoog gaat — onnodig blast radius voor MVP. Afwijking van ADR-029 (100 MB) is bewust en hier gedocumenteerd. |
| O3 | **Chunked lezen (1 MB-blokken) met lopende teller, abort bij cap+1** | De gap-analyse-schets deed `await file.read()` vóór de size-check: tot 100 MB in RAM per request = memory-DoS. De audit schrijft chunking voor. |
| O4 | **Storage-backend-switch via `settings.storage_backend`** (`local` default / `azure`) | Bestaand config-veld en bestaand patroon (`upload_router.py`). Lokaal en in tests draait alles zonder Azure; productie zet de backend op `azure`. |
| O5 | **Azure via connection string; `file_url` = canonieke blob-URL ZONDER SAS** (gewijzigd 2026-09-09 na Gate-2 review HIGH-2) | Oorspronkelijk: account-key SAS (7 dagen) in de opgeslagen URL. Dat laat na een week een dode `file_url` achter zonder regeneratiepad. SAS-generatie verhuist naar het toekomstige serveer-endpoint (P1, samen met P0-7; user-delegation SAS via managed identity is de hardening daar). Er is geen managed identity ingericht in dev. |
| O6 | **Rate limiter `portal_public_write_limit` (10/min/IP)** als decorator | Verplicht volgens backend-patroon #4 en audit N-4. Wordt ook toegevoegd aan `create_content` (zelfde decorator, zelfde facade-import). |
| O7 | **Response via `response_model=FoundationFileUploadResponse`** (niet `{"success": ...}`-wrapper) | Alle bestaande foundation-endpoints gebruiken `response_model`-schemas; lokale consistentie binnen de module weegt zwaarder dan het globale patroon dat de foundation-module zelf nergens volgt. |
| O8 | **Autorisatie: uploader van de content, of rol ADMIN/CURATOR; niet-eigenaar zonder rol krijgt 404** (gewijzigd 2026-09-09 na Gate-2 review MEDIUM) | Overgenomen uit de gap-analyse-schets; consistent met curatie-rollenmodel. Cross-tenant: 403. Niet-eigenaar-niet-curator: 404 met identieke body als niet-bestaande content, zodat het bestaan van andermans content niet lekt (existence-oracle; IDs zijn sequentieel). |
| O9 | **sha256-checksum in response + audit-log, niet in DB** | Geen kolom toevoegen = geen migratie = chirurgisch. De checksum dient integriteitscontrole in de audit-trail (ADR-019). |
| O10 | **Audit via `best_effort(...)` na commit** | Verplicht patroon #3 uit `.claude/rules/backend-patterns.md`; zoals `documents/upload_router.py`. |

### MIME-allowlist (uit ADR-029)

`image/jpeg`, `image/png`, `image/webp`, `image/gif`, `audio/mpeg`, `audio/wav`, `audio/ogg`, `application/pdf`, `text/plain`, `video/mp4`, `video/webm`.

**Uitzondering `text/plain`:** platte tekst heeft geen magic bytes; `puremagic` detecteert die niet betrouwbaar. Fallback-regel: als magic-detectie niets oplevert, mag `text/plain` alleen via extensie `.txt` + declaratie `Content-Type: text/plain` + succesvolle UTF-8-decode van de inhoud. Anders 400. Dit is gedocumenteerd als bewuste, geteste uitzondering.

---

## Build summary

### Nieuw gebouwd

- `src/core/services/foundation_storage.py` — `FoundationStorageService` (local + azure backend, `upload()` retourneert URL; blob-pad `foundation/<tenant_id>/<content_id>/<uuid4><ext>`)
- `src/core/api/v1/foundation/upload.py` — endpoint
- `tests/unit/test_be_ep_036_upload_offline.py` — DB-loze tests (validatie, MIME, size-guard, storage-paden, gemockte Azure)
- `tests/integration/api/v1/foundation/test_upload.py` — integratietests volgens `test_content.py`-patroon

### Gewijzigd

- `src/core/api/v1/foundation/dependencies.py` — facade: re-export `portal_public_write_limit` + `get_foundation_storage`
- `src/core/api/v1/foundation/router.py` — `include_router(upload.router)`
- `src/core/api/v1/foundation/schemas.py` — `FoundationFileUploadResponse`
- `src/core/api/v1/foundation/content.py` — `@portal_public_write_limit` op `create_content` (audit N-4)
- `src/core/shared/config.py` — Azure-velden: `azure_storage_connection_string: str | None = None`, `foundation_blob_container: str = "foundation-content"`
- `requirements-base.txt` — `puremagic`, `azure-storage-blob`
- `docs/backend/features/ID-REGISTRY.md` — BE-EP-036

### Verwijderd

- Niets.

### Beinvloede bestaande flows

- `create_content` krijgt een rate limiter (10/min/IP). Bestaande integratietests worden niet geraakt: de foundation-conftest reset de rate-limit-Redis-keys per test (`_clear_rate_limits`), en geen enkele bestaande test doet >10 creates vanaf hetzelfde IP.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|---|---|---|---|---|---|
| BE-EP-036 | Upload endpoint | API endpoint | `src/core/api/v1/foundation/upload.py` | Nieuw | Upload bij content |
| BE-EP-036-SVC | FoundationStorageService | Service | `src/core/services/foundation_storage.py` | Nieuw | Opslag local/azure |
| BE-EP-036-SCH | FoundationFileUploadResponse | Schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | Response |
| BE-EP-036-CFG | Azure storage config | Config | `src/core/shared/config.py` | Wijziging | Azure backend |
| BE-EP-036-N4 | Rate limiter op create_content | Hardening | `src/core/api/v1/foundation/content.py` | Wijziging | Audit N-4 |

---

## API-flows

### POST `/{tenantSlug}/foundation/content/{content_id}/upload`

1. Rate limiter: `portal_public_write_limit` (10/min/IP) — 429 bij overschrijding.
2. Auth: `require_portal_user` — 401 zonder/geldig JWT (aud `portal`, scope `portal_uploader`), 403 bij geblokkeerde user.
3. `public_tenant_scope(tenantSlug, session)` — 404 bij onbekende/inactieve slug (anti-enumeration).
4. Cross-tenant: `current_user.tenant_id != tenant.id` → 403.
5. Content laden met expliciete `tenant_id`-WHERE → 404 indien afwezig.
6. Autorisatie: `content.uploader_id != current_user.id` en rol niet in {ADMIN, CURATOR} → 404 (zelfde body als stap 5; anti-enumeratie, O8 aangepast 2026-09-09).
7. Chunked lezen (1 MB), teller > cap → 413.
8. MIME-detectie via `puremagic` op de eerste bytes; niet in allowlist → 400. `text/plain`-fallback volgens O-regel hierboven (declared Content-Type genormaliseerd: `split(";")[0].strip().lower()`). Leeg bestand → 400 (detectie slaat lege input over; `puremagic` gooit anders `PureValueError`).
9. `storage.upload(...)` → canonieke URL (azure: ZONDER SAS-token, O5 aangepast 2026-09-09).
10. `content.file_url/file_mime/file_size_bytes` zetten, flush, **expliciete `await session.commit()`** (aangepast 2026-09-09 na Gate-2 review MEDIUM: patroon #3 vereist dat de primaire wijziging duurzaam is vóór de audit; de afsluitende commit in `get_db` is daarna een no-op).
11. Audit via `best_effort` na commit: actie `foundation.content.file_upload`, met sha256, mime, size, content_id — nooit bestandsinhoud of PII. Een audit-failure kan de content-update niet meer terugrollen (`best_effort` rolt hooguit de nieuwe, lege transactie terug).
12. Response `FoundationFileUploadResponse`: `file_url`, `file_mime`, `file_size_bytes`, `sha256`.

---

## Detaildocumentatie per artefact

### BE-EP-036-SVC FoundationStorageService

1. **Type:** service (async)
2. **Locatie:** `src/core/services/foundation_storage.py`
3. **Gerelateerde flow:** upload
4. **Doel:** enige plek die weet waar bytes landen.
5. **Functionele beschrijving:** constructor leest `get_settings()`; `async upload(tenant_id, content_id, filename, data, mime_type) -> str`. Backend `local`: schrijft naar `{local_upload_dir}/foundation/<tenant_id>/<content_id>/<uuid4><ext>` via `aiofiles`, maakt dirs aan, retourneert relatief URL-pad `/uploads/foundation/...` (serving is out of scope). Backend `azure`: `BlobServiceClient.from_connection_string`, container uit config, `upload_blob(overwrite=False)`, retourneert de **canonieke blob-URL ZONDER SAS-token** (aangepast 2026-09-09 na Gate-2 review HIGH-2: een opgeslagen SAS-URL met 7-dagen-expiry laat een dode `file_url` achter; SAS-generatie hoort bij het toekomstige serveer-moment, P1 samen met P0-7, met user-delegation SAS via managed identity als hardening). Bestandsnaam wordt gesanitized (patroon `secure_filename` uit `documents/upload_router.py`); extensie afgeleid van gedetecteerde MIME, niet van de opgegeven naam.
6. **Fouten:** backend niet geconfigureerd → duidelijke exception; endpoint vertaalt naar 503.

### BE-EP-036 (endpoint)

Zie API-flow hierboven. Imports uitsluitend via `dependencies.py` (ADR-033 facade, import-linter Contract 1). Geen emoji/non-ASCII in code/comments. `datetime.now(timezone.utc)` waar nodig. Geen `str(e)` in HTTP-details of logs (OWASP A5); exceptions met `exc_info=True`.

### Tests

**Unit (offline, `tests/unit/test_be_ep_036_upload_offline.py`):** MIME-detectie met gesmede headers (PNG/JPEG/PDF/MP4), weigering van uitvoerbaar bestand met `.png`-naam, text/plain-fallback (wel/niet UTF-8), size-guard (chunk-grens), filename-sanitise, local-backend pad + wegschrijven (`tmp_path`), azure-backend met gemonkeypatchte `BlobServiceClient` (geen netwerk). Skip-don't-fail als `puremagic` ontbreekt (BE-MIG-013-patroon).

**Integratie (`tests/integration/api/v1/foundation/test_upload.py`):** succes (curator + eigenaar), 401 unauthenticated, 403 cross-tenant, 403 niet-eigenaar-niet-curator, 404 onbekende content, 413 oversize, 400 verboden MIME. Storage gemockt naar `tmp_path` via dependency-override van `get_foundation_storage`. Draait tegen Postgres 5435 + Redis zoals de bestaande foundation-integratietests.

---

## Open aannames

- **50 MB i.p.v. 100 MB** (O2): afwijking van ADR-029, bewust, hier gedocumenteerd. Als het portal later video >50 MB moet accepteren, is het pad: middleware-limiet configurabel per route maken — dat is dan een eigen feature.
- **SAS hoort bij het serveer-moment** (O5, aangepast 2026-09-09): `file_url` bevat op de azure-backend de canonieke blob-URL zonder token. Het serveer-endpoint (P1, samen met P0-7) genereert daar alsnog een read-SAS — bij voorkeur user-delegation SAS via managed identity i.p.v. account-key. Tot dat endpoint bestaat is opgeslagen content niet direct downloadbaar via `file_url`; dat is bewust (er is ook nog geen publiek frontend).
- **`text/plain`-fallback** is zwakker dan magic bytes; gedocumenteerd en afgedekt met UTF-8-eis + tests.
- Integratietests vereisen Docker/Postgres/Redis; op omgevingen zonder die stack falen ze niet stilletjes mee maar worden ze niet opgepakt (zelfde als bestaande foundation-integratietests).

## Definition of Done

- [x] Endpoint + service + facade + router + schema + config gebouwd
- [x] `puremagic` + `azure-storage-blob` in requirements
- [x] Rate limiter op upload én `create_content` (incl. bewijs-test: 11e request -> 429)
- [x] Unit-tests groen (offline): 27 passed
- [x] Integratietests groen tegen echte Postgres/Redis: hele foundation-map 87 passed
- [x] Ruff schoon; mypy 0 issues + pyright 0 errors op de 7 gewijzigde bestanden
- [x] Onafhankelijke review (Gate 2): CHANGES_REQUESTED (2 HIGH + 4 MEDIUM) -> fixes -> herreview APPROVED
- [x] ID-REGISTRY.md bijgewerkt
- [x] Review-document `docs/backend/review/review-BE-EP-036.md`

---

## Trainingssamenvatting

- **Actor:** Geauthenticeerde portal-gebruiker (rol uploader, curator of admin) die een mediabestand wil koppelen aan een bestaand content-item.
- **Voorwaarde:** Geldig JWT-token met portal-audience (aud: portal), geldige tenant slug in het pad, content-item bestaat en behoort toe aan de uploader (of de gebruiker heeft de rol CURATOR of ADMIN).
- **Actie:** POST /{tenantSlug}/foundation/content/{content_id}/upload met multipart form-data of binaire stream en declared MIME-type.
- **Systeemverwerking:** De upload-router valideert rate limits (portal_public_write_limit), controleert token en tenant-match, leest chunks tot maximaal 50 MB, detecteert het werkelijke MIME-type via magic bytes, schrijft het bestand weg naar de opslag-backend (lokaal bestandssysteem of Azure Blob Storage) via FoundationStorageService, update file_url, file_mime en file_size_bytes op het FoundationContent record, committeert de transactie en logt een best-effort audit-event.
- **Succesrespons:** HTTP 200 OK met FoundationFileUploadResponse bevattende file_url, file_mime, file_size_bytes en sha256.
- **Foutrespons:** HTTP 400 bij ongeldig/gevaarlijk MIME-type of leeg bestand; HTTP 401 bij ontbrekend/ongeldig JWT; HTTP 403 bij cross-tenant of ontoereikende permissies; HTTP 404 bij onbekende tenant of onbekend content-item; HTTP 413 bij bestandsgrootte > 50 MB; HTTP 429 bij overschrijding van de rate limit.
