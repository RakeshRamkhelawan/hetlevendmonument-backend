# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-043 |
| Naam | Foundation Portal XML Sitemap Endpoint (Sitemaps.org Protocol & Google Image Sitemap) |
| Status | Completed |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | Red Team / Shadow CEO |
| Datum | 2026-09-12 |
| User story / ticket | ADR-029 Foundation Portal P2-5 (Sitemap XML Discovery Endpoint); docs/adr/029-status-en-vervolg-2026-09-09.md |
| Router / module | `src/core/api/v1/foundation/sitemap.py` (nieuw), `src/core/api/v1/foundation/router.py` (gewijzigd), `src/core/api/registries/foundation.py` (gewijzigd), `src/core/shared/public_registry.py` (gewijzigd) |
| Frontend / Consumer endpoints | `GET /{tenantSlug}/foundation/sitemap.xml`, `GET /api/v1/foundation/sitemap.xml` |
| Database tabellen | `foundation_content` (lezen), `tenants` (lezen) |
| Versie | 1.0.0 |

---

## Doel en scope

### Doel

Publieke XML Sitemap discovery realiseren voor stichtingen en erfgoedorganisaties aangesloten op Het Levend Monument (ADR-029). Hierdoor kunnen zoekmachines (Google, Bing) en erfgoed-harvesters (zoals Netwerk Digitaal Erfgoed / NDE) geautomatiseerd alle goedgekeurde erfgoedverhalen en portalpagina's indexeren conform het officiële Sitemaps XML 0.9 protocol en de Google Image Sitemap extensie.

### In scope

1. **Sitemap Router & Services (`src/core/api/v1/foundation/sitemap.py`)**:
   - `GET /{tenantSlug}/foundation/sitemap.xml`: XML sitemap endpoint voor een specifieke tenantSlug.
   - `GET /api/v1/foundation/sitemap.xml`: Directe host-gebaseerde resolutie (`get_public_tenant`) voor aangepaste domeinen (bijv. `verhalen.ketikotivlaardingen.nl`) en subdomeinen.
   - Canonieke basis-URL resolutie: respecteert `tenant.custom_domain`, reverse proxy host headers (`x-tenant-domain`, `x-forwarded-host`, `host`) en fallback domain.
   - Statische routes: `/`, `/kaart`, `/educatie`, `/over`, `/contact`, `/nieuwsbrief`, `/data-export`, `/toegankelijkheid` met specifieke `changefreq` en `priority`.
   - Dynamische routes: `/verhaal/{id}` voor elk goedgekeurd openbaar item met ISO-datum (`lastmod`), `changefreq: monthly`, `priority: 0.7`.
   - Image sitemap extensie: opname van `<image:image>` met `<image:loc>` en `<image:title>` voor verhalen met goedgekeurde afbeeldingsmedia of `ContentType.ARTWORK`.
   - Caching headers: `Cache-Control: public, max-age=3600, s-maxage=86400` en `X-Robots-Tag: noindex`.
   - Rate limiting: beschermd via `@portal_public_read_limit`.

2. **N-2 Invariant Handhaving**:
   - Strikte query-filtering:
     - `FoundationContent.status == ContentStatus.APPROVED`
     - `FoundationContent.privacy == Privacy.PUBLIC`
     - `FoundationContent.visibility == Visibility.PUBLIC`
   - Conceptverhalen (`PENDING`), afgewezen items (`REJECTED`), verwijderde items (`REMOVED`), community-only en educatieve lesmaterialen (`Visibility.EDU`) worden te allen tijde uitgesloten van de publieke sitemap.

3. **Public Registry Exemption (`src/core/shared/public_registry.py`)**:
   - Registratie van `/api/v1/foundation/sitemap.xml` in `PUBLIC_PATHS`.
   - Vrijstelling van `/foundation/sitemap.xml` binnen `is_public` met fail-closed bescherming tegen gereserveerde padsegmenten (`_RESERVED_TOP_SEGMENTS`).

4. **Unit Tests (`tests/unit/test_foundation_sitemap.py`)**:
   - 13 unit tests met 100% dekking over schema-validatie, XML wellformedness, canonieke domeinresolutie, statische/dynamische routes, N-2 invariant en response headers.

### Out of scope

- Automatische ping naar Google/Bing search console API's (optioneel in toekomstige release).
- Dynamische gzip-compressie op applicatieniveau (reeds afgehandeld door Traefik edge gateway / GZipMiddleware).

---

## Technische architectuur

```
[Crawler / Harvester]
         │
         ▼
[GET /api/v1/foundation/sitemap.xml of /{tenantSlug}/foundation/sitemap.xml]
         │
         ▼
[RateLimiter: portal_public_read_limit]
         │
         ▼
[Tenant Resolution / Public Tenant Scope]
         │
         ▼
[AsyncSession Query: APPROVED + PUBLIC + Visibility.PUBLIC]
         │
         ▼
[XML Builder: sitemaps.org 0.9 + Google Image Sitemap]
         │
         ▼
[HTTP 200: application/xml; charset=utf-8 + Cache-Control: 1h/24h]
```

---

## Trainingssamenvatting

- **Component**: Foundation Portal XML Sitemap Endpoint
- **Doel**: Gestandaardiseerde SEO en erfgoed-harvesting indexering van openbare collecties.
- **Architectuurregel**: Alleen publieke en goedgekeurde content mag worden geprojecteerd; rate-limited en gecachet.
- **Geverifieerd met**: `tests/unit/test_foundation_sitemap.py` (13 tests PASS).
- **Actor**: Zoekmachine crawler of erfgoed-harvester
  - **Flow**: Crawler verzoekt `GET /{tenantSlug}/foundation/sitemap.xml` -> Rate limiter valideert token bucket -> Systeem haalt goedgekeurde publieke content op -> Genereert XML met URLs en beelden -> Retourneert HTTP 200 met caching headers.

